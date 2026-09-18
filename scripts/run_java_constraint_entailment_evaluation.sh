#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

OUTPUT_DIR="${OUTPUT_DIR:-outputs/java-code-only-base-0827}"
GROUND_TRUTH_SPEC_FILE="${GROUND_TRUTH_SPEC_FILE:-benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json}"
TASK_ID="${TASK_ID:-}"

args=(
  --language java
  --ground-truth-spec-file "$GROUND_TRUTH_SPEC_FILE"
  --output-dir "$OUTPUT_DIR"
)

if [[ -n "$TASK_ID" ]]; then
  args+=(--task-id "$TASK_ID")
fi

PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py "${args[@]}"
