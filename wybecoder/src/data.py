# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from collections import defaultdict
import copy
import re
from dataclasses import dataclass, field
from enum import Enum
from threading import Event
from time import time
from typing import Any

from src.args import RunArgs
from src.env import Dialog, Env, Outcomes, Task
from src.parse_utils import parse_theorem, split_decls_by_keyword, theorem_type
from src.pool import ResourcePool
from src.repl import LeanRepl


@dataclass
class Theorem:
    # correctness proofs:
    # statement := "prove_correct <method_name> by"

    name: str
    statement: str  # including ":= by"
    proof: str | None = None
    metadata: str = (
        ""  # set_option and attributes before the statement, including trailing \n
    )
    source: list[int] = field(default_factory=list)

    def render(self) -> str:
        return f"{self.metadata}\n{self.statement}\n{self.proof or 'sorry'}"

    @staticmethod
    def from_str(code: str) -> "Theorem":
        parsed = parse_theorem(code)
        if parsed is None:
            raise ValueError(code)

        return Theorem(
            parsed["name"],
            parsed["statement"],
            parsed["proof"],
            parsed["metadata"],
        )

    @staticmethod
    def unsat_theorem_from_task(task: Task) -> "Theorem":
        parsed = parse_theorem(task["unsat_theorem"])
        if parsed is None:
            raise ValueError(task["unsat_theorem"])

        return Theorem(
            parsed["name"],
            parsed["statement"],
            proof=None,
        )

    def with_proof(self, code: str) -> "Theorem":
        new = Theorem.from_str(code)
        return Theorem(self.name, self.statement, new.proof)

    def with_proof_and_meta(self, code: str) -> "Theorem":
        new = Theorem.from_str(code)
        return Theorem(self.name, self.statement, new.proof, new.metadata)

    @property
    def theorem_type(self) -> str:
        result = theorem_type(self.statement)
        assert result is not None
        return result


EXTRACT_PP_OPTIONS = """
set_option pp.coercions.types true in
set_option pp.funBinderTypes true in
set_option pp.numericTypes true in
set_option pp.structureInstances false in
""".strip()


@dataclass
class Method:
    name: str
    spec: str
    body: str  # including "do" and indent
    source: list[int] = field(default_factory=list)

    @staticmethod
    def from_str(code: str) -> "Method":
        """
        Parse method from a string, matching only standalone 'do' as the start of the body.
        Args:
            code (str): String representing a method.
        Returns:
            Method: Parsed Method object.
        Raises:
            ValueError: If the code does not contain a valid method.
        """
        # Match 'do' as a standalone word, possibly indented, at the start of a line
        match = re.search(r"(^|\n)[ \t]*\bdo\b", code)
        if not match:
            raise ValueError(f"'do' not found as a standalone word in: {code!r}")
        idx = match.start()
        header = code[:idx]
        body = code[idx:]
        # Extract the method name from the header
        for line in header.splitlines():
            stripped_line = line.strip()
            if stripped_line:
                words = stripped_line.split()
                if len(words) >= 2:
                    name = words[1]
                    return Method(name, header, body)
                else:
                    raise ValueError(f"Could not extract method name from: {code!r}")
        raise ValueError(f"Could not extract method name from: {code!r}")

    def render(self) -> str:
        return f"{self.spec}\n{self.body}"

    def correctness_theorem(self) -> Theorem:
        return Theorem(self.name, f"prove_correct {self.name} by")

    def default_correctness_theorem(self) -> Theorem:
        return Theorem(
            self.name,
            statement=f"prove_correct {self.name} by",
            proof="  loom_solve <;> try grind",
        )

    def decompose_theorem(self) -> Theorem:
        return Theorem(
            self.name,
            statement=f"prove_correct {self.name} by",
            proof="  loom_solve\n  all_goals { extract_goal }",
            metadata=f"set_option maxHeartbeats 1000000 in\n{EXTRACT_PP_OPTIONS}",
        )

    def with_body(self, code: str) -> "Method":
        new = Method.from_str(code)
        return Method(self.name, self.spec, new.body)


@dataclass
class OtherLean:
    body: str
    source: list[int] = field(default_factory=list)

    def render(self) -> str:
        return self.body


Declaration = Theorem | Method | OtherLean
Learning = str  # turn to dataclass later


@dataclass
class LeanFile:
    decls: list[Declaration]

    # used by agent algorithms:
    add_idx: int = -1  # all decls after incl. this index are new

    method_idx: int = 1  # index of method declaration
    main_theorem_idx: int = -1  # index of main theorem (correctness or unsat)
    errors: str = ""  # errors of this revision

    @property
    def decl_names(self) -> list[str]:
        return [
            d.name
            for d in self.decls
            if isinstance(d, Theorem) or isinstance(d, Method)
        ]

    def render(self) -> str:
        return "\n\n".join(d.render() for d in self.decls)

    def to_dict(self) -> dict:
        return {
            "decls": [
                {
                    "type": decl.__class__.__name__,
                    "code": decl.render(),
                    "name": getattr(decl, "name", None),
                    "source": getattr(decl, "source", []),
                    "statement": getattr(decl, "statement", None),
                }
                for decl in self.decls
            ],
            "method_idx": self.method_idx,
            "errors": self.errors,
        }

    def add_decl(self, task: Task, res: "AgentResult", decl: Declaration) -> "LeanFile":
        file = copy.deepcopy(self)
        match res.action:
            case Action.METHOD:
                assert isinstance(decl, Method)
                mth: Method = file.method
                mth.body = decl.body
                mth.source.append(res.sub_id)
            case Action.PROVE_CORRECT:
                assert isinstance(decl, Theorem)
                thm = file.method.correctness_theorem()
                thm.proof = decl.proof
                thm.metadata = decl.metadata
                thm.source.append(res.sub_id)
                file.main_theorem = thm
            case Action.DISPROVE:
                assert isinstance(decl, Theorem)
                thm = Theorem.unsat_theorem_from_task(task)
                thm.proof = decl.proof
                thm.metadata = decl.metadata
                thm.source.append(res.sub_id)
                file.main_theorem = thm
            case Action.ADD:
                assert isinstance(decl, Theorem) or isinstance(decl, OtherLean)
                declared = [thm.name for thm in file.decls if isinstance(thm, Theorem)]
                if isinstance(decl, OtherLean) or decl.name not in declared:
                    # insert just before correctness proof
                    decl.source = [res.sub_id]
                    file.decls.insert(-1, decl)
            case _:
                pass
        return file

    def add_decls(self, task: Task, res: "AgentResult") -> "LeanFile":
        file = self
        for decl in res.decls:
            file = file.add_decl(task, res, decl)
        return file

    @property
    def method(self) -> Method:
        result = self.decls[self.method_idx]
        assert isinstance(result, Method)
        return result

    @method.setter
    def method(self, value: Method) -> None:
        assert isinstance(value, Method)
        self.decls[self.method_idx] = value

    @property
    def main_theorem(self) -> Theorem:
        result = self.decls[self.main_theorem_idx]
        assert isinstance(result, Theorem)
        return result

    @main_theorem.setter
    def main_theorem(self, value: Theorem) -> None:
        assert isinstance(value, Theorem)
        self.decls[self.main_theorem_idx] = value


@dataclass
class GlobalContext:
    env: Env
    runner: LeanRepl | ResourcePool
    args: RunArgs
    learnings: list[str] = field(default_factory=list)


@dataclass
class Rollout:
    task: Task
    outcomes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "outcomes": self.outcomes,
        }


@dataclass
class LinearRollout(Rollout):
    n_turns: int
    dialog: Dialog

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_input_tokens": self.dialog.total_input_tokens,
            "total_output_tokens": self.dialog.total_output_tokens,
            "total_calls": self.dialog.total_calls,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "outcomes": self.outcomes,
            "n_turns": self.n_turns,
            "dialog": self.dialog.to_dict(),
            "stats": self.stats,
        }


class Action(str, Enum):
    METHOD = "method"  # revise method
    ADD = "add"  # add verified declarations
    PROVE_CORRECT = "prove_correct"  # revise correctness proof
    EMPTY = "empty"  # no action
    DISPROVE = "disprove"  # prove unsatisfiability

    # actions for hierarchical mode:
    PROVE_SUBGOAL = "prove_subgoal"
    FINAL_FIX = "final_fix"
    PROPOSE = "propose"  # propose a method implementation, still to be revised


@dataclass
class AgentResult:
    sub_id: int
    action: Action
    decls: list[Declaration]
    dialog: Dialog
    learning: Learning | None = None
    start: float | None = None  # optional, for measuring duration
    timestamp: float | None = None  # optional, for chronological ordering
    success: bool | None = (
        None  # was the subgoal successfully proved / theorems successfully extracted?
    )
    lean_times: list[float] = field(default_factory=list)  # per-call Lean times
    llm_times: list[float] = field(default_factory=list)  # per-call LLM times

    # merge metadata
    merged: bool = False  # was this result merged?
    merge_reason: str | None = None
    diff: str | None = None  # diff between old and new code at processing time
    diff_reviewed: str | None = None  # diff at reviewing time

    # revision index after processing this result (multi or implementer)
    revision_idx: int | None = None

    # hierarchical / decomp metadata
    rev_id: int | None = None  # revision id for decomp agent
    goal_idx: int | None = None  # index of goal in revision (replaces goal_tag)
    outcomes: Outcomes | None = None  # only for moving implementer / final fixer data
    aborted: bool = False
    auto: bool = False  # prover: ran without LLM?

    # multi metadata
    errors: str | None = None  # errors in this result (with allow_partial_proofs)

    @staticmethod
    def mk_failed(
        sub_id: int,
        dialog: Dialog,
        learning: Learning | None = None,
        start: float | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id,
            Action.EMPTY,
            [],
            dialog,
            learning=learning,
            success=False,
            timestamp=time(),
            start=start,
        )

    @staticmethod
    def mk_multi(
        sub_id: int,
        action: Action,
        decls: list[Declaration],
        dialog: Dialog,
        learning: Learning | None = None,
        errors: str | None = None,
        start: float | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id=sub_id,
            action=action,
            decls=decls,
            dialog=dialog,
            learning=learning,
            success=True,
            timestamp=time(),
            errors=errors,
            start=start,
        )

    @staticmethod
    def mk_aborted(
        sub_id: int,
        action: Action,
        dialog: Dialog,  # compulsory not to lose LLM call stats
        rev_id: int | None = None,
        goal_idx: int | None = None,
        start: float | None = None,
        lean_times: list[float] | None = None,
        llm_times: list[float] | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id=sub_id,
            action=action,
            decls=[],
            dialog=dialog,
            timestamp=time(),
            rev_id=rev_id,
            goal_idx=goal_idx,
            aborted=True,
            merged=False,
            merge_reason="aborted",
            start=start,
            lean_times=lean_times or [],
            llm_times=llm_times or [],
        )

    @staticmethod
    def mk_prover(
        sub_id: int,
        decls: list[Declaration],
        dialog: Dialog,
        rev_id: int,
        goal_idx: int,
        auto: bool,
        start: float | None = None,
        lean_times: list[float] | None = None,
        llm_times: list[float] | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id=sub_id,
            action=Action.PROVE_SUBGOAL,
            decls=decls,
            dialog=dialog,
            timestamp=time(),
            rev_id=rev_id,
            goal_idx=goal_idx,
            success=bool(decls),  # checked decls indicate success
            auto=auto,
            merged=True,
            merge_reason="not applicable to prover",
            start=start,
            lean_times=lean_times or [],
            llm_times=llm_times or [],
        )

    @staticmethod
    def mk_implementer(
        sub_id: int,
        decls: list[Declaration],
        dialog: Dialog,
        success: bool,
        outcomes: Outcomes | None,
        merged: bool = True,
        merge_reason: str | None = None,
        start: float | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id=sub_id,
            action=Action.METHOD,
            decls=decls,
            dialog=dialog,
            timestamp=time(),
            outcomes=outcomes,
            success=success,
            merged=merged,
            merge_reason=merge_reason,
            start=start,
        )

    @staticmethod
    def mk_final_fix(
        sub_id: int,
        decls: list[Declaration],
        dialog: Dialog,
        rev_id: int,
        outcomes: Outcomes | None,
        start: float | None = None,
    ) -> "AgentResult":
        return AgentResult(
            sub_id=sub_id,
            action=Action.FINAL_FIX,
            decls=decls,
            dialog=dialog,
            timestamp=time(),
            rev_id=rev_id,
            outcomes=outcomes,
            success=outcomes is not None and outcomes.get("pass"),
            merged=True,
            merge_reason="not applicable to final fixer",
            start=start,
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable representation. Dialog is stored separately."""
        return {
            "sub_id": self.sub_id,
            "learning": self.learning,
            "action": self.action.value,
            "merged": self.merged,
            "merge_reason": self.merge_reason,
            "diff": self.diff,
            "diff_reviewed": self.diff_reviewed,
            "revision_idx": self.revision_idx,
            "start": self.start,
            "timestamp": self.timestamp,
            "lean_times": self.lean_times,
            "llm_times": self.llm_times,
            "total_lean_time": sum(self.lean_times),
            "total_llm_time": sum(self.llm_times),
            "rev_id": self.rev_id,
            "goal_idx": self.goal_idx,
            "success": self.success,
            "aborted": self.aborted,
            "auto": self.auto,
            "decls": [
                {
                    "type": d.__class__.__name__,
                    "code": d.render(),
                    "name": getattr(d, "name", None),
                    "statement": getattr(d, "statement", None),
                }
                for d in self.decls
            ],
        }


def escape_tag(tag: str) -> str:
    if tag in {"ensures", "decreasing", "assert"}:
        return f"«{tag}»"
    return tag


def revert_names(proof: str) -> str:
    return proof.replace("_require_", "«require»")


@dataclass
class HierarchicalProof:
    file: LeanFile  # header + method (+ aux theorems) + dummy theorem
    goals: list[Theorem]  # extracted subgoals, indexed by position
    goal_tags: list[str]  # tags corresponding to goals (may have duplicates)
    # attempts per goal (by index):
    n_attempts: defaultdict[int, int] = field(default_factory=lambda: defaultdict(int))
    # method implementation proposals by goal index (parsed Method and raw code):
    proposals: defaultdict[int, list[Method]] = field(
        default_factory=lambda: defaultdict(list)
    )
    proposals_raw: defaultdict[int, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    reviser_launched: bool = False  # has the reviser been launched yet?

    def __post_init__(self) -> None:
        assert len(self.goals) == len(self.goal_tags), "Goals and tags length mismatch"

    def find_goal_by_tag(self, tag: str) -> Theorem | None:
        """Find the first goal with the given tag, or None if not found."""
        for idx, t in enumerate(self.goal_tags):
            if t == tag:
                return self.goals[idx]
        return None

    def proved(self, idx: int) -> bool:
        return self.goals[idx].proof is not None

    def all_proved(self) -> bool:
        return all(thm.proof is not None for thm in self.goals)

    def success(self, idx: int) -> bool:
        return self.proved(idx) or bool(self.proposals[idx])

    def all_success(self) -> bool:
        return all(self.success(idx) for idx in range(len(self.goals)))

    def done(self, idx: int, max_attempts: int) -> bool:
        return self.success(idx) or self.failed(idx, max_attempts)

    def all_done(self, max_attempts: int) -> bool:
        return all(self.done(idx, max_attempts) for idx in range(len(self.goals)))

    def failed(self, idx: int, max_attempts: int) -> bool:
        return not self.success(idx) and self.n_attempts[idx] >= max_attempts

    def any_failed(self, max_attempts: int) -> bool:
        return any(self.failed(idx, max_attempts) for idx in range(len(self.goals)))

    def to_dict(self) -> dict:
        return {
            "file": self.file.to_dict(),
            "goals": [
                {
                    "type": thm.__class__.__name__,
                    "code": thm.render(),
                    "name": thm.name,
                    "statement": thm.statement,
                    "tag": self.goal_tags[idx] if idx < len(self.goal_tags) else None,
                }
                for idx, thm in enumerate(self.goals)
            ],
            "final": self.full_file().to_dict(),
        }

    def full_file(self) -> LeanFile:
        """
        Return the reassembled Lean file with all subgoal proofs filled in
        in case there are any goals, otherwise return the original file.
        """
        if not self.goals:
            return copy.deepcopy(self.file)

        full_proof = "  loom_solve\n" + "\n".join(
            f"  case {escape_tag(self.goal_tags[idx])} => (\n{revert_names(thm.proof or 'sorry')}\n  )"
            for idx, thm in enumerate(self.goals)
        )
        new_file = copy.deepcopy(self.file)
        new_file.main_theorem.proof = full_proof
        new_file.main_theorem.metadata = "set_option maxHeartbeats 10000000 in"
        return new_file


@dataclass
class ProblemContext:
    ctx: GlobalContext
    done_event: Event | None
    task: Task
    dialogs: dict[int, Dialog]
    revisions: list[
        LeanFile | HierarchicalProof
    ]  # LeanFile for multi.py, HierarchicalProof for decomp.py
    learnings: list[str] = field(default_factory=list)
    agent_results: dict[int, AgentResult] = field(default_factory=dict)
    base_dialog: Dialog | None = None  # dialog from which other dialogs branch

    # decompsoition agent
    lock: Any | None = None
    termination_reason: str | None = None

    def terminated(self) -> bool:
        with self.lock:
            return self.termination_reason is not None

    @property
    def args(self) -> RunArgs:
        return self.ctx.args

    @property
    def env(self) -> Env:
        return self.ctx.env

    @property
    def runner(self) -> LeanRepl | ResourcePool:
        return self.ctx.runner

    @property
    def current(self) -> LeanFile | HierarchicalProof:
        return self.revisions[-1]


@dataclass
class MultiAgentRollout(Rollout):
    """Complete interaction history from a multi-agent rollout"""

    n_subs: int
    dialogs: dict[int, Dialog]  # all dialogs by sub_id
    revisions: list[LeanFile]  # evolution of the file
    learnings: list[str]
    agent_results: dict[int, AgentResult] = field(default_factory=dict)  # by sub_id
    terminated: bool = True  # False for incremental dumps

    @property
    def file(self) -> LeanFile:
        return self.revisions[-1]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_input_tokens": sum(
                dialog.total_input_tokens for dialog in self.dialogs.values()
            ),
            "total_output_tokens": sum(
                dialog.total_output_tokens for dialog in self.dialogs.values()
            ),
            "total_calls": sum(dialog.total_calls for dialog in self.dialogs.values()),
        }

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        return {
            "task": self.task,
            "n_subs": self.n_subs,
            "final_code": self.file.render(),
            "dialogs": {k: v.to_dict() for k, v in self.dialogs.items()},
            "revisions": [f.to_dict() for f in self.revisions],
            "declarations": [
                {
                    "type": decl.__class__.__name__,
                    "code": decl.render(),
                    "name": getattr(decl, "name", None),
                    "statement": getattr(decl, "statement", None),
                }
                for decl in self.file.decls
            ],
            "learnings": self.learnings,
            "outcomes": self.outcomes,
            "stats": self.stats,
            "agent_results": {
                sub_id: res.to_dict() for sub_id, res in self.agent_results.items()
            },
            "terminated": self.terminated,
        }


def detect_action(decls: list[Declaration]) -> Action:
    # for multi-agent setting
    if not decls:
        return Action.EMPTY

    if any(isinstance(d, Method) for d in decls):
        return Action.METHOD

    if any(isinstance(d, Theorem) and d.theorem_type == "prove_correct" for d in decls):
        return Action.PROVE_CORRECT

    if any(isinstance(d, Theorem) and d.name.endswith("_unsat") for d in decls):
        return Action.DISPROVE

    return Action.ADD


def detect_prover_action(decls: list[Declaration]) -> Action:
    # for hierarchical prover
    if any(isinstance(d, Method) for d in decls):
        return Action.METHOD

    return Action.PROVE_SUBGOAL


def filter_decls(decls: list[Declaration], action: Action) -> list[Declaration]:
    """
    Filter declarations based on the specified action.
    """
    match action:
        case Action.METHOD:
            methods = [d for d in decls if isinstance(d, Method)]
            assert methods
            return methods[-1:]  # return the last method
        case Action.PROVE_CORRECT:
            thms = [
                d
                for d in decls
                if isinstance(d, Theorem) and d.theorem_type == "prove_correct"
            ]
            assert thms
            return thms[:1]
        case Action.DISPROVE:
            unsat_thms = [
                d for d in decls if isinstance(d, Theorem) and d.name.endswith("_unsat")
            ]
            assert unsat_thms
            return unsat_thms[:1]
        case Action.ADD:
            return [
                d
                for d in decls
                if isinstance(d, OtherLean)
                or (isinstance(d, Theorem) and d.theorem_type != "prove_correct")
            ]
        case Action.EMPTY:
            return []
        case _:
            raise ValueError(f"Unknown action: {action}")


def make_decls(code: str) -> list[Declaration]:
    """
    Split code and convert into `Theorem` / `Method` / `OtherLean` declarations.
    """
    blocks = split_decls_by_keyword(code)
    decls = []
    for block in blocks:
        if theorem_type(block):
            decls.append(Theorem.from_str(block))
        elif re.match(r"^\s*method\b", block):
            decls.append(Method.from_str(block))
        else:
            decls.append(OtherLean(block))
    return decls


@dataclass
class HierachicalRollout(Rollout):
    n_subs: int
    dialogs: dict[int, Dialog]  # all dialogs by sub_id
    revisions: list[HierarchicalProof]
    learnings: list[str]
    termination_reason: str
    agent_results: dict[int, AgentResult] = field(default_factory=dict)  # by sub_id
    decomp_rev_id: int | None = (
        None  # revision id of hierarchical proof before final fixes
    )
    terminated: bool = True  # False for incremental dumps

    @property
    def current(self) -> HierarchicalProof:
        return self.revisions[-1]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "total_input_tokens": sum(
                dialog.total_input_tokens for dialog in self.dialogs.values()
            ),
            "total_output_tokens": sum(
                dialog.total_output_tokens for dialog in self.dialogs.values()
            ),
            "total_calls": sum(dialog.total_calls for dialog in self.dialogs.values()),
        }

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict"""
        return {
            "task": self.task,
            "n_subs": self.n_subs,
            "final_code": self.current.file.render(),
            "dialogs": {k: v.to_dict() for k, v in self.dialogs.items()},
            "revisions": [f.to_dict() for f in self.revisions],
            "learnings": self.learnings,
            "outcomes": self.outcomes,
            "stats": self.stats,
            "termination_reason": self.termination_reason,
            "agent_results": {
                sub_id: res.to_dict() for sub_id, res in self.agent_results.items()
            },
            "decomp_rev_id": self.decomp_rev_id,
            "terminated": self.terminated,
        }
