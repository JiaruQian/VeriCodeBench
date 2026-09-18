# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from logging import getLogger
from queue import Empty, Queue
from subprocess import TimeoutExpired
from threading import Lock
from time import time

from src.agent import chat
from src.args import RunArgs
from src.data import (
    Action,
    AgentResult,
    Declaration,
    detect_prover_action,
    GlobalContext,
    HierachicalRollout,
    HierarchicalProof,
    LeanFile,
    make_decls,
    Method,
    OtherLean,
    ProblemContext,
    Theorem,
)
from src.env import CRASH_MESSAGE, Dialog, Env, Message, Task, TIMEOUT_MESSAGE
from src.envs.decomp_env import DecompEnvMixin
from src.parse_utils import (
    parse_theorem,
    remove_withname_erase,
    remove_withname_mk_erase,
)
from src.pool import ResourcePool
from src.prover_prompts import initial_prover_dialog, prover_followup_dialog
from src.repl import extract_goals_and_tags, LeanRepl
from src.review_method import review, REVIEW_FEEDBACK_PROMPT
from src.utils import (
    incremental_dump,
    incremental_dump_path,
    remove_multiline_comments,
    render_diff,
)


logger = getLogger()


MPROD_BLOCK = OtherLean(
    """macro_rules
  | `(MProdWithNames.mk $a $b) => `(MProdWithNames.mk' $a $b)"""
)


def clean_tag(tag: str) -> str:
    return tag.replace(".", "_").replace("ensures", "post")


def clean_statement(statement: str) -> str:
    statement = remove_withname_mk_erase(statement)
    statement = remove_withname_erase(statement)
    statement = statement.replace("«require»", "_require_")  # cf. revert_names
    statement = statement.replace("sorry", "by sorry")
    return statement


def extract_theorems(diagnostics: dict) -> tuple[list[Theorem], list[str]]:
    """Extract theorems and their tags from diagnostics.

    Returns:
        Tuple of (list of theorems, list of tags) - tags may have duplicates.
    """
    goals_and_tags = extract_goals_and_tags(diagnostics["messages"])
    thms = []
    tags = []
    for goal, tag in goals_and_tags:
        goal = clean_statement(goal)
        parsed = parse_theorem(goal)
        assert parsed is not None, f"Failed to parse theorem: {goal}"
        goal = goal.replace(parsed["name"], clean_tag(tag))
        thm = Theorem.from_str(goal)
        thm.proof = None
        thms.append(thm)
        tags.append(tag)
    return thms, tags


def make_proof_file(
    ctx: ProblemContext, file: LeanFile, decls: list[Declaration]
) -> LeanFile:
    """
    Return a new LeanFile with added auxiliary declarations and updated main theorem.
    If `ctx.args.allow_subgoal_change` is set, also allow changing the statement of the main theorem.
    """
    file = deepcopy(file)
    for decl in decls:
        if isinstance(decl, Method):
            raise ValueError("Method declaration update not expected in proof file")
        elif isinstance(decl, Theorem) and decl.name == file.main_theorem.name:
            if ctx.args.allow_subgoal_change:
                file.main_theorem = decl
            else:
                file.main_theorem.proof = decl.proof
                file.main_theorem.metadata = decl.metadata
        else:
            # insert above main theorem
            file.decls.insert(file.main_theorem_idx, decl)
    return file


def make_impl_file(file: LeanFile, decls: list[Declaration]) -> LeanFile:
    """
    Return a new LeanFile with updated method body.
    """
    file = deepcopy(file)
    for decl in decls:
        if isinstance(decl, Method):
            file.method.body = decl.body
        else:
            logger.warning(f"Dropping unexpected declaration in implementation: {decl}")
    return file


def make_final_file(file: LeanFile, decls: list[Declaration]) -> LeanFile:
    """
    Return a new LeanFile with added auxiliary declarations and updated main theorem proof.
    Do not allow changing the method implementation for risk of losing imperativeness.
    """
    file = deepcopy(file)
    for decl in decls:
        if isinstance(decl, Method):
            logger.warning("Dropping method redefinition in final file.")
        elif isinstance(decl, Theorem) and decl.name == file.main_theorem.name:
            file.main_theorem.proof = decl.proof
            file.main_theorem.metadata = decl.metadata
        else:
            # insert above main theorem
            file.decls.insert(file.main_theorem_idx, decl)
    return file


def prover(
    ctx: ProblemContext,
    sub_id: int,
    rev_id: int,
    goal_idx: int,
    use_prover_model: bool = True,
) -> tuple[AgentResult, HierarchicalProof | None]:
    """
    Optionally decide to update the method block instead and return the new revision.
    Otherwise try to prove the given goal by index and return everything in the AgentResult.
    """
    start = time()
    llm_times: list[float] = []
    lean_times: list[float] = []

    # Use prover_model if specified, otherwise use the main model

    if use_prover_model and ctx.args.prover_model is not None:
        prover_model = ctx.args.prover_model
    else:
        prover_model = ctx.args.model

    is_goedel = "goedel" in prover_model.lower()

    def check_done() -> bool:
        # check at each turn whether there is already a proof for this theorem
        # or a subagent decided that a method change is needed
        with ctx.lock:
            if (
                ctx.termination_reason
                or ctx.revisions[rev_id].goals[goal_idx].proof is not None
                or ctx.revisions[rev_id].proposals_raw[goal_idx]
            ):
                logger.info(
                    f"Sub-agent {sub_id} stopping early for theorem at index {goal_idx}."
                )
                return True
        return False

    def check_outdated() -> bool:
        # check at the beginning if we should solve "this" goal on a more recent revision
        # if already started, finish
        with ctx.lock:
            return rev_id != len(ctx.revisions) - 1

    with ctx.lock:
        dialog = deepcopy(ctx.base_dialog)
        rev: HierarchicalProof = ctx.revisions[rev_id]
        thm = rev.goals[goal_idx]
        goal_tag = rev.goal_tags[goal_idx]
        initial_code: str | None = None
        if rev_id > 0:
            prev: HierarchicalProof = ctx.revisions[rev_id - 1]
            prev_thm = prev.find_goal_by_tag(goal_tag)
            if prev_thm is not None and prev_thm.proof is not None:
                initial_code = prev_thm.render()

        if initial_code is None:
            thm_copy = deepcopy(thm)
            thm_copy.proof = "  try simp_all ; try grind"
            initial_code = thm_copy.render()

        code: str = initial_code

    def mk_aborted_result(dialog: Dialog) -> tuple[AgentResult, None]:
        return (
            AgentResult.mk_aborted(
                sub_id,
                Action.PROVE_SUBGOAL,
                dialog,
                rev_id,
                goal_idx,
                start=start,
                lean_times=lean_times,
                llm_times=llm_times,
            ),
            None,
        )

    if check_outdated():
        logger.info(
            f"Sub-agent {sub_id} would start on an outdated revision, aborting."
        )
        return mk_aborted_result(dialog)

    file = deepcopy(rev.file)
    file.decls.insert(-1, MPROD_BLOCK)  # add mprod macro before main theorem
    file.decls[-1] = thm  # replace main theorem with current goal
    file.main_theorem_idx = -1

    for i in range(ctx.args.max_prover_turns + 1):  # +1 for auto attempt
        if check_done():  # before slow LLM turn
            return mk_aborted_result(dialog)

        if i > 0:
            start = time()
            reply: Message = chat(
                dialog, prover_model, ctx.args.temperature, ctx.args.use_mcp
            )
            llm_times.append(time() - start)
            dialog.append(reply)
            code = Env.extract_code(reply.content)
            logger.info(f"Sub-agent {sub_id} wrote code:\n{code}")
            code = remove_multiline_comments(code)

        if check_done():  # before slow execution
            return mk_aborted_result(dialog)

        decls = make_decls(code)
        action = detect_prover_action(decls)
        if action == Action.METHOD:
            # only keep last method declaration
            decls = [d for d in decls if isinstance(d, Method)][-1:]
            result: AgentResult = AgentResult.mk_implementer(
                sub_id,
                decls,
                dialog,
                success=True,
                outcomes=None,
                merged=False,
                merge_reason="Proposed method change",
                start=start,
            )
            result.action = Action.PROPOSE
            result.rev_id = rev_id
            result.goal_idx = goal_idx
            if decls:
                diff = render_diff(rev.file.method.render(), decls[0].render())
                result.diff = diff
            with ctx.lock:
                ctx.revisions[rev_id].proposals[goal_idx].extend(decls)
                ctx.revisions[rev_id].proposals_raw[goal_idx].append(code)
            return result, None
        elif action == Action.PROVE_SUBGOAL:
            pass  # continue below
        else:
            raise ValueError(f"Unknown action detected from declarations: {decls}")

        new_file = make_proof_file(ctx, file, decls)

        # Detect header by extracting the full new code string:
        # new code will start with replaced main theorem or inserted decls at its index
        new_idx = len(file.decls) - 1
        # relies on render(a ++ b) = render(a) ++ render(b)
        new_decls_file = LeanFile(new_file.decls[new_idx:])
        start_line = new_decls_file.render()  # can be multi-line

        logger.info(f"Running file:\n{new_file.render()}")
        logger.info(f"New code for header end detection:\n{start_line}")
        start = time()
        errors, outcomes = ctx.env.step(
            ctx.runner,
            ctx.task,
            new_file.render(),
            extract=False,
            final=False,
            goedel_format=is_goedel,
            start_line=start_line,
            step_type="proof",
        )
        lean_times.append(time() - start)

        if i == 0:
            dialog = initial_prover_dialog(
                prover_model,
                dialog=dialog,
                statement=thm.statement,
                proof=initial_code,
                errors=errors,
                allow_subgoal_change=ctx.args.allow_subgoal_change,
            )
            logger.info(f"Sub-agent {sub_id} initial dialog:\n{dialog.preview()}")
        else:
            dialog = prover_followup_dialog(
                prover_model,
                dialog=dialog,
                turn=i,  # 1-based bug-fixing iteration
                max_turns=ctx.args.max_prover_turns - 1,  # initial, then fix
                errors=errors,
                shrink_threshold_chars=75_000,  # 2-4 chars/tok, 40k maxlen
            )
            logger.info(f"Sub-agent {sub_id} followup dialog:\n{dialog.preview()}")

        logger.info(
            f"Sub-agent {sub_id} received message:\n{dialog.messages[-1].content}"
        )
        if not errors:
            break

    if check_done():
        return mk_aborted_result(dialog)

    auto = i == 0  # no LLM in turn 0
    if outcomes["pass"]:
        with ctx.lock:
            logger.info(
                f"Sub-agent {sub_id} successfully proved theorem at index {goal_idx}."
            )
            for decl in decls:
                if isinstance(decl, Theorem) and decl.name == rev.goals[goal_idx].name:
                    logger.info(f"Recording subgoal proof:\n{decl.render()}")
                    rev.goals[goal_idx].proof = decl.proof
                    # NOTE: theorem metadata (options, attributes) dropped at this point
                    # because proof reconstruction has no place to put them
                    rev.goals[goal_idx].source.append(sub_id)
                else:
                    logger.info(f"Saving auxiliary declaration:\n{decl.render()}")
                    decl.source.append(sub_id)
                    if isinstance(decl, Theorem) and decl.name in rev.file.decl_names:
                        # convert to comment if duplicate name
                        lines = decl.render().splitlines()
                        decl_as_comment = "\n".join(f"-- {line}" for line in lines)
                        block = OtherLean(decl_as_comment, source=decl.source)
                        rev.file.decls.insert(rev.file.main_theorem_idx, block)
                        logger.warning(
                            f"Adding auxiliary declaration with duplicate name as comment:\n{decl.render()}"
                        )
                    else:
                        # other block or new theorem name
                        rev.file.decls.insert(rev.file.main_theorem_idx, decl)

        return (
            AgentResult.mk_prover(
                sub_id,
                decls,
                dialog,
                rev_id,
                goal_idx,
                auto,
                start=start,
                lean_times=lean_times,
                llm_times=llm_times,
            ),
            None,
        )
    else:
        logger.info(f"Sub-agent {sub_id} failed to prove theorem at index {goal_idx}.")
        return (
            AgentResult.mk_prover(
                sub_id,
                [],
                dialog,
                rev_id,
                goal_idx,
                auto,
                start=start,
                lean_times=lean_times,
                llm_times=llm_times,
            ),
            None,
        )


def implementer(
    ctx: ProblemContext,
    dialog: Dialog,
    sub_id: int,
    file: LeanFile,
    turn_budget: int | None = None,
) -> tuple[AgentResult, HierarchicalProof | None, int]:
    """
    Returns (agent result, next revision, used turns).
    Dialog will be modified in-place.
    """
    start = time()
    if turn_budget is None:
        turn_budget = ctx.args.max_turns
    chat_calls = 0
    for i in range(turn_budget + 1):  # +1 for initial code
        if ctx.terminated():
            logger.info(f"Implementation agent {sub_id} stopping early.")
            return (
                AgentResult.mk_aborted(sub_id, Action.METHOD, dialog, start=start),
                None,
                chat_calls,
            )

        if i > 0:
            reply: Message = chat(
                dialog, ctx.args.model, ctx.args.temperature, ctx.args.use_mcp
            )
            chat_calls += 1
            dialog.append(reply)
            logger.info(f"Implementation agent {sub_id} wrote:\n{reply.content}")
            code = Env.extract_code(reply.content)
            logger.info(f"Implementation agent {sub_id} extracted code:\n{code}")
            code = remove_multiline_comments(code)
            decls = make_decls(code)
            file = make_impl_file(file, decls)

        logger.info(f"Running file:\n{file.render()}")
        # run manually to obtain diagnostics
        # keep roughly in sync with Env.step()
        try:
            diagnostics = ctx.runner.run(file.render())
            msg, outcomes = ctx.env.step(
                ctx.runner,
                ctx.task,
                file.render(),
                extract=False,
                diagnostics=None,
                final=False,
                step_type="method",
            )
        except RuntimeError as e:
            # REPL error (typically OOM)
            logger.error("Lean execution error.", exc_info=e)
            diagnostics = None
            msg = CRASH_MESSAGE
            outcomes = {"pass": False}
        except TimeoutExpired:
            # timeout
            logger.warning("Lean execution timeout error.")
            diagnostics = None
            msg = TIMEOUT_MESSAGE
            outcomes = {"pass": False}

        if outcomes["pass"]:
            logger.info("Default proof passed.")
            res = AgentResult.mk_implementer(
                sub_id, file.decls, dialog, True, outcomes=outcomes, start=start
            )
            return res, HierarchicalProof(file, [], []), chat_calls

        try:
            assert diagnostics is not None, msg
            theorems, tags = extract_theorems(diagnostics)  # can raise AssertionError
            assert len(theorems) > 0, "no goals extracted"  # all proved handled above
            has_sorry = [thm for thm in theorems if "sorry" in thm.statement]
            assert (
                not has_sorry
            ), f"sorry in {len(theorems)} theorem statements, first: {has_sorry[0]}"
            break
        except AssertionError as e:
            logger.error(f"Failed to extract theorems: {e}")
            dialog.append(
                Message.user(
                    IMPLEMENTATION_FOLLOWUP_PROMPT.format(message=str(e), errors=msg)
                )
            )

    else:
        logger.warning(
            f"Implementation agent failed to extract theorems after {i} turns."
        )
        res = AgentResult.mk_implementer(
            sub_id, file.decls, dialog, False, outcomes=outcomes, start=start
        )
        return res, None, chat_calls

    logger.info(f"Extracted {len(theorems)} theorems to prove.")
    for idx, thm in enumerate(theorems):
        logger.info(f"{idx} ({tags[idx]}): {thm.render()}")
    res = AgentResult.mk_implementer(
        sub_id, file.decls, dialog, True, outcomes=outcomes, start=start
    )
    return res, HierarchicalProof(file, theorems, tags), i


def judged_implementer(
    ctx: ProblemContext,
    dialog: Dialog,
    sub_id: int,
    file: LeanFile,
    env_first: bool = False,
) -> tuple[AgentResult, HierarchicalProof | None]:
    """
    Returns (agent result, next revision).
    Dialog will be modified in-place.
    If `env_first` is set, the `file` is run first and the dialog ends by an agent message.
    Otherwise, the agent acts first and the dialog ends by a user message.
    """
    assert ctx.args.max_turns > 0
    chat_calls = 0
    first_iter = True
    while True:
        if chat_calls >= ctx.args.max_turns:
            break

        if not env_first or not first_iter:
            reply: Message = chat(
                dialog, ctx.args.model, ctx.args.temperature, ctx.args.use_mcp
            )
            chat_calls += 1
            dialog.append(reply)
            code = Env.extract_code(reply.content)
            logger.info(f"Judged implementer agent {sub_id} wrote code:\n{code}")
            code = remove_multiline_comments(code)
            decls = make_decls(code)

            # only keep last method declaration
            decls = [d for d in decls if isinstance(d, Method)][-1:]
            new_file = make_impl_file(file, decls)
            logger.info(
                f"Judged implementer agent {sub_id} proposed method:\n{new_file.method.render()}"
            )
        else:
            new_file = file
        first_iter = False
        result, new_rev, used = implementer(
            ctx, dialog, sub_id, new_file, ctx.args.max_turns - chat_calls
        )
        chat_calls += used

        if new_rev is None:
            # implementer failed
            result.merged = False
            result.merge_reason = "Judged implementer failed"
            break

        accept, reason = review(ctx.args, ctx.task, new_rev.file.method.render())
        result.merged = accept
        result.merge_reason = reason
        diff = render_diff(file.method.render(), new_rev.file.method.render())
        result.diff = diff
        if accept:
            break
        logger.info(
            f"Judged implementer agent {sub_id} proposed method change but it was rejected: {reason}"
        )
        dialog.append(Message.user(REVIEW_FEEDBACK_PROMPT.format(reason=reason)))

    return result, new_rev


def reviser(
    ctx: ProblemContext, sub_id: int, rev_id: int, proposals: list[str]
) -> tuple[AgentResult, HierarchicalProof | None]:
    """
    Returns (agent result, next revision).
    Dialog will be modified in-place.
    """
    with ctx.lock:
        rev = ctx.revisions[rev_id]
        original = rev.file.method.render()
        dialog = deepcopy(ctx.base_dialog)
    proposals = "\n\n".join(f"```lean\n{proposal}\n```" for proposal in proposals)
    dialog.append(
        Message.user(
            REVISER_PROMPT.format(
                original=original,
                proposals=proposals,
            )
        )
    )

    result, new_rev = judged_implementer(ctx, dialog, sub_id, rev.file)
    result.rev_id = rev_id
    return result, new_rev


def initial_implementer(
    ctx: ProblemContext, sub_id: int, file: LeanFile
) -> tuple[AgentResult, HierarchicalProof | None]:
    """
    Returns (agent result, next revision).
    Dialog will be modified in-place.
    """
    with ctx.lock:
        dialog = deepcopy(ctx.base_dialog)
    return judged_implementer(ctx, dialog, sub_id, file, env_first=True)


def final_fixer(
    ctx: ProblemContext, rev_id: int, sub_id: int
) -> tuple[AgentResult, HierarchicalProof]:
    start = time()
    with ctx.lock:
        file = ctx.revisions[rev_id].full_file()
        dialog = deepcopy(ctx.base_dialog)
    bare_file = deepcopy(file)
    bare_file.decls = bare_file.decls[: bare_file.method_idx + 1] + [
        bare_file.main_theorem
    ]
    for i in range(ctx.args.max_turns):
        if i > 0:
            reply: Message = chat(
                dialog, ctx.args.model, ctx.args.temperature, ctx.args.use_mcp
            )
            dialog.append(reply)
            code = Env.extract_code(reply.content)
            logger.info(f"Final fixer agent {sub_id} wrote code:\n{code}")
            code = remove_multiline_comments(code)
            decls = make_decls(code)
            # add decls starting at file with header, method, main theorem:
            file = make_final_file(bare_file, decls)

        logger.info(f"Running full file:\n{file.render()}")
        msg, outcomes = ctx.env.step(
            ctx.runner,
            ctx.task,
            file.render(),
            extract=False,
            final=False,
            step_type="full",
        )
        outcomes["final_outcomes"] = None
        outcomes["pass_final"] = False

        dialog.append(Message.user(FINAL_FOLLOWUP_PROMPT.format(errors=msg)))

        if outcomes["pass"]:
            break

    result = AgentResult.mk_final_fix(
        sub_id, file.decls, dialog, rev_id, outcomes=outcomes, start=start
    )
    result.auto = i == 0  # no LLM in turn 0
    return result, HierarchicalProof(file, [], [])


def initial(
    task: Task,
    env: DecompEnvMixin,
    runner: LeanRepl | ResourcePool,
    args: RunArgs,
) -> tuple[ProblemContext, Dialog]:
    # *last* method is the task method
    header, method_tail = task["loom_header"].rsplit("method", 1)
    method_spec_str = "method" + method_tail
    method = Method.from_str(method_spec_str)
    dialog: Dialog = env.initial(task)
    logger.info(f"Prompt:\n{dialog.messages[-1].content}")
    reply: Message = chat(dialog, args.model, args.temperature)
    dialog.append(reply)
    code = Env.extract_code(reply.content).strip()

    logger.info(f"Initial implementer agent wrote code:\n{code}")
    code = remove_multiline_comments(code)
    decls = make_decls(code)

    # only keep last method declaration
    decls = [d for d in decls if isinstance(d, Method)][-1:]
    if decls:
        method_impl = decls[0]
        method.body = method_impl.body
    else:
        method.body = "  sorry"
    method.source = [0]
    correctness_thm = method.decompose_theorem()
    correctness_thm.source = [0]
    header_block = OtherLean(header, source=[0])
    file = LeanFile([header_block, method, correctness_thm])
    global_ctx = GlobalContext(env, runner, args)
    rev = HierarchicalProof(file, [], [])
    ctx = ProblemContext(
        ctx=global_ctx,
        done_event=None,
        task=task,
        dialogs={0: dialog},
        revisions=[rev],
        base_dialog=deepcopy(dialog),
    )
    logger.info(f"Initial file:\n{file.render()}")
    return ctx, dialog


def rollout(
    env: DecompEnvMixin,
    runner: LeanRepl | ResourcePool,
    task: Task,
    args: RunArgs,
) -> HierachicalRollout:
    thread_name = threading.current_thread().name
    inc_dir = incremental_dump_path(args.dump_dir, thread_name)
    inc_dir.mkdir(parents=True, exist_ok=True)
    inc_file = inc_dir / f"{task['id']}.jsonl"

    result_q: Queue[tuple[AgentResult, HierarchicalProof | None]] = Queue()
    lock = Lock()
    executor = ThreadPoolExecutor(
        max_workers=args.n_subagents, thread_name_prefix=f"{thread_name}-SubagentWorker"
    )
    agent_results: dict[int, AgentResult] = {}

    # number of results still to be processed (not yet in or taken from queue)
    # (use submit() and decrement after get(), only from this thread)
    pending = 0

    t_start: dict[int, float] = {}  # sub_id -> start time
    t_submit: dict[int, float] = {}  # sub_id -> submit time
    t_end: dict[int, float] = {}  # sub_id -> end time

    def log(message: str) -> None:
        logger.info(f"[{thread_name} - {task['id']}]: {message}")

    def _fmt_utc(ts: float | None) -> str:
        if ts is None:
            return "-"
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        # centiseconds (00–99), derived from microseconds
        cs = dt.microsecond // 10_000
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{cs:02d}Z"

    def log_subagent_times() -> None:
        # One line per subagent; timestamps as UTC; includes derived durations when possible.
        sub_ids = sorted(set(t_start) | set(t_submit) | set(t_end))
        header = (
            "subagent timing (UTC)\n"
            "sub_id | submit                  | start                   | end                     "
            "| submit→start | start→end | submit→end"
        )
        lines = []
        lines.append(header)
        lines.append("-" * len(header))
        for sid in sub_ids:
            s = t_start.get(sid)
            sub = t_submit.get(sid)
            e = t_end.get(sid)

            def dur(a: float | None, b: float | None) -> str:
                if a is None or b is None:
                    return "-"
                return f"{(b - a):.2f}s"

            lines.append(
                f"{sid:6} | {_fmt_utc(sub):23} | {_fmt_utc(s):23} | {_fmt_utc(e):23} | "
                f"{dur(sub, s):12} | {dur(s, e):9} | {dur(sub, e):8}"
            )
        log("\n".join(lines))

    def submit(fn, sub_id: int, *args, **kwargs):
        nonlocal pending
        pending += 1
        t_submit[sub_id] = time()
        future = executor.submit(fn, *args, **kwargs)
        future.add_done_callback(
            lambda f: (
                logger.error("task failed", exc_info=f.exception())
                if f.exception()
                else None
            )
        )
        return future

    def prover_wrapper(
        rev_id: int, goal_idx: int, sub_id: int, use_prover_model: bool = True
    ) -> None:
        start = time()
        t_start[sub_id] = start
        log(
            f"Launching prover sub-agent {sub_id} after {start - t_submit[sub_id]:.2f}s queue wait"
        )
        try:
            result = prover(
                ctx,
                sub_id=sub_id,
                rev_id=rev_id,
                goal_idx=goal_idx,
                use_prover_model=use_prover_model,
            )
            result_q.put(result)
        except Exception:
            logger.exception(f"Sub-agent {sub_id} on {task['id']} raised an exception")
            result_q.put(
                (
                    AgentResult.mk_prover(
                        sub_id,
                        [],
                        Dialog([]),
                        rev_id,
                        goal_idx,
                        auto=False,  # auto unknown
                        start=start,
                    ),
                    None,
                )
            )
        finally:
            end = time()
            t_end[sub_id] = end
            log(f"Prover sub-agent {sub_id} finished after {end - start:.2f}s")

    def implementer_wrapper():
        start = time()
        t_start[0] = start
        try:
            result = initial_implementer(ctx, 0, ctx.current.file)
            result_q.put(result)
        except Exception:
            logger.exception(
                f"Implementation agent 0 on {task['id']} raised an exception"
            )
            result_q.put(
                (
                    AgentResult.mk_implementer(
                        0, [], Dialog([]), False, None, start=start
                    ),
                    None,
                )
            )
        finally:
            end = time()
            t_end[0] = end
            log(f"Implementation agent 0 finished after {end - start:.2f}s")

    def reviser_wrapper(rev_id: int, proposals: list[str], sub_id: int) -> None:
        start = time()
        t_start[sub_id] = start
        try:
            result = reviser(ctx, sub_id, rev_id, proposals)
            result_q.put(result)
        except Exception:
            logger.exception(
                f"Reviser agent {sub_id} on {task['id']} raised an exception"
            )
            result_q.put(
                (
                    AgentResult.mk_implementer(
                        sub_id, [], Dialog([]), False, None, start=start
                    ),
                    None,
                )
            )
        finally:
            end = time()
            t_end[sub_id] = end
            log(f"Reviser agent {sub_id} finished after {end - start:.2f}s")

    def launch_prover(
        rev_id: int, goal_idx: int, use_prover_model: bool = True
    ) -> None:
        nonlocal sub_id
        submit(prover_wrapper, sub_id, rev_id, goal_idx, sub_id, use_prover_model)
        sub_id += 1

    def launch_reviser(rev_id: int, proposals: list[str]) -> None:
        nonlocal sub_id
        submit(reviser_wrapper, sub_id, rev_id, proposals, sub_id)
        sub_id += 1

    ctx, dialog = initial(task, env, runner, args)
    dialogs = {0: dialog}
    assert isinstance(ctx.current, HierarchicalProof)
    ctx.lock = lock
    submit(implementer_wrapper, 0)
    sub_id = 1  # number of launched sub-agents so far, next free id to use
    llm_agents = 0  # number of completed agents that used LLM calls
    good_id = -1  # index to run final fixer on

    while True:
        if ctx.terminated():
            break  # decision to stop early
        if not pending:
            # nothing left to arrive/process
            with ctx.lock:
                if ctx.termination_reason is None:
                    ctx.termination_reason = "Exhausted search (no pending results)"
            break
        try:
            res, rev = result_q.get(timeout=1.0)
        except Empty:
            continue
        pending -= 1
        log(f"Received result from sub-agent {res.sub_id}, now {pending} pending")
        log_subagent_times()
        agent_results[res.sub_id] = res
        dialogs[res.sub_id] = res.dialog
        if not (res.auto or res.aborted):
            llm_agents += 1
            if llm_agents >= args.max_subagents - 1:  # leave spot for final fixer
                with ctx.lock:
                    if ctx.termination_reason is None:
                        ctx.termination_reason = "Reached maximum number of sub-agents"
                        # do not break here, still process this result

        with ctx.lock:
            # 1. Implementation result
            if res.action == Action.METHOD and rev is None:
                pass  # implementer failed

            elif res.action == Action.METHOD and rev is not None:
                ctx.revisions.append(rev)
                revision_idx = len(ctx.revisions) - 1
                res.revision_idx = revision_idx
                if res.rev_id is None:
                    res.rev_id = -1  # initial implementation
                else:
                    # reset base dialog
                    ctx.base_dialog = deepcopy(
                        Dialog(
                            [res.dialog.messages[0], res.dialog.messages[-1]],
                            system_prompt=ctx.base_dialog.system_prompt,
                        )
                    )
                    log(f"New base dialog:\n{ctx.base_dialog.preview()}")
                if res.outcomes["pass"]:
                    log(
                        f"Implementation agent {res.sub_id} succeeded without subgoals."
                    )
                    ctx.termination_reason = "Implementation passed without subgoals"
                    good_id = revision_idx
                    break

                for _ in range(args.provers_per_goal):
                    for goal_idx in range(len(rev.goals)):
                        launch_prover(revision_idx, goal_idx)

            # 2. Prover result: subgoal proof attempt
            elif res.action == Action.PROVE_SUBGOAL:
                rev_id = res.rev_id
                rev: HierarchicalProof = ctx.revisions[rev_id]
                goal_idx = res.goal_idx
                assert goal_idx is not None
                rev.n_attempts[goal_idx] += 1
                if rev.all_proved():
                    log("All subgoals proved, terminating rollout.")
                    ctx.termination_reason = "All subgoals proved"
                    good_id = rev_id
                    break

                # If all small provers failed and we haven't done so yet,
                # fall back to main model.
                if rev.failed(goal_idx, ctx.args.provers_per_goal) and not rev.failed(
                    goal_idx, ctx.args.provers_per_goal_with_fallback
                ):
                    log(
                        f"Relaunching prover on subgoal {goal_idx} of revision {rev_id} "
                        f"with main model after failure with small prover model."
                    )
                    launch_prover(rev_id, goal_idx, use_prover_model=False)

            # 3. Prover result: method proposal (no new revision here)
            elif res.action == Action.PROPOSE:
                pass
                # proposals have already been added to rev.proposals by prover
                # reviser will be launched when all subgoals are done

            else:
                raise ValueError(f"Unknown action in result: {res.action}")

            # Check whether to launch the reviser
            if res.action in {Action.PROVE_SUBGOAL, Action.PROPOSE}:
                rev_id = res.rev_id
                rev: HierarchicalProof = ctx.revisions[rev_id]
                if rev.all_done(ctx.args.provers_per_goal_with_fallback):
                    proposals = [m for ms in rev.proposals_raw.values() for m in ms]
                    if proposals and not rev.reviser_launched:
                        log(
                            f"Launching reviser agent {sub_id} for revision {rev_id} "
                            f"with {len(proposals)} proposals."
                        )
                        launch_reviser(rev_id, proposals)
                        rev.reviser_launched = True

            # after processing the result, dump incremental result
            # (still under lock)
            rollout_result = HierachicalRollout(
                task=task,
                outcomes=res.outcomes,
                n_subs=sub_id,
                dialogs=dialogs,
                revisions=ctx.revisions,
                learnings=[],
                termination_reason=ctx.termination_reason,
                agent_results=agent_results,
                decomp_rev_id=good_id,
                terminated=False,
            )

        # outside ctx.lock
        incremental_dump(inc_file, rollout_result.to_dict())

    # join executor
    executor.shutdown(wait=True)

    # proof reconstruction
    log("All sub-agents completed. Reconstructing full proof.")
    good_id = good_id if good_id >= 0 else len(ctx.revisions) - 1
    res, final_rev = final_fixer(ctx, rev_id=good_id, sub_id=sub_id)
    with ctx.lock:
        ctx.revisions.append(final_rev)
    dialogs[sub_id] = res.dialog
    agent_results[sub_id] = res
    sub_id += 1

    with ctx.lock:
        rollout_result = HierachicalRollout(
            task=task,
            outcomes=res.outcomes,
            n_subs=sub_id,
            dialogs=dialogs,
            revisions=ctx.revisions,
            learnings=[],
            termination_reason=ctx.termination_reason,
            agent_results=agent_results,
            decomp_rev_id=good_id,
        )
    incremental_dump(inc_file, rollout_result.to_dict())
    return rollout_result


IMPLEMENTATION_FOLLOWUP_PROMPT = """
I ran the code for extracting the subgoals but did not succeed:
{message}

Here's the full list of errors in the file (the named "unsolved goals" are what I'd like to pair up with the output of `extract_goals`):

{errors}

Could you please figure out what went wrong and fix them?
Please return the new code for the `method` block only, in triple backticks.
""".strip()


FINAL_FOLLOWUP_PROMPT = """
I've reconstructed the full proof but got the following errors.
Could you please figure out what went wrong and fix them?
Please return the new proof (everything below the `method` block,
including helper lemmas or other auxiliary declarations and the main correctness theorem; no `method`, no imports),
again everything in triple backticks ```lean ... ```.

{errors}
""".strip()


REVISER_PROMPT = """
Upon proving the subgoals, we came up with several possible improvements to the method implementation
or its invariant annotations. Please review these suggestions and synthesize them into a single improved method implementation.

Original implementation:
```lean
{original}
```

Proposed implementations:

{proposals}

Please return the code of the new method implementation in triple backticks ```lean ... ```,
again without changing the method specification header.

Remember the **imperative code requirements** which are strictly enforced:
the entire asymptotically non-constant-time core must be written with explicit loops and mutable state,
not using higher-order traversals, recursive traversals, or library calls that hide iteration (map, fold, filter, sort, etc.).
Functional style is allowed only for truly O(1) operations (arithmetic, comparisons, tuple ops, single indexing, simple conditionals)
and in ghost/invariant code, not for any real data traversal or reorganization.
In particular, do NOT use functional code that directly mimics the functional specification, which would make verification trivial but
useless for our purposes.
""".strip()
