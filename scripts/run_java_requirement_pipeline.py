#!/usr/bin/env python3
"""Run Java requirement -> JML spec -> Java code -> OpenJML pipeline."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.llm.openai_compatible import ChatConfig, OpenAICompatibleClient
from autospec.pipeline.java_requirement_pipeline import (
    JavaRequirementToCodePipeline,
    load_java_requirements,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate JML specs and Java code from natural language requirements."
    )
    parser.add_argument(
        "--requirements-file",
        type=Path,
        default=Path("benchmarks/java-problems/requirements/requirements_100.json"),
        help="Path to Java requirements JSON.",
    )
    parser.add_argument(
        "--signature-file",
        type=Path,
        default=Path("benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json"),
        help=(
            "Optional dataset interface hints. Only function_signature and non-contract "
            "type_context are read; ground-truth contracts are not sent to the model."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/java-req2code"),
        help="Directory to store generated specs/code/reports.",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default="https://openrouter.ai/api/v1/chat/completions",
        help="OpenAI-compatible chat completion endpoint.",
    )
    parser.add_argument("--model", type=str, default="deepseek/deepseek-v3.2")
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--api-key-env", type=str, default="OPENROUTER_API_KEY")
    parser.add_argument("--site-url", type=str, default=os.getenv("OPENROUTER_SITE_URL"))
    parser.add_argument(
        "--app-name",
        type=str,
        default=os.getenv("OPENROUTER_APP_NAME", "AutoSpec-Java"),
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--llm-retries", type=int, default=3)
    parser.add_argument("--llm-retry-delay", type=int, default=15)
    parser.add_argument("--verify-timeout", type=int, default=120)
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--openjml-bin", type=str, default=os.getenv("OPENJML_BIN", "openjml"))
    parser.add_argument("--openjml-solver", type=str, default=os.getenv("OPENJML_SOLVER") or None)
    parser.add_argument(
        "--enable-constraint-extraction",
        dest="enable_constraint_extraction",
        action="store_true",
        default=True,
        help="Enable Java requirement constraint extraction + constraint-to-JML mapping.",
    )
    parser.add_argument(
        "--disable-constraint-extraction",
        dest="enable_constraint_extraction",
        action="store_false",
        help="Disable constraint extraction and use direct requirement-to-JML generation.",
    )
    parser.add_argument(
        "--spec-self-check-rounds",
        type=int,
        default=1,
        help="Rounds for Java spec self-check/refinement when constraint extraction is enabled.",
    )
    parser.add_argument("--enable-code-repair", dest="enable_code_repair", action="store_true", default=True)
    parser.add_argument("--disable-code-repair", dest="enable_code_repair", action="store_false")
    parser.add_argument("--code-repair-max-iter", type=int, default=3)
    parser.add_argument(
        "--code-repair-strategy",
        choices=["simple", "wybecoder"],
        default="simple",
        help=(
            "'simple' feeds OpenJML output directly into one repair prompt; "
            "'wybecoder' uses verifier-subgoal planning plus multiple repair candidates."
        ),
    )
    parser.add_argument(
        "--wybecoder-candidates",
        type=int,
        default=3,
        help="Number of focused repair candidates per WybeCoder-style repair iteration.",
    )
    parser.add_argument(
        "--reuse-artifacts-from",
        type=Path,
        default=None,
        help=(
            "Optional existing Java output directory containing specs/ and code/. "
            "When set, spec/code generation is skipped for strict incremental repair ablations."
        ),
    )
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if "openrouter.ai" in args.endpoint and not api_key:
        raise SystemExit(
            f"Missing API key for OpenRouter. Set {args.api_key_env} or pass --api-key."
        )

    signature_file = args.signature_file if args.signature_file else None
    requirements = load_java_requirements(args.requirements_file, signature_file=signature_file)
    if args.task_id is not None:
        requirements = [r for r in requirements if r.id == args.task_id]
        if not requirements:
            raise SystemExit(f"task id {args.task_id} not found in {args.requirements_file}")
    print(f"[INFO] Loaded {len(requirements)} Java requirements from {args.requirements_file}")

    client = OpenAICompatibleClient(
        ChatConfig(
            model=args.model,
            endpoint=args.endpoint,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            api_key=api_key,
            site_url=args.site_url,
            app_name=args.app_name,
            timeout_seconds=args.request_timeout,
            retry_on_connection_error=args.llm_retries,
            retry_delay_seconds=args.llm_retry_delay,
        )
    )
    pipeline = JavaRequirementToCodePipeline(
        llm_client=client,
        output_dir=args.output_dir,
        verify_timeout=args.verify_timeout,
        skip_verify=args.skip_verify,
        logger=lambda msg: print(msg, flush=True),
        openjml_bin=args.openjml_bin,
        openjml_solver=args.openjml_solver,
        enable_constraint_extraction=args.enable_constraint_extraction,
        spec_self_check_rounds=args.spec_self_check_rounds,
        enable_code_repair=args.enable_code_repair,
        code_repair_max_iter=args.code_repair_max_iter,
        code_repair_strategy=args.code_repair_strategy,
        wybecoder_candidates=args.wybecoder_candidates,
        reuse_artifacts_from=args.reuse_artifacts_from,
    )
    outcome = pipeline.run(requirements, resume=args.resume)
    report = outcome["report"]
    print(
        "[INFO] Java pipeline finished: "
        f"total={report['total']}, verified={report['verified']}, passed={report['passed']}"
    )
    print(f"[INFO] Report: {outcome['report_path']}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
