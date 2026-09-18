#!/bin/bash
# Summarize benchmark metrics at problem level.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/C-ce-dsv41-time-5-0916}"  # default output directory
RESULTS_FILE="${RESULTS_FILE:-}"         # optional
ENTAILMENT_FILE="${ENTAILMENT_FILE:-}"   # optional
REPORT_FILE="${REPORT_FILE:-}"           # optional

CMD=(
  python3 scripts/summarize_req2code_benchmark.py
  --output-dir "$OUTPUT_DIR"
)

if [[ -n "$RESULTS_FILE" ]]; then
  CMD+=(--results-file "$RESULTS_FILE")
fi

if [[ -n "$ENTAILMENT_FILE" ]]; then
  CMD+=(--entailment-file "$ENTAILMENT_FILE")
fi

if [[ -n "$REPORT_FILE" ]]; then
  CMD+=(--report-file "$REPORT_FILE")
fi

echo "[INFO] OUTPUT_DIR=$OUTPUT_DIR"
"${CMD[@]}"
