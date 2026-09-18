# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import os

def get_new_header(original_header):
    # Construct the new header
    # In case 'import Mathlib' is too slow, modify to 
    # 'import Mathlib.Algebra.BigOperators.Intervals\n import Mathlib.Algebra.Ring.Int.Defs'
    new_header = """import Auto
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true"""
    
    return new_header

def process_file(filepath):
    print(f"Processing {filepath}...")
    new_data = []
    modified_count = 0
    
    try:
        with open(filepath, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if 'loom_header' in entry:
                        original_header = entry['loom_header']
                        new_header = get_new_header(original_header)
                        
                        if new_header != original_header:
                            entry['loom_header'] = new_header
                            modified_count += 1
                    new_data.append(entry)
                except json.JSONDecodeError:
                    print(f"Error decoding line in {filepath}")
                    continue
        
        with open(filepath, 'w') as f:
            for entry in new_data:
                f.write(json.dumps(entry) + '\n')
        print(f"Finished {filepath}. Modified {modified_count} entries.")
        
    except FileNotFoundError:
        print(f"File not found: {filepath}")

if __name__ == "__main__":
    # Use absolute paths or relative to workspace root
    base_dir = os.getcwd()
    process_file(os.path.join(base_dir, "data/verina.jsonl"))
    process_file(os.path.join(base_dir, "data/clever.jsonl"))
