#!/usr/bin/env python3
"""Run requirement -> spec -> code -> verification pipeline."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make script runnable without manually exporting PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.llm.openai_compatible import ChatConfig, OpenAICompatibleClient
from autospec.pipeline.requirement_pipeline import (
    EnhancedRequirementToCodePipeline,
    RequirementToCodePipeline,
    load_requirements,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ACSL specs and C code from natural language requirements."
    )
    parser.add_argument(
        "--requirements-file",
        type=Path,
        default=Path("benchmarks/frama-c-problems/requirements/requirements_100.json"),
        help="Path to requirements JSON.",
    )
    parser.add_argument(
        "--signature-file",
        type=Path,
        default=Path("benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json"),
        help=(
            "Optional dataset signature hints. Only function_signature is read; "
            "ground-truth contracts are not sent to the model."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/req2code"),
        help="Directory to store generated specs/code/reports.",
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
        default=os.getenv("OPENROUTER_APP_NAME", "CodeNova"),
        help="Optional X-Title header value.",
    )
    parser.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature.")
    parser.add_argument("--max-tokens", type=int, default=4096, help="Max output tokens.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=120,
        help="Timeout per LLM request in seconds.",
    )
    parser.add_argument(
        "--llm-retries",
        type=int,
        default=3,
        help="Bounded retries for transient LLM/API failures.",
    )
    parser.add_argument(
        "--llm-retry-delay",
        type=int,
        default=15,
        help="Delay between LLM/API retries in seconds.",
    )
    parser.add_argument(
        "--verify-timeout",
        type=int,
        default=120,
        help="Timeout per Frama-C verification in seconds.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Generate specs/code only, skip Frama-C verification.",
    )
    parser.add_argument(
        "--pipeline-variant",
        choices=["base", "enhanced"],
        default="base",
        help="Pipeline variant for ablation: base or enhanced.",
    )
    parser.add_argument(
        "--spec-self-check-rounds",
        type=int,
        default=1,
        help=(
            "Enhanced only: rounds for spec self-check/refinement. "
            "Only used when constraint-guided specification (CGS) is enabled."
        ),
    )
    parser.add_argument(
        "--code-repair-max-iter",
        type=int,
        default=3,
        help="Enhanced only: max verification-guided code repair iterations.",
    )
    parser.add_argument(
        "--code-repair-strategy",
        choices=["simple", "vgcr"],
        default="simple",
        help=(
            "Enhanced only: repair strategy. 'simple' is the original verifier-feedback "
            "loop; 'vgcr' uses verifier-subgoal planning plus multiple repair candidates."
        ),
    )
    parser.add_argument(
        "--vgcr-candidates",
        type=int,
        default=3,
        help="Enhanced only: number of repair candidates per VGCR-style attempt.",
    )
    parser.add_argument(
        "--enable-cgs",
        dest="enable_cgs",
        action="store_true",
        default=None,
        help=(
            "Enhanced only: enable requirement constraint-guided specification (CGS) + constraint-to-ACSL "
            "mapping. Default: enabled for enhanced."
        ),
    )
    parser.add_argument(
        "--disable-cgs",
        dest="enable_cgs",
        action="store_false",
        help=(
            "Enhanced only: disable requirement constraint-guided specification (CGS) and use direct "
            "requirement-to-ACSL spec generation."
        ),
    )
    parser.add_argument(
        "--enable-code-repair",
        dest="enable_code_repair",
        action="store_true",
        default=None,
        help="Enhanced only: enable verification-guided code repair. Default: enabled for enhanced.",
    )
    parser.add_argument(
        "--disable-code-repair",
        dest="enable_code_repair",
        action="store_false",
        help="Enhanced only: disable verification-guided code repair.",
    )
    parser.add_argument(
        "--enable-spec-evaluation",
        action="store_true",
        help=(
            "Enhanced only: enable requirement-spec matching evaluation "
            "(Requirement Coverage / Over-specification Extra) using LLM-as-a-judge."
        ),
    )
    parser.add_argument(
        "--reuse-artifacts-from",
        type=Path,
        default=None,
        help=(
            "Enhanced only: copy specs/ and code/ from an existing output directory, "
            "then only run verification and optional code repair. Use this for strict "
            "incremental ablations such as base+vgcr or base+cgs+vgcr."
        ),
    )
    parser.add_argument(
        "--task-id",
        type=int,
        default=None,
        help="Run only one requirement item by id (e.g. 17).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from reports/results.partial.json or results.json and skip completed ok tasks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if "openrouter.ai" in args.endpoint and not api_key:
        raise SystemExit(
            f"Missing API key for OpenRouter. Set {args.api_key_env} or pass --api-key."
        )

    requirements = load_requirements(args.requirements_file, signature_file=args.signature_file)
    if args.task_id is not None:
        requirements = [r for r in requirements if r.id == args.task_id]
        if not requirements:
            raise SystemExit(f"task id {args.task_id} not found in {args.requirements_file}")
    print(f"[INFO] Loaded {len(requirements)} requirements from {args.requirements_file}")

    llm_config = ChatConfig(
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
    client = OpenAICompatibleClient(llm_config)
    if args.pipeline_variant == "enhanced":
        enable_cgs = (
            True
            if args.enable_cgs is None
            else args.enable_cgs
        )
        enable_code_repair = True if args.enable_code_repair is None else args.enable_code_repair
        pipeline = EnhancedRequirementToCodePipeline(
            llm_client=client,
            output_dir=args.output_dir,
            verify_timeout=args.verify_timeout,
            skip_verify=args.skip_verify,
            logger=lambda msg: print(msg, flush=True),
            spec_self_check_rounds=args.spec_self_check_rounds,
            code_repair_max_iter=args.code_repair_max_iter,
            enable_spec_evaluation=args.enable_spec_evaluation,
            enable_cgs=enable_cgs,
            enable_code_repair=enable_code_repair,
            code_repair_strategy=args.code_repair_strategy,
            vgcr_candidates=args.vgcr_candidates,
            reuse_artifacts_from=args.reuse_artifacts_from,
        )
    else:
        pipeline = RequirementToCodePipeline(
            llm_client=client,
            output_dir=args.output_dir,
            verify_timeout=args.verify_timeout,
            skip_verify=args.skip_verify,
            logger=lambda msg: print(msg, flush=True),
        )
    outcome = pipeline.run(requirements, resume=args.resume)
    report = outcome["report"]
    print(
        "[INFO] Pipeline finished: "
        f"total={report['total']}, verified={report['verified']}, passed={report['passed']}"
    )
    print(f"[INFO] Pipeline variant: {args.pipeline_variant}")
    print(f"[INFO] Report: {outcome['report_path']}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
