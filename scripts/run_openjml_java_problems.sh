#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR="${BENCH_DIR:-$ROOT_DIR/benchmarks/java-problems/ground-truth}"
REPORT_DIR="${REPORT_DIR:-$ROOT_DIR/outputs/java-openjml-reference/reports}"
TIMEOUT="${OPENJML_TIMEOUT:-120}"
OPENJML_BIN="${OPENJML_BIN:-openjml}"
OPENJML_SOLVER="${OPENJML_SOLVER:-}"

mkdir -p "$REPORT_DIR"

args=(--esc)
if [[ -n "$OPENJML_SOLVER" ]]; then
  args+=(--exec "$OPENJML_SOLVER")
fi

results="$REPORT_DIR/results.jsonl"
: > "$results"

total=0
pass=0
fail=0

while IFS= read -r -d '' file; do
  rel="${file#$BENCH_DIR/}"
  log="$REPORT_DIR/${rel%.java}.openjml.log"
  mkdir -p "$(dirname "$log")"
  total=$((total + 1))

  if timeout "$TIMEOUT" "$OPENJML_BIN" "${args[@]}" "$file" >"$log" 2>&1; then
    status="pass"
    pass=$((pass + 1))
  else
    status="fail"
    fail=$((fail + 1))
  fi

  python3 - "$results" "$rel" "$status" "$log" <<'PY'
import json
import sys

out, path, status, log = sys.argv[1:]
with open(out, "a", encoding="utf-8") as f:
    f.write(json.dumps({"path": path, "status": status, "log": log}) + "\n")
PY
  printf '%s %s\n' "$status" "$rel"
done < <(find "$BENCH_DIR" -name '*.java' -print0 | sort -z)

python3 - "$REPORT_DIR/summary.json" "$total" "$pass" "$fail" <<'PY'
import json
import sys

out, total, passed, failed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
with open(out, "w", encoding="utf-8") as f:
    json.dump({
        "total": total,
        "pass": passed,
        "fail": failed,
        "pass_rate": passed / total if total else 0.0,
    }, f, indent=2)
    f.write("\n")
PY

printf 'OpenJML reference summary: %d pass / %d total, %d fail\n' "$pass" "$total" "$fail"
