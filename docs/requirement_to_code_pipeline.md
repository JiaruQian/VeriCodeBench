# Requirement -> Spec -> Code -> Verify Pipeline (with Incremental Enhancements)

This document describes the new flow after the CodeNova refactor and provides variants that can be used directly for ablations:

- `base`: minimal runnable baseline (single round)
- `enhanced`: adds lightweight enhancement modules on top of `base`; the Constraint-Guided Specification (CGS) and code repair modules can be toggled independently

The goal is to keep experiments reproducible and comparisons clear, rather than overhauling the existing pipeline all at once.

## 1. Task Definition

We define the end-to-end task as:

`Requirement -> Spec -> Code -> Verify`

Input:

- natural-language requirement `r`

Output:

- formal specification `s` (ACSL)
- program `c` (C)

The optimization objective is dual:

1. `c |= s` (formal verification passes)
2. `s ~= r` (the specification is semantically aligned with the requirement)

> Key point: we pursue not only verify pass, but also improved requirement-spec coverage and alignment quality.

## 2. Base Pipeline (Ablation-0)

The current baseline flow:

`r --(LLM)--> s --(LLM)--> c --(Frama-C/WP)--> verify`

Characteristics:

- no structured constraint extraction (CGS)
- no requirement-spec alignment check
- no code-repair loop after verification failure

This line is kept unchanged as a stable control group.

## 3. Enhanced Pipeline (incremental enhancement, does not replace Direct)

The enhanced version adds optional lightweight modules on top of Direct. By default, `enhanced` turns everything on to stay compatible with the old commands; for ablations each module can be disabled separately.

### 3.1 Requirement -> Constraint-Guided Specification (CGS)

First decompose the requirement into structured constraints:

`r -> {preconditions, postconditions, invariants}`

and optionally produce a `function_signature` candidate. The output is JSON so it can be evaluated and reused later.

Switches:

- CLI: `--enable-cgs` / `--disable-cgs`
- OpenRouter wrapper: `ENABLE_CGS=true|false`

When disabled, spec generation falls back to the Direct `requirement -> ACSL` prompt and no longer runs `Constraint -> ACSL Mapping` or `Spec Self-Check + Refine`.

### 3.2 Constraint -> ACSL Mapping

Map structured constraints to ACSL (`requires/assigns/ensures`).

Compared with producing ACSL directly from the requirement in one step, this two-stage approach is more robust:

- reduces hallucination
- improves constraint coverage
- makes later missing-constraint analysis easier

The output JSON may contain `code_annotation_hints`:

```json
{
  "function_signature": "int f(int *a, int n);",
  "acsl_block": "/*@ requires ...; assigns ...; ensures ...; */",
  "code_annotation_hints": {
    "loop_invariants": ["0 <= i <= n"],
    "loop_assigns": ["i, sum"],
    "loop_variants": ["n - i"]
  },
  "notes": "..."
}
```

`acsl_block` must contain only the function contract. `loop invariant`, `loop assigns`, and
`loop variant` are statement annotations inside the function body and must not be written into the
function contract. If the model mistakenly writes these loop annotations into `acsl_block`, the
pipeline moves them into `code_annotation_hints` and removes them from the contract.

### 3.3 Spec Self-Check + Refine (1-2 rounds)

Add a lightweight alignment check:

- input: `requirement + constraints + spec`
- output: `is_aligned / missing_constraints / inconsistent_items / refinement_hints`

If missing or inconsistent items are found, refinement is performed automatically (the number of rounds is configurable).

This forms:

`generate -> check -> refine`

### 3.4 Code Generation with Annotation Hints

Inputs to the code generation stage:

- `requirement`
- `function_signature`
- function contract `acsl_block`
- `code_annotation_hints`

The generated C file must keep `acsl_block` directly above the function definition. If loop hints
are used, they may only be inserted into the function body as statement annotations before the loop,
for example:

```c
/*@
  loop invariant 0 <= i <= n;
  loop assigns i, sum;
  loop variant n - i;
*/
while (i < n) {
  ...
}
```

This preserves the `req -> spec -> code` structure: the spec stage may propose loop-annotation
candidates needed for verification, but these candidates do not participate in the main
requirement-spec coverage evaluation and do not pollute the function contract.

The Java/JML/OpenJML backend additionally maintains a contract-preservation invariant:

- `jml_block` in `specs/*.json` is the canonical method contract.
- After code generation, the pipeline locates the target method by `function_signature` and
  programmatically inserts or replaces the canonical `jml_block` directly above the method
  definition.
- Java source verified by OpenJML must use this canonical contract; it must not use a weaker or
  different JML contract rewritten into the source by the model.
- This post-processing information is recorded in the `contract_enforcement` field of
  `reports/results.json`.

### 3.5 Verification-guided Code Repair (3-5 rounds)

`spec -> c0 -> verify`

If verification fails, the error information is fed back to the LLM to repair the code:

`c0 -> verify -> c1 -> verify -> ...`

A maximum iteration count is set by default to avoid infinite loops.

Switches:

- CLI: `--enable-code-repair` / `--disable-code-repair`
- CLI strategy: `--code-repair-strategy simple|vgcr`
- OpenRouter wrapper: `ENABLE_CODE_REPAIR=true|false`
- OpenRouter strategy: `CODE_REPAIR_STRATEGY=simple|vgcr`

When disabled, only the first Frama-C/WP verify round runs and no repair loop is entered. The same
effect can be achieved with `--code-repair-max-iter 0`.

The current default repair strategy is `simple`, i.e. feeding the verifier failure information
directly back to the LLM to generate the next version of the code.
The experimental `vgcr` strategy follows the Verifier-Guided Candidate Repair (VGCR)
prove-as-you-generate idea: it first summarizes the Frama-C/WP failure log into a structured
failure/subgoal plan, then generates multiple repair candidates with different focuses and verifies
them one by one.
It is still only allowed to modify the code body and statement-level annotations; it may not weaken
or replace the generated function contract.
See `docs/wybecoder_repair_migration_plan.md` for the detailed migration plan.

Java/JML/OpenJML repair likewise enforces preservation of the canonical `jml_block`. The model may
modify the Java method body, helper code, and loop annotations, but before repair output is written
to file the JML contract in the source is overwritten again with the method contract from
`specs/*.json`. Therefore `code_validity_rate` means "the code passes OpenJML under the generated
spec", not "the code passes OpenJML under the possibly weakened source contract after repair".

The Rust/Verus backend additionally performs Rust-only canonicalization:

- If a generated Rust function signature is missing its trailing semicolon, the pipeline adds it
  automatically.
- If the return value is in unnamed form (for example `-> u64;`), the pipeline rewrites it to the
  Verus-friendly named return `-> (r: u64);` and normalizes `result` in the generated clauses to
  `r`.
- The pipeline filters out C/Viper-style spec fragments that the current Rust/Verus problem set
  does not support, such as `null`, `pointer_valid`, `valid`, `wf`, `well_formed`, `fully_owned`,
  `independent_of`, `allocated`, and `panics`.
- If self-check/refine does not obtain an aligned spec within the configured number of rounds, the
  pipeline no longer blindly uses the last refinement; instead it falls back to the spec from
  before refinement. The fallback information is recorded in `alignment_check`.

The Python/Nagini backend additionally maintains a contract-preservation invariant:

- `nagini_contract` and the structured `nagini_clauses` in `specs/*.json` are the canonical
  function contract.
- After code generation, the pipeline locates the target function by `function_signature` and
  inserts or replaces the canonical `Requires(...)`/`Ensures(...)` statements as the first
  statements of the function body.
- Python source verified by Nagini must use this canonical contract; it must not use a weaker or
  different Nagini contract rewritten into the source by the model.
- The repair stage may modify the function body and loop `Invariant(...)`, but before writing back
  to file it again forcibly restores the canonical function contract. This post-processing
  information is recorded in the `contract_enforcement` field of `reports/results.json`.

### 3.6 Requirement-Spec Evaluation

To avoid the problem that `spec` and `code` can verify each other while both drift away from
`requirement`, the current main evaluation uses the **Constraint Entailment Framework (CEF)**; see
`docs/constraint_entailment_benchmark.md`.

CEF uses a unified manual ground-truth spec file and ACSL clause extraction, and checks the
entailment direction by clause type:

- `requires`: check whether the manual ground-truth `requires` entails the generated `requires`
- `ensures/assigns`: check whether the generated `ensures/assigns` entails the manual ground-truth
  clauses

Java/JML evaluation uses the same entailment framework, but clause extraction supports `assignable`,
`signals`, and `signals_only`, and tasks with a missing spec are counted as `0/n` in the
ground-truth coverage denominator. The Java summary also checks whether the JML clauses in the
source are consistent with the canonical `jml_block` in `specs/*.json`; on mismatch, the code
validity of that task is treated as failed and counted in `contract_mismatch_count`.

Rust/Verus evaluation likewise uses the same entailment framework, but Rust signatures use a
Rust-only parser, avoiding misidentifying the return type as a parameter; `r`, `result`, and named
returns are also canonicalized to the same return-value alias, reducing coverage false negatives
caused by purely naming differences.

Python/Nagini evaluation likewise uses the same entailment framework. The Python spec artifact
preferentially reads the structured `nagini_clauses`; if absent, it falls back to parsing
`Requires(...)` and `Ensures(...)` from `nagini_contract`. Python signatures use a Python-only
parser, avoiding misidentifying a type annotation such as `int` in `x: int` as a parameter name;
`Result()`/`result` are canonicalized to the same return-value alias. Tasks with a missing spec are
counted as `0/n` in the Python ground-truth coverage denominator.

Main ground-truth file:

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

Output files:

- `reports/cef.json`
- `reports/benchmark_summary.json`

`benchmark_summary.json` aggregates three main metrics:

- code valid count / validity rate
- requirement coverage micro/macro
- joint success: code valid and requirement coverage full

The old LLM-as-a-judge spec evaluation can still serve as an auxiliary debugging entry point, but it
is not a main metric of the current benchmark.

## 4. Implementation Locations

- `autospec/pipeline/requirement_pipeline.py`
  - `RequirementToCodePipeline`: base (keeps the original logic)
  - `EnhancedRequirementToCodePipeline`: enhanced (newly added)
- `autospec/pipeline/java_requirement_pipeline.py`
  - Java/JML/OpenJML backend
- `autospec/pipeline/rust_requirement_pipeline.py`
  - Rust/Verus backend
- `autospec/pipeline/python_nagini_requirement_pipeline.py`
  - Python/Nagini backend
- `autospec/verifier/openjml.py`
  - OpenJML verifier adapter
- `autospec/verifier/verus.py`
  - Verus verifier adapter
- `autospec/verifier/nagini.py`
  - Nagini verifier adapter
- `scripts/run_requirement_pipeline.py`
  - adds `--pipeline-variant` and enhancement parameters
- `scripts/run_openrouter_requirement_pipeline.sh`
  - adds environment variables controlling the enhanced parameters
- `scripts/run_python_nagini_requirement_pipeline.py`
  - Python/Nagini LLM generation CLI
- `autospec/pipeline/python_code_only_pipeline.py`
  - Python/Nagini frozen oracle-contract code-only pipeline
- `scripts/run_python_code_only_pipeline.py`
  - Python/Nagini code-only generation and repair CLI
- `scripts/run_openrouter_python_code_only_pipeline.sh`
  - Python/Nagini code-only OpenRouter wrapper
- `scripts/evaluate_python_code_only_oracle.py`
  - Python/Nagini oracle contract consistency checker
- `scripts/run_openrouter_python_nagini_requirement_pipeline.sh`
  - Python/Nagini OpenRouter wrapper
- `scripts/run_python_nagini_constraint_entailment_evaluation.sh`
  - Python/Nagini requirement coverage evaluator wrapper
- `scripts/evaluate_constraint_entailment.py`
  - performs manual ground-truth spec coverage evaluation on existing `specs/*.json`
- `scripts/summarize_req2code_benchmark.py`
  - aggregates code verification, requirement coverage, and joint success

## 5. Data Format

Example requirement data (array):

```json
[
  {
    "id": 1,
    "path": "pointers/swap.c",
    "requirement_en": "Given pointers to two integers, swap their stored values in place."
  }
]
```

Text field read priority:

1. `requirement_zh`
2. `requirement_en`
3. `requirement`

## 6. Output Directory

When `--output-dir outputs/req2code` is used:

- `outputs/req2code/specs/<relative_path>.json`
- `outputs/req2code/code/<relative_path>.c`
- `outputs/req2code/reports/results.partial.json`
- `outputs/req2code/reports/results.json`
- `outputs/req2code/reports/<relative_path>.verify.log`

Additional enhanced information is written to `specs/*.json` and `results.json`, including:

- `enhanced_modules`
- `constraints`
- `alignment_check`
- `code_annotation_hints`
- `moved_loop_annotations`
- `spec_evaluation` (optional old LLM judge debugging information)
- `repair_attempts` / `repair_history`
- intermediate failure logs (`*.repairN.verify.log`)

## 7. How to Run

Strict ablations use artifact chaining rather than rerunning the four groups independently:

```text
Direct
  -> VGCR        # reuse specs/ and code/ from Direct, run only verify/repair
CGS
  -> CodeNova    # reuse specs/ and code/ from CGS, run only verify/repair
```

This way, Direct and VGCR have exactly the same requirement coverage, and CGS and CodeNova also have
exactly the same requirement coverage. Code repair only measures how much verification/joint-success
improvement verification-guided repair can bring on the same generated spec and initial code.

It is recommended that all long-running jobs that call `scripts/run_*_requirement_pipeline.py`
directly pass the following explicitly:

- `--request-timeout 120`: upper bound on a single LLM/API generation request, used to ensure fair
  comparison.
- `--llm-retries 3 --llm-retry-delay 15`: bounded retries only for transient failures such as
  connection interruptions, `IncompleteRead`, 429/5xx.
- `--resume`: from an existing `reports/results.partial.json` or `reports/results.json`, skip
  already-completed `status=ok` tasks; failed or half-finished tasks are regenerated.
- `--signature-file ..._ground_truth_specs.json`: read a fixed `function_signature`; for Java it
  also reads `type_context` that does not include the target method contract (fields and invariants
  of helper types), and does not send `ground_truth_contract` or `ground_truth_clauses` to the
  model. Without this interface context, an independently generated model may rename
  `Range.low/high` to `min/max`, or turn public fields into getters, causing representation drift
  unrelated to the requirement.

### 7.1 Run Direct (recommended first as the control)

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-base-dsv41-time-5-0915 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model deepseek/deepseek-v4.1-flash \
  --api-key-env OPENROUTER_API_KEY \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

The corresponding basic run for Java/JML/OpenJML:

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-base-kimi-0701 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --disable-cgs \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

The corresponding basic run for Rust/Verus:

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-base-rust-0707 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0 \
  --max-tokens 4096
```

The corresponding basic run for Python/Nagini:

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-base-kimi-0704 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

### 7.2 Run CGS (the second generation stage of the strict incremental chain)

In a strict ablation, CGS should only generate the spec/code with constraint extraction / spec
self-check enabled, and disable repair. The subsequent CodeNova must reuse the artifacts from here.

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-cgs-dsv41-time-5-0916 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model deepseek/deepseek-v4.1-flash  \
  --api-key-env OPENROUTER_API_KEY \
  --pipeline-variant enhanced \
  --enable-cgs \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

The corresponding CGS run for Java/JML/OpenJML:

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-cgs-kimi-0701 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --enable-cgs \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

The corresponding CGS run for Rust/Verus:

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-cgs-claude-0707 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus \
  --pipeline-variant enhanced \
  --enhancement-method cgs \
  --spec-self-check-rounds 1 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0 \
  --max-tokens 4096
```

The corresponding CGS run for Python/Nagini:

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-cgs-kimi-0704 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --enhancement-method cgs \
  --spec-self-check-rounds 1 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

### 7.3 C/ACSL Strict Incremental Repair and VGCR Repair

A strict repair ablation does not regenerate spec/code; instead it reuses frozen artifacts via
`--reuse-artifacts-from`.

VGCR: reuse the `specs/` and `code/` of Direct, and run only verification + simple repair.

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-base-repair-0520 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/req2code-base-0520 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

CodeNova: reuse the `specs/` and `code/` of CGS, and run only verification + simple repair.

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-cgs-repair-0520 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/req2code-cgs-only-0520 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

VGCR: reuse the `specs/` and `code/` of Direct, and run only verification + VGCR repair.

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-vgcr-dsv41-time-5-0916 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --model deepseek/deepseek-v4.1-flash \
  --max-tokens 4096 \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/C-base-dsv41-time-5-0915 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

CodeNova: reuse the `specs/` and `code/` of CGS, and run only verification + VGCR repair.

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-cgs-vgcr-dsv41-time-5-0916 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --model deepseek/deepseek-v4.1-flash \
  --max-tokens 4096 \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/C-cgs-dsv41-time-5-0916 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

`--reuse-artifacts-from` copies the source directory's `specs/` and `code/` into the current output
directory, then skips spec/code generation and runs only verification and optional repair. When used
for VGCR, the source should be the Direct output directory; when used for CodeNova, the source
should be the CGS output directory.

### 7.4 Java/JML/OpenJML Strict Incremental Repair Ablation

The Java/JML/OpenJML backend has now been adapted to the same strict incremental run rules as
C/ACSL: repair variants must reuse frozen `specs/` and `code/` via `--reuse-artifacts-from` or
`REUSE_ARTIFACTS_FROM`, skip spec/code regeneration, and run only OpenJML verification and optional
repair. Thus the four main Java paradigms can be organized as follows:

- Direct: disable constraint extraction and code repair.
- CGS: enable constraint extraction/self-check, disable code repair.
- VGCR: reuse the frozen Direct output, run only VGCR repair.
- CodeNova: reuse the frozen CGS output, run only VGCR repair.

Java VGCR (simple repair, reusing the Direct output):

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-base-repair-0624 \
  --reuse-artifacts-from outputs/java-base-0624 \
  --openjml-solver /usr/bin/z3 \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java VGCR (reusing the Direct output):

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-vgcr-kimi-0702 \
  --reuse-artifacts-from outputs/java-base-kimi-0701 \
  --openjml-solver /usr/bin/z3 \
  --disable-cgs \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java CGS (generate frozen CGS artifacts, no repair):

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-cgs-only-0624 \
  --openjml-solver /usr/bin/z3 \
  --enable-cgs \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java CodeNova (reusing the CGS output):

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-cgs-vgcr-kimi-0702 \
  --reuse-artifacts-from outputs/java-cgs-kimi-0701 \
  --openjml-solver /usr/bin/z3 \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

`--reuse-artifacts-from` copies the source directory's `specs/` and `code/` into the current Java
output directory, and forcibly restores the canonical `jml_block` from `specs/*.json` before
writing the source back. Repair may modify the method body, helper code, and loop annotations, but
must not weaken or replace the generated JML method contract.

Rust/Verus now also supports the same artifact chaining as C/Java. Strict VGCR and CodeNova variants
should set `--reuse-artifacts-from`, reusing only the frozen `specs/` and `code/` and running
verification + repair.

Rust/Verus VGCR (reusing the Direct output):

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-vgcr-claude-0709 \
  --reuse-artifacts-from outputs/rust-base-rust-0707 \
  --verus-bin verus \
  --model anthropic/claude-sonnet-5 \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Rust/Verus CodeNova (reusing the CGS output):

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-cgs-vgcr-claude-0709 \
  --reuse-artifacts-from outputs/rust-cgs-claude-0707 \
  --verus-bin verus \
  --model anthropic/claude-sonnet-5 \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

The Verus contract for Rust/Verus, unlike Java/JML, does not require writing back a separate comment
block; when reusing, the pipeline copies the frozen `specs/*.json` and `code/*.rs`, and uses
`verus_clauses` from the spec artifact as the frozen contract for the repair prompt.

The Rust pipeline forcibly writes back the canonical `verus_clauses` on the initial generation and
on each repair candidate, so repair can only modify the function body, helper proofs, and loop
annotations. The summary stage also compares the spec artifact with the contract in the actually
verified source; when contract drift is found, the code validity of that task is counted directly
as failed. Old Rust artifacts can be copied to `*-offline-v2` via
`scripts/migrate_rust_outputs_v2.py`, then subjected to raw-clause recovery, contract locking, Verus
re-verification, and coverage recomputation.

The Rust coverage evaluator further performs conservative matching for semantically equivalent
contract shapes: boolean and typed-enum surface forms, equivalent integer bounds, multiple `ensures`
split by the same guard, `if/else`, and `Seq.update`/`push`/`subrange` expressed via "length,
modified positions, unmodified intervals". Sequence rules match only when the length, point values,
and frame conditions are all present; a partial frame is not treated as a complete sequence effect.

The corresponding non-strict code repair ablation for Python/Nagini:

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-req2code-repair-only-0610 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --enhancement-method vgcr \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini strict VGCR (reuse the Direct output, run only verification + simple repair):

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-base-repair-0627 \
  --reuse-artifacts-from outputs/python-nagini-base-0627 \
  --nagini-bin nagini \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini strict VGCR (reuse the Direct output, run only verification + VGCR repair):

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-vgcr-kimi-ds-0706 \
  --reuse-artifacts-from outputs/python-base-kimi-0704 \
  --model deepseek/deepseek-v3.2 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Python/Nagini strict CodeNova (reuse the CGS output, run only verification + simple repair):

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-cgs-repair-0627 \
  --reuse-artifacts-from outputs/python-nagini-cgs-0627 \
  --nagini-bin nagini \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini strict CodeNova (reuse the CGS output, run only verification + VGCR repair):

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-cgs-vgcr-kimi-0706 \
  --reuse-artifacts-from outputs/python-cgs-kimi-0704 \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --disable-cgs \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

When Python/Nagini reuses frozen artifacts, it copies `specs/*.json` and `code/*.py`, and before
verification or repair it forcibly writes back the beginning of the function body according to the
canonical `nagini_contract` in the spec artifact, ensuring that repair cannot weaken or replace the
generated function contract.

### 7.5 Run a Single Task (most common for prompt debugging)

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-debug \
  --pipeline-variant enhanced \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

The corresponding Java/JML/OpenJML command:

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-req2code-debug \
  --openjml-solver /usr/bin/z3 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

The corresponding Rust/Verus command:

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-req2code-debug \
  --pipeline-variant enhanced \
  --enhancement-method both \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

The corresponding Python/Nagini command:

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-req2code-debug \
  --pipeline-variant enhanced \
  --enhancement-method both \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

### 7.6 C/ACSL Code-Only Oracle-Contract Evaluation

Code-only tasks fix a manually constructed and validated function contract, evaluating only the
model's ability to generate a C implementation and implementation-level proof annotations:

`Requirement + Signature + Oracle Contract -> Code + Proof Annotations -> Frama-C/WP`

It uses the separate entry point `scripts/run_c_code_only_pipeline.py` and does not run spec
generation, constraint extraction, or spec self-check. After each generation and repair, the
pipeline programmatically restores the canonical ACSL contract in
`requirements_100_code_only_contracts.json`; the model may only modify the function body, loop
annotations, and statement annotations.

Initial generation (no repair):

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-base-claude-0826 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

Simple repair must reuse the initial `specs/` and `code/` above:

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-simple-0825 \
  --reuse-artifacts-from outputs/c-code-only-base-0825 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

VGCR repair likewise reuses exactly the same initial artifacts:

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-vgcr-claude-0826 \
  --reuse-artifacts-from outputs/c-code-only-base-claude-0826 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

Equivalent OpenRouter wrapper commands:

```bash
OUTPUT_DIR=outputs/c-code-only-base-0825 \
MODEL=anthropic/claude-sonnet-5 \
ENABLE_CODE_REPAIR=false \
bash scripts/run_openrouter_c_code_only_pipeline.sh

OUTPUT_DIR=outputs/c-code-only-vgcr-0825 \
REUSE_ARTIFACTS_FROM=outputs/c-code-only-base-0825 \
MODEL=anthropic/claude-sonnet-5 \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
bash scripts/run_openrouter_c_code_only_pipeline.sh
```

Code-only oracle consistency must be evaluated separately and cannot be replaced by requirement
entailment coverage. This check directly compares the frozen oracle contract with the output
`specs/` artifact; therefore, as long as the pipeline has not rewritten the contract, the result
should be 100% and does not depend on C/ACSL-to-Z3 expression parsing:

```bash
OUTPUT_DIR=outputs/c-code-only-base-0825 \
bash scripts/run_code_only_oracle_evaluation.sh
```

This command generates `reports/oracle_contract_consistency.json`. The existing
`run_constraint_entailment_evaluation.sh` is still used for requirement semantic coverage; it
answers whether the oracle contract covers the manual semantic targets, not whether the oracle
contract is correctly preserved.

### 7.6.1 Java/JML Code-Only Oracle-Contract Evaluation

Java code-only tasks follow the same strict incremental semantics: fix the method-level JML contract
in `benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json`, and evaluate
only the Java implementation and implementation-level loop annotations. The entry point is
`scripts/run_java_code_only_pipeline.py`, which does not execute spec generation, constraint
extraction, or spec self-check; after each generation and repair it restores the canonical
`jml_block`.

Initial generation (no repair):

moonshotai/kimi-k2.7-code
qwen/qwen3.6-plus

```bash
PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --verify-timeout 120 --request-timeout 120 \
  --llm-retries 3 --llm-retry-delay 15 \
  --max-tokens 4096 --temperature 0 --resume
```

Simple repair and VGCR repair must reuse the same initial artifacts:

```bash
PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-simple \
  --reuse-artifacts-from outputs/java-code-only-base \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 --enable-code-repair \
  --code-repair-strategy simple --code-repair-max-iter 3 --resume

PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-vgcr-claude-0827 \
  --reuse-artifacts-from outputs/java-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 --enable-code-repair \
  --code-repair-strategy vgcr --vgcr-candidates 3 \
  --code-repair-max-iter 3 --max-tokens 4096 --temperature 0 --resume
```

Run Java oracle consistency separately:

```bash
PYTHONPATH=. python3 scripts/evaluate_java_code_only_oracle.py \
  --oracle-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --specs-dir outputs/java-code-only-base/specs \
  --report-file outputs/java-code-only-base/reports/java_oracle_contract_consistency.json
```

### 7.6.2 Rust/Verus Code-Only Oracle-Contract Evaluation

Rust code-only data is located at
`benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json`.
The constructor locates the reference target function by dataset signature and extracts only
`requires/ensures` from the function header; the function body, loop invariants, `decreases`,
assertions, and proof code do not enter the oracle input. The 100 reference contracts correspond
exactly one-to-one with the manual semantic targets, no auxiliary contract clauses need to be added
at present, and the reference Verus regression is 100/100 pass.

Initial generation:

```bash
PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --contracts-file benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/rust-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus --verify-timeout 120 \
  --request-timeout 120 --llm-retries 3 --llm-retry-delay 15 \
  --max-tokens 4096 --temperature 0 --resume
```

Repair must reuse the same batch of initial artifacts:

```bash
PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --output-dir outputs/rust-code-only-simple \
  --reuse-artifacts-from outputs/rust-code-only-base \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair --code-repair-strategy simple \
  --code-repair-max-iter 3 --resume

PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --output-dir outputs/rust-code-only-vgcr-claude-0828 \
  --reuse-artifacts-from outputs/rust-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair --code-repair-strategy vgcr \
  --vgcr-candidates 3 --code-repair-max-iter 3 --resume
```

The Rust contract is embedded in the function header, so enforcement restores both the canonical
named signature and the structured `verus_clauses`. The consistency check both compares
`specs/*.json` and re-extracts the target function header from `code/*.rs`:

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
bash scripts/run_rust_code_only_oracle_evaluation.sh
```

The OpenRouter wrapper is `scripts/run_openrouter_rust_code_only_pipeline.sh`. It keeps the same
`ENABLE_CODE_REPAIR`, `CODE_REPAIR_STRATEGY`, `VGCR_CANDIDATES`, `REUSE_ARTIFACTS_FROM`, `TASK_ID`,
and `RESUME` semantics as C/Java.

In C code-only mode, `run_constraint_entailment_evaluation.sh` reads
`task_type=code_only_oracle_contract` and adopts oracle-specific semantic directions: auxiliary
`requires` may be added for memory safety, overflow, and termination, but the oracle contract is
required to entail every audited semantic target. The C/ACSL parser correctly handles
quantifier-binding semicolons, inline comments, chained comparisons, `\result`, labels, and pointer
dereferences; a parser failure must not be treated as a coverage failure.

The output still uses a unified layout: `specs/` stores the frozen oracle artifacts, `code/` stores
the initial or repaired C, and `reports/results.json` stores initial/post-repair validity, the
repair trajectory, and `contract_enforcement`. Rust/Verus already uses independent code-only
contract data and a pipeline; Python/Nagini already uses independent code-only contract data and a
pipeline, keeping the same CLI semantics, artifact chaining, and metric fields.

### 7.6.3 Python/Nagini Code-Only Oracle Contract Usage:

This flow skips model spec generation and directly reads the fixed
`benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json`.
The model generates only the implementation and implementation-level `Invariant`/`Assert`, and the
oracle function contract is frozen during both generation and repair.

```bash
PYTHONPATH=. python3 scripts/run_python_code_only_pipeline.py \
  --contracts-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/python-code-only-base-claude-0902 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

Code-only repair variants must reuse the same batch of initial code and may not resample:

```bash
PYTHONPATH=. python3 scripts/run_python_code_only_pipeline.py \
  --contracts-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/python-code-only-vgcr-kimi-0902 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --enable-code-repair \
  --code-repair-strategy vgcr \
  --vgcr-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/python-code-only-kimi-0902 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

The OpenRouter wrapper can also be used:

```bash
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
REUSE_ARTIFACTS_FROM=outputs/python-code-only-kimi-0902 \
OUTPUT_DIR=outputs/python-code-only-vgcr-kimi-0902 \
scripts/run_openrouter_python_code_only_pipeline.sh
```

Oracle artifact consistency check:

```bash
PYTHONPATH=. python3 scripts/evaluate_python_code_only_oracle.py \
  --oracle-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --specs-dir outputs/python-code-only-kimi-0902/specs \
  --code-dir outputs/python-code-only-kimi-0902/code \
  --report-file outputs/python-code-only-kimi-0902/reports/oracle_contract_consistency.json
```

### 7.7 Skip Verification (generation only)

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py --skip-verify
```

The corresponding Java/JML command:

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py --skip-verify
```

The corresponding Rust/Verus command:

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py --skip-verify
```

The corresponding Python/Nagini command:

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py --skip-verify
```

## 8. OpenRouter One-Click Scripts

`scripts/run_openrouter_requirement_pipeline.sh` supports the following variables:

- `PIPELINE_VARIANT=base|enhanced`
- `ENABLE_CGS=true|false` (effective for enhanced, default true)
- `SPEC_SELF_CHECK_ROUNDS` (effective for enhanced)
- `ENABLE_CODE_REPAIR=true|false` (effective for enhanced, default true)
- `CODE_REPAIR_MAX_ITER` (effective for enhanced)
- `CODE_REPAIR_STRATEGY=simple|vgcr` (effective for C/ACSL, Java/JML, Rust/Verus, and Python/Nagini enhanced, default simple)
- `VGCR_CANDIDATES` (effective for C/ACSL, Java/JML, Rust/Verus, and Python/Nagini VGCR repair, default 3)
- `REUSE_ARTIFACTS_FROM` (required for C/ACSL, Java/JML, Rust/Verus, and Python/Nagini strict repair ablations)
- `ENABLE_SPEC_EVALUATION=true|false` (effective for enhanced, default false)
- `SIGNATURE_FILE` (source of the fixed function signature; for C the default is
  `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`)
- `REQUEST_TIMEOUT` (single LLM/API request timeout, default 120)
- `LLM_RETRIES`, `LLM_RETRY_DELAY` (bounded retries for transient LLM/API failures, default 3 / 15)
- `RESUME=true|false` (whether to skip tasks with `status=ok` already present in a report, default false)
- `TASK_ID`, `SKIP_VERIFY`, `MODEL`, etc.

Example of generating CGS:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=true \
SPEC_SELF_CHECK_ROUNDS=1 \
ENABLE_CODE_REPAIR=false \
ENABLE_SPEC_EVALUATION=true \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-cgs-only-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

Strict VGCR example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/req2code-base-0520 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-base-repair-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

Strict CodeNova example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/req2code-cgs-only-0520 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-cgs-vgcr-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

The corresponding one-click script for Java/JML/OpenJML:

```bash
ENABLE_CODE_REPAIR=true \
ENABLE_CGS=true \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-req2code-openrouter \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Java strict VGCR one-click script example:

```bash
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/java-base-0624 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-base-vgcr-0624 \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Java strict CodeNova one-click script example:

```bash
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/java-cgs-only-0624 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-cgs-vgcr-0624 \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

The corresponding one-click script for Rust/Verus:

```bash
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=both \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Rust strict VGCR one-click script example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/rust-base-0626 \
REQUEST_TIMEOUT=120 \
OUTPUT_DIR=outputs/rust-base-vgcr-0626 \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Rust strict CodeNova one-click script example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/rust-cgs-only-0626 \
REQUEST_TIMEOUT=120 \
OUTPUT_DIR=outputs/rust-cgs-vgcr-0626 \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

The corresponding one-click script for Python/Nagini:

```bash
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=both \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini strict VGCR one-click script example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-base-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-base-vgcr-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini strict CodeNova (simple repair) one-click script example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-cgs-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-cgs-repair-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini strict CodeNova (candidate repair) one-click script example:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
VGCR_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-cgs-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-cgs-vgcr-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Rust/Python ablations can be selected via `PIPELINE_VARIANT=base`, or
`PIPELINE_VARIANT=enhanced ENHANCEMENT_METHOD=cgs|repair|both`. Strict repair / VGCR ablations use
`REUSE_ARTIFACTS_FROM` to reuse the Direct or CGS outputs.

Post-evaluation scripts (evaluate existing outputs only, no regeneration):

- `scripts/run_constraint_entailment_evaluation.sh`
  - input: `OUTPUT_DIR/specs/*.json` + fixed manual ground-truth spec file
  - output: `OUTPUT_DIR/reports/cef.json`
  - metrics: ground-truth spec coverage, post/frame coverage, pre over-constraint

Example:

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_constraint_entailment_evaluation.sh
```

The corresponding Java/JML command:

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_java_constraint_entailment_evaluation.sh
```

The corresponding Rust/Verus command:

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh
```

The corresponding Python/Nagini command:

```bash
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_python_nagini_constraint_entailment_evaluation.sh
```

Generate the final benchmark summary:

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_req2code_benchmark_summary.sh
```

The corresponding Java/JML command:

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

The corresponding Rust/Verus command also uses the unified summary:

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

The corresponding Python/Nagini command also uses the unified summary:

```bash
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

## 9. Experimental and Comparison Recommendations (paper-friendly)

It is recommended to report at least four groups:

1. Direct
2. CGS (only constraint extraction / spec self-check enabled)
3. VGCR (reuse Direct artifacts, only code repair enabled)
4. CodeNova (reuse CGS artifacts, only code repair enabled)

VGCR must inherit the `specs/` and `code/` of Direct; CodeNova must inherit the `specs/` and `code/`
of CGS. Independent reruns may serve as supplementary randomness/robustness experiments, but not as
the basis for the marginal contribution of the main ablation.

Key metrics:

- verify pass rate
- average number of repair rounds
- number of missing requirement-spec constraints (from `alignment_check`)
- requirement coverage micro/macro (from `benchmark_summary.json`)
- joint success (from `benchmark_summary.json`)
- per-task token/latency cost (optional)

## 10. Current Boundaries and Optional Future Enhancements

The current enhancement still follows the "lightweight modification" principle and does not yet
include:

- spec-aware code skeleton (e.g. `requires` -> explicit check template)
- embedding matching between requirement and spec (method B, a possible future enhancement)
- finer-grained constraint type labels (safety, bounds, monotonicity, etc.)

These can be added as next-stage increments without affecting the comparability of the existing
Direct/enhanced variants.

## 11. C/ACSL Stage Summary and Multi-Language Migration Baseline

The C language track has completed the closed loop from data, parsing, and evaluation to pipeline;
subsequent Java, Rust, and Python should use the constraints in this section as the migration
baseline.

### 11.1 Completed Items

- **Ground-truth audit**: fixed truncated quantifiers, parameter names, array indices, behaviors, assigns, and expression errors in 23 tasks; the revisions are preserved as a replayable script by `scripts/fix_c_ground_truth_clauses.py`.
- **ACSL/C parsing**: the CEF evaluator now handles quantifier-binding semicolons, inline comments, chained comparisons, `\result`/`result`, ACSL labels, pointer dereferences, and complex equality normalization. A parse failure must not be recorded directly as a coverage failure.
- **Code-only oracle**: 100 C tasks have an independent canonical `code_only_contract` containing only interface-level requires/assigns/ensures, without leaking loop invariants, variants, or other implementation-level proof annotations.
- **Contract preservation**: the canonical contract is restored before and after initial generation and each repair round, and `contract_enforcement` is recorded; simple repair and VGCR reuse the same batch of initial artifacts.
- **Unified evaluation**: the full pipeline reports code validity, requirement coverage (micro/macro), and joint success; code-only additionally uses `oracle_contract_consistency.json` to check whether the contract has been tampered with.

### 11.2 Current C Results and Data Boundaries

The re-evaluation uses the revised ground truth, parser, and evaluation directions. The Direct
baseline for DeepSeek default is `outputs/req2code-base-0622`; the four-model four-paradigm summary
is written to `outputs/c_re_evaluation_current.json`.
100% applies only to the code-only oracle consistency check on audited and unmodified contracts;
full-pipeline coverage still faithfully reflects how well the model-generated spec aligns with the
manual semantic targets.

The divisibility semantic target of task 42 (GCD) has been retained, but the reference WP proof
currently times out. It should be marked as an oracle validation/proof issue and tracked separately;
the target must not be deleted, the contract must not be weakened, and unreasonable preconditions
must not be added.

Current re-evaluation summary (`Code Valid`, `Coverage`, and `Joint` are respectively passing
tasks/100, macro coverage, and passing tasks/100):

| Model | Direct | CGS | VGCR | CodeNova |
| --- | --- | --- | --- | --- |
| DeepSeek default | 34 / 0.4327 / 14 | 30 / 0.6047 / 17 | 60 / 0.4327 / 21 | 54 / 0.6047 / 24 |
| Kimi-k2.7-code | 68 / 0.6831 / 26 | 71 / 0.7350 / 31 | 86 / 0.6831 / 30 | 86 / 0.7350 / 35 |
| Qwen3.6-plus | 50 / 0.5233 / 21 | 39 / 0.7131 / 23 | 64 / 0.5233 / 25 | 66 / 0.7131 / 29 |
| Claude-Sonnet-5 | 73 / 0.7826 / 39 | 56 / 0.7879 / 34 | 80 / 0.7826 / 41 | 77 / 0.7879 / 40 |

This table represents only results under the current C data and evaluation rules; when migrating to
other languages, field meanings should be preserved and absolute difficulty across different
verifiers should not be compared directly.

### 11.3 Java/Rust/Python Migration Requirements

Each language should provide independent requirement/signature/ground-truth, a canonical code-only
contract, reference validation, and generation/contract-restoration/verifier/repair/summary
pipelines, and should use language-specific parsers and verifier auxiliary-condition rules. When
spec-only conditions are naturally satisfied, there is no need to create a separate spec-only track;
code-only must not treat verifier auxiliary conditions as requirement coverage; repair may only
modify the implementation and implementation-level annotations; missing output, parse failures,
verification errors, and timeouts are counted in the report using a fixed denominator.
Language-specific tasks should be reported separately first, and not merged into a cross-language
total score before semantics are unified.
