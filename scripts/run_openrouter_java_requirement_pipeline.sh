#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-benchmarks/java-problems/requirements/requirements_100.json}"
SIGNATURE_FILE="${SIGNATURE_FILE:-benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/java-req2code-openrouter}"
MODEL="${MODEL:-deepseek/deepseek-v3.2}"
ENDPOINT="${ENDPOINT:-https://openrouter.ai/api/v1/chat/completions}"
API_KEY_ENV="${API_KEY_ENV:-OPENROUTER_API_KEY}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
LLM_RETRIES="${LLM_RETRIES:-3}"
LLM_RETRY_DELAY="${LLM_RETRY_DELAY:-15}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"
OPENJML_BIN="${OPENJML_BIN:-openjml}"
OPENJML_SOLVER="${OPENJML_SOLVER:-}"
ENABLE_CGS="${ENABLE_CGS:-true}"
SPEC_SELF_CHECK_ROUNDS="${SPEC_SELF_CHECK_ROUNDS:-1}"
CODE_REPAIR_MAX_ITER="${CODE_REPAIR_MAX_ITER:-3}"
ENABLE_CODE_REPAIR="${ENABLE_CODE_REPAIR:-true}"
CODE_REPAIR_STRATEGY="${CODE_REPAIR_STRATEGY:-simple}"
VGCR_CANDIDATES="${VGCR_CANDIDATES:-3}"
REUSE_ARTIFACTS_FROM="${REUSE_ARTIFACTS_FROM:-}"
SKIP_VERIFY="${SKIP_VERIFY:-false}"
TASK_ID="${TASK_ID:-}"
RESUME="${RESUME:-false}"

args=(
  --requirements-file "$REQUIREMENTS_FILE"
  --signature-file "$SIGNATURE_FILE"
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
  --openjml-bin "$OPENJML_BIN"
  --spec-self-check-rounds "$SPEC_SELF_CHECK_ROUNDS"
  --code-repair-max-iter "$CODE_REPAIR_MAX_ITER"
  --code-repair-strategy "$CODE_REPAIR_STRATEGY"
)

if [[ -n "$OPENJML_SOLVER" ]]; then
  args+=(--openjml-solver "$OPENJML_SOLVER")
fi
if [[ "$ENABLE_CGS" == "true" ]]; then
  args+=(--enable-cgs)
else
  args+=(--disable-cgs)
fi
if [[ "$ENABLE_CODE_REPAIR" == "true" ]]; then
  args+=(--enable-code-repair)
else
  args+=(--disable-code-repair)
fi
if [[ "$SKIP_VERIFY" == "true" ]]; then
  args+=(--skip-verify)
fi
if [[ "$CODE_REPAIR_STRATEGY" == "vgcr" ]]; then
  args+=(--vgcr-candidates "$VGCR_CANDIDATES")
fi
if [[ -n "$REUSE_ARTIFACTS_FROM" ]]; then
  args+=(--reuse-artifacts-from "$REUSE_ARTIFACTS_FROM")
fi
if [[ -n "$TASK_ID" ]]; then
  args+=(--task-id "$TASK_ID")
fi
if [[ "${RESUME,,}" == "true" ]]; then
  args+=(--resume)
fi

echo "[INFO] Running Java requirement pipeline with OpenRouter..."
echo "[INFO] REQUIREMENTS_FILE=$REQUIREMENTS_FILE"
echo "[INFO] SIGNATURE_FILE=$SIGNATURE_FILE"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
echo "[INFO] MODEL=$MODEL"
echo "[INFO] ENABLE_CGS=$ENABLE_CGS"
echo "[INFO] ENABLE_CODE_REPAIR=$ENABLE_CODE_REPAIR"
echo "[INFO] CODE_REPAIR_STRATEGY=$CODE_REPAIR_STRATEGY"
echo "[INFO] SKIP_VERIFY=$SKIP_VERIFY"
echo "[INFO] RESUME=$RESUME"

PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py "${args[@]}"
