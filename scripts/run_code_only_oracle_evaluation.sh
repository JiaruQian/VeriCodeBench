#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

ORACLE_FILE="${ORACLE_FILE:-benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json}"
OUTPUT_DIR="${OUTPUT_DIR:-outputs/c-code-only-base-0825}"
SPECS_DIR="${SPECS_DIR:-$OUTPUT_DIR/specs}"
REPORT_FILE="${REPORT_FILE:-$OUTPUT_DIR/reports/oracle_contract_consistency.json}"

CMD=(python3 scripts/evaluate_code_only_oracle.py
  --oracle-file "$ORACLE_FILE" --specs-dir "$SPECS_DIR" --report-file "$REPORT_FILE")
if [[ -n "${TASK_ID:-}" ]]; then CMD+=(--task-id "$TASK_ID"); fi
"${CMD[@]}"
