#!/usr/bin/env bash
set -euo pipefail

ORACLE_FILE="${ORACLE_FILE:-benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json}"
OUTPUT_DIR="${OUTPUT_DIR:?set OUTPUT_DIR to the Rust code-only output directory}"
SPECS_DIR="${SPECS_DIR:-$OUTPUT_DIR/specs}"
CODE_DIR="${CODE_DIR:-$OUTPUT_DIR/code}"
REPORT_FILE="${REPORT_FILE:-$OUTPUT_DIR/reports/rust_oracle_contract_consistency.json}"

python3 scripts/evaluate_rust_code_only_oracle.py \
  --oracle-file "$ORACLE_FILE" \
  --specs-dir "$SPECS_DIR" \
  --code-dir "$CODE_DIR" \
  --report-file "$REPORT_FILE" \
  "$@"
