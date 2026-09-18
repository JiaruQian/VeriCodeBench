# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""MCP Client for lean-lsp-mcp server integration."""

from logging import getLogger
import shutil
from typing import Any
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = getLogger(__name__)


class LeanLspMcpClient:
    """Client for connecting to lean-lsp-mcp server and executing tools."""

    def __init__(
        self,
        lean_file_path: str | None = None,
        lean_project_path: str | None = None,
    ):
        """
        Initialize the MCP client.

        Args:
            lean_file_path: Path to the Lean file being worked on (optional)
            lean_project_path: Path to the Lean project workspace (optional, will set LEAN_PROJECT_PATH env var)
        """
        self.lean_file_path = lean_file_path
        self.session: ClientSession | None = None

        # Set up environment with LEAN_PROJECT_PATH if provided

        env = os.environ.copy() if lean_project_path else None

        if lean_project_path and env:
            env["LEAN_PROJECT_PATH"] = lean_project_path

        if not shutil.which("lean-lsp-mcp"):
            raise RuntimeError(
                "This requires lean-lsp-mcp to be installed (optional dependency, as of 24 Nov 2025 not needed for main).\n"
                "Install with:\n    pip install lean-lsp-mcp"
            )
        # Use the lean-lsp-mcp command directly
        self.server_params = StdioServerParameters(
            command="lean-lsp-mcp", args=[], env=env
        )
        self.stdio_ctx = None
        self.session_ctx = None

    async def __aenter__(self):
        """Async context manager entry."""
        self.stdio_ctx = stdio_client(self.server_params)
        self.read, self.write = await self.stdio_ctx.__aenter__()
        self.session_ctx = ClientSession(self.read, self.write)
        self.session = await self.session_ctx.__aenter__()
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session_ctx:
            await self.session_ctx.__aexit__(exc_type, exc_val, exc_tb)
        if self.stdio_ctx:
            await self.stdio_ctx.__aexit__(exc_type, exc_val, exc_tb)

    async def list_tools(
        self, filter_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        List all available MCP tools.

        Args:
            filter_names: Optional list of tool names to include. If None, returns all tools.

        Returns:
            List of tool definitions compatible with Gemini function calling
        """
        if not self.session:
            raise RuntimeError("Session not initialized")

        mcp_tools = await self.session.list_tools()

        # Convert MCP tools to Gemini function declaration format
        tools = []
        for tool in mcp_tools.tools:
            # Skip tools not in filter list (if filter is provided)
            if filter_names is not None and tool.name not in filter_names:
                continue

            # Clean the schema to remove fields unsupported by Gemini
            cleaned_schema = _clean_schema_for_gemini(tool.inputSchema)

            tool_def = {
                "name": tool.name,
                "description": tool.description or f"Execute {tool.name}",
                "parameters": cleaned_schema,
            }
            tools.append(tool_def)

        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call an MCP tool with the given arguments.

        Args:
            tool_name: Name of the tool to call
            arguments: Dictionary of arguments for the tool

        Returns:
            The result from the tool execution
        """
        if not self.session:
            raise RuntimeError("Session not initialized")

        logger.info(f"Calling MCP tool: {tool_name} with args: {arguments}")

        result = await self.session.call_tool(tool_name, arguments)

        # Return the MCP result structure which includes content array
        return {
            "content": [
                {"text": item.text if hasattr(item, "text") else str(item)}
                for item in result.content
            ]
            if hasattr(result, "content")
            else []
        }


def _clean_schema_for_gemini(schema: dict) -> dict:
    """
    Recursively clean JSON schema to remove fields unsupported by Gemini.

    Gemini doesn't support: title, $schema, additionalProperties, default, examples, etc.
    """
    if not isinstance(schema, dict):
        return schema

    # Fields to remove at any level
    forbidden_fields = {
        "title",
        "$schema",
        "additionalProperties",
        "default",
        "examples",
        "const",
        "anyOf",
        "oneOf",
        "allOf",
        "x-fastmcp-wrap-result",
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
