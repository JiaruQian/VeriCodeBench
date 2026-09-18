# Constraint Entailment Framework (CEF) Benchmark: Requirement->Spec->Code Design (Manual Ground-Truth Spec Entailment)

This document records the current unified evaluation method for the `requirement -> specification -> code -> verify` benchmark, focusing on:

- Whether `code` conforms to the generated `spec` (verified by Frama-C/WP)
- Whether the generated `spec` covers the manually constructed ground-truth `spec`

---

## 1. Core Idea

All 100 problems use the same manual ground-truth spec file as the coverage target:

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

The ACSL clauses in this file come from manually constructed specifications: some clauses can be
extracted directly from the requirement semantics, while others reference the ground-truth ACSL of
the original Frama-C dataset. Both are treated as the same kind of manual ground truth in the
benchmark.

During evaluation:

- The generated ACSL block is extracted as a clause set `S`
- The manual ground-truth ACSL is extracted as the target clause set `G`
- For each `g_i in G`, the entailment direction is determined by clause type
  - `requires`: check `g_i ⊨ generated_requires`
  - `ensures/assigns`: check `generated_clause(s) ⊨ g_i`

Intuitive meaning:

- For preconditions, the generated spec must not be stronger than the manual ground truth, otherwise it over-constrains the input
- For postconditions and frames, the generated spec must be strong enough to entail the behavior required by the manual ground truth

---

## 2. Data Construction

### 2.1 Manual Ground Truth Spec

Main file:

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

Each sample contains:

- `id`, `path`
- `ground_truth_file`
- `ground_truth_source`
- `function_signature`
- `ground_truth_clauses[]`
  - `type`: `requires` / `ensures` / `assigns`
  - `expr`: ACSL clause expression
- `ground_truth_contract`

Validation script:

```bash
python3 scripts/generate_ground_truth_specs.py
```

This script only validates and formats the maintained manual ground-truth file; it does not
re-extract all ACSL contracts from the reference C files, otherwise verification-helper conditions
would be mistakenly added to the evaluation targets.

## 3. Evaluation Pipeline

Script:

- `scripts/evaluate_constraint_entailment.py`

Inputs:

- `--ground-truth-spec-file`
- `OUTPUT_DIR/specs/*.json`

Outputs:

- `OUTPUT_DIR/reports/cef.json`

### 3.1 Clause Extraction

Uniformly extract from the generated spec and the manual ground truth:

- `requires ...;`
- `ensures ...;`
- `assigns ...;`

### 3.2 Entailment Decision

For each ground-truth clause:

1. Select candidate generated clauses by `requires/ensures/assigns`
2. Perform exact match and top-level conjunctive clause matching
3. Search generated clause combinations, capped by `--max-combo-size`
4. If `z3-solver` is installed, attempt SMT entailment decision

Before evaluation, parameter positions are canonicalized based on the function signature, e.g., both
`x,y` and `a,b` are mapped to `arg0,arg1`, reducing false judgments caused by variable naming
differences.

### 3.3 Metrics

Primary metrics:

- `ground_truth_spec_micro_coverage`
- `macro_avg_requirement_coverage`
- `requirement_coverage_x / requirement_coverage_n` per problem

Auxiliary metrics:

- `pre_admissibility`
- `pre_overconstraint`
- `post_frame_coverage`

The final summary still uses:

- code validity rate
- requirement coverage micro/macro
- joint success: code valid and manual ground-truth spec coverage full

---

## 4. One-Click Run

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_req2code_benchmark_summary.sh
```

Corresponding commands for Java/JML/OpenJML:

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_java_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Corresponding commands for Rust/Verus:

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

You can also invoke it directly:

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --ground-truth-spec-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-cgs-0624
```

Direct invocation for Java/JML:

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --language java \
  --ground-truth-spec-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-req2code-cgs-only-0602-tem0
```

Direct invocation for Rust/Verus:

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --language rust \
  --ground-truth-spec-file benchmarks/rust-verus-problems/requirements/requirements_50_ground_truth_specs.json \
  --output-dir outputs/rust-req2code-both-0608-tem0
```

The coverage denominator for all languages is fixed by the manual ground truth:

- A missing or unparsable generated spec is counted into the denominator according to that problem's
  number of ground-truth clauses and recorded as `0/n`. This way, an LLM request failure or a
  generation failure does not shrink the coverage denominator.
- C/ACSL, Java/JML, and Rust/Verus all use this rule, ensuring the requirement coverage denominator
  is consistent across ablations.

The Java/JML evaluation has an additional constraint:

- `benchmark_summary.json` checks whether the JML clauses in the Java source match the canonical
  `jml_block` in `specs/*.json`. A mismatch means the contract verified by OpenJML and the contract
  used for requirement coverage evaluation are not the same contract, and that problem's code
  validity is counted as a failure.

Java/JML expressions also undergo conservative surface normalization before CEF:

- Expand top-level conjunctions such as `requires P && Q` into atomic candidates while retaining the original compound clause;
- Strip the leading `@` from multi-line JML, and normalize Java widening casts, character constants, string `length()`,
  boolean return values, and object-field notation;
- Treat a getter read and the corresponding field read as the same expression only when the generated `helper_declarations` explicitly provides `getX(){ return x; }`;
- Alpha-rename quantifier-bound variables and normalize the order of the two sides of `==`/`!=`.

These rules do not treat `a[*]` as an exact `a[i], a[j]` frame, nor treat `Range.min/max` as
`Range.low/high`; genuine frame widening or interface field drift is still penalized.

The Rust/Verus evaluation reuses the same CEF, but the generated spec is read from the canonical
`verus_clauses` in `specs/*.json`; only if an old artifact lacks that field does it fall back to
parsing `verus_contract`. The Rust signature uses a Rust-only parser that supports commas within
parameter types such as `Result<u64, ()>`, and maps `r`, `result`, and a named return uniformly to
the same return-value alias, avoiding coverage misjudgments caused by return-value naming
differences.

Python/Nagini expressions undergo language-specific normalization before SMT decision:

- Preserve the boolean type of `bool` parameters and `bool` return values from the function signature, avoiding incorrectly modeling them as integers;
- Convert `len(...)`, `Old(...)`, list/dict indexing, membership tests, and `is`/`is not` into stable solver expressions;
- Recursively support equivalence decisions among `Implies(p, q)`, `p ==> q`, and ordinary boolean disjunctions, including composite expressions formed by conjoining multiple clauses;
- Support re-conjoining atomic `Requires` split into multiple entries and comparing them against the ground truth's compound precondition.

These rules only eliminate false negatives caused by surface syntax and do not equate post-state
container reads with `Old(...)`; if the generated spec omits pre-state semantics, it is still scored
as a genuine coverage miss. This version is marked in reports as
`manual_ground_truth_spec_entailment_v3`.
