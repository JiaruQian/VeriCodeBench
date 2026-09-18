#!/bin/bash
# Run the offline Constraint Entailment Framework (CEF) benchmark evaluation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

GROUND_TRUTH_SPEC_FILE="${GROUND_TRUTH_SPEC_FILE:-benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/C-cgs-dsv41-time-5-0916}"
SPECS_DIR="${SPECS_DIR:-}"          # optional, default <OUTPUT_DIR>/specs
REPORT_FILE="${REPORT_FILE:-}"      # optional, default <OUTPUT_DIR>/reports/cef.json
TASK_ID="${TASK_ID:-}"              # optional
MAX_COMBO_SIZE="${MAX_COMBO_SIZE:-5}"
MAX_COMBINATION_TRIALS="${MAX_COMBINATION_TRIALS:-2000}"

CMD=(
  python3 scripts/evaluate_constraint_entailment.py
  --ground-truth-spec-file "$GROUND_TRUTH_SPEC_FILE"
  --output-dir "$OUTPUT_DIR"
  --max-combo-size "$MAX_COMBO_SIZE"
  --max-combination-trials "$MAX_COMBINATION_TRIALS"
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

echo "[INFO] Running Constraint Entailment Framework (CEF) evaluation..."
echo "[INFO] GROUND_TRUTH_SPEC_FILE=$GROUND_TRUTH_SPEC_FILE"
echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
echo "[INFO] MAX_COMBO_SIZE=$MAX_COMBO_SIZE"
echo "[INFO] MAX_COMBINATION_TRIALS=$MAX_COMBINATION_TRIALS"
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
