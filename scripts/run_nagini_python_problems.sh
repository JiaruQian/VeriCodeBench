#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR="${BENCH_DIR:-$ROOT_DIR/benchmarks/python-nagini-problems/ground-truth}"
NAGINI_BIN="${NAGINI_BIN:-nagini}"
TIMEOUT_SECONDS="${VERIFY_TIMEOUT:-120}"

pass=0
fail=0

while IFS= read -r -d '' file; do
  rel="${file#$ROOT_DIR/}"
  printf '[python-nagini] %s ... ' "$rel"
  output="$(timeout "$TIMEOUT_SECONDS" "$NAGINI_BIN" "$file" 2>&1)"
  status=$?
  if [ "$status" -eq 0 ]; then
    pass=$((pass + 1))
    printf 'PASS\n'
  else
    fail=$((fail + 1))
    printf 'FAIL\n'
    printf '%s\n' "$output"
  fi
done < <(find "$BENCH_DIR" -name '*.py' -print0 | sort -z)

total=$((pass + fail))
printf '\n[python-nagini] %d pass / %d total\n' "$pass" "$total"

if [ "$fail" -ne 0 ]; then
  exit 1
fi
