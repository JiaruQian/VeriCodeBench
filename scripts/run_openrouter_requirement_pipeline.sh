#!/bin/bash
# Run requirement -> spec -> code -> verify pipeline with OpenRouter.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

# Auto-detect libclang for compatibility with existing project tooling.
if [[ -z "${LIBCLANG_PATH:-}" ]]; then
  if [[ -f "/opt/clang/lib/libclang.so" ]]; then
    export LIBCLANG_PATH="/opt/clang/lib/libclang.so"
  elif [[ -f "/usr/lib/llvm-18/lib/libclang.so" ]]; then
    export LIBCLANG_PATH="/usr/lib/llvm-18/lib/libclang.so"
  fi
fi

if [[ -n "${LIBCLANG_PATH:-}" ]]; then
  libclang_dir="$(dirname "$LIBCLANG_PATH")"
  export LD_LIBRARY_PATH="$libclang_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

# -----------------------------
# User-configurable parameters
# -----------------------------
MODEL="${MODEL:-deepseek/deepseek-v3.2}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

# If key is defined in shell init files, load them for non-interactive runs.
if [[ -z "$OPENROUTER_API_KEY" ]]; then
  if [[ -f "$HOME/.bashrc" ]]; then
    # shellcheck disable=SC1090
    source "$HOME/.bashrc"
  fi
  if [[ -z "${OPENROUTER_API_KEY:-}" ]] && [[ -f "$HOME/.profile" ]]; then
    # shellcheck disable=SC1090
    source "$HOME/.profile"
  fi
fi
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
export OPENROUTER_API_KEY

REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-benchmarks/frama-c-problems/requirements/requirements_100.json}"
SIGNATURE_FILE="${SIGNATURE_FILE:-benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/req2code-openrouter-enhanced-0324}"
VERIFY_TIMEOUT="${VERIFY_TIMEOUT:-120}"
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
LLM_RETRIES="${LLM_RETRIES:-3}"
LLM_RETRY_DELAY="${LLM_RETRY_DELAY:-15}"
TEMPERATURE="${TEMPERATURE:-0.1}"
MAX_TOKENS="${MAX_TOKENS:-2048}"
SKIP_VERIFY="${SKIP_VERIFY:-false}" # true/false
TASK_ID="${TASK_ID:-}"              # optional single task id
PIPELINE_VARIANT="${PIPELINE_VARIANT:-enhanced}" # base/enhanced
ENABLE_CONSTRAINT_EXTRACTION="${ENABLE_CONSTRAINT_EXTRACTION:-true}" # true/false
SPEC_SELF_CHECK_ROUNDS="${SPEC_SELF_CHECK_ROUNDS:-1}"
ENABLE_CODE_REPAIR="${ENABLE_CODE_REPAIR:-true}" # true/false
CODE_REPAIR_MAX_ITER="${CODE_REPAIR_MAX_ITER:-3}"
CODE_REPAIR_STRATEGY="${CODE_REPAIR_STRATEGY:-simple}" # simple/wybecoder
WYBECODER_CANDIDATES="${WYBECODER_CANDIDATES:-3}"
ENABLE_SPEC_EVALUATION="${ENABLE_SPEC_EVALUATION:-false}" # true/false
REUSE_ARTIFACTS_FROM="${REUSE_ARTIFACTS_FROM:-}" # optional existing output dir for strict incremental ablations
RESUME="${RESUME:-false}" # true/false; skip completed ok tasks from existing report

if [[ -z "$OPENROUTER_API_KEY" ]]; then
  echo "ERROR: OPENROUTER_API_KEY is not set."
  echo "Set it before running, for example:"
  echo "  export OPENROUTER_API_KEY=sk-or-xxxx"
  exit 1
fi

CMD=(
  python3 scripts/run_requirement_pipeline.py
  --requirements-file "$REQUIREMENTS_FILE"
  --signature-file "$SIGNATURE_FILE"
  --output-dir "$OUTPUT_DIR"
  --endpoint "https://openrouter.ai/api/v1/chat/completions"
  --model "$MODEL"
  --api-key "$OPENROUTER_API_KEY"
  --api-key-env "OPENROUTER_API_KEY"
  --temperature "$TEMPERATURE"
  --max-tokens "$MAX_TOKENS"
  --request-timeout "$REQUEST_TIMEOUT"
  --llm-retries "$LLM_RETRIES"
  --llm-retry-delay "$LLM_RETRY_DELAY"
  --verify-timeout "$VERIFY_TIMEOUT"
  --pipeline-variant "$PIPELINE_VARIANT"
)

if [[ "${SKIP_VERIFY,,}" == "true" ]]; then
  CMD+=(--skip-verify)
fi

if [[ -n "$TASK_ID" ]]; then
  CMD+=(--task-id "$TASK_ID")
fi

if [[ "${RESUME,,}" == "true" ]]; then
  CMD+=(--resume)
fi

if [[ "$PIPELINE_VARIANT" == "enhanced" ]]; then
  if [[ "${ENABLE_CONSTRAINT_EXTRACTION,,}" == "true" ]]; then
    CMD+=(--enable-constraint-extraction)
  else
    CMD+=(--disable-constraint-extraction)
  fi
  CMD+=(--spec-self-check-rounds "$SPEC_SELF_CHECK_ROUNDS")

  if [[ "${ENABLE_CODE_REPAIR,,}" == "true" ]]; then
    CMD+=(--enable-code-repair)
  else
    CMD+=(--disable-code-repair)
  fi
  CMD+=(--code-repair-max-iter "$CODE_REPAIR_MAX_ITER")
  CMD+=(--code-repair-strategy "$CODE_REPAIR_STRATEGY")
  CMD+=(--wybecoder-candidates "$WYBECODER_CANDIDATES")

  if [[ "${ENABLE_SPEC_EVALUATION,,}" == "true" ]]; then
    CMD+=(--enable-spec-evaluation)
  fi

  if [[ -n "$REUSE_ARTIFACTS_FROM" ]]; then
    CMD+=(--reuse-artifacts-from "$REUSE_ARTIFACTS_FROM")
  fi
fi

echo "[INFO] Running requirement pipeline with OpenRouter..."
echo "[INFO] REQUIREMENTS_FILE=$REQUIREMENTS_FILE"
echo "[INFO] SIGNATURE_FILE=$SIGNATURE_FILE"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
echo "[INFO] MODEL=$MODEL"
echo "[INFO] REQUEST_TIMEOUT=$REQUEST_TIMEOUT"
echo "[INFO] LLM_RETRIES=$LLM_RETRIES"
echo "[INFO] LLM_RETRY_DELAY=$LLM_RETRY_DELAY"
echo "[INFO] PIPELINE_VARIANT=$PIPELINE_VARIANT"
echo "[INFO] ENABLE_CONSTRAINT_EXTRACTION=$ENABLE_CONSTRAINT_EXTRACTION"
echo "[INFO] ENABLE_CODE_REPAIR=$ENABLE_CODE_REPAIR"
echo "[INFO] CODE_REPAIR_STRATEGY=$CODE_REPAIR_STRATEGY"
echo "[INFO] WYBECODER_CANDIDATES=$WYBECODER_CANDIDATES"
echo "[INFO] ENABLE_SPEC_EVALUATION=$ENABLE_SPEC_EVALUATION"
echo "[INFO] RESUME=$RESUME"
if [[ -n "$REUSE_ARTIFACTS_FROM" ]]; then
  echo "[INFO] REUSE_ARTIFACTS_FROM=$REUSE_ARTIFACTS_FROM"
fi
echo "[INFO] SKIP_VERIFY=$SKIP_VERIFY"
if [[ -n "$TASK_ID" ]]; then
  echo "[INFO] TASK_ID=$TASK_ID"
fi

"${CMD[@]}"
