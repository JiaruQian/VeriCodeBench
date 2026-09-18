# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger
from typing import ClassVar
from src.utils import (
    extract_benchmark_blocks,
    extract_method_name,
    header_unmodified,
    extract_benchmark_content_for_tag,
    includes_guard_statements,
    normalize_lean,
)

from src.env import Env, Task, Dialog, Message
from src.envs.common_strings import (
    MODIFIED_HEADER_MESSAGE,
    ADDITIONAL_GUARD_STATEMENTS_MESSAGE,
)

logger = getLogger()


INITIAL = """
Please help me define and prove a function that matches the description using Velvet in Lean.
You should prove that it satisfies the `require` / `ensures` specification given below.
Feel free to add helper lemmas that help for the automatic or manual proof.

{description}

The specification which your method should be proved to satisfy is as follows.
Please use this header and DO NOT MODIFY the code above the `do`.
A string comparison will be used to check that the specification wasn't tampered with,
so we cannot change it at all.
If you need to define helper lemmas or to tag lemmas as `solverHints`,
please do so AFTER the Loom `method` definition.
```lean
{loom_header}
```

Please also return your code in triple backticks ```lean ... ``` including the above header so that I can copy it into a file.
I will only read the last `lean` code block and not perform any other actions in the source directory.
""".strip()


class CleverProofEnv(Env):
    initial_prompt: ClassVar[str] = INITIAL

    @classmethod
    def initial(cls, task: Task) -> Dialog:
        system = cls.get_system_prompt(task)
        user = cls.initial_prompt.format(**task)

        return Dialog([Message.user(user)], system)

    @classmethod
    def get_test_cases(cls, task: Task, method_name: str) -> str:
        if "lean_code" not in task:
            return ""
        benchmark_blocks = extract_benchmark_blocks(task["lean_code"])
        return extract_benchmark_content_for_tag(
            benchmark_blocks, tag_name="Lean tests"
        )

    @classmethod
    def evaluate(
        cls,
        task: Task,
        code: str,
        diagnostics: dict,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        # Use the base _evaluate method which includes axiom checking and test validity
        success, message = cls._evaluate(
            diagnostics,
            allow_sorry=False,
            check_axiom_usage=True,
            check_test_validity=True,
            goedel_format=goedel_format,
            start_line=start_line,
        )

        method_name = extract_method_name(task.get("loom_header", ""))
        if not method_name:
            raise ValueError(
                "Could not extract method name from loom_header. Please check the task format."
            )

        normalized = normalize_lean(code)
        has_correctness_proof = f"prove_correct {method_name} by" in normalized

        # Check if the header was modified and if guard statements were added
        is_header_unmodified = header_unmodified(code, task["loom_header"])
        has_guard_statements = includes_guard_statements(code)
        is_valid = is_header_unmodified and has_correctness_proof
        if is_valid and not has_guard_statements:
            return success, message
        else:
            final_message_parts: list[str] = []
            if message:
                final_message_parts.append(message + "\n\n")
            if not is_valid:
                final_message_parts.append(MODIFIED_HEADER_MESSAGE + "\n\n")
            if has_guard_statements:
                final_message_parts.append(ADDITIONAL_GUARD_STATEMENTS_MESSAGE)

        return False, "\n\n".join(final_message_parts)


MULTI_INITIAL = """
Please help me define and prove a function that matches the description using Velvet in Lean.
You should prove that it satisfies the `require` / `ensures` specification given below.
Feel free to add helper lemmas that help for the automatic or manual proof.

{description}

The specification which your method should be proved to satisfy is as follows.
Please use this header and DO NOT MODIFY the code above the last `do`.
A string comparison will be used to check that the specification wasn't tampered with,
so we cannot change it at all. If there are additional methods and proofs with `sorry`
above the main method, these are helper methods that you may use according to their specification
without having to implement/prove them. You can keep those `sorry`s as they are.
If you need to define helper lemmas or to tag lemmas as `solverHints`,
please do so AFTER the Loom `method` definition.
```lean
{loom_header}
```

Please also return your code in triple backticks ```lean ... ``` including the above header so that I can copy it into a file.
I will only read the last `lean` code block and not perform any other actions in the source directory.
""".strip()


class LongHeaderProofEnv(CleverProofEnv):
    """
    Same as CleverProofEnv but compatible with multi method setups that
    use `sorry` in header method declarations and proofs by setting `allow_sorry_in_header=True`.
    """

    initial_prompt: ClassVar[str] = MULTI_INITIAL
    allow_sorry_in_header: ClassVar[bool] = True
