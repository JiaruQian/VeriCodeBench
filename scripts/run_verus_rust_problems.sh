#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR="${ROOT_DIR}/benchmarks/rust-verus-problems/ground-truth"
VERUS_BIN="${VERUS_BIN:-verus}"

total=0
passed=0

while IFS= read -r -d '' file; do
  total=$((total + 1))
  if "${VERUS_BIN}" "${file}" >/tmp/verus-rust-problem.log 2>&1; then
    passed=$((passed + 1))
  else
    echo "FAIL ${file}"
    cat /tmp/verus-rust-problem.log
  fi
done < <(find "${BENCH_DIR}" -name '*.rs' -print0 | sort -z)

rm -f /tmp/verus-rust-problem.log
echo "${passed} pass / ${total} total"

if [[ "${passed}" -ne "${total}" ]]; then
  exit 1
fi
