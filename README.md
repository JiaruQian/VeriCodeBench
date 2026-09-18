# VeriCodeBench

Multi-language Requirement-to-Code Formal Verification Benchmark.

This is the anonymous source release. See [release notes](docs/anonymous_release.md)
for its contents, dependency attribution, and portable workspace conventions.

This repository contains a benchmark for evaluating LLM pipelines that translate natural-language requirements into language-specific formal specifications and verified code.

The benchmark started from 51 Frama-C problems, but the task is no longer "add specs to existing code." The general evaluated workflow is:

```text
Requirement -> Language-specific Spec -> Code -> Verifier
```

The existing C backend instantiates this workflow as:

```text
Requirement -> ACSL Spec -> C Code -> Frama-C/WP Verification
```

The Java backend is the first multi-language extension target:

```text
Requirement -> JML Spec -> Java Code -> OpenJML Verification
```

The Python/Nagini benchmark track instantiates the same shape as:

```text
Requirement -> Nagini Contract -> Python Code -> Nagini Verification
```

The benchmark measures two independent properties for each language backend:

- whether generated code verifies against the generated language-specific spec
- whether the generated spec covers the manually constructed ground-truth spec targets

## Benchmark Data

Current C/ACSL requirement dataset:

```text
benchmarks/frama-c-problems/requirements/requirements_100.json
```

Current C/ACSL manual ground-truth spec targets:

```text
benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json
```

The ground-truth spec file is curated. Some targets are directly derived from requirement semantics; others are derived from the reference Frama-C ACSL contracts when the requirement text alone is not precise enough. Both are treated as one unified manual ground truth.

The benchmark intentionally separates requirement semantic coverage from verification-oriented contract completeness. Auxiliary proof/safety conditions such as `\valid`, `\separated`, overflow guards, or frame clauses are included only when they are part of the curated target set.

For multi-language expansion, each backend may maintain its own requirement set, signatures, spec language, verifier adapter, and ground-truth spec targets. The legacy C 51-problem set is retained for historical reproducibility, while the current C track uses 100 ACSL/Frama-C problems. See [Multi-language Benchmark Plan](docs/multilanguage_benchmark_plan.md).

Current Python/Nagini requirement dataset:

```text
benchmarks/python-nagini-problems/requirements/requirements_100.json
```

Current Python/Nagini manual ground-truth spec targets:

```text
benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json
```

## Docker Setup

Build the container:

```bash
docker build --platform linux/amd64 -t autospec-benchmark:dev .
```

Run it with the repository mounted at `/workspace`:

```bash
docker run -dit --name autospec-benchmark \
  --platform linux/amd64 \
  -v "$(pwd)":/workspace \
  autospec-benchmark:dev

docker exec -it autospec-benchmark /bin/bash
```

Inside the container, most commands assume:

```bash
cd /workspace
export PYTHONPATH=/workspace
```

## Run Requirement -> Spec -> Code

The current runnable generation pipeline is the C/ACSL backend. It uses an OpenAI-compatible endpoint, and the helper script is configured for OpenRouter by default.

```bash
export OPENROUTER_API_KEY=sk-or-xxxx

MODEL=deepseek/deepseek-v3.2 \
OUTPUT_DIR=outputs/req2code-enhanced-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

Useful environment overrides:

```bash
REQUIREMENTS_FILE=benchmarks/frama-c-problems/requirements/requirements_100.json
OUTPUT_DIR=outputs/req2code-enhanced-0520
TASK_ID=1                         # optional: run one problem
PIPELINE_VARIANT=enhanced         # base or enhanced
ENABLE_CONSTRAINT_EXTRACTION=true
SPEC_SELF_CHECK_ROUNDS=1
ENABLE_CODE_REPAIR=true
CODE_REPAIR_STRATEGY=simple        # simple or wybecoder
WYBECODER_CANDIDATES=3             # only used by wybecoder repair
CODE_REPAIR_MAX_ITER=3
REUSE_ARTIFACTS_FROM=outputs/req2code-ce-only-0520  # optional for strict incremental repair ablations
SKIP_VERIFY=false
VERIFY_TIMEOUT=120
```

For strict ablation, do not independently rerun repair variants. Run `base`, run
`base+ce`, then run repair variants by reusing frozen artifacts:

```bash
# base+repair: reuse base specs/code, only verify and repair
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
REUSE_ARTIFACTS_FROM=outputs/req2code-base-0520 \
OUTPUT_DIR=outputs/req2code-base-repair-0520 \
./scripts/run_openrouter_requirement_pipeline.sh

# base+ce+repair: reuse base+ce specs/code, only verify and repair
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
REUSE_ARTIFACTS_FROM=outputs/req2code-ce-only-0520 \
OUTPUT_DIR=outputs/req2code-ce-repair-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

This keeps requirement coverage identical between `base` and `base+repair`, and
between `base+ce` and `base+ce+repair`; repair is measured only as a verification
improvement on the same generated spec and initial code.

The C backend also supports an experimental WybeCoder-style repair strategy:
`CODE_REPAIR_STRATEGY=wybecoder`. It keeps the same strict artifact reuse rule,
but replaces the one-shot repair prompt with verifier-failure planning plus
multiple focused repair candidates. See
`docs/wybecoder_repair_migration_plan.md`.

The pipeline writes:

```text
<OUTPUT_DIR>/specs/...             # generated ACSL spec artifacts
<OUTPUT_DIR>/code/...              # generated C code with ACSL
<OUTPUT_DIR>/reports/results.json  # Frama-C verification results
```

Future Java output should follow the same high-level shape, with JML spec artifacts, Java source files, and OpenJML verification reports.

### Java / JML / OpenJML

In the Java/OpenJML container, run the Java backend with:

```bash
export OPENROUTER_API_KEY=sk-or-xxxx

MODEL=deepseek/deepseek-v3.2 \
OUTPUT_DIR=outputs/java-req2code-openrouter \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Useful Java environment overrides:

```bash
REQUIREMENTS_FILE=benchmarks/java-problems/requirements/requirements_100.json
SIGNATURE_FILE=benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json
OUTPUT_DIR=outputs/java-req2code-openrouter
TASK_ID=1
ENABLE_CODE_REPAIR=true
ENABLE_CONSTRAINT_EXTRACTION=true
SPEC_SELF_CHECK_ROUNDS=1
CODE_REPAIR_MAX_ITER=3
CODE_REPAIR_STRATEGY=simple        # simple or wybecoder
WYBECODER_CANDIDATES=3             # only used by wybecoder repair
REUSE_ARTIFACTS_FROM=outputs/java-req2code-base-0520  # optional strict incremental repair ablations
SKIP_VERIFY=false
OPENJML_BIN=openjml
OPENJML_SOLVER=/usr/bin/z3
VERIFY_TIMEOUT=120
```

The Java pipeline writes:

```text
<OUTPUT_DIR>/specs/...             # generated JML spec artifacts
<OUTPUT_DIR>/code/...              # generated Java source files
<OUTPUT_DIR>/reports/results.json  # OpenJML verification results
```

For Java, the JML block in `specs/*.json` is the canonical method contract. The
pipeline rewrites generated and repaired Java source files so that this
canonical `jml_block` appears directly above the target method before OpenJML is
run. Code repair may change method bodies, helper code, and loop annotations,
but it is not allowed to weaken or replace the generated method contract.

Java requirement entries may also include `type_context` for helper types such
as `Box`, `Counter`, and `Range`. This fixes the available fields and class
invariants for both base and independently generated CE runs; it does not expose
the target method's ground-truth JML contract.

Java also supports the same strict incremental repair pattern as C: run `base`
or `base+ce` first, then set `REUSE_ARTIFACTS_FROM` for `base+repair`,
`base+wybecoder`, or `base+ce+wybecoder` so the repair run reuses frozen
`specs/` and `code/` artifacts instead of regenerating them.

## Offline Benchmark Evaluation

For the current C/ACSL backend, after generation, run the deterministic spec coverage evaluator:

```bash
OUTPUT_DIR=outputs/req2code-enhanced-0520 \
./scripts/run_constraint_entailment_evaluation.sh
```

Then build the final problem-level benchmark summary:

```bash
OUTPUT_DIR=outputs/req2code-enhanced-0520 \
./scripts/run_req2code_benchmark_summary.sh
```

Reports:

```text
<OUTPUT_DIR>/reports/constraint_entailment.json
<OUTPUT_DIR>/reports/benchmark_summary.json
```

You can also call the evaluator directly:

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --ground-truth-spec-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-enhanced-0520
```

For Java/JML:

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_java_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

The Java coverage evaluator counts missing generated specs as `0/n` against the
Java ground-truth clauses, so failed generation does not shrink the denominator.
The Java benchmark summary also checks that the source-level JML clauses match
the canonical spec artifact; mismatches are counted in `contract_mismatch_count`
and are not treated as valid code.

### Rust / Verus

In the Rust/Verus container, run the Rust backend with:

```bash
export OPENROUTER_API_KEY=sk-or-xxxx

MODEL=deepseek/deepseek-v3.2 \
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Useful Rust environment overrides:

```bash
REQUIREMENTS_FILE=benchmarks/rust-verus-problems/requirements/requirements_100.json
SIGNATURE_FILE=benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json
OUTPUT_DIR=outputs/rust-req2code-openrouter
TASK_ID=1
PIPELINE_VARIANT=base|enhanced
ENHANCEMENT_METHOD=ce|repair|both
ENABLE_CODE_REPAIR=true
ENABLE_CONSTRAINT_EXTRACTION=true
SPEC_SELF_CHECK_ROUNDS=1
CODE_REPAIR_MAX_ITER=3
CODE_REPAIR_STRATEGY=simple        # simple or wybecoder
WYBECODER_CANDIDATES=3             # only used by wybecoder repair
REUSE_ARTIFACTS_FROM=outputs/rust-req2code-base  # optional strict incremental repair ablations
SKIP_VERIFY=false
VERUS_BIN=verus
VERIFY_TIMEOUT=120
```

For a base Rust run, use `PIPELINE_VARIANT=base`. For ablation, use
`PIPELINE_VARIANT=enhanced` with `ENHANCEMENT_METHOD=ce`, `repair`, or `both`.
If `ENHANCEMENT_METHOD` is unset, the explicit `ENABLE_CONSTRAINT_EXTRACTION`
and `ENABLE_CODE_REPAIR` flags are used.

Rust supports the same strict incremental repair pattern as C and Java: run
`base` or `base+ce` first, then set `REUSE_ARTIFACTS_FROM` for `base+repair`,
`base+wybecoder`, or `base+ce+wybecoder` so repair reuses frozen `specs/` and
`code/` artifacts instead of regenerating them.

The Rust pipeline writes:

```text
<OUTPUT_DIR>/specs/...             # generated Verus spec artifacts
<OUTPUT_DIR>/code/...              # generated Rust/Verus source files
<OUTPUT_DIR>/reports/results.json  # Verus verification results
```

For Rust, Verus contracts are part of function signatures rather than separate
comment blocks. The canonical spec artifact therefore stores structured
`verus_clauses` for requirement coverage evaluation. The Rust pipeline also
normalizes generated specs before code generation: missing signature semicolons
are repaired, unnamed returns such as `-> u64` are rewritten to named Verus
returns such as `-> (r: u64)`, `result` clauses are mapped to the canonical
return name, and unsupported C/Viper-style predicates such as `null`,
`pointer_valid`, `wf`, `well_formed`, `fully_owned`, `independent_of`, and
`panics` are removed from generated Rust clauses.

For Rust/Verus coverage evaluation:

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Rust generation and repair lock the target function header to the canonical
`verus_clauses` before verification. The summary also compares the canonical
spec artifact with the contract actually present in the verified Rust source;
any semantic contract drift makes code validity fail.

Rust also has an isolated code-only oracle-contract track. It skips Verus spec
generation and freezes the audited reference function header while leaving all
implementation-level proof annotations for the model to synthesize:

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
ENABLE_CODE_REPAIR=false \
./scripts/run_openrouter_rust_code_only_pipeline.sh

OUTPUT_DIR=outputs/rust-code-only-wybecoder \
REUSE_ARTIFACTS_FROM=outputs/rust-code-only-base \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
./scripts/run_openrouter_rust_code_only_pipeline.sh
```

Validate both frozen spec artifacts and source-level target contracts with:

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
./scripts/run_rust_code_only_oracle_evaluation.sh
```

To correct and re-evaluate older Rust artifacts without overwriting them:

```bash
PYTHONPATH=. python3 scripts/migrate_rust_outputs_v2.py \
  outputs/rust-base-kimi-0702 outputs/rust-ce-kimi-0702
```

The command creates sibling `*-offline-v2` directories, recovers canonical
clauses from stored raw model output, applies parameter-aware return aliases,
normalizes Rust pre/post-state syntax, locks the source contract, reruns Verus,
and rebuilds coverage and benchmark summaries. Use `--overwrite` only to replace
an already-created migrated copy; source outputs are never modified.

Rust coverage evaluation also recognizes semantics-preserving contract forms:
boolean/typed-enum surface variants, equivalent bounded-arithmetic guards,
guarded clauses split across several `ensures`, `if/else` contracts, and
`Seq.update`/`push`/`subrange` effects expressed as length plus pointwise frame
facts. Sequence matches require all relevant length, changed-element, and
unchanged-region facts; partial frames are not counted as full sequence effects.

### Python / Nagini

In the Python/Nagini container, run the Python backend with:

```bash
export OPENROUTER_API_KEY=sk-or-xxxx

MODEL=deepseek/deepseek-v3.2 \
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Useful Python/Nagini environment overrides:

```bash
REQUIREMENTS_FILE=benchmarks/python-nagini-problems/requirements/requirements_100.json
SIGNATURE_FILE=benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter
TASK_ID=1
PIPELINE_VARIANT=base|enhanced
ENHANCEMENT_METHOD=ce|repair|both
ENABLE_CODE_REPAIR=true
ENABLE_CONSTRAINT_EXTRACTION=true
SPEC_SELF_CHECK_ROUNDS=1
CODE_REPAIR_MAX_ITER=3
CODE_REPAIR_STRATEGY=simple        # simple or wybecoder
WYBECODER_CANDIDATES=3             # only used by wybecoder repair
REUSE_ARTIFACTS_FROM=outputs/python-nagini-req2code-base  # optional strict incremental repair ablations
SKIP_VERIFY=false
NAGINI_BIN=nagini
VERIFY_TIMEOUT=120
```

For a base Python run, use `PIPELINE_VARIANT=base`. For ablation, use
`PIPELINE_VARIANT=enhanced` with `ENHANCEMENT_METHOD=ce`, `repair`, or `both`.
If `ENHANCEMENT_METHOD` is unset, the explicit `ENABLE_CONSTRAINT_EXTRACTION`
and `ENABLE_CODE_REPAIR` flags are used.

Python also supports the same strict incremental repair pattern as C, Java, and
Rust: run `base` or `base+ce` first, then set `REUSE_ARTIFACTS_FROM` for
`base+repair`, `base+wybecoder`, or `base+ce+wybecoder` so repair reuses frozen
`specs/` and `code/` artifacts instead of regenerating them.

The Python pipeline writes:

```text
<OUTPUT_DIR>/specs/...             # generated Nagini spec artifacts
<OUTPUT_DIR>/code/...              # generated Python source files
<OUTPUT_DIR>/reports/results.json  # Nagini verification results
```

For Python, the canonical spec artifact stores both `nagini_contract` text and
structured `nagini_clauses`. The generated and repaired Python source is
rewritten so that the canonical `Requires(...)`/`Ensures(...)` statements appear
as the first statements in the target function body before Nagini is run. Code
repair may change function bodies and loop invariants, but it is not allowed to
weaken or replace the generated function contract.

The Python/Nagini dataset contains 100 Python-specific problems covering typed
contracts, `Optional`/`None` compatibility, list and dictionary
permissions/mutation, pure scalar APIs, and simple exception-freedom
preconditions.

Reference implementations can be checked with:

```bash
./scripts/run_nagini_python_problems.sh
```

For Python/Nagini coverage evaluation:

```bash
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_python_nagini_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Current reference status in this container:

```text
100 pass / 100 total
```

The curated requirement and ground-truth files follow the same dataset shape as
the Java and Rust tracks.

## Metrics

The final summary reports language-backend-specific metrics:

- `code_validity_rate`: fraction of generated files that pass the selected verifier against their generated specs
- `requirement_coverage_micro`: matched manual ground-truth spec targets over all targets
- `requirement_coverage_macro`: average per-problem requirement coverage
- `joint_success_rate`: fraction of problems where code is valid and requirement coverage is complete

The entailment report also includes:

- `ground_truth_spec_micro_coverage`
- `pre_admissibility`
- `pre_overconstraint`
- `post_frame_coverage`

For `requires` clauses, the evaluator checks that the manual ground truth entails the generated precondition. This penalizes over-constraining generated specs. For `ensures` and `assigns`, it checks that generated clauses entail the manual ground-truth target.

## Current C Reference Run

For `outputs/req2code-enhanced-0520`, the current evaluation gives:

```text
code_valid_count = 26 / 51
requirement_coverage = 94 / 165
joint_success_count = 13 / 51
```

The joint-success problem ids are:

```text
1, 21, 24, 27, 28, 32, 37, 38, 41, 43, 48, 49, 51
```

## Ground-Truth File Maintenance

Validate and normalize the current C/ACSL curated ground-truth spec file:

```bash
python3 scripts/generate_ground_truth_specs.py
```

This script does not regenerate targets from reference C files. It checks that `requirements_100_ground_truth_specs.json` is well formed and keeps formatting stable.

## Manual Verification

### C / Frama-C

Verify a generated or reference C file directly:

```bash
python3 -m autospec.cli.main verify outputs/req2code-enhanced-0520/code/pointers/swap.c --timeout 120 --verbose
```

Verify the original reference benchmark files:

```bash
./scripts/run_frama_c_problems.sh -d benchmarks/frama-c-problems/ground-truth
```

If `frama-c` is not visible in the shell, initialize the opam environment:

```bash
eval $(opam env)
```

### Java / OpenJML

Java support is being added as the first multi-language extension. The recommended backend is JML with OpenJML. In a Java/OpenJML container, a generated Java file should be checked with an OpenJML ESC command such as:

```bash
openjml --esc Solution.java
```

On linux/arm64 containers, OpenJML may warn that ESC is not fully functional. In that environment, prefer an amd64 OpenJML container for official benchmark runs, or force a known system solver if the local environment provides one:

```bash
openjml --esc --exec /usr/bin/z3 Solution.java
```

### Python / Nagini

Verify a Python/Nagini reference file directly:

```bash
nagini benchmarks/python-nagini-problems/ground-truth/scalar_arithmetic/Problem001_MaxInt.py
```

Verify all Python/Nagini reference files:

```bash
./scripts/run_nagini_python_problems.sh
```

## Documentation

More detailed design notes:

- [Requirement Pipeline](docs/requirement_to_code_pipeline.md)
- [Manual Ground-Truth Spec Entailment](docs/constraint_entailment_benchmark.md)
- [Multi-language Benchmark Plan](docs/multilanguage_benchmark_plan.md)
