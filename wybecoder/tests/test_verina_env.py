# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import pytest
from src.envs.verina_proof import VerinaProofEnv, verina_tests_to_guard_statements
from src.repl import LeanRepl
from tests.tests_data.verina_env_data import SAMPLE_TASK, SAMPLE_CODE, CODE_WITH_AXIOM


@pytest.fixture(scope="function")
def lean_repl():
    repl = LeanRepl()
    yield repl
    repl.close()


def test_verina_tests_to_guard_statements():
    method_name = "DoubleQuadruple"
    guards = verina_tests_to_guard_statements(SAMPLE_TASK, method_name)

    # Check that guards are generated correctly
    expected_0 = "#guard (DoubleQuadruple 0).extract == (0, 0)"
    expected_1 = "#guard (DoubleQuadruple 1).extract == (2, 4)"

    assert expected_0 in guards, f"Expected guard not found\n{expected_0}\nin\n{guards}"
    assert expected_1 in guards, f"Expected guard not found\n{expected_1}\nin\n{guards}"


def test_evaluate_success(lean_repl):
    # Run the code using real LeanRepl
    # We need to append the test cases to the code to verify them
    method_name = "DoubleQuadruple"
    # Also need to print axioms to verify axiom checking
    # The VerinaProofEnv.evaluate doesn't run the code, it expects diagnostics.
    # But in a real flow, we run code + tests + axiom checks.
    full_code = SAMPLE_CODE
    full_code += f"\n\n#print axioms {method_name}"
    full_code += f"\n\n#print axioms {method_name}_correct"

    print("\nRunning code via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = VerinaProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is True, f"Expected: success=True. Actual success={success}"
    assert message is None, f"Expected: message=None. Actual message={message}"


def test_evaluate_axiom_failure(lean_repl):
    # To test axiom failure with real LeanRepl, we need to use a disallowed axiom.
    # 'sorry' uses the 'sorryAx' axiom.
    # But 'sorry' is also checked separately.
    # Let's try to use Classical.choice if it was disallowed, but it is allowed.
    # We can temporarily disallow Classical.choice by passing a custom list to check_axioms,
    # but VerinaProofEnv.evaluate uses the default list.

    # Prepend imports
    imports = "\n".join(
        [
            line
            for line in SAMPLE_CODE.splitlines()
            if line.startswith("import")
            or line.startswith("open")
            or line.startswith("set_option")
        ]
    )
    full_code = imports + "\n" + CODE_WITH_AXIOM
    # Add axiom check command
    full_code += "\n\n#print axioms DoubleQuadruple"

    print("\nRunning code with Bad.Axiom via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    # We need to trick VerinaProofEnv to check this code against the task
    # The task header check might fail if we changed the code too much.
    # But here we just want to test axiom checking.
    # We can bypass header check if we make the code look like it starts with header?
    # Or we can just rely on the fact that evaluate calls check_axioms.

    # Actually, VerinaProofEnv.evaluate checks header first? No, it checks header AFTER base evaluation.
    # So if axiom check fails, it returns False immediately.
    success, message = VerinaProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=False. Actual success={success}"
    assert "uses non-allowed axioms" in message, (
        f"Expected message to contain 'uses non-allowed axioms'. Actual message={message}"
    )
    assert "Bad.Axiom" in message, (
        "Expected message to contain 'Bad.Axiom' indicating axiom usage. Actual message={message}"
    )


def test_evaluate_test_failure(lean_repl):
    # Create a failing test case
    # We'll modify the guard to fail
    # Generate a failing guard: 0 -> (1, 1) which is wrong
    failing_guard = "#guard (DoubleQuadruple 0).extract == (1, 1)"
    full_code = SAMPLE_CODE + "\n\n" + failing_guard

    print("\nRunning code with failing test via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = VerinaProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=False. Actual success={success}"
    assert "Test case failed" in message, (
        f"Expected message to contain 'Test case failed'. Actual message={message}"
    )


def test_evaluate_with_guard_statements_fails(lean_repl):
    # Modify the code to include a guard instead of guard
    guard = "#guard (has_close_elements [1.0, 2.0, 3.0] 0.5).extract == false"
    full_code = SAMPLE_CODE + "\n\n" + guard

    print("\nRunning code with guard statements via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = VerinaProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=True. Actual success={success}"
    assert "you added guard statements" in message, (
        f"Expected message to contain 'you added guard statements'. Actual message={message}"
    )


def test_evaluate_with_eval_statements_passes(lean_repl):
    # Modify the code to include an eval instead of guard
    eval = "#eval (DoubleQuadruple 0).extract"
    full_code = SAMPLE_CODE + "\n\n" + eval

    print("\nRunning code with eval statements via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = VerinaProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is True, f"Expected: success=True. Actual success={success}"
    assert message is None, f"Expected message to be None. Actual message={message}"
