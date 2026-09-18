# rust-verus-problems

Rust/Verus requirement-to-code benchmark dataset.

This is the first Rust-specific extension of the C/ACSL and Java/JML benchmark
tracks. It follows:

```text
Requirement -> Verus Spec -> Rust Code -> Verus -> Spec Coverage
```

The set is intentionally Rust-oriented rather than a direct port of the C
problems. It prioritizes safe Rust functional correctness, ownership and
borrowing, vector and slice bounds, panic freedom, `Option`, `Result`, and
unique-borrow mutation.

## Problem Set

This dataset contains 100 problems. Every reference implementation in
`ground-truth/` is expected to pass `verus` in the Rust/Verus container.

Category distribution:

- `scalar_arithmetic`: 10
- `option_result`: 10
- `vec_immutable`: 12
- `vec_mutation`: 12
- `ownership_slices`: 6
- `scalar_arithmetic_ext`: 10
- `option_result_ext`: 10
- `vec_immutable_ext`: 10
- `vec_mutation_ext`: 10
- `ownership_slices_ext`: 10

## Layout

- `requirements/requirements_100.json`: natural-language requirements.
- `requirements/requirements_100_ground_truth_specs.json`: curated Verus ground-truth targets.
- `requirements/requirements_100_code_only_contracts.json`: frozen code-only oracle contracts.
- `ground-truth/**/*.rs`: reference Rust implementations annotated with Verus specifications.

## Verify Reference Implementations

Use the local Verus installation:

```bash
./scripts/run_verus_rust_problems.sh
```

Current reference status in this container:

```text
100 pass / 100 total
```

## Run Requirement Pipeline

Use the Rust/OpenRouter wrapper:

```bash
MODEL=deepseek/deepseek-v3.2 \
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

The Rust runner supports the same base/enhanced ablation shape as the C and
Java tracks:

```bash
# Direct: requirement -> Verus spec -> Rust code -> Verus, no CGS or repair.
PIPELINE_VARIANT=base \
OUTPUT_DIR=outputs/rust-req2code-base \
./scripts/run_openrouter_rust_requirement_pipeline.sh

# CGS: constraint-guided specification/spec self-check only.
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=cgs \
OUTPUT_DIR=outputs/rust-req2code-cgs-only \
./scripts/run_openrouter_rust_requirement_pipeline.sh

# VGCR: verifier-guided candidate repair only.
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=vgcr \
OUTPUT_DIR=outputs/rust-req2code-repair-only \
./scripts/run_openrouter_rust_requirement_pipeline.sh

# CodeNova: CGS + VGCR.
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=both \
OUTPUT_DIR=outputs/rust-req2code-codenova \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Generated Rust specs are canonicalized before code generation and evaluation:
the runner repairs missing signature semicolons, rewrites unnamed returns to
named Verus returns, maps `result` to the canonical return name, filters
unsupported non-Verus predicates such as `null`, `pointer_valid`, `wf`,
`well_formed`, `fully_owned`, `independent_of`, and `panics`, and falls back to
the pre-refinement spec when self-check/refine does not converge.

Then evaluate generated Verus specs against manual ground-truth clauses:

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

## Run Code-Only Oracle-Contract Evaluation

The code-only track skips spec generation and provides only the requirement,
canonical named signature, and frozen function-level `requires`/`ensures` clauses.
Reference loop invariants, decreases clauses, assertions, proof code, and function
bodies are excluded.

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
ENABLE_CODE_REPAIR=false \
./scripts/run_openrouter_rust_code_only_pipeline.sh
```

Simple and VGCR repair runs must reuse the same initial artifacts:

```bash
OUTPUT_DIR=outputs/rust-code-only-vgcr \
REUSE_ARTIFACTS_FROM=outputs/rust-code-only-base \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
./scripts/run_openrouter_rust_code_only_pipeline.sh
```

Check that both the spec artifacts and final Rust sources preserve the oracle:

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
./scripts/run_rust_code_only_oracle_evaluation.sh
```
