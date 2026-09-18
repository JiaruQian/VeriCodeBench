#!/usr/bin/env python3
"""Post-hoc requirement-spec evaluation for existing pipeline outputs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Make script runnable without manually exporting PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.llm.openai_compatible import ChatConfig, OpenAICompatibleClient
from autospec.pipeline.requirement_pipeline import (
    EnhancedRequirementToCodePipeline,
    load_requirements,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate requirement-spec alignment (Coverage/Extra) from existing specs/*.json "
            "without regenerating code or running Frama-C verification."
        )
    )
    parser.add_argument(
        "--requirements-file",
        type=Path,
        default=Path("benchmarks/frama-c-problems/requirements/requirements_100.json"),
        help="Path to requirements JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/req2code"),
        help="Pipeline output directory containing specs/ and reports/.",
    )
    parser.add_argument(
        "--specs-dir",
        type=Path,
        default=None,
        help="Optional override for specs directory (default: <output-dir>/specs).",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Optional report path (default: <output-dir>/reports/spec_evaluation.json).",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="https://openrouter.ai/api/v1/chat/completions",
        help="OpenAI-compatible chat completion endpoint.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="deepseek/deepseek-v3.2",
        help="Model name sent to endpoint.",
    )
    parser.add_argument("--api-key", type=str, default=None, help="Direct API key.")
    parser.add_argument(
        "--api-key-env",
        type=str,
        default="OPENROUTER_API_KEY",
        help="Environment variable name holding API key.",
    )
    parser.add_argument(
        "--site-url",
        type=str,
        default=os.getenv("OPENROUTER_SITE_URL"),
        help="Optional HTTP-Referer header value.",
    )
    parser.add_argument(
        "--app-name",
        type=str,
        default=os.getenv("OPENROUTER_APP_NAME", "AutoSpec"),
        help="Optional X-Title header value.",
    )
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Max output tokens.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=120,
        help="Timeout per LLM request in seconds.",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        default=None,
        help="Evaluate only one requirement item by id (e.g. 17).",
    )
    return parser.parse_args()


def _read_spec_fields(spec_file: Path) -> Dict[str, str]:
    data = json.loads(spec_file.read_text())
    function_signature = str(data.get("function_signature", "")).strip()
    acsl_block = str(data.get("acsl_block", "")).strip()
    if not function_signature:
        raise ValueError(f"Missing function_signature in {spec_file}")
    if not acsl_block:
        raise ValueError(f"Missing acsl_block in {spec_file}")
    return {
        "function_signature": function_signature,
        "acsl_block": acsl_block,
    }


def _build_summary(results: List[Dict[str, Any]], total_expected: int) -> Dict[str, Any]:
    evaluated = [r for r in results if r.get("status") == "ok" and "coverage" in r and "extra" in r]
    missing_specs = [r for r in results if r.get("status") == "missing_spec"]
    errors = [r for r in results if r.get("status") == "error"]

    avg_coverage = 0.0
    avg_extra = 0.0
    if evaluated:
        avg_coverage = sum(float(r["coverage"]) for r in evaluated) / len(evaluated)
        avg_extra = sum(float(r["extra"]) for r in evaluated) / len(evaluated)

    return {
        "total_expected": total_expected,
        "processed": len(results),
        "evaluated": len(evaluated),
        "missing_specs": len(missing_specs),
        "errors": len(errors),
        "avg_coverage": avg_coverage,
        "avg_extra": avg_extra,
    }


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if "openrouter.ai" in args.endpoint and not api_key:
        raise SystemExit(
            f"Missing API key for OpenRouter. Set {args.api_key_env} or pass --api-key."
        )

    output_dir = args.output_dir
    specs_dir = args.specs_dir or (output_dir / "specs")
    report_file = args.report_file or (output_dir / "reports" / "spec_evaluation.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    requirements = load_requirements(args.requirements_file)
    if args.task_id is not None:
        requirements = [r for r in requirements if r.id == args.task_id]
        if not requirements:
            raise SystemExit(f"task id {args.task_id} not found in {args.requirements_file}")

    llm_config = ChatConfig(
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        api_key=api_key,
        site_url=args.site_url,
        app_name=args.app_name,
        timeout_seconds=args.request_timeout,
    )
    client = OpenAICompatibleClient(llm_config)

    evaluator = EnhancedRequirementToCodePipeline(
        llm_client=client,
        output_dir=output_dir,
        verify_timeout=1,
        skip_verify=True,
        logger=lambda msg: print(msg, flush=True),
        spec_self_check_rounds=0,
        code_repair_max_iter=0,
        enable_spec_evaluation=True,
    )

    print(f"[INFO] Loaded {len(requirements)} requirements from {args.requirements_file}")
    print(f"[INFO] Specs directory: {specs_dir}")
    print("[INFO] Running post-hoc requirement-spec evaluation...")

    results: List[Dict[str, Any]] = []
    total = len(requirements)
    for idx, item in enumerate(requirements, start=1):
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        row: Dict[str, Any] = {
            "id": item.id,
            "path": item.path,
            "requirement": item.requirement,
            "spec_file": str(spec_file),
        }
        print(f"[TASK {idx}/{total}] id={item.id} path={item.path}")
        if not spec_file.exists():
            row["status"] = "missing_spec"
            row["error"] = "spec file not found"
            results.append(row)
            print(f"[TASK {idx}/{total}] status=missing_spec")
            continue

        try:
            spec_fields = _read_spec_fields(spec_file)
            evaluation = evaluator._evaluate_spec_against_requirement(
                requirement=item.requirement,
                function_signature=spec_fields["function_signature"],
                acsl_block=spec_fields["acsl_block"],
            )
            row["status"] = "ok"
            row["coverage"] = evaluation.get("coverage", 0.0)
            row["extra"] = evaluation.get("extra", 0.0)
            row["spec_evaluation"] = evaluation
            print(
                f"[TASK {idx}/{total}] status=ok "
                f"coverage={row['coverage']:.3f} extra={row['extra']:.3f}"
            )
        except Exception as exc:  # keep batch resilient
            row["status"] = "error"
            row["error"] = str(exc)
            print(f"[TASK {idx}/{total}] status=error error={exc}")
        results.append(row)

    summary = _build_summary(results, total_expected=total)
    report = {
        "method": "llm_judge_binary",
        "summary": summary,
        "results": results,
    }
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(
        "[INFO] Evaluation finished: "
        f"processed={summary['processed']} evaluated={summary['evaluated']} "
        f"missing_specs={summary['missing_specs']} errors={summary['errors']}"
    )
    print(
        "[INFO] Metrics: "
        f"avg_coverage={summary['avg_coverage']:.4f}, avg_extra={summary['avg_extra']:.4f}"
    )
    print(f"[INFO] Report: {report_file}")


if __name__ == "__main__":
    main()
