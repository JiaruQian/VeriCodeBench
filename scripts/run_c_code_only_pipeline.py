#!/usr/bin/env python3
"""Run the C code-only oracle-contract benchmark."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.llm.openai_compatible import ChatConfig, OpenAICompatibleClient
from autospec.pipeline.code_only_pipeline import (
    CodeOnlyContractPipeline,
    as_requirement_items,
    load_code_only_contracts,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and verify C code under frozen oracle contracts.")
    parser.add_argument("--contracts-file", type=Path, default=Path("benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/c-code-only"))
    parser.add_argument("--endpoint", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--model", default="deepseek/deepseek-v3.2")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--llm-retries", type=int, default=3)
    parser.add_argument("--llm-retry-delay", type=int, default=15)
    parser.add_argument("--verify-timeout", type=int, default=120)
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--enable-code-repair", action="store_true")
    parser.add_argument("--code-repair-max-iter", type=int, default=3)
    parser.add_argument("--code-repair-strategy", choices=["simple", "wybecoder"], default="simple")
    parser.add_argument("--wybecoder-candidates", type=int, default=3)
    parser.add_argument("--reuse-artifacts-from", type=Path, default=None)
    parser.add_argument("--task-id", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key or os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if "openrouter.ai" in args.endpoint and not api_key:
        raise SystemExit(f"Missing API key. Set {args.api_key_env} or pass --api-key.")
    contracts = load_code_only_contracts(args.contracts_file)
    if args.task_id is not None:
        contracts = [item for item in contracts if item.id == args.task_id]
        if not contracts:
            raise SystemExit(f"task id {args.task_id} not found")
    client = OpenAICompatibleClient(ChatConfig(
        model=args.model, endpoint=args.endpoint, temperature=args.temperature,
        max_tokens=args.max_tokens, api_key=api_key, timeout_seconds=args.request_timeout,
        retry_on_connection_error=args.llm_retries, retry_delay_seconds=args.llm_retry_delay,
    ))
    pipeline = CodeOnlyContractPipeline(
        contracts=contracts, llm_client=client, output_dir=args.output_dir,
        verify_timeout=args.verify_timeout, skip_verify=args.skip_verify,
        logger=lambda message: print(message, flush=True),
        enable_code_repair=args.enable_code_repair,
        code_repair_max_iter=args.code_repair_max_iter,
        code_repair_strategy=args.code_repair_strategy,
        wybecoder_candidates=args.wybecoder_candidates,
        reuse_artifacts_from=args.reuse_artifacts_from,
    )
    result = pipeline.run(as_requirement_items(contracts), resume=args.resume)
    print(f"[DONE] report={result['report_path']}")


if __name__ == "__main__":
    main()
