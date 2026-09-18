# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from logging import getLogger
from queue import Queue
from threading import Event
from time import time

from src.agent import chat
from src.args import RunArgs
from src.data import (
    Action,
    AgentResult,
    Declaration,
    detect_action,
    filter_decls,
    GlobalContext,
    LeanFile,
    make_decls,
    Method,
    MultiAgentRollout,
    OtherLean,
    ProblemContext,
    Theorem,
)
from src.env import Dialog, Env, Message, Outcomes, Task
from src.pool import ResourcePool
from src.repl import LeanRepl
from src.review import review_merge
from src.review_method import review as review_method, REVIEW_FEEDBACK_PROMPT
from src.utils import (
    incremental_dump,
    incremental_dump_path,
    normalize_whitespace,
    remove_multiline_comments,
    render_diff,
)


logger = getLogger()


def make_file(
    file: LeanFile, action: Action, task: Task, decls: list[Declaration]
) -> LeanFile:
    file = deepcopy(file)
    match action:
        case Action.METHOD:
            file.decls = file.decls[: file.method_idx + 1]
            mth = file.method
            assert isinstance(mth, Method)
            file.decls[-1] = mth.with_body(decls[0].render())  # make sure to keep spec
            file.add_idx = len(file.decls) - 1
        case Action.PROVE_CORRECT:
            mth = file.method
            assert isinstance(mth, Method)
            thm = mth.correctness_theorem()
            new_thm = decls[0]
            assert (
                new_thm.theorem_type == "prove_correct"
            ), f"Expected prove_correct theorem: {new_thm}"
            # allow set_option etc but still enforce same statement
            assert normalize_whitespace(thm.statement) in normalize_whitespace(
                new_thm.statement
            ), f"prove_correct theorem statement changed: {thm.statement} vs {new_thm.statement}"
            file.decls[-1] = new_thm
            file.add_idx = len(file.decls) - 1
        case Action.ADD:
            file.decls = file.decls[:-1]  # remove correctness theorem
            file.add_idx = len(file.decls)
            file.decls += decls
        case Action.DISPROVE:
            thm = Theorem.unsat_theorem_from_task(task)
            new_thm = decls[0]
            if normalize_whitespace(thm.statement) != normalize_whitespace(
                new_thm.statement
            ):
                logger.warning(
                    f"Copying proof of unsat_theorem although the statement changed: "
                    f"{thm.statement} vs {new_thm.statement}"
                )
            file.decls[-1] = thm
            thm.proof = new_thm.proof
            thm.metadata = new_thm.metadata
            file.add_idx = len(file.decls) - 1
        case Action.EMPTY:
            pass
        case _:
            logger.warning(f"Invalid action {action}")
    return file


def implement(
    ctx: ProblemContext,
    dialog: Dialog,
    file: LeanFile,
    sub_id: int,
    turn_budget: int | None = None,
) -> tuple[AgentResult, Outcomes, LeanFile]:
    """
    Starts with env turn.
    Checks `ctx.done_event` before LLM calls and execution.
    """
    start = time()
    outcomes: Outcomes = {"pass": False}
    if turn_budget is None:
        turn_budget = ctx.args.max_turns
    assert turn_budget > 0
    for i in range(turn_budget):
        if ctx.done_event.is_set():
            return (
                AgentResult.mk_failed(sub_id, dialog, start=start),
                {"pass": False},
                file,
            )

        if i > 0:
            reply: Message = chat(
                dialog, ctx.args.model, ctx.args.temperature, ctx.args.use_mcp
            )
            dialog.append(reply)
            code = Env.extract_code(reply.content)
            code = remove_multiline_comments(code)
            decls = make_decls(code)
            decls = filter_decls(decls, Action.METHOD)  # prescribe METHOD
            file = make_file(file, Action.METHOD, ctx.task, decls)

        if ctx.done_event.is_set():
            return (
                AgentResult.mk_failed(sub_id, dialog, start=start),
                {"pass": False},
                file,
            )
        feedback, outcomes = ctx.env.step(
            ctx.runner, ctx.task, file.render(), extract=False, final=False
        )
        file.errors = feedback

        # next prompt
        if feedback:
            dialog.append(
                Message.user(IMPLEMENTATION_FOLLOWUP_PROMPT.format(errors=feedback))
            )
        else:
            # success or imperativeness check
            # reason not saved here but available in dialog
            accept, reason = review_method(ctx.args, ctx.task, file.method.render())
            if accept:
                break
            logger.info(
                f"Sub-agent {sub_id} proposed method change but it was rejected: {reason}"
            )
            dialog.append(Message.user(REVIEW_FEEDBACK_PROMPT.format(reason=reason)))

    else:
        logger.info(
            f"Implementer sub-agent {sub_id} reached max turns without success."
        )
        return AgentResult.mk_failed(sub_id, dialog, start=start), outcomes, file

    logger.info("SUCCESS! Returning from implementer")
    result = AgentResult.mk_multi(
        sub_id, Action.METHOD, [file.method], dialog, start=start
    )
    return result, outcomes, file


def sub_agent(
    ctx: ProblemContext, dialog: Dialog, errors: str, sub_id: int
) -> AgentResult:
    """
    Checks `ctx.done_event` before LLM calls and execution.
    """
    start = time()
    feedback: str | None = errors
    file = deepcopy(ctx.current)
    dialog.append(
        Message.user(DECIDE_PROMPT.format(code=file.render(), errors=feedback))
    )
    for i in range(ctx.args.max_turns):
        if ctx.done_event.is_set():
            return AgentResult.mk_failed(sub_id, dialog, start=start)
        reply: Message = chat(
            dialog,
            ctx.args.model,
            ctx.args.temperature,
            ctx.args.use_mcp,
        )
        dialog.append(reply)
        code = Env.extract_code(reply.content)
        code = remove_multiline_comments(code)
        decls = make_decls(code)
        action = detect_action(decls)
        decls = filter_decls(decls, action)
        file = make_file(file, action, ctx.task, decls)
        logger.info(f"Sub-agent {sub_id} turn {i}: {action}")
        if action == Action.METHOD:
            result, _, _ = implement(
                ctx, dialog, file, sub_id, turn_budget=ctx.args.max_turns - i
            )
            return result

        if ctx.done_event.is_set():
            return AgentResult.mk_failed(sub_id, dialog, start=start)
        # logger.info(f"Sub-agent {sub_id} turn {i} running code:\n{file.render()}")
        feedback, outcomes = ctx.env.step(
            ctx.runner, ctx.task, file.render(), extract=False, final=False
        )
        if not feedback:
            break

        dialog.append(Message.user(FOLLOWUP_PROMPT.format(errors=feedback)))

    if action in {Action.ADD, Action.PROVE_CORRECT, Action.DISPROVE}:
        feedback_str = feedback or "Success! No errors."
        dialog.append(
            Message.user(
                LEARNING_PROMPT.format(code=file.render(), errors=feedback_str)
            )
        )
        learning_msg: Message = chat(dialog, ctx.args.model, ctx.args.temperature)
        dialog.append(learning_msg)
        learning = learning_msg.content
    else:
        # these almost always succeed, so not interesting to take learnings from
        learning = None

    if outcomes["pass"] or (
        ctx.args.allow_partial_proofs
        and action in {Action.PROVE_CORRECT, Action.DISPROVE}
    ):
        logger.info(
            f"Returning from subagent with {action}. "
            f"(success={outcomes['pass']}, partial_allowed={ctx.args.allow_partial_proofs})"
        )
        result = AgentResult.mk_multi(
            sub_id,
            action,
            file.decls[file.add_idx :],
            dialog,
            learning=learning,
            errors=feedback,
            start=start,
        )
        return result

    else:
        logger.info("Subagent timed out.")
        return AgentResult.mk_failed(sub_id, dialog, learning=learning, start=start)


def initial(
    task: Task,
    env: Env,
    runner: LeanRepl | ResourcePool,
    args: RunArgs,
    done_event: Event,
) -> tuple[ProblemContext, Outcomes, Dialog, AgentResult]:
    header = task["loom_header"].split("method")[0]
    method_spec_str = "method" + task["loom_header"].split("method", maxsplit=1)[-1]
    method_spec = Method.from_str(method_spec_str)
    dialog = env.initial(task)

    # multiturn: method syntax check + imperativeness judge
    reply: Message = chat(dialog, args.model, args.temperature)
    dialog.append(reply)
    code = Env.extract_code(reply.content).strip()
    method = method_spec.with_body(code)
    method.source = [0]
    header_block = OtherLean(header, source=[0])
    file = LeanFile([header_block, method])
    global_ctx = GlobalContext(env, runner, args)
    ctx = ProblemContext(global_ctx, done_event, task, {0: dialog}, [file])
    logger.info(f"Initial file:\n{file.render()}")
    result, outcomes, file = implement(ctx, dialog, file, sub_id=0)
    result.merged = True
    result.merge_reason = "Initial attempt."

    # add default correctness theorem
    method = file.method
    correctness_thm = method.default_correctness_theorem()
    correctness_thm.source = [0]
    file = LeanFile([header_block, method, correctness_thm])
    ctx.revisions[-1] = file

    # run initial attempt with correctness theorem
    feedback, outcomes = ctx.env.step(
        ctx.runner, ctx.task, file.render(), extract=False, final=False
    )
    file.errors = feedback
    return ctx, outcomes, dialog, result


def rollout(
    env: Env,
    runner: LeanRepl | ResourcePool,
    task: Task,
    args: RunArgs,
) -> MultiAgentRollout:
    thread_name = threading.current_thread().name
    inc_dir = incremental_dump_path(args.dump_dir, thread_name)
    inc_dir.mkdir(parents=True, exist_ok=True)
    inc_file = inc_dir / f"{task['id']}.jsonl"

    result_q: Queue[AgentResult | None] = Queue()
    done_event = Event()
    executor = ThreadPoolExecutor(
        max_workers=args.n_subagents, thread_name_prefix=f"{thread_name}-SubagentWorker"
    )
    sub_id = 0  # running sub-agent id, 0 for main

    def dump(terminated: bool) -> MultiAgentRollout:
        rollout_result = MultiAgentRollout(
            task=task,
            outcomes=outcomes,
            n_subs=sub_id + 1,
            dialogs=ctx.dialogs,
            revisions=ctx.revisions,
            learnings=ctx.learnings,
            agent_results=ctx.agent_results,
            terminated=terminated,
        )
        incremental_dump(inc_file, rollout_result.to_dict())
        return rollout_result

    def sub_agent_wrapper(errors_pp: str, sub_id: int) -> None:
        start = time()
        try:
            res: AgentResult = sub_agent(
                ctx, deepcopy(dialog), errors_pp, sub_id=sub_id
            )
            if not done_event.is_set():
                result_q.put(res)
        except Exception:
            logger.exception(f"Sub-agent {sub_id} raised an exception:")
            res = AgentResult.mk_failed(sub_id, deepcopy(dialog), start=start)
            result_q.put(res)

    def launch(errors_pp: str) -> None:
        nonlocal sub_id
        sub_id += 1
        executor.submit(sub_agent_wrapper, errors_pp, sub_id)

    def process_result(res: AgentResult) -> None:
        logger.info(f"Sub-agent returned {res.action}")
        res.timestamp = time()

        for decl in res.decls:
            logger.info(f"Received new declaration:\n{decl.render()}")

        # annotate diff at receipt time
        current_code = ctx.current.render()
        proposed: LeanFile = ctx.current.add_decls(ctx.task, res)
        res.diff = render_diff(current_code, proposed.render())

        should_merge, reason = review_merge(ctx, res)
        res.merged = should_merge
        res.merge_reason = reason

        if should_merge:
            logger.info(f"Merge approved: {reason}")
            ctx.revisions.append(proposed)
        else:
            logger.info(f"Merge rejected: {reason}")

        res.revision_idx = len(ctx.revisions)

        if res.learning is not None:
            logger.info(f"Received learning:\n{res.learning}")
            ctx.learnings.append(res.learning)

        ctx.dialogs[res.sub_id] = res.dialog
        ctx.agent_results[res.sub_id] = res

        logger.info(f"Current file contents:\n{ctx.current.render()}")

    # set up context
    ctx, outcomes, dialog, res = initial(task, env, runner, args, done_event)
    ctx.agent_results[0] = res
    errors = ctx.current.errors

    if outcomes["pass"]:
        return dump(terminated=True)

    try:
        for _ in range(args.n_subagents):
            launch(errors)
        n_active = args.n_subagents

        while n_active > 0:
            res: AgentResult | None = result_q.get()
            if done_event.is_set():
                break

            process_result(res)
            errors_pp, outcomes = env.step(
                runner, task, ctx.current.render(), extract=False, final=False
            )
            if outcomes["pass"]:
                # rerun with final checks
                errors_pp, outcomes = env.step(
                    runner, task, ctx.current.render(), extract=False, final=True
                )

            errors = errors_pp or ""
            ctx.current.errors = errors
            logger.info(f"Current errors:\n{errors}")

            if outcomes["pass"]:
                logger.info("SUCCESS! Leaving multi-agent rollout.")
                done_event.set()
                # drain queue
                while not result_q.empty():
                    try:
                        result_q.get_nowait()
                    except queue.Empty:
                        break

                break

            if sub_id + 1 < args.max_subagents:
                launch(errors)
            else:
                # not relaunching, one returned
                n_active -= 1

            dump(terminated=False)

        return dump(terminated=True)

    finally:
        executor.shutdown(wait=True, cancel_futures=True)


DECIDE_PROMPT = """
I ran the following proof attempt to prove this method:

```lean
{code}
```

But I got the following errors. We will now go into an iterative
refinement process where we add content to the file and improve it bit by bit
until we have a full correct proof.

Could you please decide on one angle for making progress on the proof in this file,
by using Options 1-5 described above and summarized below.
Remember to only return the code that should be added
or replaced -- not the full file -- in triple backticks.
Note that you cannot delete any declarations but modify the
`method` and `prove_correct` blocks if necessary.

Specifically, you can pick exactly one of the following:
1. Redact the `method` declaration.
   Make sure your code starts with the `method` keyword for this
   and ONLY return the updated `method` block.
2. Redact the `prove_correct` block.
   Make sure your code starts with the `prove_correct` keyword for this
   and ONLY return the updated `prove_correct` block.
3. State and prove one or multiple theorems, set options or `attribute`s.
   This action will be selected in all other cases.
   ONLY return the code block you want to add.
   It will be inserted above the `prove_correct` block
   and below any of the other existing declarations you see in the file I shared above.

   You can include several declarations (e.g. a definition and a theorem,
   or a theorem and an attribute), but please keep your edit self-contained
   and minimal to faciliate checking and review (we can always add more theorems later).
   Please separate declarations/blocks by empty lines, do not put empty lines inside proofs
   and do not use namespace declarations and non-standard Lean declaration syntax
   as the output is post-processed by a simple Python script.

   Note that you should basically always tag new theorems with automation
   tags like `solverHint` or `grind`.

Note that it can be very useful to pick `prove_correct` if it feels
like the proof of the remaining proof obligations should be doable
in a few rounds of interactive proving, or for instance if dedicated
`simp_all` calls with appropriate lemmas can resolve the remaining goals better than
pure automation.
Also, auxiliary theorems can be very helpful in the long run even if
they are not sufficient by themselves to complete the proof.
Changing the `method` is most useful if you know that there is a bug or conceptual
error, you want to add invariants or know which alternate approach would make
verification easier. Do not simply try changing the method and hoping that the
SMT solver will miraculously succeed.

In some cases, it may turn out that the specification is actually unsatisfiable.
In this case, you can pick option 3 and prove the unsatisfiability theorem stated at the very beginning instead.
Of course you can also prove other theorems or set attributes to prepare for and facilitate that.

The errors I encountered:

{errors}
""".strip()


FOLLOWUP_PROMPT = """
I ran the code but got the following errors.
Could you please figure out what went wrong and fix them?
Please return the new code for the block you suggested/edited above, again in triple backticks.

{errors}

# NOTE

In case you figure out that another part of the file needs to be changed instead,
you can decide to switch between the provided actions anytime
(e.g. modifying the `method` instead of the `prove_correct` block).
""".strip()


IMPLEMENTATION_FOLLOWUP_PROMPT = """
I ran the code but got the following errors.
Could you please figure out what went wrong and fix them?
Please return the new code for the method, again in triple backticks.

{errors}
""".strip()


LEARNING_PROMPT = """
I ran this code
```lean
{code}
```

and got:
{errors}

Based on our above conversation, can you summarize learnings that could be useful
for continued work on this problem?
I will discard our conversation but provide you with the notes / hints / learnings
that you provide here.
Please return ONLY the learnings in Markdown formatting.
""".strip()
