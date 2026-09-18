#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/python-ce-claude-0714}"
GROUND_TRUTH_SPEC_FILE="${GROUND_TRUTH_SPEC_FILE:-benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json}"
TASK_ID="${TASK_ID:-}"
OFFLINE_REPAIR="${OFFLINE_REPAIR:-false}"
REPAIRED_OUTPUT_DIR="${REPAIRED_OUTPUT_DIR:-${OUTPUT_DIR}-offline-repaired}"
OFFLINE_REPAIR_VERIFY="${OFFLINE_REPAIR_VERIFY:-failed}"
OFFLINE_REPAIR_VERIFY_TIMEOUT="${OFFLINE_REPAIR_VERIFY_TIMEOUT:-120}"
OFFLINE_REPAIR_OVERWRITE="${OFFLINE_REPAIR_OVERWRITE:-true}"
RUN_BENCHMARK_SUMMARY="${RUN_BENCHMARK_SUMMARY:-$OFFLINE_REPAIR}"

is_true() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

EFFECTIVE_OUTPUT_DIR="$OUTPUT_DIR"
if is_true "$OFFLINE_REPAIR"; then
  repair_args=(
    --source-output-dir "$OUTPUT_DIR"
    --output-dir "$REPAIRED_OUTPUT_DIR"
    --verify "$OFFLINE_REPAIR_VERIFY"
    --verify-timeout "$OFFLINE_REPAIR_VERIFY_TIMEOUT"
  )
  if is_true "$OFFLINE_REPAIR_OVERWRITE"; then
    repair_args+=(--overwrite)
  fi
  echo "[INFO] Offline-repairing Python/Nagini artifacts: $OUTPUT_DIR -> $REPAIRED_OUTPUT_DIR"
  python3 scripts/repair_python_nagini_artifacts.py "${repair_args[@]}"
  EFFECTIVE_OUTPUT_DIR="$REPAIRED_OUTPUT_DIR"
fi

args=(
  --language python
  --ground-truth-spec-file "$GROUND_TRUTH_SPEC_FILE"
  --output-dir "$EFFECTIVE_OUTPUT_DIR"
)

if [[ -n "$TASK_ID" ]]; then
  args+=(--task-id "$TASK_ID")
fi

PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py "${args[@]}"

if is_true "$RUN_BENCHMARK_SUMMARY"; then
  OUTPUT_DIR="$EFFECTIVE_OUTPUT_DIR" ./scripts/run_req2code_benchmark_summary.sh
fi

echo "[INFO] EFFECTIVE_OUTPUT_DIR=$EFFECTIVE_OUTPUT_DIR"
