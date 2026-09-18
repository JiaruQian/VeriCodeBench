# Self-Spec Verifiable Code Generation

Large language models (LLMs) may generate unreliable code on corner cases missed by testing, while formal verification can provide machine-checkable guarantees. 
Recently, researchers have proposed several benchmarks to evaluate the capabilities
of LLMs in generating formally verifiable code. An LLM needs to formulate formal specifications, generate the corresponding code, and verify its correctness.
However, existing benchmarks have two key limitations:
(I) They only evaluate specification and code generation independently, where code generation is typically conditioned on an oracle specification. This setup overlooks how specification errors can propagate to code generation and verification in realistic use.
(II) They mainly focus on a single proof-oriented language and mathematically structured tasks, offering limited coverage of tasks common in software development.
In this paper, we introduce \textsc{VeriCodeBench}, a benchmark for \underline{self-spec} verifiable code generation, where the LLM relies solely on its own generated specification and code throughout the entire process.  \textsc{VeriCodeBench} contains 400 language-native problems across C, Java, Rust, and Python, covering practical concerns in software development. We evaluate specification coverage, code validity, and joint problem-level success across representative LLMs. We further introduce \textsc{CodeNova} to enhance the capabilities of LLMs in self-spec verifiable code generation. \textsc{CodeNova} makes requirements explicit through constraint-guided specification and uses verifier feedback to guide targeted implementation repairs. 
Experimental results reveal that self-generated specification remain a major bottleneck for formal verification, while increasingly detailed specifications do not necessarily yield higher verification success.

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
docker build --platform linux/amd64 -t codenova-benchmark:dev .
```

Run it with the repository mounted at `/workspace`:

```bash
docker run -dit --name codenova-benchmark \
  --platform linux/amd64 \
  -v "$(pwd)":/workspace \
  codenova-benchmark:dev

docker exec -it codenova-benchmark /bin/bash
```

Inside the container, most commands assume:

```bash
cd /workspace
export PYTHONPATH=/workspace
```

## Run Requirement -> Spec -> Code

The current runnable generation pipeline is the C/ACSL backend. It implements \textsc{CodeNova}, which combines Constraint-Guided Specification (CGS) with Verifier-Guided Candidate Repair (VGCR). CGS extracts atomic behavioral and safety constraints from the requirement, translates them into the target contract language, and self-checks the resulting contract. VGCR then uses native verifier diagnostics to plan repairs and propose focused implementation candidates while keeping the generated contract fixed. The backend uses an OpenAI-compatible endpoint, and the helper script is configured for OpenRouter by default.

The pipeline exposes four configurations that match the paper: **Direct** (`PIPELINE_VARIANT=base`), **CGS** (`base+cgs`), **VGCR** (`base+vgcr`), and **CodeNova** (`base+cgs+vgcr`).

Detailed instructions can be found in docs/requirement_to_code_pipeline.md + scripts/run_()_constraint_entailment_evaluation.sh + scripts/run_req2code_benchmark_summary.sh