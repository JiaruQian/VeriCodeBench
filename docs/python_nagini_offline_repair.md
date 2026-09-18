# Python/Nagini Offline Artifact Repair

New pipeline runs do not need this repair command. The ordinary Python/Nagini
generation pipeline always performs the same deterministic normalization in
the original `OUTPUT_DIR` before its first Nagini invocation: it sanitizes the
canonical contract, removes code fences, enforces the contract in the source,
and requires the resulting file to pass `ast.parse`.

This offline tool exists only for artifacts generated before that pipeline
stage was added.

`scripts/repair_python_nagini_artifacts.py` repairs existing Python/Nagini
artifacts without making any LLM request and without overwriting the source
output directory.

The repair is intentionally conservative:

- rewrite evaluator-only `condition ==> conclusion` into legal Nagini
  `Implies(condition, conclusion)` syntax;
- remove unmatched Markdown code fences;
- remove invalid `Result()` clauses from functions returning `None`;
- order contract clauses by their well-formedness dependencies: permissions,
  structural facts such as length, then indexed expressions;
- rebuild and enforce the canonical contract in the copied Python source;
- reject repaired Python files that do not pass `ast.parse`.

Run it on failed artifacts only:

```bash
PYTHONPATH=. python3 scripts/repair_python_nagini_artifacts.py \
  --source-output-dir outputs/python-ce-kimi-0713 \
  --output-dir outputs/python-ce-kimi-0713-offline-repaired \
  --verify failed \
  --verify-timeout 120
```

Then refresh coverage and the benchmark summary:

```bash
OUTPUT_DIR=outputs/python-ce-kimi-0713-offline-repaired \
  ./scripts/run_python_nagini_constraint_entailment_evaluation.sh
OUTPUT_DIR=outputs/python-ce-kimi-0713-offline-repaired \
  ./scripts/run_req2code_benchmark_summary.sh
```

The Python coverage wrapper can run the complete repair, verification,
coverage, and summary workflow directly:

```bash
OUTPUT_DIR=outputs/python-ce-kimi-0713 \
OFFLINE_REPAIR=true \
OFFLINE_REPAIR_VERIFY=failed \
./scripts/run_python_nagini_constraint_entailment_evaluation.sh
```

The source directory remains unchanged. The default repaired directory is
`${OUTPUT_DIR}-offline-repaired`. Useful overrides are:

- `REPAIRED_OUTPUT_DIR=...`
- `OFFLINE_REPAIR_VERIFY=none|failed|all`
- `OFFLINE_REPAIR_VERIFY_TIMEOUT=120`
- `OFFLINE_REPAIR_OVERWRITE=true|false`
- `RUN_BENCHMARK_SUMMARY=true|false`

The coverage evaluator recursively normalizes `Implies(...)`, including when
multiple clauses are conjuncted during subset search. Reports using this
behavior are marked `manual_ground_truth_spec_entailment_v3`.
