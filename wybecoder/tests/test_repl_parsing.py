# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import pytest
from src.repl import parse_axioms_from_messages, check_axioms, parse_test_failures_from_messages, check_test_validity, LeanRepl

@pytest.fixture(scope="function")
def lean_repl():
    repl = LeanRepl()
    yield repl
    repl.close()

# --- Unit Tests (Synthetic Data) ---

def test_parse_axioms_from_messages_unit():
    # Case 1: Single message with axioms
    messages = [
        {
            "severity": "info",
            "data": "'foo' depends on axioms: [Classical.choice, propext]"
        }
    ]
    assert parse_axioms_from_messages(messages) == {"foo": ["Classical.choice", "propext"]}

    # Case 2: Multiple messages
    messages = [
        {
            "severity": "info",
            "data": "'foo' depends on axioms: [Classical.choice]"
        },
        {
            "severity": "info",
            "data": "'bar' depends on axioms: [propext]"
        }
    ]
    assert parse_axioms_from_messages(messages) == {
        "foo": ["Classical.choice"],
        "bar": ["propext"]
    }

    # Case 3: No axioms
    messages = [
        {
            "severity": "info",
            "data": "'foo' does not depend on any axioms"
        }
    ]
    assert parse_axioms_from_messages(messages) == {"foo": []}

def test_check_axioms_unit():
    # Case 1: Allowed axioms
    diagnostics = {
        "messages": [
            {
                "severity": "info",
                "data": "'foo' depends on axioms: [Classical.choice]"
            }
        ]
    }
    allowed = ["Classical.choice"]
    assert check_axioms(diagnostics, allowed_axioms=allowed) == []

    # Case 2: Disallowed axioms
    diagnostics = {
        "messages": [
            {
                "severity": "info",
                "data": "'foo' depends on axioms: [Bad.Axiom]"
            }
        ]
    }
    allowed = ["Classical.choice"]
    errors = check_axioms(diagnostics, allowed_axioms=allowed)
    assert len(errors) == 1
    assert "Method 'foo' uses non-allowed axioms" in errors[0]["data"]
    assert "Bad.Axiom" in errors[0]["data"]
    assert errors[0]["severity"] == "error"
    assert "pos" not in errors[0]

def test_parse_test_failures_from_messages_unit():
    executed_code = """
def foo : Nat := 1
#guard foo == 1
#guard foo == 2
"""
    # Case 1: Test failure with specific pattern
    messages = [
        {
            "severity": "error",
            "pos": {"line": 4},
            "data": "Expression\n  foo == 2\ndid not evaluate to `true`"
        }
    ]
    failures = parse_test_failures_from_messages(messages, executed_code)
    assert len(failures) == 1
    assert "Test case failed: #guard foo == 2" in failures[0]["data"]
    assert "pos" not in failures[0]

# --- Integration Tests (Real LeanRepl) ---

def test_parse_axioms_integration(lean_repl):
    code = """
axiom MyAxiom : True
theorem use_axiom : True := MyAxiom
#print axioms use_axiom
"""
    
    print(f"\nRunning axiom code via LeanRepl...")
    diagnostics = lean_repl.run(code)
    axioms_map = parse_axioms_from_messages(diagnostics["messages"])
    print(f"Parsed axioms: {axioms_map}")
    
    assert "MyAxiom" in axioms_map.get("use_axiom", [])

def test_check_test_validity_integration(lean_repl):
    code = """
#guard 1 == 1 -- Pass
#guard 1 == 2 -- Fail
"""

    print(f"\nRunning test code via LeanRepl...")
    diagnostics = lean_repl.run(code)

    failures = check_test_validity(diagnostics)
    print(f"Parsed failures: {failures}")
    
    assert len(failures) == 1
    assert "#guard 1 == 2" in failures[0]["data"]
