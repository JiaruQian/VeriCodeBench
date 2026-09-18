# Verifier-Guided Candidate Repair (VGCR)

This note describes the **Verifier-Guided Candidate Repair (VGCR)** component of
CodeNova. CodeNova combines Constraint-Guided Specification (CGS) with VGCR to
generate verified code under a self-generated contract: CGS produces a frozen
function contract, and VGCR repairs the implementation against that contract
using native verifier feedback. VGCR can address implementation and proof
failures but cannot recover omitted requirements, because it is never allowed to
change the contract.

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

- `Direct`: direct requirement-to-ACSL and ACSL-to-C generation, then verification.
- `CGS` (`base+cgs`): adds constraint-guided specification generation,
  constraint-to-spec mapping, and optional spec self-check/refinement before code
  generation.
- `VGCR` (`base+vgcr`): reuses frozen `Direct` specs and code, then only runs
  verification and VGCR repair.
- `CodeNova` (`base+cgs+vgcr`): reuses frozen `CGS` specs and code, then only
  runs verification and VGCR repair.

The strict incremental rule is important: repair variants must not regenerate
specs or initial code. They may only start from the saved artifacts in
`REUSE_ARTIFACTS_FROM`, run the verifier, and update the code during repair.
This keeps requirement coverage identical between `Direct` and `VGCR`, and
between `CGS` and `CodeNova`.

The simple repair loop is intentionally lightweight:

```text
code_i -> verifier -> failed verdict/log -> LLM repair -> code_{i+1}
```

It passes the full requirement, frozen function contract, current code, and
native verifier output to the model. The model returns a complete source file.
The loop repeats for a small number of iterations.

## VGCR Procedure

VGCR replaces the one-shot repair prompt with verifier-failure planning plus
multiple focused repair candidates. For a failed verdict it:

- extracts and summarizes verifier diagnostics into smaller obligations;
- generates several independent repair candidates that share the same starting
  code and plan but differ in focus;
- verifies each candidate as a complete program and keeps the first accepted
  candidate, or the last attempted one to seed the next round.

The transferable design ideas are:

- Prove-as-you-generate: code, invariants, and proof obligations co-evolve
  under verifier feedback.
- Subgoal decomposition: unsolved verification conditions are summarized into
  smaller obligations.
- Multiple independent attempts: several candidates try different repairs,
  improving pass@k behavior.
- Candidate focus schedule: candidates target all subgoals, individual
  subgoals, or an alternative implementation.
- Contract discipline: the generated function contract is treated as fixed
  during implementation repair.
- Anti-cheating review: candidates should remain imperative and should not make
  verification trivial by replacing the algorithm with a direct specification
  expression.

### Step 1: Failure/Subgoal Planning

On a failed verdict, ask the model for strict JSON:

- `failure_summary`
- `subgoals`: named verifier issues such as memory safety, postcondition,
  loop invariant preservation, loop assigns, loop variant, overflow, syntax,
  timeout, or unknown
- `global_strategy`
- `risk_notes`

Each subgoal records an issue type, supporting diagnostic evidence, and a
proposed implementation or annotation change. Subgoals are LLM interpretations
of diagnostics, not independently proved lemmas; a failed or timed-out proof
attempt is not treated as a concrete counterexample.

### Step 2: Candidate Repair Search

For each repair attempt, generate `K` candidates with different focuses:

- one candidate tries to synthesize all subgoals
- one or more candidates prioritize individual subgoals
- one fallback candidate tries an alternative verification-friendly
  implementation

Each candidate must preserve the frozen function contract and may only change
the executable body plus implementation-level annotations such as loop
`invariant`/`assigns`/`variant`. Candidates are generated from the same starting
code and plan within a round.

Candidates are verified immediately as complete programs. The first accepted
candidate is returned. If none passes, the last candidate submitted to the
verifier becomes the next loop state so the next repair attempt can learn from
its verifier output. Candidates rejected by language-subset prechecks do not
replace the current code. On budget exhaustion, the final implementation is
retained for analysis.

### Step 3: Trajectory Logging

Record the following under `verification.repair_history`:

- repair strategy
- pre-repair verdict type/message
- saved verifier log path
- VGCR plan JSON
- candidate focuses and candidate verdicts
- post-repair verdict type/message

This trajectory-first design makes later error analysis possible.

## Strict Incremental Variants

The VGCR strategy must be run through the existing artifact reuse mechanism.

For `base+vgcr`:

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
REUSE_ARTIFACTS_FROM=outputs/req2code-base \
OUTPUT_DIR=outputs/req2code-base-vgcr \
./scripts/run_openrouter_requirement_pipeline.sh
```

For `base+cgs+vgcr` (CodeNova):

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CGS=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=vgcr \
REUSE_ARTIFACTS_FROM=outputs/req2code-cgs-only \
OUTPUT_DIR=outputs/req2code-cgs-vgcr \
./scripts/run_openrouter_requirement_pipeline.sh
```

Constraint-Guided Specification is disabled in these repair-only runs because
specs/code come from frozen artifacts. The CGS effect is already represented by
the source artifact directory.

## Current Implementation Scope

The implementation is intentionally conservative:

- C/ACSL, Java/JML, Rust/Verus, and Python/Nagini backends support `simple` and
  `vgcr` repair strategies.
- Default repair strategy remains `simple`.
- CLI option: `--code-repair-strategy simple|vgcr`.
- CLI option: `--vgcr-candidates N`.
- Wrapper environment variables:
  - `CODE_REPAIR_STRATEGY=simple|vgcr`
  - `VGCR_CANDIDATES=3`
- C, Java, Rust, and Python support strict repair-only ablations through
  `REUSE_ARTIFACTS_FROM` / `--reuse-artifacts-from`.
- No extra runtime dependency on any third-party repair framework.


### Java/OpenJML Commands

For Java `base+vgcr`:

```bash
ENABLE_CGS=false ENABLE_CODE_REPAIR=true CODE_REPAIR_STRATEGY=vgcr VGCR_CANDIDATES=3 REUSE_ARTIFACTS_FROM=outputs/java-req2code-base OUTPUT_DIR=outputs/java-req2code-base-vgcr OPENJML_SOLVER=/usr/bin/z3 ./scripts/run_openrouter_java_requirement_pipeline.sh
```

For Java `base+cgs+vgcr` (CodeNova), point `REUSE_ARTIFACTS_FROM` at the frozen
Java `base+cgs` output directory instead.
