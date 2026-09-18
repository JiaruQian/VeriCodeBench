#!/usr/bin/env python3
"""Run Python requirement -> Nagini spec -> Python code -> Nagini pipeline."""
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
from autospec.pipeline.python_nagini_requirement_pipeline import (
    PythonNaginiRequirementToCodePipeline,
    load_python_nagini_requirements,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Nagini specs and Python code from natural language requirements."
    )
    parser.add_argument(
        "--requirements-file",
        type=Path,
        default=Path("benchmarks/python-nagini-problems/requirements/requirements_100.json"),
        help="Path to Python/Nagini requirements JSON.",
    )
    parser.add_argument(
        "--signature-file",
        type=Path,
        default=Path(
            "benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json"
        ),
        help=(
            "Optional dataset signature hints. Only function_signature is read; "
            "ground-truth contracts are not sent to the model."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/python-nagini-req2code"),
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
        default=os.getenv("OPENROUTER_APP_NAME", "AutoSpec-Python-Nagini"),
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--llm-retries", type=int, default=3)
    parser.add_argument("--llm-retry-delay", type=int, default=15)
    parser.add_argument("--verify-timeout", type=int, default=120)
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--nagini-bin", type=str, default=os.getenv("NAGINI_BIN", "nagini"))
    parser.add_argument(
        "--pipeline-variant",
        choices=["base", "enhanced"],
        default="base",
        help=(
            "Pipeline variant for ablation. base disables constraint extraction "
            "and code repair; enhanced enables the selected enhancement method."
        ),
    )
    parser.add_argument(
        "--enhancement-method",
        choices=["ce", "repair", "both"],
        default=None,
        help=(
            "Enhanced-only shorthand: ce enables constraint extraction/spec self-check, "
            "repair enables verification-guided repair, both enables both modules."
        ),
    )
    parser.add_argument(
        "--enable-constraint-extraction",
        dest="enable_constraint_extraction",
        action="store_true",
        default=None,
        help="Enable Python requirement constraint extraction + constraint-to-Nagini mapping.",
    )
    parser.add_argument(
        "--disable-constraint-extraction",
        dest="enable_constraint_extraction",
        action="store_false",
        help="Disable constraint extraction and use direct requirement-to-Nagini generation.",
    )
    parser.add_argument(
        "--spec-self-check-rounds",
        type=int,
        default=1,
        help="Rounds for Python spec self-check/refinement when constraint extraction is enabled.",
    )
    parser.add_argument("--enable-code-repair", dest="enable_code_repair", action="store_true", default=None)
    parser.add_argument("--disable-code-repair", dest="enable_code_repair", action="store_false")
    parser.add_argument("--code-repair-max-iter", type=int, default=3)
    parser.add_argument(
        "--code-repair-strategy",
        choices=["simple", "wybecoder"],
        default="simple",
        help=(
            "'simple' feeds Nagini output directly into one repair prompt; "
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
            "Optional existing Python/Nagini output directory containing specs/ and code/. "
            "When set, spec/code generation is skipped for strict incremental repair ablations."
        ),
    )
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _effective_enhancement_config(args: argparse.Namespace) -> tuple[bool, int, bool, int]:
    if args.pipeline_variant == "base":
        return False, 0, False, 0

    if args.enhancement_method == "ce":
        enable_constraint_extraction = True
        enable_code_repair = False
    elif args.enhancement_method == "repair":
        enable_constraint_extraction = False
        enable_code_repair = True
    elif args.enhancement_method == "both":
        enable_constraint_extraction = True
        enable_code_repair = True
    else:
        enable_constraint_extraction = (
            True
            if args.enable_constraint_extraction is None
            else args.enable_constraint_extraction
        )
        enable_code_repair = True if args.enable_code_repair is None else args.enable_code_repair

    spec_self_check_rounds = args.spec_self_check_rounds if enable_constraint_extraction else 0
    code_repair_max_iter = args.code_repair_max_iter if enable_code_repair else 0
    return (
        enable_constraint_extraction,
        spec_self_check_rounds,
        enable_code_repair,
        code_repair_max_iter,
    )


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if "openrouter.ai" in args.endpoint and not api_key:
        raise SystemExit(
            f"Missing API key for OpenRouter. Set {args.api_key_env} or pass --api-key."
        )

    signature_file = args.signature_file if args.signature_file else None
    requirements = load_python_nagini_requirements(args.requirements_file, signature_file=signature_file)
    if args.task_id is not None:
        requirements = [r for r in requirements if r.id == args.task_id]
        if not requirements:
            raise SystemExit(f"task id {args.task_id} not found in {args.requirements_file}")
    print(f"[INFO] Loaded {len(requirements)} Python/Nagini requirements from {args.requirements_file}")

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
    (
        enable_constraint_extraction,
        spec_self_check_rounds,
        enable_code_repair,
        code_repair_max_iter,
    ) = _effective_enhancement_config(args)
    print(
        "[INFO] Python/Nagini pipeline config: "
        f"variant={args.pipeline_variant}, "
        f"enhancement_method={args.enhancement_method or 'manual'}, "
        f"constraint_extraction={enable_constraint_extraction}, "
        f"spec_self_check_rounds={spec_self_check_rounds}, "
        f"code_repair={enable_code_repair}, "
        f"code_repair_max_iter={code_repair_max_iter}, "
        f"code_repair_strategy={args.code_repair_strategy}, "
        f"reuse_artifacts_from={args.reuse_artifacts_from}"
    )
    pipeline = PythonNaginiRequirementToCodePipeline(
        llm_client=client,
        output_dir=args.output_dir,
        verify_timeout=args.verify_timeout,
        skip_verify=args.skip_verify,
        logger=lambda msg: print(msg, flush=True),
        nagini_bin=args.nagini_bin,
        enable_constraint_extraction=enable_constraint_extraction,
        spec_self_check_rounds=spec_self_check_rounds,
        enable_code_repair=enable_code_repair,
        code_repair_max_iter=code_repair_max_iter,
        code_repair_strategy=args.code_repair_strategy,
        wybecoder_candidates=args.wybecoder_candidates,
        reuse_artifacts_from=args.reuse_artifacts_from,
        pipeline_variant=args.pipeline_variant,
        enhancement_method=args.enhancement_method,
    )
    outcome = pipeline.run(requirements, resume=args.resume)
    report = outcome["report"]
    print(
        "[INFO] Python/Nagini pipeline finished: "
        f"total={report['total']}, verified={report['verified']}, passed={report['passed']}"
    )
    print(f"[INFO] Report: {outcome['report_path']}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
