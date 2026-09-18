#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONTRACTS_FILE="${CONTRACTS_FILE:-benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/rust-code-only}"
MODEL="${MODEL:-deepseek/deepseek-v3.2}"
ENDPOINT="${ENDPOINT:-https://openrouter.ai/api/v1/chat/completions}"
API_KEY_ENV="${API_KEY_ENV:-OPENROUTER_API_KEY}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
LLM_RETRIES="${LLM_RETRIES:-3}"
LLM_RETRY_DELAY="${LLM_RETRY_DELAY:-15}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"
VERUS_BIN="${VERUS_BIN:-verus}"
ENABLE_CODE_REPAIR="${ENABLE_CODE_REPAIR:-false}"
CODE_REPAIR_MAX_ITER="${CODE_REPAIR_MAX_ITER:-3}"
CODE_REPAIR_STRATEGY="${CODE_REPAIR_STRATEGY:-simple}"
VGCR_CANDIDATES="${VGCR_CANDIDATES:-3}"
REUSE_ARTIFACTS_FROM="${REUSE_ARTIFACTS_FROM:-}"
SKIP_VERIFY="${SKIP_VERIFY:-false}"
TASK_ID="${TASK_ID:-}"
RESUME="${RESUME:-false}"

args=(
  --contracts-file "$CONTRACTS_FILE"
  --output-dir "$OUTPUT_DIR"
  --endpoint "$ENDPOINT"
  --model "$MODEL"
  --api-key-env "$API_KEY_ENV"
  --temperature "$TEMPERATURE"
  --max-tokens "$MAX_TOKENS"
  --request-timeout "$REQUEST_TIMEOUT"
  --llm-retries "$LLM_RETRIES"
  --llm-retry-delay "$LLM_RETRY_DELAY"
  --verify-timeout "$VERIFY_TIMEOUT"
  --verus-bin "$VERUS_BIN"
  --code-repair-max-iter "$CODE_REPAIR_MAX_ITER"
  --code-repair-strategy "$CODE_REPAIR_STRATEGY"
  --vgcr-candidates "$VGCR_CANDIDATES"
)

[[ "${ENABLE_CODE_REPAIR,,}" == "true" ]] && args+=(--enable-code-repair)
[[ "${SKIP_VERIFY,,}" == "true" ]] && args+=(--skip-verify)
[[ "${RESUME,,}" == "true" ]] && args+=(--resume)
[[ -n "$REUSE_ARTIFACTS_FROM" ]] && args+=(--reuse-artifacts-from "$REUSE_ARTIFACTS_FROM")
[[ -n "$TASK_ID" ]] && args+=(--task-id "$TASK_ID")

echo "[INFO] Running Rust/Verus code-only oracle-contract pipeline..."
echo "[INFO] CONTRACTS_FILE=$CONTRACTS_FILE"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
echo "[INFO] MODEL=$MODEL"
echo "[INFO] ENABLE_CODE_REPAIR=$ENABLE_CODE_REPAIR"
echo "[INFO] CODE_REPAIR_STRATEGY=$CODE_REPAIR_STRATEGY"
echo "[INFO] REUSE_ARTIFACTS_FROM=$REUSE_ARTIFACTS_FROM"

PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py "${args[@]}"
