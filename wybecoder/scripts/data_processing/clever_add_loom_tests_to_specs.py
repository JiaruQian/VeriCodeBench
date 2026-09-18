# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Script to add Loom guard test cases to the CLEVER dataset. 
It also modifies the 'loom_header' field to include necessary imports and the Loom specification.
"""
import json
from pathlib import Path
from src.utils import extract_benchmark_blocks, extract_benchmark_content_for_tag


def construct_id(obj):
    """Construct ID from object's id and function_name fields."""
    id_field = obj.get("id", "")
    function_name = obj.get("function_name", "")

    parts = id_field.split(":")
    if len(parts) >= 2:
        return f"id_{parts[1]}_{function_name}"
    else:
        raise ValueError(f"Invalid ID format: {id_field}")

def main():
    # Path to CLEVER dataset with Loom tests
    dataset_path_1 = "data/clever_loom.jsonl"
    # Path to CLEVER dataset with Loom specification
    dataset_path_2 = "data/clever.jsonl"
    output_path = "data/clever_with_tests.jsonl"

    lookup = {}
    with open(dataset_path_1, 'r') as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                obj_id = construct_id(obj)
                lookup[obj_id] = obj

    print(f"Loaded {len(lookup)} objects from {dataset_path_1}")

    output_objects = []
    matched_count = 0
    unmatched_count = 0

    with open(dataset_path_2, 'r') as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                obj_id = obj.get("id", "")

                if obj_id in lookup:
                    # Add test_cases_loom from `dataset_path_1`
                    if "-- benchmark @start Lean tests" not in obj["lean_code"]:
                        obj["lean_code"] = obj["lean_code"] + TESTS.format(lean_tests=lookup[obj_id]["test_cases_loom"])
                    matched_count += 1
                else:
                    obj["test_cases_loom"] = []
                    unmatched_count += 1
                    print(f"Warning: No match found for ID: {obj_id}")
                    raise ValueError(f"ID not found: {obj_id}")

                # Modify 'loom_header' field to include the imports and the Loom specification
                benchmark_blocks = extract_benchmark_blocks(obj["lean_code"])
                lean_imports = extract_benchmark_content_for_tag(benchmark_blocks, tag_name="Imports")
                problem_spec_loom = extract_benchmark_content_for_tag(benchmark_blocks, tag_name="Specification")
                loom_header = f"{lean_imports}\n{problem_spec_loom}"
                obj["loom_header"] = loom_header

                output_objects.append(obj)

    if unmatched_count == 0:
        with open(output_path, 'w') as f:
            for obj in output_objects:
                f.write(json.dumps(obj) + '\n')
        print(f"Output written to {output_path}")

    print(f"\nProcessed {len(output_objects)} objects from {output_path}")
    print(f"Matched: {matched_count}, Unmatched: {unmatched_count}")


TESTS = """

-- benchmark @start Lean tests
{lean_tests}
-- benchmark @end Lean tests"""

if __name__ == "__main__":
    main()
