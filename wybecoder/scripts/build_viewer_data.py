#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Build viewer data for the static trajectory viewer.

Processes raw trajectory JSONL files from runs/trajectories/ into:
  1. docs/viewer_data.json — index with problem metadata, pass/fail, final code
  2. docs/viewer_data/dialogs/<run_name>.json — bundled dialog data per run

Key optimizations:
  - System prompts removed
  - Linear runs: only last 10 messages kept
  - Decomp: only last assistant message per sub-agent
  - Agent results slimmed to essential fields
  - Decomp rollouts > DECOMP_SIZE_LIMIT get structure only (no dialog content)

Usage:
    python scripts/build_viewer_data.py
"""

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs" / "trajectories"
OUT_DIR = REPO_ROOT / "docs" / "viewer_data" / "dialogs"
INDEX_FILE = REPO_ROOT / "docs" / "viewer_data.json"

# Decomp rollouts above this threshold (in bytes) get structure-only output
DECOMP_SIZE_LIMIT = 2 * 1024 * 1024  # 2MB


RUN_DISPLAY_NAMES = {
    "opus-4-5-linear-verina": "Verina — Opus 4.5 Sequential (32×16)",
    "opus-4-5-linear-clever": "Clever — Opus 4.5 Sequential (32×16)",
    "opus-4-5-decomp-clever": "Clever — Opus 4.5 Decomp (8×128)",
    "opus-4-5-decomp-verina": "Verina — Opus 4.5 Decomp (8×128)",
}

RUN_BENCHMARK_SIZES = {
    "opus-4-5-linear-verina": 189,
    "opus-4-5-linear-clever": 161,
    "opus-4-5-decomp-clever": 161,
    "opus-4-5-decomp-verina": 189,
}

RUNS = {
    "opus-4-5-linear-verina": {"type": "linear"},
    "opus-4-5-linear-clever": {"type": "linear"},
    "opus-4-5-decomp-clever": {"type": "decomp"},
    "opus-4-5-decomp-verina": {"type": "decomp"},
}


def slim_linear(obj: dict) -> dict:
    """Extract dialog from a linear rollout."""
    dialog = obj.get("dialog", {})
    messages = dialog.get("messages", [])
    slim_msgs = []
    for msg in messages:
        if msg.get("role") == "system":
            continue
        content = msg.get("content", "")
        if msg.get("role") == "user":
            marker = "\n# FULL CODE WITH LINE NUMBERS FOR REFERENCE"
            idx = content.find(marker)
            if idx >= 0:
                content = content[:idx] + "\n[... full code omitted ...]"
        slim_msgs.append({"role": msg["role"], "content": content})

    return {
        "messages": slim_msgs,
        "tokens_in": dialog.get("total_input_tokens"),
        "tokens_out": dialog.get("total_output_tokens"),
    }


def slim_agent_results(agent_results: dict) -> dict:
    """Keep only essential fields from agent_results."""
    slim = {}
    for k, v in agent_results.items():
        slim[k] = {
            "sub_id": v.get("sub_id"),
            "success": v.get("success"),
            "action": v.get("action"),
            "goal_idx": v.get("goal_idx"),
            "rev_id": v.get("rev_id"),
            "aborted": v.get("aborted"),
            "auto": v.get("auto", False),
        }
    return slim


def slim_revisions(revisions: list) -> list:
    """Slim revisions: keep goal tags and method code, drop full goal code/statements."""
    slim = []
    for rev in revisions:
        goals = rev.get("goals", [])
        slim_goals = []
        if isinstance(goals, list):
            for g in goals:
                if isinstance(g, dict):
                    slim_goals.append({"tag": g.get("tag") or g.get("name", "?")})
                else:
                    slim_goals.append({"tag": str(g)})
        elif isinstance(goals, dict):
            for k in goals:
                slim_goals.append({"tag": k})

        final = rev.get("final", {})
        decls = final.get("decls", [])
        method_idx = final.get("method_idx", rev.get("method_idx", 1))
        method_code = decls[method_idx]["code"] if method_idx < len(decls) else None

        slim.append({
            "n_goals": len(slim_goals),
            "goals": slim_goals,
            "method_code": method_code,
            "errors": final.get("errors", ""),
        })
    return slim


def slim_decomp(obj: dict) -> dict:
    """Extract slim data from a decomp rollout, with size-based cutoff."""
    dialogs = obj.get("dialogs", {})
    agent_results = obj.get("agent_results", {})
    revisions = obj.get("revisions", [])

    slim_ar = slim_agent_results(agent_results)
    slim_revs = slim_revisions(revisions)

    # Build slim sub-agent dialogs (last assistant message + token counts)
    aborted_ids = {k for k, v in agent_results.items() if v.get("aborted")}
    slim_subs = {}
    for sid, dlg in dialogs.items():
        if isinstance(dlg, dict):
            msgs = dlg.get("messages", [])
            tokens_in = dlg.get("total_input_tokens")
            tokens_out = dlg.get("total_output_tokens")
        else:
            msgs = dlg if isinstance(dlg, list) else []
            tokens_in = tokens_out = None

        assistants = [m for m in msgs if m.get("role") == "assistant"]
        last_msg = "" if sid in aborted_ids else (assistants[-1]["content"] if assistants else "")

        slim_subs[sid] = {
            "last_response": last_msg,
            "n_turns": len(assistants),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    result = {
        "revisions": slim_revs,
        "agent_results": slim_ar,
        "sub_agents": slim_subs,
    }

    payload = json.dumps(result, separators=(",", ":"))
    if len(payload) > DECOMP_SIZE_LIMIT:
        result = {
            "revisions": slim_revs,
            "agent_results": slim_ar,
            "too_large": True,
            "n_sub_agents": len(dialogs),
        }

    return result


def build_rollout_index(obj: dict, run_type: str, worker_stem: str, line_num: int) -> dict:
    """Build index entry for a single rollout (for viewer_data.json)."""
    outcomes = obj.get("outcomes", {})
    stats = obj.get("stats", {})

    entry = {
        "pass": outcomes.get("pass_judged", outcomes.get("pass", False)),
        "raw_pass": outcomes.get("raw_pass", False),
        "disproof_pass": outcomes.get("disproof_pass", False),
        "final_code": outcomes.get("final_code", obj.get("final_code", "")),
        "tokens_in": stats.get("total_input_tokens", 0),
        "tokens_out": stats.get("total_output_tokens", 0),
        "termination": obj.get("termination_reason", ""),
        "source_file": f"{worker_stem}.jsonl",
        "source_line": line_num,
    }

    if run_type == "decomp":
        entry["n_subs"] = obj.get("n_subs", len(obj.get("dialogs", {})))
        entry["n_revisions"] = len(obj.get("revisions", []))
        # Slim revisions for index (just goal counts)
        revisions = obj.get("revisions", [])
        entry["revisions"] = [len(r.get("goals", [])) for r in revisions]
    else:
        dialog = obj.get("dialog", {})
        msgs = dialog.get("messages", [])
        entry["n_turns"] = len([m for m in msgs if m.get("role") == "assistant"])
        entry["dialog_len"] = len(msgs)

    return entry


def process_run(run_name: str, run_config: dict):
    """Process a single run: build bundled dialog file and index entries."""
    run_dir = RUNS_DIR / run_name
    if not run_dir.exists():
        print(f"  Skipping {run_name}: directory not found")
        return {}, {}

    all_dialogs = {}  # key -> slim dialog data
    problems = {}     # task_id -> {rollouts: [...]}

    for worker_file in sorted(run_dir.iterdir()):
        if not worker_file.name.endswith(".jsonl"):
            continue

        with open(worker_file) as f:
            for line_num, line in enumerate(f):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                task_id = obj.get("task", {}).get("id", f"unknown_{line_num}")
                safe_id = task_id.replace("/", "_").replace(" ", "_")
                key = f"{safe_id}_{worker_file.stem}_{line_num}"

                # Build dialog data
                if run_config["type"] == "decomp":
                    slim = slim_decomp(obj)
                else:
                    slim = slim_linear(obj)
                all_dialogs[key] = slim

                # Build index entry
                idx_entry = build_rollout_index(obj, run_config["type"], worker_file.stem, line_num)
                idx_entry["dialog_key"] = key
                if slim.get("too_large"):
                    idx_entry["too_large"] = True

                if task_id not in problems:
                    problems[task_id] = {"id": task_id, "rollouts": []}
                problems[task_id]["rollouts"].append(idx_entry)

    return all_dialogs, problems


def main():
    print("Building viewer data...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    index = {}

    for run_name, config in RUNS.items():
        display_name = RUN_DISPLAY_NAMES.get(run_name, run_name)
        print(f"Processing {run_name}...")

        all_dialogs, problems = process_run(run_name, config)

        if not problems:
            continue

        # Write bundled dialog file
        dialog_file = OUT_DIR / f"{run_name}.json"
        payload = json.dumps(all_dialogs, separators=(",", ":"))
        dialog_file.write_text(payload)
        size_mb = len(payload) / 1024 / 1024
        n_too_large = sum(1 for d in all_dialogs.values() if d.get("too_large"))
        extra = f", {n_too_large} structure-only" if n_too_large else ""
        print(f"  {len(all_dialogs)} rollouts, {size_mb:.1f}MB{extra}")

        # Build index entry
        problem_list = sorted(problems.values(), key=lambda p: p["id"])
        n_resolved = sum(1 for p in problem_list if any(r.get("pass") or r.get("disproof_pass") for r in p["rollouts"]))
        benchmark_size = RUN_BENCHMARK_SIZES.get(run_name, len(problem_list))

        index[display_name] = {
            "problems": problem_list,
            "total_problems": len(problem_list),
            "total_resolved": n_resolved,
            "solve_rate": round(n_resolved / benchmark_size * 100, 1) if benchmark_size else 0,
            "base_path": f"runs/trajectories/{run_name}",
            "type": config["type"],
            "benchmark_size": benchmark_size,
        }

        for p in problem_list:
            p["n_rollouts"] = len(p["rollouts"])
            p["n_pass"] = sum(1 for r in p["rollouts"] if r.get("pass"))
            p["n_disproof"] = sum(1 for r in p["rollouts"] if r.get("disproof_pass"))
            p["n_resolved"] = p["n_pass"] + p["n_disproof"]

    # Write index
    index_payload = json.dumps(index, indent=2)
    INDEX_FILE.write_text(index_payload)
    print(f"\nIndex: {len(index_payload) // 1024}KB → {INDEX_FILE.relative_to(REPO_ROOT)}")
    print("Done.")


if __name__ == "__main__":
    main()
