# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Test agent with MCP tools on a sample Lean problem."""
# python -m scripts.test_agent_with_mcp

import os
from pathlib import Path

from src.utils import initialize_logger
import logging
import fire
import sys

logger = logging.getLogger()

from src.agent import rollout
from src.args import RunArgs
from src.envs.verina_proof import VerinaProofEnv
from src.env import Message
from src.repl import LeanRepl
from src import local_mcp as MCP


def load_verina_task():
    """Load a single verina task from the dataset."""

    import json

    repo_root = Path(__file__).parent.parent
    verina_file = repo_root / "data" / "verina.jsonl"

    if not verina_file.exists():
        raise FileNotFoundError(
            f"Verina dataset not found at {verina_file}. "
            "Please ensure data/verina.jsonl exists."
        )

    with open(verina_file, "r") as f:
        first_line = f.readline()
        if not first_line.strip():
            raise ValueError(f"Verina file {verina_file} is empty")
        task = json.loads(first_line)

    # Add MCP-specific fields
    task["use_mcp"] = True
    task["lean_project_path"] = str(repo_root)
    # Note: loogle_url is no longer needed as MCP.initialize() handles server startup

    # Add instruction to require MCP tool usage
    task["description"] = (
        task["description"]
        + "\n\n**IMPORTANT for this test:** You MUST use the"
        # `lean_loogle` to test leanexplore, this is now commented out
        + "`leanexplore_search` "
        + "tool at least once before any attempt to solve the task. You will be penalized otherwise."  # :)
    )

    return task


def main(model="gemini-2.5-flash-lite"):
    print("=" * 70)
    print("Testing Agent with MCP Tools")
    print("=" * 70)

    # Load verina task
    print("\nLoading verina task...")
    try:
        task = load_verina_task()
        print(f"✓ Task loaded: {task.get('id', 'unknown')}")
        description = task.get("description", "No description")
        print(f"  Description: {description[:100]}...")
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Failed to load task: {e}")
        return 1

    # Set up environment and runner
    print("\nSetting up environment...")
    env = VerinaProofEnv()

    # Initialize MCP servers (Loogle + leanexplore via HTTP proxy)
    print("Initializing MCP servers (this may take a moment)...")
    try:
        MCP.initialize(
            start_loogle=True,
            start_leanexplore=True,
            leanexplore_backend="local",
        )
        print("✓ MCP servers initialized")
    except Exception as e:
        print(f"❌ Failed to initialize MCP servers: {e}")
        import traceback

        traceback.print_exc()
        return 1

    runner = LeanRepl(max_mem_mb=40960)

    # Configure args for MCP
    run_args = RunArgs(
        name="test_mcp",
        model=model,
        temperature=0.0,
        max_turns=5,
        use_mcp=True,
    )
    print(f"✓ Using model: {run_args.model}")
    print(f"✓ MCP enabled: {run_args.use_mcp}")
    print(f"✓ Max turns: {run_args.max_turns}")

    # Run the agent
    print("\n" + "=" * 70)
    print("Running Agent...")
    print("=" * 70)
    print(
        "\nNote: This may take a while as it initializes Lean REPL and calls Gemini API..."
    )
    print("Check for log messages below to see progress.\n")

    try:
        result = rollout(env, runner, task, run_args)

        # Generate log filename with timestamp
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"runs/agent_conversation_{timestamp}.log"

        # Ensure runs directory exists
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        # Log to file
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 70 + "\n")
            f.write("AGENT CONVERSATION LOG\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Task ID: {result.task.get('id', 'unknown')}\n")
            f.write(f"Task: {result.task.get('function_name', 'unknown')}\n")
            f.write(f"Completed in {result.n_turns} turns\n")
            f.write(f"Success: {result.outcomes.get('success', False)}\n")
            f.write(f"Pass: {result.outcomes.get('pass', False)}\n\n")

            f.write("=" * 70 + "\n")
            f.write("FULL CONVERSATION\n")
            f.write("=" * 70 + "\n\n")
            for msg in result.dialog:
                assert isinstance(msg, Message)
                f.write(f"[{msg.role.upper()}]\n")
                f.write(f"{msg.content}\n\n")
                if msg.tool_dialog:
                    f.write("TOOL DIALOG:")
                    for m in msg.tool_dialog:
                        f.write(f"[{m.role.upper()}]\n")
                        f.write(f"{m.content}\n\n")

        print(f"\n✓ Conversation logged to: {log_file}")
        print(f"✓ Completed in {result.n_turns} turns")
        if result.outcomes.get("pass"):
            print("✅ Agent succeeded!")
        else:
            print("⚠ Agent did not complete successfully")

        return 0

    except Exception as e:
        print(f"\n❌ Error running agent: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        # Cleanup: shutdown MCP servers
        print("\nShutting down MCP servers...")
        try:
            MCP.shutdown()
            print("✓ MCP servers shut down")
        except Exception as e:
            print(f"⚠ Warning during shutdown: {e}")


if __name__ == "__main__":
    initialize_logger(level="info")  # use "debug" for more details
    sys.exit(fire.Fire(main))
