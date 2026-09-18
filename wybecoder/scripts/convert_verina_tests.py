#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Convert Verina test cases to #guard format."""

import json
from typing import Any


def verina_tests_to_guard_statements(test_data: dict, method_name: str) -> str:
    """
    Convert Verina test cases to #guard statements.
    
    Args:
        test_data: Verina task dictionary with 'tests' field
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
    param_names = signature.get("parameters", {}).get("param_name", [])
    return_type = signature.get("return_type", "")
    
    guard_statements = []
    
    for input_str, expected_list in zip(inputs, expected):
        if not expected_list:
            continue
        
        # Parse input JSON string
        try:
            input_dict = json.loads(input_str)
        except (json.JSONDecodeError, TypeError):
            continue
        
        # Build method call with parameters
        param_values = []
        for param_name in param_names:
            if param_name in input_dict:
                value = input_dict[param_name]
                # Convert to Lean format
                if isinstance(value, str):
                    value_str = f'"{value}"'
                elif isinstance(value, (int, float)):
                    value_str = str(value)
                elif isinstance(value, list):
                    # Convert list to Lean format
                    if value:
                        if isinstance(value[0], str):
                            value_str = f'[{", ".join(f\'"{v}\' for v in value)}]'
                        else:
                            value_str = f'[{", ".join(str(v) for v in value)}]'
                    else:
                        value_str = "[]"
                else:
                    value_str = str(value)
                param_values.append(value_str)
        
        method_call = f"{method_name} {' '.join(param_values)}"
        
        # Get expected output (take first if multiple)
        expected_val = expected_list[0] if expected_list else None
        if expected_val is None:
            continue
        
        # Convert expected to Lean format
        if isinstance(expected_val, str):
            expected_str = f'"{expected_val}"'
        elif isinstance(expected_val, (int, float)):
            expected_str = str(expected_val)
        elif isinstance(expected_val, bool):
            expected_str = "true" if expected_val else "false"
        elif isinstance(expected_val, list):
            if expected_val:
                if isinstance(expected_val[0], str):
                    expected_str = f'[{", ".join(f\'"{v}\' for v in expected_val)}]'
                else:
                    expected_str = f'[{", ".join(str(v) for v in expected_val)}]'
            else:
                expected_str = "[]"
        else:
            expected_str = str(expected_val)
        
        # Create #guard statement
        # Note: For methods that return values, we need to check the result
        # Verina methods return values, so we check: method_call == expected_val
        guard_statements.append(f"#guard {method_call} == {expected_str}")
    
    return "\n".join(guard_statements)


if __name__ == "__main__":
    # Test with a sample Verina task
    import sys
    from pathlib import Path
    
    repo_root = Path(__file__).parent.parent
    verina_file = repo_root / "data" / "verina.jsonl"
    
    with open(verina_file) as f:
        first_line = f.readline()
        test_data = json.loads(first_line)
    
    method_name = test_data.get("signature", {}).get("name", "unknown")
    guard_statements = verina_tests_to_guard_statements(test_data, method_name)
    
    print(f"Method: {method_name}")
    print(f"\nGenerated #guard statements:\n{guard_statements}")
