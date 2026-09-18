# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
from collections import defaultdict
import fire


def analyze_jsonl(filepath: str):
    """
    Reads a JSONL file, checks 'critique' and 'pass' fields,
    and prints counts and a confusion matrix.
    """
    confusion_matrix = defaultdict(lambda: defaultdict(int))

    total_lines = 0
    critique_categories = ["INCORRECT", "CORRECT", "IMPRECISE", "NONE"]

    print(f"Starting analysis of: {filepath}\n")

    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            total_lines += 1
            line = line.strip()

            if not line:
                continue

            data = json.loads(line)

            critique_text = data["critique"]
            success = data["pass"]

            critique_category = "NONE"
            if "INCORRECT" in critique_text:
                critique_category = "INCORRECT"
            elif "CORRECT" in critique_text:
                critique_category = "CORRECT"
            elif "IMPRECISE" in critique_text:
                critique_category = "IMPRECISE"

            confusion_matrix[critique_category][success] += 1

    # --- Print Final Report ---
    print("--- Analysis Complete ---")
    print(f"Total lines processed: {total_lines}\n")

    # --- Calculate and Print Keyword Counts ---
    print("Keyword Counts (Totals):")
    totals = {}
    for category in critique_categories:
        # Sum counts for True and False pass_status
        total_count = (
            confusion_matrix[category][True] + confusion_matrix[category][False]
        )
        totals[category] = total_count
        # Format for alignment
        print(f"  {category:<10}: {total_count}")

    # --- Print Confusion Matrix ---
    print("\n--- Confusion Matrix ---")

    # Get all pass statuses found (e.g., True, False, maybe others)
    # We'll assume True and False for clean output, but find all columns just in case
    pass_columns = sorted(
        list(
            set(
                status
                for cat_counts in confusion_matrix.values()
                for status in cat_counts.keys()
            )
        ),
        key=lambda x: not x,
    )  # Put True before False

    # Header
    header = f"| {'Category':<10} |"
    for col in pass_columns:
        header += f" {f'pass={col}':<10} |"
    print(header)
    print(f"|{'-' * 12}|{'-' * 12 * len(pass_columns)}|")  # Separator

    # Rows
    for category in critique_categories:
        row = f"| {category:<10} |"
        for col in pass_columns:
            count = confusion_matrix[category].get(col, 0)
            row += f" {count:<10} |"
        print(row)


if __name__ == "__main__":
    fire.Fire(analyze_jsonl)
