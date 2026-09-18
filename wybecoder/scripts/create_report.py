# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from pathlib import Path
import json
import fire

from src.llm_reduce import main as summarize_run
from src.utils import initialize_logger


def main(
    input_dir: str, output_path: str, batch_size: int = 8, max_concurrent: int = 100
):
    trajs = []
    for fn in Path(input_dir).glob("*.jsonl"):
        with fn.open() as f:
            trajs += [json.loads(line) for line in f]

    aborted = [d for d in trajs if d["abort"] and not d["pass"]]
    summarize_run(
        aborted,
        output_path,
        "data/snippet.prompt",
        "data/extract.prompt",
        "data/join.prompt",
        batch_size,
        max_concurrent,
    )


if __name__ == "__main__":
    initialize_logger(level="INFO")
    fire.Fire(main)
