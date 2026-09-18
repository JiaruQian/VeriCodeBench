# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# python -m scripts.test_leanexplore
"""Test script for Leanexplore MCP server"""

import sys
import json

from src import local_mcp as MCP
from src.utils import initialize_logger


def test_leanexplore():
    """Test the Leanexplore MCP server"""
    print("=" * 70)
    print("Testing Leanexplore MCP Server")
    print("=" * 70)

    # Initialize both servers
    print("\n1. Initializing unified MCP server...")
    print("   (This will start both Loogle and leanexplore servers)")
    MCP.initialize(
        start_loogle=False,
        start_leanexplore=True,
        leanexplore_backend="local",
        leanexplore_log_level="ERROR",
    )
    print("✓ Unified MCP server initialized")

    # List all available tools
    print("\n2. Listing available tools...")
    tools = MCP.list_tools()
    print(f"✓ Found {len(tools)} tool(s):")
    for tool in tools:
        print(
            f"  - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description').splitlines()[0]}..."
        )

    # Test leanexplore search
    print("\n3. Testing leanexplore search for 'List.sum'...")
    result = MCP.call_tool("leanexplore_search", {"query": "List.sum", "limit": 3})

    # Extract content from new format: {"content": [{"text": ...}]}
    assert isinstance(result, dict) and "content" in result and result["content"]
    text = result["content"][0].get("text", "")
    # Parse the JSON-encoded text
    parsed_result = json.loads(text)
    if isinstance(parsed_result, dict) and "results" in parsed_result:
        results = parsed_result["results"]
        print(f"✓ leanexplore search successful! Found {len(results)} results")
        print(
            f"  Total candidates: {parsed_result.get('total_candidates_considered', 'N/A')}"
        )
        print(f"  Processing time: {parsed_result.get('processing_time_ms', 'N/A')} ms")
        if len(results) > 0:
            name = results[0].get("primary_declaration", {}).get("lean_name", "Unknown")
            print(f"  First result: {name}")
    elif isinstance(parsed_result, dict) and "error" in parsed_result:
        print(f"⚠ Error: {parsed_result['error']}")
    else:
        print(f"⚠ Unexpected result: {type(parsed_result)}")

    # Shutdown
    print("\n4. Shutting down MCP server...")
    MCP.shutdown()
    print("✓ Server shut down")

    print("\n" + "=" * 70)
    print("✅ Leanexplore MCP server test complete!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    initialize_logger()

    success = test_leanexplore()
    sys.exit(0 if success else 1)
