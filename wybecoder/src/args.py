# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import asdict, dataclass
from pathlib import Path
import yaml


def get_root_dump_dir() -> str:
    return str(Path("runs") / "dumps")


@dataclass
class RunArgs:
    name: str
    dump_dir: str | None = None

    task: str = "clever_full"
    problems: str = "data/clever_loom.jsonl"
    n_attempts: int = 1
    max_turns: int = 1
    max_repls: int = 20
    max_usage: int = 50
    n_worker_threads: int = 40
    imperativeness_judge: bool = True  # use LLM to judge whether method is imperative

    # multiagent settings:
    # maximum number of concurrent subagents on a problem, 0 for linear agent
    n_subagents: int = 0
    max_subagents: int = 8  # maxmum number of subagents per problem

    # for lemma writing (multi.py):
    merge_review: bool = True  # use LLM to judge whether to add code to the file
    allow_partial_proofs: bool = (
        False  # allow final proof subagents to return partial proofs
    )

    # for hierarchical (decomp.py):
    provers_per_goal: int = (
        0  # number of provers to try per goal, 0 for lemma multiagent
    )
    max_prover_turns: int = 8  # maximum number of turns for each prover subagent

    model: str = "gemini-2.5-pro"  # "gpt-5", "vllm-gptoss"
    prover_model: str | None = None  # if None, use `model` for prover as well
    temperature: float = 1.0

    # vLLM-specific configuration (if `model` contains "vllm")
    vllm_base_url: str | None = None  # None for self-hosted server (auto-start)

    # vLLM server auto-start configuration
    vllm_model_path: str = ""  # Path to model (can be same as model, or different)
    vllm_tensor_parallel_size: int = 1  # Number of GPUs for tensor parallelism
    vllm_server_timeout: float = 300.0  # Server startup timeout in seconds
    vllm_extra_args: dict[str, str | int | float | bool | None] | None = (
        None  # Extra vLLM CLI args
    )

    use_mcp: bool = False  # Enable MCP tool integration
    use_loogle: bool = False
    use_leanexplore: bool = False

    use_cheatsheet: bool = False  # include API docs in the prompt

    # prompt configuration
    prompt_path: str = "data/prompt_linear.md"  # path to main system prompt

    allow_subgoal_change: bool = False

    @property
    def provers_per_goal_with_fallback(self) -> int:
        """Account for extra fallback attempt when using a small prover model."""
        return self.provers_per_goal + int(self.prover_model is not None)

    @property
    def needs_vllm(self) -> bool:
        return "vllm" in self.model or (
            self.prover_model is not None and "vllm" in self.prover_model
        )

    def __post_init__(self):
        if self.dump_dir is None:
            self.dump_dir = str(Path(get_root_dump_dir()) / self.name)

    def to_yaml(self) -> str:
        return yaml.dump(asdict(self), sort_keys=False)
