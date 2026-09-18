# WybeCoder: Verified Imperative Code Generation

**WybeCoder** is an agentic code verification framework that enables *prove-as-you-generate* development where code, invariants, and proofs co-evolve. It combines automatic verification condition generation and SMT solvers (cvc5) with interactive proofs in Lean 4, operating on [Velvet](https://github.com/faabian/loom) — a Dafny-like imperative language embedded in Lean 4 via the Loom framework.

> Named in homage to Edsger *Wybe* Dijkstra.

**Paper:** [WybeCoder: Verified Imperative Code Generation](https://facebookresearch.github.io/wybecoder/paper.pdf)

**Project page:** [https://facebookresearch.github.io/wybecoder](https://facebookresearch.github.io/wybecoder)


## Results

| Benchmark | Solve Rate | Details |
|---|---|---|
| **Verina** (189 problems) | **74.1%** | 128 proved + 12 disproved (Claude Opus 4.5, 32 turns x 16 agents) |
| **Clever-Loom** (161 problems) | **62.1%** | 100 / 161 problems solved (Claude Opus 4.5, 32 turns x 16 agents) |

## Agent Strategies

- **Sequential Agent** — Single-agent turn-based loop with iterative refinement. Multiple independent attempts run in parallel (pass@k).
- **Subgoal Decomposition** — Extracts verification subgoals, dispatches parallel provers, and reconstructs the full proof. Supports conflict-driven method modification across iterations.

## Installation

### Python environment

```bash
micromamba create -n wybecoder python=3.12
micromamba activate wybecoder
pip install -r requirements.txt
```

### Lean setup

```bash
lake update          # downloads Loom, loogle, and precompiled Mathlib
cd .lake/packages/Loom
lake build Loom CaseStudies Mathlib REPL
cd ../loogle
lake exe cache get && lake build LoogleMathlibCache && lake build
cd ../../..          # back to repo root
```

Recent Loom should automatically install the **cvc5** prover.
Manual installation (if needed):
- macOS: `brew install --cask cvc5/cvc5/cvc5`
- Linux: download from the [cvc5 releases page](https://github.com/cvc5/cvc5/releases/tag/cvc5-1.3.1)
- Verify: `which cvc5`

### Verify your setup

Run the quick-start command below with `--max_repls 1` to confirm that the Lean REPL starts and the model API responds (see [Quick Start](#quick-start)).

## API Keys

Set the environment variable for the model provider you plan to use:

| Model prefix | Provider | Environment variable |
|---|---|---|
| `gemini-*` | Google Gemini | `GOOGLE_API_KEY` |
| `claude-*` | Llama API (hosts Claude via Vertex) | `LLAMA_API_KEY` |
| `gpt-*` | Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` |
| `vllm-*` | Local vLLM server | None (auto-started or set `vllm_base_url`) |

## Quick Start

Run a lightweight smoke test (2 workers, 1 attempt):

```bash
export LLAMA_API_KEY=your-key        # or GOOGLE_API_KEY for Gemini configs
python -m src.worker configs/other_models/clever_linear_claude_4_5_sonnet_32t_32agents.yaml \
  --n_worker_threads 2 --n_attempts 1 --max_repls 2
```

You should see `Started successfully with config: ...` followed by HTTP 200 responses. Results are written to `runs/dumps/<run_name>/trajectories/`. Kill with Ctrl-C once satisfied.

View results with the trajectory viewer:

```bash
python scripts/build_viewer_data.py   # generate viewer data
python scripts/serve_viewer.py        # serve at http://localhost:8000/viewer.html
```

## Running Full Experiments

Single node:
```bash
python -m src.worker configs/decomp.yaml
```

Multi-node with SLURM:
```bash
srun -N <nodes> --ntasks-per-node=1 python -u -m src.worker configs/decomp.yaml
```

### Available Configs

| Directory | Strategy | Examples |
|---|---|---|
| `configs/` | Decomposition / multi-agent | `decomp.yaml`, `clever_decomp.yaml`, `multi.yaml`, `sort_decomp.yaml` |
| `configs/other_models/` | Sequential (linear) agent | `clever_linear_claude_4_5_sonnet_32t_32agents.yaml`, `verina_linear_gemini_2_5_pro_32t_32agents.yaml` |
| `configs/ablation/` | Ablation studies | `a1_no_invariant.yaml`, `a2_no_fallback.yaml`, ... |

## Datasets

- **Clever-Loom** (`data/clever_loom.jsonl`) — 161 algorithm and data structure problems from the CLEVER benchmark, manually converted and verified in Loom format.
- **Verina** — 189 program verification problems. Convert to Loom format with `python -m scripts.verina_to_loom`.
- **Sorting** (`data/sorting.jsonl`) — Sorting algorithm verification (Heapsort, Mergesort, Quicksort, etc.).

## MCP Integration (Optional)

The agent supports [Model Context Protocol](https://modelcontextprotocol.io/) integration for enhanced theorem search via **Loogle** and **Leanexplore**.

### Setup

```bash
# Loogle
./src/start_loogle_server.sh       # starts on localhost:8088
python -m scripts.test_loogle

# Leanexplore
leanexplore data fetch
python -m scripts.test_leanexplore

# Test both together
python -m scripts.test_mcp

# End-to-end with the agent
python -m scripts.test_agent_with_mcp
```

Enable in a config:
```yaml
use_mcp: true
use_loogle: true
use_leanexplore: true
```

See [`docs/mcp_architecture.md`](docs/mcp_architecture.md) for implementation details.

## Citation

```bibtex
@article{gloeckle2026wybecoder,
  title     = {WybeCoder: Verified Imperative Code Generation},
  author    = {Gloeckle, Fabian and Bak{\v{s}}ys, Mantas and Feher, Darius
               and Zheng, Kunhao and Hayat, Amaury and Holden, Sean B.
               and Synnaeve, Gabriel and O'Hearn, Peter},
  journal   = {Preprint},
  year      = {2026}
}
```

## License

This project is licensed under CC-BY-NC 4.0. See [LICENSE](LICENSE) for details.
