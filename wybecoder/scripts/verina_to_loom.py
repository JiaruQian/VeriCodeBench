#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Extract Lean code components and construct Loom method with specification"""

import json
import re
import os
import textwrap
import fire


def extract_benchmark_section(lean_code, section_name):
    """
    Extract content between benchmark markers.

    Args:
        lean_code: The full lean_code string
        section_name: Name of the section (e.g., 'solution_aux', 'precond', 'postcond')

    Returns:
        Extracted content as a string, or empty string if not found
    """
    # Use word boundary or space to ensure exact match (not code matching code_aux)
    pattern = rf"-- !benchmark @start {section_name}(?:\s|$)(.*?)\s*-- !benchmark @end {section_name}"
    match = re.search(pattern, lean_code, re.DOTALL)
    if match:
        content = match.group(1)
        # dedent so that relative indentation is preserved
        # (necessary for let statements to be handled correctly)
        return textwrap.dedent(content)
    return ""


def extract_precondition(lean_code, function_name):
    """Extract the precondition from the _precond definition."""
    # Look for the precondition inside the benchmark markers
    precond_content = extract_benchmark_section(lean_code, "precond")
    if precond_content and precond_content != "True":
        return precond_content
    return None


def extract_postcondition(lean_code, function_name):
    """Extract the postcondition from the _postcond definition."""
    # Look for the postcondition inside the benchmark markers
    postcond_content = extract_benchmark_section(lean_code, "postcond")
    if postcond_content and postcond_content != "True":
        return postcond_content
    return None


def extract_code_body(lean_code, function_name):
    """Extract the main code body."""
    code_content = extract_benchmark_section(lean_code, "code")
    if code_content:
        return code_content
    return ""


ALL_AUX_FIELDS = [
    "task_aux",
    "solution_aux",
    "precond_aux",
    "code_aux",
    "postcond_aux",
    "proof_aux",
]

SPEC_AUX_FIELDS = [
    "task_aux",  # needed for spec
    "solution_aux",  # needed for spec
    "precond_aux",  # needed for spec
    # "code_aux",  # partially leaks implementation
    "postcond_aux",  # needed for spec
    # "proof_aux",  # partially leaks proof
]


def get_aux_defs(entry, fields: list[str]) -> str:
    """Extract all auxiliary definitions from the entry's lean_code."""
    lean_code = entry["lean_code"]

    aux_defs = []
    for section in fields:
        content = extract_benchmark_section(lean_code, section)
        if content:
            aux_defs.append(content)

    return "\n\n".join(aux_defs)


def construct_loom_method(entry):
    """
    Construct a complete Loom method from a verina.jsonl entry.

    Args:
        entry: A dict from verina.jsonl containing signature, lean_code, etc.

    Returns:
        A string with the complete Loom method including:
        - Auxiliary definitions before the method
        - Method signature with parameters and return type
        - Require clause (preconditions)
        - Ensures clause (postconditions)
        - Do block with implementation
    """
    lean_code = entry["lean_code"]
    signature = entry["signature"]

    # Extract components
    function_name = signature["name"]
    param_names = signature["parameters"]["param_name"]
    param_types = signature["parameters"]["param_type"]
    return_type = signature["return_type"]

    # Extract precondition and postcondition
    precond = extract_precondition(lean_code, function_name)
    postcond = extract_postcondition(lean_code, function_name)

    # Construct parameter list for method signature
    params = []
    for name, type_ in zip(param_names, param_types):
        params.append(f"({name} : {type_})")
    params_str = " ".join(params)

    # Build the complete method
    result = []

    # Add auxiliary definitions first with blank lines between each def
    aux_defs = get_aux_defs(entry, SPEC_AUX_FIELDS)
    if aux_defs:
        result.append(aux_defs)
        result.append("")

    # Add method signature
    result.append(
        f"method {function_name} {params_str} return (result : {return_type})"
    )

    # Add require clause if precondition is not trivial
    if precond:
        # Handle multi-line pre-conditions with proper indentation
        precond_lines = precond.split("\n")
        if len(precond_lines) == 1:
            result.append(f"  require {precond}")
        else:
            result.append(f"  require {precond_lines[0]}")
            for line in precond_lines[1:]:
                result.append(f"    {line}")

    # Add ensures clause if postcondition is not trivial
    if postcond:
        # Handle multi-line postconditions with proper indentation
        postcond_lines = postcond.split("\n")
        if len(postcond_lines) == 1:
            result.append(f"  ensures {postcond}")
        else:
            result.append(f"  ensures {postcond_lines[0]}")
            for line in postcond_lines[1:]:
                result.append(f"    {line}")

    result.append("  do")
    result.append("    sorry")

    return "\n".join(result)


def construct_unsat_theorem(entry):
    """
    Construct a Lean theorem stating that the method specification is unsatisfiable:

      theorem <name>_spec_unsat :
        ∃ (params...), <precond> ∧ ∀ (result : τ), ¬ (<postcond>) := by
        sorry

    Only generated if both precondition and postcondition are non-trivial.
    """
    lean_code = entry["lean_code"]
    signature = entry["signature"]

    function_name = signature["name"]
    param_names = signature["parameters"]["param_name"]
    param_types = signature["parameters"]["param_type"]
    return_type = signature["return_type"]

    # Extract pre/post using existing helpers
    precond = extract_precondition(lean_code, function_name) or "True"
    postcond = extract_postcondition(lean_code, function_name) or "True"

    # Split into lines for indentation
    pre_lines = precond.split("\n")
    post_lines = postcond.split("\n")

    # Theorem name
    theorem_name = f"{function_name}_spec_unsat"

    # ∃ binder for parameters
    if param_names:
        exists_params = " ".join(
            f"({n} : {t})" for n, t in zip(param_names, param_types)
        )
    else:
        # No params: we quantify over unit
        exists_params = "(u : Unit)"

    # Build ∀ result binder
    forall_result = f"(result : {return_type})"

    lines = []

    # Header
    lines.append(f"theorem {theorem_name} :")
    lines.append(f"  ∃ {exists_params},")
    # precondition
    for line in pre_lines:
        lines.append("    " + line)

    # Add the conjunction and the ∀ binder
    lines.append("    ∧")
    lines.append(f"    ∀ {forall_result}, ¬ (")

    # postcondition
    for line in post_lines:
        lines.append("        " + line)
    # Close the parentheses
    lines.append("      )")

    # Proof skeleton
    lines.append("  := by")
    lines.append("    sorry")

    return "\n".join(lines)


# Standard Loom header used for all generated files
LOOM_HEADER = """import Auto
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true
"""


# Loom header with Aesop import and open namespaces
# compatible with Goedel prover's expected environment
GOEDEL_LOOM_HEADER = """import Auto
import Lean
import Mathlib
import Aesop

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true

open BigOperators Real Nat Topology Rat
"""


def get_unsat_header(entry, goedel: bool = False) -> str:
    return (
        GOEDEL_LOOM_HEADER
        if goedel
        else LOOM_HEADER
        + "\n"
        + get_aux_defs(entry, SPEC_AUX_FIELDS)
        + "\n\n"
        + construct_unsat_theorem(entry)
    )


def main(
    input_jsonl_path: str,
    output_jsonl_path: str | None,
    lean_dir: str | None = None,
    goedel: bool = False,
    keep_loom_header: bool = False,  # doesn't touch loom_header if activated to keep manual changes
):
    print("Reading verina.jsonl...")

    # Load all entries, update in-memory, and write files
    with open(input_jsonl_path) as f:
        entries = [json.loads(line) for line in f]

    if lean_dir is not None:
        os.makedirs(lean_dir, exist_ok=True)

    for i, entry in enumerate(entries):
        entry_id = entry.get("id", f"entry_{i}")

        if not keep_loom_header:
            # Construct the Loom method
            loom_method = construct_loom_method(entry)

            # Build full content using global LOOM_HEADER and method
            header = GOEDEL_LOOM_HEADER if goedel else LOOM_HEADER
            full_content = header + "\n" + loom_method

            # Save Loom header into the entry as 'loom_header'
            entry["loom_header"] = full_content

        entry["unsat_theorem"] = construct_unsat_theorem(entry)
        entry["unsat_header"] = get_unsat_header(entry)

        # Write to file
        if lean_dir is not None:
            output_file = os.path.join(lean_dir, f"{entry_id}.lean")
            with open(output_file, "w") as out_f:
                out_f.write(full_content)

    if lean_dir is not None:
        print(f"Saved {len(entries)} Lean files in {lean_dir}")

    # Overwrite JSONL with the updated entries
    output_jsonl_path = output_jsonl_path or input_jsonl_path
    with open(output_jsonl_path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    print(
        f"Updated {len(entries)} items in {output_jsonl_path} with loom_header or unsat_theorem fields."
    )


if __name__ == "__main__":
    fire.Fire(main)
