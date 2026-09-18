# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Standalone leanexplore MCP server host and client.

This allows hosting the leanexplore MCP server independently.
"""

import asyncio
import json
import subprocess
import atexit
import threading
from pathlib import Path
from typing import Any
from logging import getLogger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = getLogger()

_STDIO_CTX = None
_SESSION_CTX = None
_CLIENT_SESSION: ClientSession | None = None
_BACKEND: str = "local"
_LOG_LEVEL: str = "ERROR"
_EVENT_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_THREAD: threading.Thread | None = None
_LOOP_READY = threading.Event()


def start_server(backend: str = "local", log_level: str = "ERROR") -> None:
    """
    Start the leanexplore MCP server in a background thread.
    
    Args:
        backend: Backend to use ("local" or "api")
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global _BACKEND, _LOG_LEVEL, _LOOP_THREAD, _LOOP_READY
    
    if _LOOP_THREAD is not None and _LOOP_THREAD.is_alive():
        logger.info("leanexplore MCP server already running")
        return
    
    _BACKEND = backend
    _LOG_LEVEL = log_level
    _LOOP_READY.clear()
    
    logger.info(f"Starting leanexplore MCP server: backend={backend}, log_level={log_level}")
    _LOOP_THREAD = threading.Thread(target=_start_event_loop_thread, daemon=True, name="LeanExploreLoop")
    _LOOP_THREAD.start()
    
    # Wait for session to be ready
    _LOOP_READY.wait(timeout=30)
    if _CLIENT_SESSION is None:
        raise RuntimeError("Failed to initialize leanexplore MCP server")


def stop_server() -> None:
    """Stop the leanexplore MCP server."""
    global _STDIO_CTX, _SESSION_CTX, _CLIENT_SESSION, _EVENT_LOOP, _LOOP_THREAD
    
    if _EVENT_LOOP and _EVENT_LOOP.is_running():
        async def _cleanup():
            global _SESSION_CTX, _STDIO_CTX, _CLIENT_SESSION
            if _SESSION_CTX:
                try:
                    await _SESSION_CTX.__aexit__(None, None, None)
                except Exception:
                    pass
                _SESSION_CTX = None
            
            if _STDIO_CTX:
                try:
                    await _STDIO_CTX.__aexit__(None, None, None)
                except Exception:
                    pass
                _STDIO_CTX = None
            
            _CLIENT_SESSION = None
        
        try:
            future = asyncio.run_coroutine_threadsafe(_cleanup(), _EVENT_LOOP)
            future.result(timeout=5)
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        
        _EVENT_LOOP.call_soon_threadsafe(_EVENT_LOOP.stop)
    
    if _LOOP_THREAD and _LOOP_THREAD.is_alive():
        _LOOP_THREAD.join(timeout=5)
        _LOOP_THREAD = None
    
    _EVENT_LOOP = None
    logger.info("leanexplore MCP server stopped")


def _start_event_loop_thread():
    """Start a background thread with a persistent event loop."""
    global _EVENT_LOOP, _CLIENT_SESSION, _STDIO_CTX, _SESSION_CTX, _BACKEND, _LOG_LEVEL
    
    async def _init_session():
        """Initialize the session in the persistent event loop."""
        global _CLIENT_SESSION, _STDIO_CTX, _SESSION_CTX
        
        if _CLIENT_SESSION is not None:
            return
        
        # Find Python executable (prefer venv, fallback to system)
        venv_python = Path(__file__).parent.parent / "venv" / "bin" / "python"
        if venv_python.exists():
            python_cmd = str(venv_python)
        else:
            python_cmd = "python3"
        
        # Use stdio_client to spawn and manage the process
        server_params = StdioServerParameters(
            command=python_cmd,
            args=["-m", "lean_explore.mcp.server", "--backend", _BACKEND, "--log-level", _LOG_LEVEL],
        )
        
        logger.info(f"Connecting to leanexplore MCP server...")
        _STDIO_CTX = stdio_client(server_params)
        read, write = await _STDIO_CTX.__aenter__()
        
        _SESSION_CTX = ClientSession(read, write)
        _CLIENT_SESSION = await _SESSION_CTX.__aenter__()
        await _CLIENT_SESSION.initialize()
        
        logger.info("leanexplore MCP server connected")
        _LOOP_READY.set()
    
    try:
        _EVENT_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_EVENT_LOOP)
        _EVENT_LOOP.run_until_complete(_init_session())
        _EVENT_LOOP.run_forever()
    except Exception as e:
        logger.error(f"Error in event loop thread: {e}")
        _LOOP_READY.set()
    finally:
        if _EVENT_LOOP:
            _EVENT_LOOP.close()


async def _get_session() -> ClientSession:
    """Get the MCP client session (must be called from the event loop thread)."""
    global _CLIENT_SESSION
    
    if _CLIENT_SESSION is None:
        raise RuntimeError("Session not initialized")
    
    return _CLIENT_SESSION


def _run_in_loop(coro):
    """Run a coroutine in the persistent event loop."""
    global _EVENT_LOOP
    
    if _EVENT_LOOP is None or not _EVENT_LOOP.is_running():
        raise RuntimeError("Event loop not running")
    
    # Submit coroutine to the event loop and wait for result
    task = asyncio.run_coroutine_threadsafe(coro, _EVENT_LOOP)
    return task.result()


def search(query: str, limit: int = 10, package_filters: list[str] | None = None) -> dict[str, Any]:
    """
    Search for Lean definitions and theorems using leanexplore.
    
    Args:
        query: Search query string
        limit: Maximum number of results to return
        package_filters: Optional list of package names to filter by
    
    Returns:
        Dictionary with search results
    """
    if _CLIENT_SESSION is None:
        raise RuntimeError("Server not initialized. Call initialize() first.")
    
    return _run_in_loop(_search_async(query, limit, package_filters))


async def _search_async(
    query: str, limit: int = 10, package_filters: list[str] | None = None
) -> dict[str, Any]:
    """Async implementation of search."""
    session = await _get_session()
    
    args = {"query": query, "limit": limit}
    if package_filters:
        args["package_filters"] = package_filters
    
    result = await session.call_tool("search", args)
    
    # Extract text content from result
    if hasattr(result, "content") and result.content:
        text_content = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
        return json.loads(text_content)
    
    return {}


def initialize(backend: str = "local", log_level: str = "ERROR") -> None:
    """
    Initialize the leanexplore MCP server.
    
    Args:
        backend: Backend to use ("local" or "api")
        log_level: Logging level
    """
    start_server(backend, log_level)
    # Give it a moment to start
    import time
    time.sleep(1)


def shutdown() -> None:
    """Shutdown the leanexplore MCP server."""
    stop_server()
