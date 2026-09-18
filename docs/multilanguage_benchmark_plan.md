# Multi-language Requirement-to-Code Verification Benchmark Plan

This document records the design rationale, container strategy, and verifier-environment recommendations for extending the current C/ACSL/Frama-C benchmark to Java, Rust, and Python.

The core task of the current repository is:

```text
Requirement -> ACSL Spec -> C Code -> Frama-C/WP Verification
```

After the multilingual extension, the task should not be understood as a simple syntax substitution but should be abstracted as:

```text
Requirement -> Language-specific Spec -> Code -> Verifier -> Spec Coverage
```

Here `ACSL + Frama-C` is the C backend; Java, Rust, and Python each introduce their own specification language and verifier backend.

As of the current milestone, the C/ACSL/Frama-C track has been completed and serves as the migration baseline: the ground-truth clauses have been audited, the ACSL entailment parser covers the main syntactic boundaries, and for 100 problems the code-only oracle contracts, contract-forced restoration, reference validation, and full-chain re-evaluation have all been implemented. Subsequent languages must maintain the same artifact chain and metric semantics while implementing language-specific contract parsers, verifier adapters, and oracle data; one cannot assume that ACSL text or Frama-C's proof rules can be reused directly.

## 1. Overall Assessment

The current benchmark can be extended to Java, Rust, and Python, but the three differ in maturity:

| Language | Recommended stage | Spec ecosystem | Verifier candidates | Fit with current paradigm |
| --- | --- | --- | --- | --- |
| C | existing | ACSL | Frama-C/WP | baseline |
| Java | stage 1 | JML | OpenJML, KeY | very close |
| Rust | stage 2 / active Verus track | Verus contracts | Verus | strong but verifier-specific |
| Python | stage 3 / separate track | Nagini contracts, CrossHair contracts | Nagini, CrossHair | useful but not equivalent |

Java is the most natural first extension target. JML and ACSL are both contract-style specifications next to the source code, and OpenJML can directly check JML annotations in Java programs.

Rust is well worth studying because it can showcase the differences between C and Rust in memory safety, aliasing, ownership, and panic freedom. However, Rust has no unified ACSL equivalent, and different verifiers differ considerably in their specification languages and supported Rust subsets. The current Rust track in this repository uses Verus; the dataset is located at `benchmarks/rust-verus-problems`, and the pipeline entry points are `scripts/run_rust_requirement_pipeline.py` and `scripts/run_openrouter_rust_requirement_pipeline.sh`.

Python is better suited as a dynamic-language contract verification track. The current Python track uses Nagini; the dataset is located at `benchmarks/python-nagini-problems`, the pipeline entry points are `scripts/run_python_nagini_requirement_pipeline.py` and `scripts/run_openrouter_python_nagini_requirement_pipeline.sh`, and the coverage entry point is `scripts/run_python_nagini_constraint_entailment_evaluation.sh`. Nagini is closer to static verification, while CrossHair is closer to contract checking under symbolic execution. Their results should not be directly merged with Frama-C/OpenJML/Verus into a single total score.

## 2. Benchmark Architecture Abstraction

It is suggested to split the parts of the existing pipeline that are strongly bound to C into three backend interfaces. The first stage does not require different languages to share the same problem or to maintain a unified language-independent semantic IR; each language can first use the problems and ground truth that best fit its own verification ecosystem.

```text
SpecBackend
  - generate language-specific contract
  - parse generated clauses
  - compare generated clauses with language-specific ground truth

VerifierAdapter
  - run verifier
  - parse pass/fail/error/timeout
  - collect diagnostics for repair

DatasetBackend
  - choose language-specific signature
  - choose file extension and source layout
  - choose language-specific problem set
```

Recommended directory layout:

```text
benchmarks/
  multilang/
    c/
      problem_001/
        requirement.json
        ground_truth_spec.json
        solution.c
    java/
      problem_001/
        requirement.json
        ground_truth_spec.json
        Solution.java
    rust/
      problem_001/
        requirement.json
        ground_truth_spec.json
        lib.rs
    python/
      problem_001/
        requirement.json
        ground_truth_spec.json
        solution.py
    cross_language_core_optional/
      problem_001/
        requirement.json
        c/
          ground_truth_spec.json
        java/
          ground_truth_spec.json
        rust/
          ground_truth_spec.json
        python/
          ground_truth_spec.json
```

If a strict comparison of the same requirement across different languages is genuinely needed later, a small overlapping problem set can be maintained in `cross_language_core_optional/`. This subset may further introduce `semantic_targets.json` or another language-independent IR, but it should not become a requirement of the first stage.

## 3. Dataset Expansion Strategy

It is suggested that the first stage adopt language-specific problem sets. That is, neither C's legacy 51 problems nor the current 100 problems need to be fully ported to Java, Rust, and Python; each language should prioritize problems that best fit its own verification ecosystem.

### 3.1 Why not directly port all 51 C problems

Some of C's problem set is suitable for migration to Java/Rust/Python, such as array traversal, search, maximum, sortedness, and arithmetic constraints. But not all of them are suitable as shared multilingual problems.

Reasons they are not suitable for direct sharing:

- Many C problems revolve around pointer validity, aliasing, `\valid`, `\separated`, buffer bounds, and manual frame conditions, which are core semantics of C/ACSL/Frama-C.
- Java has no raw pointers, and memory-safety issues are more often expressed as nullability, object invariants, field frames, and exception behavior.
- Rust's safe subset already rules out many C preconditions through ownership/borrowing, so directly copying C problems would make the Rust problems unnatural.
- Python's verification ecosystem is better suited to typed contracts, list/dict behavior, and symbolic-execution-friendly functions; directly porting C pointer problems is meaningless.

Therefore, the C problem set can serve as a source of inspiration for problem types, rather than as a mandatory multilingual parent set.

### 3.2 Language-specific set

These problems reflect each language's own real-world development semantics and constitute the main dataset of the first stage.

The problem sets of the four languages have currently been implemented with the following category distribution.

C/ACSL/Frama-C (`benchmarks/frama-c-problems`, 100 problems):

- `array_slices`: 15
- `arrays_and_loops`: 5
- `bytes_strings`: 9
- `general_wp_problems`: 12
- `immutable_arrays`: 8
- `loops`: 8
- `miscellaneous`: 5
- `more_arrays`: 3
- `mutable_arrays`: 2
- `pointer_blocks`: 10
- `pointers`: 8
- `scalar_c`: 5
- `struct_records`: 10

This group retains the characteristics of the C/ACSL baseline, covering verification topics such as weakest-precondition basics, loop invariants, array reads and writes, pointer operations, frame conditions, buffer/pointer validity, byte/string buffers, struct-field frames, and C integer bounds.

Java/JML/OpenJML (`benchmarks/java-problems`, 100 problems):

- `array_basics`: 5
- `array_extrema`: 2
- `array_extra`: 16
- `array_ordering`: 2
- `array_predicates`: 2
- `array_search`: 3
- `boolean_logic`: 8
- `exceptions`: 12
- `loop_arithmetic`: 2
- `mutable_arrays`: 8
- `nullability`: 1
- `object_frames`: 4
- `object_invariants`: 3
- `scalar_arithmetic`: 24
- `strings_chars`: 8

This group focuses on array bounds, array query and update, scalar arithmetic, boolean logic, basic string/character properties, nullability, object invariants, field/object frame conditions, and exceptional behavior in Java's natural semantics.

Rust/Verus (`benchmarks/rust-verus-problems`, 50 problems):

- `scalar_arithmetic`: 10
- `option_result`: 10
- `vec_immutable`: 12
- `vec_mutation`: 12
- `ownership_slices`: 6

This group focuses on safe Rust functional correctness, `Option`/`Result`, vector/slice bounds, panic freedom, ownership/borrowing, and unique-borrow mutation.

Python/Nagini (`benchmarks/python-nagini-problems`, 100 problems):

- `dict_apis`: 8
- `dict_apis_ext`: 8
- `exception_freedom`: 4
- `exception_freedom_ext`: 4
- `list_basics`: 10
- `list_basics_ext`: 10
- `list_mutation`: 10
- `list_mutation_ext`: 10
- `optional_none`: 8
- `optional_none_ext`: 8
- `scalar_arithmetic`: 10
- `scalar_arithmetic_ext`: 10

This group focuses on typed function contracts, `Optional`/`None` compatibility, list/dict API behavior, container permissions, mutation postconditions, symbolic-execution-friendly pure functions, and simple API exception freedom.

Language-specific problems should not be mixed with cross-language problems into an uninterpretable total score. The following can be reported:

```text
language_specific_code_validity_rate
language_specific_requirement_coverage
language_specific_joint_success_rate
```

### 3.3 Optional cross-language core set

A small cross-language core set can be maintained later to answer "under which language/verifier is the same requirement easier for the model to complete." This is not the main line of the first stage.

Problem types suitable for inclusion in the optional core set:

- scalar arithmetic with overflow constraints
- array/list search
- max/min/sum/count
- sortedness
- binary search
- prefix sum
- swap or in-place update
- frame/no-mutation properties
- simple string or sequence transformations

The metrics of the optional core set should be reported separately:

```text
core_code_validity_rate
core_requirement_coverage_micro
core_requirement_coverage_macro
core_joint_success_rate
```


## 4. Container Strategy

It is suggested to have one or more independent containers per language, and not to cram all verifiers into a single large container. The probability of dependency conflicts among verifiers is high, especially for the Rust verifier, Why3, Viper, Z3, the Java runtime, and opam.

Recommended structure:

```text
docker/
  c-framac.Dockerfile
  java-openjml.Dockerfile
  rust-verus.Dockerfile
  rust-creusot.Dockerfile
  python-nagini.Dockerfile
  python-crosshair.Dockerfile
```

The upper-level runner can be unified:

```bash
PYTHONPATH=. python3 scripts/run_multilang_pipeline.py \
  --language java \
  --verifier openjml \
  --requirements-file benchmarks/multilang/core/requirements.json \
  --output-dir outputs/multilang-java-openjml
```

The lower level executes the verifier through different Docker images:

```text
c/framac          -> Frama-C/WP
java/openjml      -> OpenJML
rust/verus        -> Verus
rust/creusot      -> Creusot + Why3
python/nagini     -> Nagini + Viper
python/crosshair  -> CrossHair
```

## 5. Docker Hub base image recommendations

The following are Docker Hub official images suitable as starting points for each language's verifier container.

### 5.1 Java

Recommended base:

```dockerfile
FROM eclipse-temurin:21-jdk-noble
```

Alternative:

```dockerfile
FROM eclipse-temurin:25-jdk-noble
```

Rationale:

- `eclipse-temurin` is a Docker Official Image.
- The current OpenJML release bundles `openjml-java`, but its installation and run scripts still require a stable JDK environment.
- Java 21 is a conservative LTS choice; if an OpenJML release explicitly supports a newer JDK, it can be upgraded to Java 25.

Reference:

- https://hub.docker.com/_/eclipse-temurin
- https://www.openjml.org/downloads/

### 5.2 Rust

Recommended base:

```dockerfile
FROM rust:1-bookworm
```

Alternative for Verus binary compatibility:

```dockerfile
FROM ubuntu:22.04
```

Rationale:

- `rust` is a Docker Official Image, suitable for installing the Rust verifier and building Rust projects.
- The official Verus binary release has first-class support for Ubuntu 22.04 x86_64; if the Verus prebuilt package is used directly, `ubuntu:22.04 + rustup` may be more stable than `rust:1-bookworm`.
- Creusot usually needs Rust, cargo, opam, Why3, and SMT provers, so it is suggested to build a separate `rust-creusot` container.

Reference:

- https://hub.docker.com/_/rust
- https://github.com/verus-lang/verus/blob/main/INSTALL.md
- https://creusot-rs.github.io/creusot/guide/installation.html

### 5.3 Python

Recommended base for Nagini:

```dockerfile
FROM python:3.12-bookworm
```

Recommended base for CrossHair:

```dockerfile
FROM python:3.12-slim-bookworm
```

Rationale:

- `python` is a Docker Official Image.
- The Nagini documentation requires Java 11+ and Python 3.12 to 3.14; `python:3.12-bookworm` is a relatively conservative choice.
- CrossHair has far lighter dependencies and can use the slim image.

Reference:

- https://hub.docker.com/_/python
- https://github.com/marcoeilers/nagini
- https://crosshair.readthedocs.io/en/latest/contracts.html

## 6. Verifier installation sketches

These steps are drafts for container construction and should not be regarded as a locked-down reproducible Dockerfile. When formally implemented, the verifier release, checksum, and solver version need to be pinned.

### 6.1 Java: OpenJML

Candidate file: `docker/java-openjml.Dockerfile`

```dockerfile
FROM eclipse-temurin:21-jdk-noble

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip bash coreutils \
    && rm -rf /var/lib/apt/lists/*

ARG OPENJML_ZIP_URL
ENV OPENJML_HOME=/opt/openjml
ENV PATH="${OPENJML_HOME}:${PATH}"

RUN test -n "${OPENJML_ZIP_URL}" \
    && mkdir -p /opt \
    && curl -L "${OPENJML_ZIP_URL}" -o /tmp/openjml.zip \
    && unzip /tmp/openjml.zip -d /opt \
    && mv /opt/openjml* "${OPENJML_HOME}" \
    && chmod +x "${OPENJML_HOME}/openjml" \
    && rm /tmp/openjml.zip

RUN openjml --version
```

Verification command shape:

```bash
openjml --esc Solution.java
```

Pipeline target:

```text
Requirement -> JML contract -> Java code -> openjml --esc
```

Notes:

- OpenJML release is OS-dependent and distributed as a zip from the GitHub latest release page.
- OpenJML bundles supported SMT solvers in its release, so the initial container does not need a separate solver install unless a specific experiment requires it.
- KeY can be considered later, but OpenJML is the better first backend because it has a CLI workflow closer to Frama-C/WP.
- The generated `jml_block` artifact is the canonical method contract. Java code generation and repair must enforce that exact contract in the source file before OpenJML runs; repair may change implementation code and loop annotations, but not the method contract being verified.

### 6.2 Rust: Verus

Candidate file: `docker/rust-verus.Dockerfile`

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip git build-essential pkg-config python3 \
    && rm -rf /var/lib/apt/lists/*

ARG VERUS_ZIP_URL
ENV VERUS_HOME=/opt/verus
ENV PATH="${VERUS_HOME}:${PATH}"

RUN test -n "${VERUS_ZIP_URL}" \
    && curl -L "${VERUS_ZIP_URL}" -o /tmp/verus.zip \
    && unzip /tmp/verus.zip -d /opt \
    && mv /opt/verus* "${VERUS_HOME}" \
    && chmod +x "${VERUS_HOME}/verus" \
    && rm /tmp/verus.zip

# First run may print the exact rustup/toolchain command required by this Verus release.
RUN verus --version || true
```

Verification command shape:

```bash
verus lib.rs
```

Pipeline target:

```text
Requirement -> Verus spec/code -> verus
```

Notes:

- Verus official install flow recommends binary releases and states that Ubuntu 22.04 x86_64 has prebuilt artifacts.
- Verus may require a specific Rust toolchain. The Dockerfile should eventually run the rustup command required by the pinned Verus release instead of leaving `verus --version || true`.
- Verus is a strong candidate for Rust stage 2 because it provides an integrated spec language and verifier workflow.

### 6.3 Rust: Creusot

Candidate file: `docker/rust-creusot.Dockerfile`

```dockerfile
FROM rust:1-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential pkg-config opam m4 unzip \
    && rm -rf /var/lib/apt/lists/*

RUN opam init --disable-sandboxing -y \
    && opam update

WORKDIR /opt
ARG CREUSOT_REPO=https://github.com/creusot-rs/creusot.git
ARG CREUSOT_REF=master

RUN git clone "${CREUSOT_REPO}" creusot \
    && cd creusot \
    && git checkout "${CREUSOT_REF}" \
    && ./INSTALL

ENV PATH="/root/.cargo/bin:${PATH}"
```

Verification command shape:

```bash
cargo creusot prove
```

Pipeline target:

```text
Requirement -> Creusot contracts -> Rust crate -> cargo creusot prove
```

Notes:

- Creusot's quick install script installs Creusot and accompanying tools.
- The install script requires cargo, opam, curl, Why3-related tools, and SMT provers.
- This container will be heavier than Verus. It is worth keeping separate.

### 6.4 Rust: Prusti

Prusti is a useful candidate but not recommended as the first Rust backend unless the project specifically wants Viper-based Rust verification.

Potential flow:

```dockerfile
FROM rust:1-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential default-jre unzip python3 \
    && rm -rf /var/lib/apt/lists/*

# Then install a pinned Prusti release or build from source.
```

Verification command shape:

```bash
prusti-rustc src/lib.rs
```

Notes:

- Prusti verifies absence of panics/overflows and supports preconditions, postconditions, and loop invariants.
- It depends on the Viper infrastructure and specific Rust toolchain assumptions.
- Keep it as an alternative Rust backend after Verus or Creusot is stable.

### 6.5 Python: Nagini

Candidate file: `docker/python-nagini.Dockerfile`

```dockerfile
FROM python:3.12-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git build-essential python3-dev default-jre unzip \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip virtualenv \
    && python -m pip install nagini

RUN nagini --help
```

Verification command shape:

```bash
nagini --verifier silicon solution.py
```

Pipeline target:

```text
Requirement -> Nagini contracts -> typed Python code -> nagini
```

Notes:

- Nagini is a static verifier for statically typed Python programs, based on Viper.
- Current docs require Java 11+ and Python 3.12 to 3.14.
- Some runs may need an explicit Z3 path. If reproducibility becomes unstable, pin Z3 to the version recommended by Nagini docs.

### 6.6 Python: CrossHair

Candidate file: `docker/python-crosshair.Dockerfile`

```dockerfile
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip \
    && python -m pip install crosshair-tool icontract deal

RUN crosshair check --help
```

Verification command shape:

```bash
crosshair check solution.py --analysis_kind=icontract
```

Pipeline target:

```text
Requirement -> Python contracts -> Python code -> crosshair check
```

Notes:

- CrossHair checks contracts with symbolic execution and can produce counterexamples.
- It supports assert-based, PEP 316, icontract, and deal-style contracts.
- Its result should be interpreted as contract counterexample search, not as full deductive verification equivalent to Frama-C/WP.

## 7. Recommended rollout

Do not start by implementing all languages at once. Recommended order:

1. Keep the current C/ACSL/Frama-C 100-problem benchmark as the C track, with the legacy 51-problem files retained for reproducibility.
2. Add a Java/JML/OpenJML track with Java-appropriate problems, not direct ports of all C problems.
3. Reuse the existing evaluation shape: code validity, spec coverage, and joint success.
4. Add Rust with one backend only, preferably Verus for the first pilot.
5. Add Python as a separate dynamic-language contract track.
6. Add an optional cross-language core subset only after at least two language-specific tracks are stable.

The first milestone should be:

```text
existing 100 C problems available as the C track
new Java problem set
Java/JML/OpenJML verifier adapter
Java-specific ground-truth JML clauses
same final metrics as current benchmark
```

Once this is stable, extend to Rust and language-specific memory-safety or ownership-focused tasks. A small cross-language core set can be added later if the benchmark needs direct comparability across languages.

## 8. Open design questions

- Should a small optional cross-language core subset be added after language-specific tracks are stable?
- If such a subset is added, is `semantic_targets.json` worth the maintenance cost?
- Should verifier-specific auxiliary proof obligations be excluded from requirement coverage, as in the current ACSL benchmark?
- For Rust, should the first backend be Verus or Creusot?
- For Python, should the track be Nagini-first or CrossHair-first?
- Should memory safety properties be reported as a separate metric from functional correctness?

Current recommendation:

- Use Java/OpenJML to validate the multi-language architecture with Java-specific problems.
- Use Verus for the first Rust pilot.
- Use CrossHair only for a lightweight Python track, and Nagini for a stricter but heavier static-verification track.
- Do not require all C problems to be ported to every language.
- Keep code validity, spec coverage, and joint success as the main benchmark metrics.
