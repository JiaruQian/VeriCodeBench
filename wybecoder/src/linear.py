# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from src.agent import chat
from src.args import RunArgs
from src.data import LinearRollout
from src.env import Env, Message, Task
from src.pool import ResourcePool
from src.repl import LeanRepl
from src.review_method import REVIEW_FEEDBACK_PROMPT, review


def rollout(
    env: Env,
    runner: LeanRepl | ResourcePool,
    task: Task,
    args: RunArgs,
) -> LinearRollout:
    dialog = env.initial(task)
    for i in range(args.max_turns):
        msg = chat(
            dialog,
            args.model,
            args.temperature,
            args.use_mcp,
        )
        dialog.append(msg)
        feedback, outcomes = env.step(runner, task, msg.content)
        if outcomes["pass"] and args.imperativeness_judge:  # correctness proof
            code = Env.extract_code(msg.content).strip()
            accept, reason = review(args, task, code)
            outcomes["imperative"] = accept
            outcomes["pass_judged"] = outcomes["pass"] and accept
            if accept:
                break
            dialog.append(Message.user(REVIEW_FEEDBACK_PROMPT.format(reason=reason)))
        elif outcomes["pass"] or outcomes["disproof_pass"] or outcomes["abort"]:
            # correctness proof or spec disproof or abort
            break
        else:
            dialog.append(Message.user(feedback))

    return LinearRollout(
        task=task,
        outcomes=outcomes,
        n_turns=i + 1,
        dialog=dialog,
    )
