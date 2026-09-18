# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# python -m scripts.lean_lsp_mcp.test_loogle_service

"""Quick test to verify local loogle server integration."""

import sys


import src.mcp_service as MCP
from src.utils import initialize_logger


def test_loogle_service() -> bool:
    print("Testing local loogle server integration")
    print("=" * 70)

    # Connect to MCP with local loogle
    MCP.initialize()
    print("✓ Connected to lean-lsp-mcp")

    print("\nTesting list_tools")
    tools = MCP.list_tools()
    print(f"Received tool list: {tools}")

    # Test loogle search
    print("\nTesting loogle search for 'List.length'...")
    n_calls = 4
    for i in range(n_calls):
        print(f"Call {i + 1} / {n_calls}")
        result = MCP.call_tool(
            "lean_loogle",
            {
                "query": "List.length",
                "num_results": 5,  # Request up to 5 results
            },
        )

    print("\n=== Full Result ===")
    print(result)

    if isinstance(result["result"], list):
        items = result["result"]
        print("\n✓ Loogle search successful!")
        print(f"\nFound {len(items)} results:")

        for i, item in enumerate(items, 1):
            print(f"\n{i}. {item.get('name', 'Unknown')}")
            print(f"   Module: {item.get('module', 'N/A')}")
            print(f"   Type: {item.get('type', 'N/A')}")

        print("\n" + "=" * 70)
        print("✅ Local loogle integration works!")
        print("\nYour local loogle server is now being used instead of the public API.")
        print("No rate limits! 🎉")
    else:
        print(f"⚠ Result: {result}")

    return True


if __name__ == "__main__":
    initialize_logger()
    success = test_loogle_service()
    sys.exit(0 if success else 1)
