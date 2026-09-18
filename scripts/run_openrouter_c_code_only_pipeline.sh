#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

MODEL="${MODEL:-deepseek/deepseek-v3.2}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
CONTRACTS_FILE="${CONTRACTS_FILE:-benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/c-code-only}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
LLM_RETRIES="${LLM_RETRIES:-3}"
LLM_RETRY_DELAY="${LLM_RETRY_DELAY:-15}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
ENABLE_CODE_REPAIR="${ENABLE_CODE_REPAIR:-false}"
CODE_REPAIR_MAX_ITER="${CODE_REPAIR_MAX_ITER:-3}"
CODE_REPAIR_STRATEGY="${CODE_REPAIR_STRATEGY:-simple}"
VGCR_CANDIDATES="${VGCR_CANDIDATES:-3}"
REUSE_ARTIFACTS_FROM="${REUSE_ARTIFACTS_FROM:-}"
TASK_ID="${TASK_ID:-}"
RESUME="${RESUME:-false}"
SKIP_VERIFY="${SKIP_VERIFY:-false}"

if [[ -z "$OPENROUTER_API_KEY" ]]; then
  echo "ERROR: OPENROUTER_API_KEY is not set."
  exit 1
fi

CMD=(python3 scripts/run_c_code_only_pipeline.py
  --contracts-file "$CONTRACTS_FILE" --output-dir "$OUTPUT_DIR"
  --endpoint https://openrouter.ai/api/v1/chat/completions --model "$MODEL"
  --api-key-env OPENROUTER_API_KEY --temperature "$TEMPERATURE" --max-tokens "$MAX_TOKENS"
  --request-timeout "$REQUEST_TIMEOUT" --llm-retries "$LLM_RETRIES"
  --llm-retry-delay "$LLM_RETRY_DELAY" --verify-timeout "$VERIFY_TIMEOUT"
  --code-repair-max-iter "$CODE_REPAIR_MAX_ITER"
  --code-repair-strategy "$CODE_REPAIR_STRATEGY" --vgcr-candidates "$VGCR_CANDIDATES")

[[ "${ENABLE_CODE_REPAIR,,}" == "true" ]] && CMD+=(--enable-code-repair)
[[ "${RESUME,,}" == "true" ]] && CMD+=(--resume)
[[ "${SKIP_VERIFY,,}" == "true" ]] && CMD+=(--skip-verify)
[[ -n "$REUSE_ARTIFACTS_FROM" ]] && CMD+=(--reuse-artifacts-from "$REUSE_ARTIFACTS_FROM")
[[ -n "$TASK_ID" ]] && CMD+=(--task-id "$TASK_ID")

echo "[INFO] C code-only oracle-contract pipeline"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR MODEL=$MODEL REPAIR=$ENABLE_CODE_REPAIR/$CODE_REPAIR_STRATEGY"
[[ -n "$REUSE_ARTIFACTS_FROM" ]] && echo "[INFO] REUSE_ARTIFACTS_FROM=$REUSE_ARTIFACTS_FROM"
"${CMD[@]}"
