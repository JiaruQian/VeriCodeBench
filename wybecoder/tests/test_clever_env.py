# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import pytest
from src.envs.clever_proof import CleverProofEnv
from src.repl import LeanRepl
from tests.tests_data.clever_env_data import SAMPLE_TASK, SAMPLE_CODE, SAMPLE_CODE_AXIOM


@pytest.fixture(scope="function")
def lean_repl():
    repl = LeanRepl()
    yield repl
    repl.close()


def test_evaluate_success_with_axioms_prints(lean_repl):
    # Run the code using real LeanRepl
    method_name = "has_close_elements"
    full_code = SAMPLE_CODE + "\n\n"
    full_code += f"\n\n#print axioms {method_name}"
    full_code += f"\n\n#print axioms {method_name}_correct"

    print("\nRunning code via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is True, f"Expected: success=True. Actual success={success}"
    assert message is None, f"Expected: message=None. Actual message={message}"


def test_evaluate_axiom_failure(lean_repl):
    # Use the axiom code
    full_code = SAMPLE_CODE_AXIOM
    full_code += "\n\n#print axioms has_close_elements"
    full_code += "\n\n#print axioms has_close_elements_correct"

    print("\nRunning code with axioms via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=False. Actual success={success}"
    assert "uses non-allowed axioms" in message, (
        f"Expected message to contain 'uses non-allowed axioms'. Actual message={message}"
    )
    assert "_false_1" in message or "_false_2" in message, (
        "Expected message to contain '_false_1' or '_false_2' indicating axiom usage. Actual message={message}"
    )


def test_evaluate_guard_test_failure(lean_repl):
    # Generate a failing guard
    # [1.0, 2.0, 3.0] 0.5 -> false. We assert true to fail.
    failing_guard = "#guard (has_close_elements [1.0, 2.0, 3.0] 0.5).extract == true"
    full_code = SAMPLE_CODE + "\n\n" + failing_guard

    print("\nRunning code with failing test via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=False. Actual success={success}"
    assert "Test case failed" in message, (
        f"Expected message to contain 'Test case failed'. Actual message={message}"
    )


def test_evaluate_header_modified(lean_repl):
    # Modify the header in the code
    modified_code = SAMPLE_CODE.replace(
        "set_option maxHeartbeats 100000", "set_option maxHeartbeats 200000"
    )
    method_name = "has_close_elements"
    guards = SAMPLE_TASK["tests"]
    full_code = modified_code + "\n\n" + guards
    full_code += f"\n\n#print axioms {method_name}"
    full_code += f"\n\n#print axioms {method_name}_correct"

    print("\nRunning code with modified header via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=False. Actual success={success}"
    assert "header was modified" in message, (
        f"Expected message to contain 'header was modified'. Actual message={message}"
    )


def test_evaluate_with_guard_statements_fails(lean_repl):
    # Modify the code to include a guard instead of guard
    guard = "#guard (has_close_elements [1.0, 2.0, 3.0] 0.5).extract == false"
    full_code = SAMPLE_CODE + "\n\n" + guard

    print("\nRunning code with guard statements via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is False, f"Expected: success=True. Actual success={success}"
    assert "you added guard statements" in message, (
        f"Expected message to contain 'you added guard statements'. Actual message={message}"
    )


def test_evaluate_with_eval_statements_passes(lean_repl):
    # Modify the code to include an eval instead of guard
    eval = "#eval (has_close_elements [1.0, 2.0, 3.0] 0.5).extract"
    full_code = SAMPLE_CODE + "\n\n" + eval

    print("\nRunning code with eval statements via LeanRepl...")
    diagnostics = lean_repl.run(full_code)
    success, message = CleverProofEnv.evaluate(SAMPLE_TASK, full_code, diagnostics)

    assert success is True, f"Expected: success=True. Actual success={success}"
    assert message is None, f"Expected message to be None. Actual message={message}"
