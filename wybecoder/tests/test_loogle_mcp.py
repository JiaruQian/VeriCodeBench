# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# python -m scripts.lean_lsp_mcp.test_loogle
"""Quick test to verify remote loogle server integration."""

import asyncio
import os
import sys
from pathlib import Path


from src.mcp_client import LeanLspMcpClient


async def test_loogle():
    print("Testing lean-lsp-mcp Loogle setup")
    print("=" * 70)

    try:
        # Connect to MCP with remote loogle
        workspace_path = str(Path(__file__).parent.parent)
        lean_file = os.path.join(workspace_path, "swap.lean")

        print("\nConnecting to lean-lsp-mcp with remote loogle...")
        mcp_client = LeanLspMcpClient(
            lean_file_path=lean_file,
            lean_project_path=workspace_path,
        )
        await mcp_client.__aenter__()
        print("✓ Connected to lean-lsp-mcp")

        print("Testing list_tools")
        tools = await mcp_client.list_tools()
        print(f"Received tool list: {tools}")

        # Test loogle search
        print("\nTesting loogle search for 'List.length'...")
        result = await mcp_client.call_tool(
            "lean_loogle",
            {
                "query": "List.length",
                "num_results": 5,  # Request up to 5 results
            },
        )

        print("\n=== Full Result ===")
        print(result)

        if result and "content" in result:
            print("\n✓ Loogle search successful!")
            print(f"\nFound {len(result['content'])} results:")

            # Parse and display each result
            import json

            for i, item in enumerate(result["content"], 1):
                result_text = item["text"]
                try:
                    res = json.loads(result_text)
                    print(f"\n{i}. {res.get('name', 'Unknown')}")
                    print(f"   Module: {res.get('module', 'N/A')}")
                    print(f"   Type: {res.get('type', 'N/A')}")
                except json.JSONDecodeError:
                    print(f"\n{i}. {result_text[:150]}...")
        else:
            print(f"⚠ Result: {result}")

        await mcp_client.__aexit__(None, None, None)
        print("\n" + "=" * 70)
        print("✅ Remote loogle integration works!")

        return True

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_loogle())
    sys.exit(0 if success else 1)
