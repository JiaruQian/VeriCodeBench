# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import abc
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from itertools import groupby
from logging import getLogger
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, ClassVar, Iterator, Optional

from src.repl import (
    check_axioms,
    check_test_validity as check_test_validity_fn,
    filter_errors,
    format_errors,
    sorry_errors,
)
from src.utils import (
    contains_normalized,
    extract_method_name,
    log_time,
    method_spec_line,
    raw_first_line_idx,
)

logger = getLogger()


Task = dict[str, str]
Outcomes = dict[str, Any]


@dataclass
class Message:
    role: str
    content: str
    tool_dialog: Optional["Dialog"] = None
    input_tokens: int = 0
    output_tokens: int = 0

    @staticmethod
    def user(content: str) -> "Message":
        return Message("user", content)

    @staticmethod
    def assistant(
        content: str,
        tool_dialog: Optional["Dialog"] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> "Message":
        return Message("assistant", content, tool_dialog, input_tokens, output_tokens)

    def to_gemini(self) -> dict:
        match self.role:
            case "user":
                return {"role": "user", "parts": [{"text": self.content}]}
            case "assistant":
                return {"role": "model", "parts": [{"text": self.content}]}
            case _:
                raise ValueError(f"unknown role: {self.role}")

    def to_openai(self) -> dict:
        return {"role": self.role, "content": self.content}

    @property
    def n_calls(self) -> int:
        if self.tool_dialog is None:
            return int(self.role == "assistant")

        # Count groups of consecutive assistant messages in the tool dialog.
        # Note that the last tool_dialog message is the current message,
        # so we do not need to take it into account.
        return sum(
            1
            for role, _ in groupby(self.tool_dialog, key=lambda m: m.role)
            if role == "assistant"
        )

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "tool_dialog": self.tool_dialog.to_dict() if self.tool_dialog else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass
class Dialog:
    messages: list[Message] = field(default_factory=list)
    system_prompt: str | None = None

    def append(self, msg: Message) -> None:
        self.messages.append(msg)

    def __len__(self) -> int:
        return len(self.messages)

    def __iter__(self) -> Iterator[Message]:
        return iter(self.messages)

    def to_gemini(self) -> list[dict]:
        return [msg.to_gemini() for msg in self.messages]

    def to_openai(self) -> list[dict]:
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        return result + [msg.to_openai() for msg in self.messages]

    @property
    def total_input_tokens(self) -> int:
        return sum(msg.input_tokens for msg in self.messages)

    @property
    def total_output_tokens(self) -> int:
        return sum(msg.output_tokens for msg in self.messages)

    @property
    def total_calls(self) -> int:
        return sum(msg.n_calls for msg in self.messages)

    def to_dict(self) -> dict:
        return {
            "messages": [m.to_dict() for m in self.messages],
            "system_prompt": self.system_prompt,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_calls": self.total_calls,
        }

    def preview(self, max_msg_chars: int = 100) -> str:
        preview_msgs = []
        for msg in self.messages:
            content_preview = (
                msg.content
                if len(msg.content) <= max_msg_chars
                else msg.content[: max_msg_chars - 3]
                + f"... (total {len(msg.content)} chars)"
            )
            preview_msgs.append(f"{msg.role.upper()}:\n{content_preview}\n")
        return "\n".join(preview_msgs)


class Env(abc.ABC):
    """Defines a **stateless** environment interface.

    Structure for an environment that does not maintain its
    own internal state. All methods are static,
    ensuring that no instance state is accessed or modified.

    The environment's state should be managed within the `task` object,
    while the `runner` object is responsible for executing actions.
    """

    allow_sorry_in_header: ClassVar[bool] = False

    @classmethod
    @abc.abstractmethod
    def initial(cls, task: Task) -> Dialog:
        """Gets the initial state of the environment.

        Args:
            task: The Task object containing the environment's static
                configuration and definition.

        Returns:
            A Dialog object representing the initial system and user messages
            that start the trajectory.
        """
        raise NotImplementedError

    @classmethod
    def _evaluate(
        cls,
        diagnostics: dict,
        allow_sorry: bool = False,
        allow_sorry_in_header: bool | None = None,
        check_axiom_usage: bool = True,
        check_test_validity: bool = True,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Evaluates the result of a code execution.

        Args:
            diagnostics: The diagnostics dictionary from the runner.
            allow_sorry: If True, don't treat sorries as errors.
            allow_sorry_header: If True, allow sorries in the header part of the code.
                If unset, use class variable `allow_sorry_in_header`.
            check_axiom_usage: If True, check for non-allowed axioms.
            check_test_validity: If True, check if test cases pass.
            goedel_format: If True, format errors in Goedel style.
            start_line: Line starting at which to check for sorry errors.
                If None, uses the line of the method spec in the executed code.
                Only with `allow_sorry_in_header=True`.

        Flags always influence success, but don't influence error formatting
        for Goedel format style.

        Returns:
            success (bool) - whether the code is deemed correct.
            message (str | None): A feedback message, or `None` if successful.
        """
        errors = filter_errors(diagnostics.get("messages", []))

        ran = diagnostics["executed_code"]

        allow_sorry_in_header = (
            allow_sorry_in_header
            if allow_sorry_in_header is not None
            else cls.allow_sorry_in_header
        )

        if allow_sorry:
            # no sorry error checks
            pass
        elif allow_sorry_in_header:
            try:
                if start_line is not None:
                    idx = raw_first_line_idx(ran, start_line)
                else:
                    idx = method_spec_line(ran)
            except ValueError as e:
                idx = None  # fall back to stricter check
                logger.warning(
                    f"Caught error for allow_sorry_in_header, falling back to stricter check: {e}"
                )
            errors += sorry_errors(diagnostics, start_line_idx=idx)
        else:
            errors += sorry_errors(diagnostics, start_line_idx=None)

        # Check for non-allowed axioms if requested
        if check_axiom_usage:
            axiom_errors = check_axioms(diagnostics)
            errors += axiom_errors

        # Check for test case failures if requested
        if check_test_validity:
            test_errors = check_test_validity_fn(diagnostics)
            errors += test_errors

        if not errors:
            return True, None

        # errors found, format them
        errors_pp = format_errors(ran, errors, goedel_format=goedel_format)
        return False, cls.get_feedback_prompt().format(errors_pp)

    @classmethod
    def evaluate(
        cls,
        task: Task,
        code: str,
        diagnostics: dict,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        return cls._evaluate(
            diagnostics,
            allow_sorry=False,
            goedel_format=goedel_format,
            start_line=start_line,
        )

    @classmethod
    def get_test_cases(cls, task: Task, method_name: str) -> str:
        """Extracts and converts test cases to Lean code.

        Subclasses should override this to handle specific test formats.
        """
        return ""

    @classmethod
    def is_unsat_proof(cls, task: Task, code: str) -> bool:
        """Determines if the provided code is intended to be an unsat proof.

        This method checks if the (normalized) code contains the (normalized) unsat theorem from the task.

        Args:
            task: The Task object containing the unsat header.
            code: The Lean code to be checked.

        Returns:
            bool: True if the code contains the unsat theorem, False otherwise.
        """
        if "unsat_theorem" not in task:
            return False
        unsat_theorem = task["unsat_theorem"]
        return contains_normalized(code, unsat_theorem, stop_word="by")

    @classmethod
    def prepare_code(cls, task: Task, code: str, final: bool) -> str:
        """Prepares the code for execution.

        If final is set, injects test cases (via get_test_cases) and axiom checks.
        This is the default for linear agents but typically not for multi-agent systems.
        """
        # For non-final code, no tests / axiom checks
        if not final:
            return code

        method_name = extract_method_name(task.get("loom_header", ""))
        if not method_name:
            raise ValueError(
                "Could not extract method name from loom_header. Please check the task format."
            )
        is_unsat = cls.is_unsat_proof(task, code)

        # Add test cases
        test_cases = cls.get_test_cases(task, method_name)
        if test_cases and not is_unsat:
            code += f"\n\n{test_cases}"

        # Add axiom checks
        if is_unsat:
            code += f"\n\n#print axioms {method_name}_spec_unsat"
        else:
            code += f"\n\n#print axioms {method_name}"
            code += f"\n\n#print axioms {method_name}_correct"

        return code

    @classmethod
    def _step(
        cls,
        runner: Any,
        task: Task,
        action: str,
        extract: bool = True,
        diagnostics: dict | None = None,
        final: bool = True,
        goedel_format: bool = False,
        start_line: str | None = None,
        evaluate_fn: Callable[
            [Task, str, dict, bool, str], tuple[bool, str | None]
        ] = None,
    ) -> tuple[str | None, Outcomes]:
        """
        Same as Env.step, but allows custom evaluation functions.
        """
        if extract:
            code = Env.extract_code(action).strip()
        else:
            code = action
        is_disproof = cls.is_unsat_proof(task, code) if code else False

        def mk_outcomes(success=False, lean_oom=False):
            "Closure over `abort` and `code`."

            return {
                "raw_pass": success,
                "pass": success and not is_disproof,
                "lean_oom": lean_oom,
                "final_code": code,
                "abort": False,  # disabled feature, keep for compatibility
                "is_disproof": is_disproof,
                "disproof_pass": success and is_disproof,
            }

        if not code:
            return PARSING_MESSAGE, mk_outcomes()

        try:
            if diagnostics is None:
                code_to_run = cls.prepare_code(task, code, final)
                diagnostics = runner.run(code_to_run)
            success, message = evaluate_fn(
                task,
                code,
                diagnostics,
                goedel_format=goedel_format,
                start_line=start_line,
            )
            if success:
                return None, mk_outcomes(success=True)

        except RuntimeError as e:
            # REPL error (typically OOM)
            logger.error("Lean execution error.", exc_info=e)
            return CRASH_MESSAGE, mk_outcomes(lean_oom=True)
        except TimeoutExpired:
            # timeout
            logger.warning("Lean execution timeout error.")
            message = TIMEOUT_MESSAGE

        return message, mk_outcomes()

    @classmethod
    @log_time
    def step(
        cls,
        runner: Any,
        task: Task,
        action: str,
        extract: bool = True,
        diagnostics: dict | None = None,
        final: bool = True,
        goedel_format: bool = False,
        start_line: str | None = None,
        **kwargs,
    ) -> tuple[str | None, Outcomes]:
        """Executes one action and advances the environment.

        This method uses the `runner` to perform the given `action`. If this
        action causes the trajectory to terminate, this method returns
        the final outcomes.

        Use _step for custom evaluation functions instead of cls.evaluate.

        Args:
            runner: The execution agent responsible for performing the action.
            task: The Task object representing the current state.
            action: The action string to be executed.
            extract: Flag to extract code from action.
            diagnostics: Optional diagnostics to use instead of running.
            final: Whether this is the final proof check (inject tests / axiom checks).
            goedel_format: Whether to format errors in Goedel style.
            start_line (optional): Line starting at which the code was edited.
        Returns:
            observation (str | None): The observation for the next action if
                the episode is not terminated, otherwise `None`.
            outcomes (Outcomes): step execution results.
        """
        return cls._step(
            runner,
            task,
            action,
            extract,
            diagnostics,
            final,
            goedel_format,
            start_line,
            evaluate_fn=cls.evaluate,
        )

    @staticmethod
    def extract_code(text: str, last: bool = True) -> str:
        matches = re.findall(r"```lean4?(.*?)```", text, re.DOTALL)
        if matches:
            idx = -1 if last else 0
            return matches[idx]
        else:
            return ""

    @staticmethod
    def get_loom_prompt(prompt_path: str = "data/prompt_linear.md") -> str:
        return _get_prompt(prompt_path)

    @staticmethod
    def get_mcp_prompt() -> str:
        return _get_prompt("data/prompt_mcp.md")

    @staticmethod
    def get_cheatsheet_prompt() -> str:
        return _get_prompt("data/prompt_cheatsheet.md")

    @classmethod
    def get_system_prompt(cls, task: Task) -> str:
        prompt_path = task.get("prompt_path", "data/prompt_linear.md")
        result = Env.get_loom_prompt(prompt_path)
        if task.get("use_cheatsheet"):
            result += "\n" + Env.get_cheatsheet_prompt()
        # If MCP is enabled, append MCP guidance
        if task.get("use_mcp"):
            result += "\n" + Env.get_mcp_prompt()
        return result

    @classmethod
    def get_feedback_prompt(cls) -> str:
        return FOLLOWUP_PROMPT


FOLLOWUP_PROMPT = """
I ran the code but got the following errors.
Could you please figure out what went wrong and fix them?
Please return the new full code again in triple backticks.

{}

Note: if you figure out that the spec is unsatisfiable,
you MUST prove the unsatisfiability theorem provided in my first message.
In this case we will do several rounds of interactive proving with Lean's feedback.
""".strip()


PARSING_MESSAGE = """
Could not extract code, please try again in the expected format described above.
""".strip()


TIMEOUT_MESSAGE = """
The code execution timed out. Please revise the code for faster proof search and checking.
""".strip()


CRASH_MESSAGE = """
The code execution crashed or ran out of memory. Please revise the code to avoid this.
""".strip()


HEADER = """
import Auto
import Aesop
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil
""".strip()


STARTER = f"""
{HEADER}

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true
""".strip()


@cache
def _get_prompt(relative_path: str) -> str:
    "relative_path is relative to svagent/"
    fn = Path(__file__).parent.parent / relative_path
    with fn.open() as f:
        return f.read()
