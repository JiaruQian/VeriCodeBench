# Multi-language Requirement-to-Code Verification Benchmark Plan

本文档记录将当前 C/ACSL/Frama-C benchmark 扩展到 Java、Rust、Python 的设计思路、容器策略和验证器环境建议。

当前仓库的核心任务是：

```text
Requirement -> ACSL Spec -> C Code -> Frama-C/WP Verification
```

多语言扩展后，不应把任务理解为简单替换语法，而应抽象为：

```text
Requirement -> Language-specific Spec -> Code -> Verifier -> Spec Coverage
```

其中 `ACSL + Frama-C` 是 C 后端；Java、Rust、Python 分别引入自己的规格语言和验证器后端。

截至当前里程碑，C/ACSL/Frama-C track 已完成并作为迁移基线：ground-truth clauses 已审计，
ACSL entailment parser 已覆盖主要语法边界，100 道题的 code-only oracle contracts、合同强制
恢复、reference validation 和 full-chain 重评估均已落地。后续语言必须保持相同的 artifact
链路和指标语义，同时实现语言专属的 contract parser、verifier adapter 与 oracle 数据；不能
假设 ACSL 文本或 Frama-C 的证明规则可以直接复用。

## 1. 总体判断

当前 benchmark 可以扩展到 Java、Rust 和 Python，但三者成熟度不同：

| Language | Recommended stage | Spec ecosystem | Verifier candidates | Fit with current paradigm |
| --- | --- | --- | --- | --- |
| C | existing | ACSL | Frama-C/WP | baseline |
| Java | stage 1 | JML | OpenJML, KeY | very close |
| Rust | stage 2 / active Verus track | Verus contracts | Verus | strong but verifier-specific |
| Python | stage 3 / separate track | Nagini contracts, CrossHair contracts | Nagini, CrossHair | useful but not equivalent |

Java 是最自然的第一扩展对象。JML 和 ACSL 都是源代码旁边的契约式规格，OpenJML 可以直接检查 Java 程序中的 JML 注解。

Rust 很有研究价值，因为它能体现 C 和 Rust 在内存安全、aliasing、ownership、panic freedom 上的差异。但 Rust 没有统一的 ACSL 等价物，不同验证器的规格语言和受支持 Rust 子集差别较大。本仓库当前 Rust track 选用 Verus，数据集位于 `benchmarks/rust-verus-problems`，pipeline 入口为 `scripts/run_rust_requirement_pipeline.py` 和 `scripts/run_openrouter_rust_requirement_pipeline.sh`。

Python 更适合作为 dynamic-language contract verification track。当前 Python track 选用 Nagini，
数据集位于 `benchmarks/python-nagini-problems`，pipeline 入口为
`scripts/run_python_nagini_requirement_pipeline.py` 和
`scripts/run_openrouter_python_nagini_requirement_pipeline.sh`，coverage 入口为
`scripts/run_python_nagini_constraint_entailment_evaluation.sh`。Nagini 更接近静态验证，
CrossHair 更接近符号执行下的 contract checking。它们的结果不应和
Frama-C/OpenJML/Verus 直接混成一个总分。

## 2. Benchmark 架构抽象

建议把现有 pipeline 中和 C 强绑定的部分拆成三个后端接口。第一阶段不要求不同语言共享同一道题，也不要求维护统一的语言无关语义 IR；每种语言可以先使用最适合自身验证生态的题目和 ground truth。

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

推荐目录形态：

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

如果后期确实需要严格比较同一需求在不同语言上的表现，可以在 `cross_language_core_optional/` 中维护小规模重合题。这个子集可以再引入 `semantic_targets.json` 或其他语言无关 IR，但它不应成为第一阶段的必要条件。

## 3. 数据集扩容策略

建议第一阶段采用 language-specific 题库。也就是说，C 的 legacy 51 道题和当前 100 道题都不必全部移植到 Java、Rust、Python；不同语言应优先选择最适合自身验证生态的题目。

### 3.1 Why not directly port all 51 C problems

C 的题库里有一部分适合迁移到 Java/Rust/Python，例如数组遍历、查找、最大值、排序性、算术约束等。但并不是全部都适合作为多语言共享题。

不适合直接共享的原因：

- C 的很多题目围绕 pointer validity、aliasing、`\valid`、`\separated`、buffer bounds 和手动 frame condition，这些是 C/ACSL/Frama-C 的核心语义。
- Java 没有裸指针，内存安全问题更多体现为 nullability、object invariant、field frame、exception behavior。
- Rust 的 safe subset 已经通过 ownership/borrowing 排除了大量 C 前置条件，直接照搬 C 题会让 Rust 题目变得不自然。
- Python 的验证生态更适合 typed contracts、list/dict 行为和符号执行友好的函数，直接移植 C 指针题没有意义。

因此，C 题库可以作为题型灵感来源，而不是强制多语言母题。

### 3.2 Language-specific set

这部分题目体现每种语言自己的现实开发语义，是第一阶段的主数据集。

当前四种语言的题库已经落地为如下 category distribution。

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

这组题保留 C/ACSL baseline 的特征，覆盖 weakest-precondition 基础题、循环不变式、数组读写、指针操作、frame condition、buffer/pointer validity、字节/字符串 buffer、struct 字段 frame 和 C 整数边界等验证主题。

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

这组题重点覆盖 Java 自然语义中的数组边界、数组查询和更新、标量算术、布尔逻辑、字符串/字符基础性质、nullability、object invariant、field/object frame condition 和 exceptional behavior。

Rust/Verus (`benchmarks/rust-verus-problems`, 50 problems):

- `scalar_arithmetic`: 10
- `option_result`: 10
- `vec_immutable`: 12
- `vec_mutation`: 12
- `ownership_slices`: 6

这组题重点覆盖 safe Rust functional correctness、`Option`/`Result`、vector/slice bounds、panic freedom、ownership/borrowing 和 unique-borrow mutation。

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

这组题重点覆盖 typed function contracts、`Optional`/`None` compatibility、list/dict API 行为、container permission、mutation postcondition、symbolic-execution-friendly pure functions 和 simple API exception freedom。

语言特有题不应和跨语言题混成一个不可解释的总分。可以报告：

```text
language_specific_code_validity_rate
language_specific_requirement_coverage
language_specific_joint_success_rate
```

### 3.3 Optional cross-language core set

后期可以维护一个小规模 cross-language core set，用于回答“同一需求在不同语言/验证器下哪个更容易被模型完成”。这不是第一阶段的主线。

适合放入 optional core set 的题型：

- scalar arithmetic with overflow constraints
- array/list search
- max/min/sum/count
- sortedness
- binary search
- prefix sum
- swap or in-place update
- frame/no-mutation properties
- simple string or sequence transformations

optional core set 的指标应单独报告：

```text
core_code_validity_rate
core_requirement_coverage_micro
core_requirement_coverage_macro
core_joint_success_rate
```


## 4. 容器策略

建议每种语言一个或多个独立容器，不建议把所有验证器塞进单个大容器。验证器之间依赖冲突概率很高，尤其是 Rust verifier、Why3、Viper、Z3、Java runtime 和 opam。

推荐结构：

```text
docker/
  c-framac.Dockerfile
  java-openjml.Dockerfile
  rust-verus.Dockerfile
  rust-creusot.Dockerfile
  python-nagini.Dockerfile
  python-crosshair.Dockerfile
```

上层 runner 可以统一：

```bash
PYTHONPATH=. python3 scripts/run_multilang_pipeline.py \
  --language java \
  --verifier openjml \
  --requirements-file benchmarks/multilang/core/requirements.json \
  --output-dir outputs/multilang-java-openjml
```

底层通过不同 Docker image 执行 verifier：

```text
c/framac          -> Frama-C/WP
java/openjml      -> OpenJML
rust/verus        -> Verus
rust/creusot      -> Creusot + Why3
python/nagini     -> Nagini + Viper
python/crosshair  -> CrossHair
```

## 5. Docker Hub base image recommendations

以下是适合作为各语言 verifier 容器起点的 Docker Hub 官方镜像。

### 5.1 Java

Recommended base:

```dockerfile
FROM eclipse-temurin:21-jdk-noble
```

Alternative:

```dockerfile
FROM eclipse-temurin:25-jdk-noble
```

理由：

- `eclipse-temurin` 是 Docker Official Image。
- OpenJML 当前发行包自带 `openjml-java`，但安装和运行脚本仍需要稳定 JDK 环境。
- Java 21 是保守 LTS 选择；如果 OpenJML release 明确支持更新 JDK，可以升级到 Java 25。

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

理由：

- `rust` 是 Docker Official Image，适合安装 Rust verifier 和构建 Rust 项目。
- Verus 官方 binary release 对 Ubuntu 22.04 x86_64 有一等支持；如果直接使用 Verus 预编译包，`ubuntu:22.04 + rustup` 可能比 `rust:1-bookworm` 更稳。
- Creusot 通常需要 Rust、cargo、opam、Why3 和 SMT provers，建议单独建 `rust-creusot` 容器。

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

理由：

- `python` 是 Docker Official Image。
- Nagini 文档要求 Java 11+ 和 Python 3.12 到 3.14；`python:3.12-bookworm` 是较保守选择。
- CrossHair 的依赖轻得多，可以使用 slim 镜像。

Reference:

- https://hub.docker.com/_/python
- https://github.com/marcoeilers/nagini
- https://crosshair.readthedocs.io/en/latest/contracts.html

## 6. Verifier installation sketches

这些步骤是容器构造草案，不应视为已经锁定的 reproducible Dockerfile。正式落地时需要 pin verifier release、checksum 和 solver version。

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
