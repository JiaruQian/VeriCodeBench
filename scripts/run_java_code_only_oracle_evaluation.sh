#!/usr/bin/env bash
set -euo pipefail
ORACLE_FILE="${ORACLE_FILE:-benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json}"
SPECS_DIR="${SPECS_DIR:?set SPECS_DIR to generated specs directory}"
REPORT_FILE="${REPORT_FILE:-$SPECS_DIR/../reports/java_oracle_contract_consistency.json}"
python3 scripts/evaluate_java_code_only_oracle.py --oracle-file "$ORACLE_FILE" --specs-dir "$SPECS_DIR" --report-file "$REPORT_FILE" "$@"
