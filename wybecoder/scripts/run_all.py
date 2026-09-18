# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
from logging import getLogger

import fire

from src.env import HEADER
from src.utils import initialize_logger, method_spec_line

from src.repl import LeanRepl, filter_errors, format_errors, sorry_errors

logger = getLogger()


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f]


def main(
    jsonl: str,
    *,
    timeout: float = 300.0,
    init_timeout: float = 60.0,
    max_mem_mb: int = 10240,
):
    """
    Runs entries from a JSONL file using LeanRepl with cached `loom_header`.

    Reports formatted Lean errors (including `sorry` after method spec line, if found).
    """
    n_ok, n_err = 0, 0

    env = LeanRepl(header=HEADER, init_timeout=init_timeout, max_mem_mb=max_mem_mb)

    for i, d in enumerate(load_jsonl(jsonl)):
        code = d["loom_header"]
        logger.info(f"[item {i}] start (execute)")
        diagnostics = env.run(code, timeout=timeout)

        errors = diagnostics.get("messages", [])
        ran = diagnostics.get("executed_code")

        if filter_errors(errors):
            n_err += 1
            logger.error(f"[item {i}] FAILED\n{format_errors(ran, errors)}")
        else:
            n_ok += 1
            logger.info(f"[item {i}] OK (no errors)")

    logger.info(f"Done. OK={n_ok} ERR={n_err} TOTAL={n_ok + n_err}")


if __name__ == "__main__":
    initialize_logger()
    fire.Fire(main)
