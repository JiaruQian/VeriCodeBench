# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import asyncio
import json
from typing import Any, Callable
import urllib
from pathlib import Path
import os
import signal
import orjson
from logging import getLogger
from time import sleep
from fastmcp.tools import Tool
import subprocess
import atexit

_USE_HTTP_PROXY = True

if _USE_HTTP_PROXY:
    from src.leanexplore_client import (
        search as _leanexplore_search,
    )
    from src.leanexplore_proxy import (
        start_http_proxy as _leanexplore_start_server,
        stop_http_proxy as _leanexplore_stop_server,
    )
else:
    from src.leanexplore_mcp import (
        search as _leanexplore_search,
        start_server as _leanexplore_start_server,
        stop_server as _leanexplore_stop_server,
    )

logger = getLogger()

_LOOGLE_PROCESS: subprocess.Popen | None = None

TOOL_REGISTRY: dict[str, Tool] = {}


def _clean_schema_for_gemini(schema: dict) -> dict:
    """
    Recursively clean JSON schema to remove fields unsupported by Gemini.

    Removes fields that cause errors in Gemini API:
    - additionalProperties (causes ValueError)
    - default (causes ValueError)
    - title, $schema (metadata, not needed)
    - const, anyOf, oneOf, allOf (complex validation, likely unsupported)
    - x-fastmcp-wrap-result (FastMCP extension, not needed)

    Note: Default values are still documented in function docstrings,
    so the model can see them in the description.
    """
    if not isinstance(schema, dict):
        return schema

    # Only remove fields that are known to cause errors or are clearly not supported
    forbidden_fields = {
        "title",  # Redundant with parameter names
        "$schema",  # JSON Schema metadata
        "additionalProperties",  # Causes ValueError in Gemini API
        "default",  # Causes ValueError in Gemini API
        "const",  # Complex validation, likely unsupported
        "anyOf",  # Complex validation, likely unsupported
        "oneOf",  # Complex validation, likely unsupported
        "allOf",  # Complex validation, likely unsupported
        "x-fastmcp-wrap-result",  # FastMCP extension
    }
    cleaned = {}
    for key, value in schema.items():
        if key in forbidden_fields:
            continue

        if isinstance(value, dict):
            cleaned[key] = _clean_schema_for_gemini(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _clean_schema_for_gemini(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned


def _clean_schema_for_openai(schema: dict) -> dict:
    """
    Recursively clean JSON schema for OpenAI.
    OpenAI is more permissive than Gemini, but we still remove:
    - title, $schema (metadata, not needed)
    - x-fastmcp-wrap-result (FastMCP extension, not needed)
    """
    if not isinstance(schema, dict):
        return schema

    forbidden_fields = {
        "title",
        "$schema",
        "x-fastmcp-wrap-result",
    }

    cleaned = {}
    for key, value in schema.items():
        if key in forbidden_fields:
            continue

        if isinstance(value, dict):
            cleaned[key] = _clean_schema_for_openai(value)
        elif isinstance(value, list):
            cleaned[key] = [
                _clean_schema_for_openai(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value

    return cleaned


def _ensure_valid_openai_parameters(schema: dict | None) -> dict:
    """
    Ensure schema is a valid OpenAI parameters object:
    top-level has required "type": "object" and "properties".
    """
    if schema is None:
        return {"type": "object", "properties": {}}

    cleaned = _clean_schema_for_openai(schema)

    # OpenAI requires these at top level
    if "type" not in cleaned:
        cleaned["type"] = "object"
    if "properties" not in cleaned:
        cleaned["properties"] = {}

    return cleaned


def list_tools(
    filter_names: list[str] | None = None,
    format: str = "gemini",
) -> list[dict[str, Any]]:
    """
    Lists tool schemas in the specified format.
    Args:
        filter_names: Optional list of tool names to include.
        format: Target format ("openai" or "gemini").
    Returns:
        List of tool schemas in the requested format.
    """
    tools_to_list = TOOL_REGISTRY.values()
    if filter_names:
        tools_to_list = [
            tool for name, tool in TOOL_REGISTRY.items() if name in filter_names
        ]
    schemas = []
    for tool in tools_to_list:
        raw_input_schema = tool.parameters
        match format:
            case "gemini":
                cleaned_schema = (
                    _clean_schema_for_gemini(raw_input_schema)
                    if raw_input_schema
                    else None
                )
                tool_schema = {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": cleaned_schema,
                }
                # Remove None values for Gemini
                tool_schema = {k: v for k, v in tool_schema.items() if v is not None}

            case "openai":
                tool_schema = {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": _ensure_valid_openai_parameters(raw_input_schema),
                    },
                }
        schemas.append(tool_schema)
    return schemas


def register_tool(func: Callable) -> Callable:
    """
    A simple decorator to:
    1. Create a Tool, which parses the schema.
    2. Register the tool object in our local registry.
    """
    tool = Tool.from_function(func)
    tool_name = tool.name
    TOOL_REGISTRY[tool_name] = tool
    return func


def call_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Calls a tool from the local in-process registry and returns a dict.

    - Always returns a dict with "content" key
    - Content is a list of {"text": ...} items
    """
    tool = TOOL_REGISTRY.get(tool_name)

    if not tool:
        return {"content": [{"text": f"MCP server error: tool {tool_name} not found."}]}

    try:
        result = asyncio.run(tool.run(arguments))
        content = [{"text": part.text} for part in result.content]
        return {"content": content}

    except Exception as e:
        return {"content": [{"text": json.dumps({"error": str(e)})}]}


# @register_tool
def lean_loogle(query: str, num_results: int = 8) -> list[dict] | str:
    """
    Search for definitions and theorems using loogle.
    Query patterns:
      - By constant: Real.sin  # finds lemmas mentioning Real.sin
      - By lemma name: "differ"  # finds lemmas with "differ" in the name
      - By subexpression: _ * (_ ^ _)  # finds lemmas with a product and power
      - Non-linear: Real.sqrt ?a * Real.sqrt ?a
      - By type shape: (?a -> ?b) -> List ?a -> List ?b
      - By conclusion: |- tsum _ = _ * tsum _
      - By conclusion w/hyps: |- _ < _ → tsum _ < tsum _

    Args:
        query (str): Search query
        num_results (int, optional): Max results. Defaults to 8.

    Returns:
        List[dict] | str: Search results or error msg
    """
    try:
        req = urllib.request.Request(
            f"http://localhost:8088/json?q={urllib.parse.quote(query)}",
            headers={"User-Agent": "local_mcp"},
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            results = orjson.loads(response.read())

        if "hits" not in results:
            return results.get("error") or str(results)

        results = results["hits"][:num_results]
        for result in results:
            result.pop("doc", None)
        return results
    except Exception as e:
        return f"loogle error:\n{str(e)}"


# @register_tool
def leanexplore_search(
    query: str, limit: int = 10, package_filters: list[str] | None = None
) -> dict[str, Any]:
    """
    Search for Lean definitions and theorems using leanexplore.

    Args:
        query: Search query string
        limit: Maximum number of results to return (default: 10)
        package_filters: Optional list of package names to filter by

    Returns:
        Dictionary with search results containing:
        - results: List of search result objects
        - count: Number of results returned
        - total_candidates_considered: Total matches found
        - processing_time_ms: Time taken for the search
    """
    try:
        return _leanexplore_search(query, limit, package_filters)
    except Exception as e:
        return {"error": str(e)}


def initialize(
    start_loogle: bool = True,
    start_leanexplore: bool = True,
    leanexplore_backend: str = "local",
    leanexplore_log_level: str = "ERROR",
) -> None:
    """
    Initialize both Loogle and leanexplore servers.

    Args:
        start_loogle: Whether to start the Loogle server (default: True)
        start_leanexplore: Whether to start the leanexplore server (default: True)
        leanexplore_backend: Backend for leanexplore ("local" or "api", default: "local")
        leanexplore_log_level: Log level for leanexplore (default: "ERROR")
    """
    global _LOOGLE_PROCESS

    # Start Loogle server if requested
    if start_loogle:
        if _LOOGLE_PROCESS is not None:
            logger.info("Loogle server already running")
        else:
            current_dir = Path(__file__).parent.resolve()
            script_path = current_dir / "start_loogle_server.sh"
            logger.info(f"Launching Loogle server via {script_path}")
            _LOOGLE_PROCESS = subprocess.Popen(
                ["bash", str(script_path)],
                preexec_fn=os.setsid,  # process group
            )
            atexit.register(shutdown)

            # Wait 10 seconds for the server process to start before checking
            logger.info("Waiting 10 seconds for Loogle server to initialize...")
            sleep(10)

            register_tool(lean_loogle)

            while True:
                result = call_tool("lean_loogle", {"query": "List.length"})

                # Extract text from {"content": [{"text": ...}]} format
                text = result.get("content", [{}])[0].get("text", "")

                # Parse if JSON-encoded string
                try:
                    parsed = json.loads(text)
                    text = parsed if isinstance(parsed, str) else text
                except (json.JSONDecodeError, TypeError):
                    pass

                # Check if server is ready
                if (
                    not text
                    or "backend process is starting up" in text
                    or "loogle error" in text.lower()
                ):
                    logger.info("Loogle server not ready yet, waiting...")
                    sleep(5)
                else:
                    break
            logger.info("Loogle server startup complete.")

    # Start leanexplore server if requested
    if start_leanexplore:
        if _USE_HTTP_PROXY:
            # HTTP proxy takes port as first arg, backend as keyword
            _leanexplore_start_server(port=8089, backend=leanexplore_backend)
        else:
            # MCP takes backend and log_level
            _leanexplore_start_server(
                backend=leanexplore_backend, log_level=leanexplore_log_level
            )
        logger.info("leanexplore server initialized")

        register_tool(leanexplore_search)


def shutdown() -> None:
    """Shutdown both Loogle and leanexplore servers."""
    global _LOOGLE_PROCESS
    if _LOOGLE_PROCESS is not None:
        if _LOOGLE_PROCESS.poll() is None:
            logger.info("Terminating Loogle server process group...")
            try:
                # Kill entire process group
                pgid = os.getpgid(_LOOGLE_PROCESS.pid)
                os.killpg(pgid, signal.SIGTERM)

                _LOOGLE_PROCESS.wait(timeout=10)
                logger.info("Loogle server process group terminated.")
            except subprocess.TimeoutExpired:
                logger.warning("Process group did not terminate in time. Killing...")
                os.killpg(pgid, signal.SIGKILL)
                _LOOGLE_PROCESS.wait()
                logger.info("Loogle server process group killed.")
            except ProcessLookupError:
                logger.info("Process group already terminated.")
        else:
            logger.info("Loogle server process is not running.")
        _LOOGLE_PROCESS = None
    else:
        logger.info("No Loogle server process to shut down.")

    # Shutdown leanexplore
    _leanexplore_stop_server()
