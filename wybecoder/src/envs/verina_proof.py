# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger

from src.env import Dialog, Env, Message, Task

import json
from src.utils import (
    extract_method_name,
    header_unmodified,
    includes_guard_statements,
    normalize_lean,
)
from src.envs.common_strings import (
    MODIFIED_HEADER_MESSAGE,
    ADDITIONAL_GUARD_STATEMENTS_MESSAGE,
)

logger = getLogger()


def format_lean_value(value, lean_type: str) -> str:
    """Format a value for Lean based on its expected type."""
    if lean_type == "String":
        return f'"{value}"'
    elif lean_type == "Char":
        return f"'{value}'"
    elif lean_type == "Bool":
        # Bool values come as "True" or "False" strings, need to lowercase
        return str(value).lower()
    else:
        # For all other types, assume the value is already valid Lean code
        s = str(value)
        # Wrap negative numbers in parentheses
        if s.startswith("-"):
            s = f"({s})"
        return s


def verina_tests_to_guard_statements(test_data: dict, method_name: str) -> str:
    """
    Convert Verina test cases to #guard statements.

    Args:
        test_data: Verina test dictionary with 'tests' field
        method_name: Name of the method to test

    Returns:
        String with #guard statements, or empty string if no tests
    """
    tests = test_data.get("tests", {})
    if not tests:
        return ""

    inputs = tests.get("input", [])
    expected = tests.get("expected", [])

    if not inputs or not expected:
        return ""

    signature = test_data.get("signature", {})
    parameters = signature.get("parameters", {})
    param_names = parameters.get("param_name", [])
    param_types = parameters.get("param_type", [])
    return_type = signature.get("return_type", None)

    # Map param name to type
    param_type_map = dict(zip(param_names, param_types))

    guard_statements = []

    for input_str, expected_list in zip(inputs, expected):
        if not expected_list:
            continue

        # Parse input JSON string
        try:
            input_dict = json.loads(input_str)
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(
                f"Failed to parse VERINA test input JSON: {input_str}. "
                f"Error: {e}. Please check the test data format."
            )

        # Build method call with parameters
        param_values = []
        for param_name in param_names:
            if param_name in input_dict:
                value = input_dict[param_name]
                lean_type = param_type_map.get(param_name, None)
                value_str = format_lean_value(value, lean_type)
                param_values.append(value_str)

        method_call = f"{method_name} {' '.join(param_values)}"

        # Get expected output (take first if multiple)
        expected_val = expected_list[0] if expected_list else None
        if expected_val is None:
            continue

        expected_str = format_lean_value(expected_val, return_type)

        # Create #guard statement
        # Methods return values, so we check: (method_call).extract == expected_val
        guard_statements.append(f"#guard ({method_call}).extract == {expected_str}")

    return "\n".join(guard_statements)


class VerinaProofEnv(Env):
    @classmethod
    def initial(cls, task: Task) -> Dialog:
        system = cls.get_system_prompt(task)
        user = INITIAL.format(**task)
        return Dialog([Message.user(user)], system)

    @classmethod
    def get_test_cases(cls, task: Task, method_name: str) -> str:
        return verina_tests_to_guard_statements(task, method_name)

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

        is_method = header_unmodified(code, task["loom_header"])
        is_unsat = cls.is_unsat_proof(task, code)

        # Check if the header was modified and if guard statements were added
        is_valid = (is_method and has_correctness_proof) or is_unsat
        has_guard_statements = includes_guard_statements(code)
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

NOTE: in some cases, the specification may turn out to be unsatisfiable.
In this case, please prove the following theorem instead, again without modifying the statement in any way (string comparison).
You will be able to do an interactive proof with Lean's feedback.

```lean
{unsat_theorem}
```
""".strip()
