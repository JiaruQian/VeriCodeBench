# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger
from typing import Any, ClassVar

from src.env import Dialog, Message, Outcomes, Task, _get_prompt
from src.envs.clever_proof import CleverProofEnv
from src.envs.verina_proof import VerinaProofEnv
from src.utils import header_unmodified, log_time


logger = getLogger()


INITIAL = """
Please help me implement a function that matches the description using Velvet in Lean.
We will later prove its correctness, i.e. that it satisfies the given `require` / `ensures` specification.

{description}

The specification which your method should satisfy is as follows.
Please assume this header to be fixed and DO NOT MODIFY the specification (the code above the last `do`).
A string comparison will be used to check that the specification wasn't tampered with,
so we cannot change it at all.
```lean
{loom_header}
```

Please return the code of the last `method` declaration (starting with "method") in triple backticks ```lean ... ```
I will only read the last `lean` code block and not perform any other actions in the source directory.
For all `invariant`, `done_with` and `decreasing` annotations, you MUST use identifier labels
such as `invariant hi : i < n` so that I can refer to them later.

Remember the **imperative code requirements** which are strictly enforced:
the entire asymptotically non-constant-time core must be written with explicit loops and mutable state,
not using higher-order traversals, recursive traversals, or library calls that hide iteration (map, fold, filter, sort, etc.).
Functional style is allowed only for truly O(1) operations (arithmetic, comparisons, tuple ops, single indexing, simple conditionals)
and in ghost/invariant code, not for any real data traversal or reorganization.
In particular, do NOT use functional code that directly mimics the functional specification, which would make verification trivial but
useless for our purposes.
""".strip()


UNSAT_INITIAL = """
Please help me implement a function that matches the description using Velvet in Lean.
We will later prove its correctness, i.e. that it satisfies the given `require` / `ensures` specification.

{description}

The specification which your method should satisfy is as follows.
Please assume this header to be fixed and DO NOT MODIFY the specification (the code above the last `do`).
A string comparison will be used to check that the specification wasn't tampered with,
so we cannot change it at all.
```lean
{loom_header}
```

Please return the code of the last `method` declaration (starting with "method") in triple backticks ```lean ... ```
I will only read the last `lean` code block and not perform any other actions in the source directory.
For all `invariant`, `done_with` and `decreasing` annotations, you MUST use identifier labels
such as `invariant hi : i < n` so that I can refer to them later.

Remember the **imperative code requirements** which are strictly enforced:
the entire asymptotically non-constant-time core must be written with explicit loops and mutable state,
not using higher-order traversals, recursive traversals, or library calls that hide iteration (map, fold, filter, sort, etc.).
Functional style is allowed only for truly O(1) operations (arithmetic, comparisons, tuple ops, single indexing, simple conditionals)
and in ghost/invariant code, not for any real data traversal or reorganization.
In particular, do NOT use functional code that directly mimics the functional specification, which would make verification trivial but
useless for our purposes.

NOTE: in some cases, the specification may turn out to be unsatisfiable.
For future reference, I'll already give you the statement of the corresponding unsatisfiability theorem here:
```lean
{unsat_theorem}
```
""".strip()


MODIFIED_HEADER_MESSAGE = """
The code ran successfully, but the specification header was modified.
Please revert to the header I provided originally.
""".strip()


class MultiEnvMixin:
    """Overrides for multi.py interaction style."""

    initial_prompt: ClassVar[str]  # subclasses set this

    @classmethod
    def initial(cls, task: Task) -> Dialog:
        system = cls.get_system_prompt(task)
        user = cls.initial_prompt.format(**task)
        return Dialog([Message.user(user)], system)

    @staticmethod
    def get_loom_prompt() -> str:
        return _get_prompt("data/prompt_multi.md")

    @classmethod
    def get_feedback_prompt(cls) -> str:
        # Bare errors only, wrapped elsewhere
        return "{}"


class VerinaMultiEnv(MultiEnvMixin, VerinaProofEnv):
    initial_prompt = UNSAT_INITIAL


class CleverMultiEnv(MultiEnvMixin, CleverProofEnv):
    initial_prompt = INITIAL


class LongHeaderMultiEnv(MultiEnvMixin, CleverProofEnv):
    initial_prompt = INITIAL
    allow_sorry_in_header: ClassVar[bool] = True


class DecompEnvMixin:
    """Overrides for decomp.py interaction style."""

    @classmethod
    def get_loom_prompt(cls) -> str:
        return _get_prompt("data/prompt_decomp.md")

    @classmethod
    def evaluate_method(
        cls,
        task: Task,
        code: str,
        diagnostics: dict,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Like VerinaProofEnv.evaluate, but expects only a method implementation.
        Use this for initial interactions in decomposition multi-agents.
        """
        # Use the base _evaluate method which includes axiom checking and test validity
        success, message = cls._evaluate(
            diagnostics,
            allow_sorry=False,
            check_axiom_usage=True,
            check_test_validity=True,
            goedel_format=goedel_format,
            start_line=start_line,
        )

        is_method = header_unmodified(code, task["loom_header"])

        if is_method:
            return success, message
        else:
            final_message_parts: list[str] = []
            if message:
                final_message_parts.append(message + "\n\n")
            if not is_method:
                final_message_parts.append(MODIFIED_HEADER_MESSAGE + "\n\n")

        return False, "\n\n".join(final_message_parts)

    @classmethod
    def evaluate_proof(
        cls,
        task: Task,
        code: str,
        diagnostics: dict,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Evaluate subgoal proofs in decomposition multi-agents.
        """
        # extract the line of the beginning of the

        return cls._evaluate(
            diagnostics,
            allow_sorry=False,
            check_axiom_usage=True,
            check_test_validity=True,
            goedel_format=goedel_format,
            start_line=start_line,
        )

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
        step_type = kwargs.get("step_type", "full")
        if step_type == "method":
            evaluate_fn = cls.evaluate_method
        elif step_type == "proof":
            evaluate_fn = cls.evaluate_proof
        elif step_type == "full":
            evaluate_fn = cls.evaluate
        else:
            raise ValueError(f"Unknown step_type: {step_type}")

        return cls._step(
            runner,
            task,
            action,
            extract,
            diagnostics,
            final,
            goedel_format,
            start_line=start_line,
            evaluate_fn=evaluate_fn,
        )


class VerinaDecompEnv(DecompEnvMixin, VerinaMultiEnv):
    pass


class CleverDecompEnv(DecompEnvMixin, CleverMultiEnv):
    pass


class LongHeaderDecompEnv(DecompEnvMixin, LongHeaderMultiEnv):
    pass
