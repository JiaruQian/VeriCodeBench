# WybeCoder-style Repair Migration Plan

This note explains how to borrow the useful parts of WybeCoder for the
AutoSpec requirement-to-code benchmark without replacing the current benchmark
design or weakening strict incremental evaluation.

## Current Benchmark Pipeline

The benchmark evaluates:

```text
Requirement -> language-specific Spec -> Code -> Verifier
```

For the C backend this is:

```text
Requirement -> ACSL Spec -> C Code -> Frama-C/WP
```

The main ablation families are:

- `base`: direct requirement-to-ACSL and ACSL-to-C generation, then verification.
- `base+ce`: adds requirement constraint extraction, constraint-to-spec mapping,
  and optional spec self-check/refinement before code generation.
- `base+repair`: reuses frozen `base` specs and code, then only runs verification
  and code repair.
- `base+ce+repair`: reuses frozen `base+ce` specs and code, then only runs
  verification and code repair.

The strict incremental rule is important: repair variants must not regenerate
specs or initial code. They may only start from the saved artifacts in
`REUSE_ARTIFACTS_FROM`, run the verifier, and update the code during repair.
This keeps requirement coverage identical between `base` and `base+repair`, and
between `base+ce` and `base+ce+repair`.

The existing repair loop is intentionally lightweight:

```text
code_i -> verifier -> failed verdict/log -> LLM repair -> code_{i+1}
```

It passes the full requirement, frozen function contract, current code, and
Frama-C output to the model. The model returns a complete C source file. The
loop repeats for a small number of iterations.

## What WybeCoder Contributes

WybeCoder targets Lean/Loom/Velvet, not C/ACSL. Its concrete verifier hooks,
proof reconstruction, theorem search, and MCP tools are Lean-specific. The
transferable ideas are higher-level:

- Prove-as-you-generate: code, invariants, and proof obligations co-evolve
  under verifier feedback.
- Subgoal decomposition: unsolved verification conditions are extracted or
  summarized into smaller obligations.
- Multiple independent attempts: several agents/candidates try different
  repairs, improving pass@k behavior.
- Proposal/reviser pattern: failed subgoal attempts can propose implementation
  or invariant changes; a later synthesis step merges them.
- Contract discipline: the method specification header is treated as fixed
  during implementation repair.
- Anti-cheating review: candidates should remain imperative and should not make
  verification trivial by replacing the algorithm with a direct specification
  expression.

## Non-transferable Parts

The following WybeCoder components should not be copied directly into this
benchmark:

- Lean theorem extraction and proof reconstruction. Frama-C/WP does not produce
  standalone Lean theorem statements.
- Loom/Velvet syntax and `prove_correct` blocks.
- Loogle and leanexplore MCP search. These help Lean proof search but do not
  help ACSL/C directly.
- The full multi-agent scheduler. It is useful for large Lean proof search, but
  too heavy for the current benchmark's simple repair loop and cost model.
- Any flow that changes the generated function contract during code repair.
  That would break the benchmark's separation between requirement-spec coverage
  and code-validity improvement.

## Proposed Migration

Add a second repair strategy named `wybecoder` beside the current `simple`
repair strategy.

```text
simple:
  verifier log -> one LLM repair -> verify

wybecoder:
  verifier log -> structured failure/subgoal plan
               -> multiple focused repair candidates
               -> verify each candidate
               -> keep the first passing candidate, or the last attempted one
```

The new strategy is still a code repair method. It does not replace base
generation, constraint extraction, or requirement coverage evaluation.

### Step 1: Failure/Subgoal Planning

On a failed Frama-C verdict, ask the model for strict JSON:

- `failure_summary`
- `subgoals`: named verifier issues such as memory safety, postcondition,
  loop invariant preservation, loop assigns, loop variant, overflow, syntax,
  timeout, or unknown
- `global_strategy`
- `risk_notes`

This is the C/ACSL analogue of WybeCoder's verification-condition extraction.
It is less precise than Lean theorem extraction, but it gives the repair model
a stable intermediate representation.

### Step 2: Candidate Repair Search

For each repair attempt, generate `N` candidates with different focuses:

- one candidate tries to synthesize all subgoals
- one or more candidates prioritize individual subgoals
- one fallback candidate tries an alternative verification-friendly
  implementation

Each candidate must preserve the frozen ACSL function contract and may only
change the C body plus statement-level annotations such as loop
`invariant`/`assigns`/`variant`.

Candidates are verified immediately. The first passing candidate is retained.
If none passes, the last candidate becomes the next loop state so the next
repair attempt can learn from its verifier output.

### Step 3: Trajectory Logging

Record the following under `verification.repair_history`:

- repair strategy
- pre-repair verdict type/message
- saved verifier log path
- WybeCoder-style plan JSON
- candidate focuses and candidate verdicts
- post-repair verdict type/message

This mirrors WybeCoder's trajectory-first design and makes later error analysis
possible.

## Strict Incremental Variants

The new strategy must be run through the existing artifact reuse mechanism.

For `base+wybecoder`:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
REUSE_ARTIFACTS_FROM=outputs/req2code-base \
OUTPUT_DIR=outputs/req2code-base-wybecoder \
./scripts/run_openrouter_requirement_pipeline.sh
```

For `base+ce+wybecoder`:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
REUSE_ARTIFACTS_FROM=outputs/req2code-ce-only \
OUTPUT_DIR=outputs/req2code-ce-wybecoder \
./scripts/run_openrouter_requirement_pipeline.sh
```

Constraint extraction is disabled in these repair-only runs because specs/code
come from frozen artifacts. The CE effect is already represented by the source
artifact directory.

## Current Implementation Scope

The implementation is intentionally conservative:

- C/ACSL and Java/JML backends support `simple` and `wybecoder` repair strategies.
- Default repair strategy remains `simple`.
- CLI option: `--code-repair-strategy simple|wybecoder`.
- CLI option: `--wybecoder-candidates N`.
- Wrapper environment variables:
  - `CODE_REPAIR_STRATEGY=simple|wybecoder`
  - `WYBECODER_CANDIDATES=3`
- C and Java support strict repair-only ablations through `REUSE_ARTIFACTS_FROM` / `--reuse-artifacts-from`.
- No extra runtime dependency on the WybeCoder repository.

Future extensions can port the same strategy interface to Rust/Verus and
Python/Nagini by changing the verifier-specific failure taxonomy and
contract-preservation enforcement.


### Java/OpenJML Commands

For Java `base+wybecoder`:

```bash
ENABLE_CONSTRAINT_EXTRACTION=false ENABLE_CODE_REPAIR=true CODE_REPAIR_STRATEGY=wybecoder WYBECODER_CANDIDATES=3 REUSE_ARTIFACTS_FROM=outputs/java-req2code-base OUTPUT_DIR=outputs/java-req2code-base-wybecoder OPENJML_SOLVER=/usr/bin/z3 ./scripts/run_openrouter_java_requirement_pipeline.sh
```

For Java `base+ce+wybecoder`, point `REUSE_ARTIFACTS_FROM` at the frozen Java
`base+ce` output directory instead.
