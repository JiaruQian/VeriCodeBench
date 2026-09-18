# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# python -m scripts.test_mcp
"""Unified test script for Loogle and Leanexplore MCP server"""

import sys
import json

from src import local_mcp as MCP
from src.utils import initialize_logger


def test_mcp():
    """Test the Loogle and Leanxplore MCP server"""
    print("=" * 70)
    print("Testing Loogle and Leanexplore MCP server")
    print("=" * 70)

    # Initialize both servers
    print("\n1. Initializing MCP server...")
    MCP.initialize(
        start_loogle=True,
        start_leanexplore=True,
        leanexplore_backend="local",
        leanexplore_log_level="ERROR",
    )
    print("✓ MCP server initialized")

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

    # Test Loogle search
    print("\n4. Testing Loogle search for 'List.reverse'...")
    result = MCP.call_tool("lean_loogle", {"query": "List.reverse", "num_results": 3})
    assert isinstance(result, dict) and "content" in result and result["content"]
    text = result["content"][0].get("text", "")
    # Parse the JSON-encoded text
    parsed_result = json.loads(text)
    print(parsed_result)
    if isinstance(parsed_result, list) and len(parsed_result) > 0:
        print(f"✓ Loogle search successful! Found {len(parsed_result)} results")
        print(f"  First result: {parsed_result[0].get('name', 'Unknown')}")
    elif isinstance(parsed_result, str):
        print(f"⚠ Loogle returned: {parsed_result[:100]}...")
    else:
        print(f"⚠ Unexpected result: {type(parsed_result)}")

    # Shutdown
    print("\n5. Shutting down MCP server...")
    MCP.shutdown()
    print("✓ Server shut down")

    print("\n" + "=" * 70)
    print("✅ MCP server test complete!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    initialize_logger()

    success = test_mcp()
    sys.exit(0 if success else 1)
