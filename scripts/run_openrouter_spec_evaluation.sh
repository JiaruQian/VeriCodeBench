#!/bin/bash
# Run post-hoc requirement-spec evaluation on existing outputs with OpenRouter.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

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
OUTPUT_DIR="${OUTPUT_DIR:-outputs/req2code-openrouter-enhanced-0324}"
SPECS_DIR="${SPECS_DIR:-}"          # optional; default to <OUTPUT_DIR>/specs
REPORT_FILE="${REPORT_FILE:-}"      # optional; default to <OUTPUT_DIR>/reports/spec_evaluation.json
REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-120}"
TEMPERATURE="${TEMPERATURE:-0.0}"
MAX_TOKENS="${MAX_TOKENS:-1024}"
TASK_ID="${TASK_ID:-}"              # optional single task id

if [[ -z "$OPENROUTER_API_KEY" ]]; then
  echo "ERROR: OPENROUTER_API_KEY is not set."
  echo "Set it before running, for example:"
  echo "  export OPENROUTER_API_KEY=sk-or-xxxx"
  exit 1
fi

CMD=(
  python3 scripts/evaluate_spec_alignment.py
  --requirements-file "$REQUIREMENTS_FILE"
  --output-dir "$OUTPUT_DIR"
  --endpoint "https://openrouter.ai/api/v1/chat/completions"
  --model "$MODEL"
  --api-key "$OPENROUTER_API_KEY"
  --api-key-env "OPENROUTER_API_KEY"
  --temperature "$TEMPERATURE"
  --max-tokens "$MAX_TOKENS"
  --request-timeout "$REQUEST_TIMEOUT"
)

if [[ -n "$SPECS_DIR" ]]; then
  CMD+=(--specs-dir "$SPECS_DIR")
fi

if [[ -n "$REPORT_FILE" ]]; then
  CMD+=(--report-file "$REPORT_FILE")
fi

if [[ -n "$TASK_ID" ]]; then
  CMD+=(--task-id "$TASK_ID")
fi

echo "[INFO] Running post-hoc spec evaluation with OpenRouter..."
echo "[INFO] REQUIREMENTS_FILE=$REQUIREMENTS_FILE"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
echo "[INFO] MODEL=$MODEL"
if [[ -n "$SPECS_DIR" ]]; then
  echo "[INFO] SPECS_DIR=$SPECS_DIR"
fi
if [[ -n "$REPORT_FILE" ]]; then
  echo "[INFO] REPORT_FILE=$REPORT_FILE"
fi
if [[ -n "$TASK_ID" ]]; then
  echo "[INFO] TASK_ID=$TASK_ID"
fi

"${CMD[@]}"
