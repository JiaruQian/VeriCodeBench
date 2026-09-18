# Unified MCP Server Architecture

## Overview

This document describes the unified MCP (Model Context Protocol) server that provides a single endpoint for search tools, including Loogle and leanexplore.

## Architecture

### Single Endpoint: `src/local_mcp.py`

The unified MCP server consolidates multiple search tools into one FastMCP-based server:

```
┌─────────────────────────────────────┐
│   src/local_mcp.py                  │
│   (Unified FastMCP Server)          │
├─────────────────────────────────────┤
│  • Tool Registry                    |
│  • Unified list_tools()             │
│  • Unified call_tool()              │
└─────────────────────────────────────┘
           │              │
           ▼              ▼
    ┌──────────┐   ┌──────────────────┐
    │  Loogle  │   │ leanexplore      │
    │  (HTTP)  │   │ (HTTP Proxy)     │
    └──────────┘   └──────────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │ leanexplore  │
                    │ (MCP Client) │
                    └──────────────┘
```

## Available Tools

### 1. `lean_loogle`
- **Type**: Direct HTTP client
- **Purpose**: Search Lean definitions/theorems using Loogle
- **Query Patterns**: 
  - By constant: `Real.sin`
  - By lemma name: `"differ"`
  - By subexpression: `_ * (_ ^ _)`
  - By type shape: `(?a -> ?b) -> List ?a -> List ?b`

### 2. `leanexplore_search`
- **Type**: HTTP client wrapper (via HTTP proxy)
- **Purpose**: Search using leanexplore backend
- **Features**: Package filtering, result limiting

## Key Files

### `src/local_mcp.py` (Main Unified Server)
- **Purpose**: FastMCP server hosting all tools
- **Key Functions**:
  - `initialize()`: Start both Loogle and leanexplore servers
  - `list_tools()`: Return all available tools (Gemini-compatible format)
  - `call_tool()`: Execute any registered tool
  - `shutdown()`: Stop all servers
- **Tool Registration**: Uses `@register_tool` decorator

### `src/leanexplore_mcp.py` (leanexplore MCP Client)
- **Purpose**: MCP client for leanexplore server
- **Architecture**: Persistent event loop in background thread
- **Key Functions**:
  - `search()`: Search for definitions/theorems
- **Why Background Thread**: Maintains async context managers across calls

### `src/leanexplore_proxy.py` (HTTP Proxy)
- **Purpose**: HTTP wrapper around leanexplore MCP server
- **Architecture**: Threaded HTTP server with backlog of 128
- **Endpoints**: `/search`, `/health`
- **Why HTTP Proxy**: Enables better parallelism and stateless requests

### `src/leanexplore_client.py` (HTTP Client)
- **Purpose**: HTTP client for leanexplore proxy
- **Used by**: `local_mcp.py` when `_USE_HTTP_PROXY = True`

## Usage Example

```python
from src import local_mcp as MCP

# Initialize both servers
# Note: This may take 2-3 minutes on first startup (Loogle takes ~2 min)
MCP.initialize(
    start_loogle=True,
    start_leanexplore=True,
    leanexplore_backend="local",
    leanexplore_log_level="ERROR"
)

# List available tools
tools = MCP.list_tools()
# Returns: [
#   {"name": "lean_loogle", "description": "...", "parameters": {...}},
#   {"name": "leanexplore_search", "description": "...", "parameters": {...}},
#   ...
# ]

# Call a tool
result = MCP.call_tool("lean_loogle", {"query": "List.sum", "num_results": 5})

# Or call leanexplore
result = MCP.call_tool("leanexplore_search", {"query": "List.sum", "limit": 5})

# Shutdown
MCP.shutdown()
```

## Startup Times

On macOS M3 machines, initialization times are approximately:
- **Loogle server**: ~2 minutes to start up and become ready
- **leanexplore HTTP proxy**: ~10 seconds to initialize

The `initialize()` function includes built-in waiting logic that polls the Loogle server until it's ready, so the initialization call will block until both servers are operational. Most of the startup time is spent waiting for the Loogle server to fully initialize its backend.