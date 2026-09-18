# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
import os
import argparse
from pathlib import Path

# ANSI color codes for highlighting
RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RESET = '\033[0m'
BOLD = '\033[1m'

def filter_comments(code):
    """
    Remove comment lines from Lean code.
    A line is a comment if it starts with -- (after stripping whitespace).
    """
    if code is None:
        return ""
    
    code_str = str(code)
    non_comment_lines = []
    
    for line in code_str.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('--'):
            non_comment_lines.append(line)
    
    return '\n'.join(non_comment_lines)

def highlight_keywords(text):
    """
    Highlight problematic keywords in the text.
    """
    # Highlight "sorry" and "SMTSorry" in red
    text = text.replace("sorry", f"{RED}{BOLD}sorry{RESET}")
    text = text.replace("SMTSorry", f"{RED}{BOLD}SMTSorry{RESET}")
    
    # Highlight "axiom" in yellow
    text = text.replace("axiom", f"{YELLOW}{BOLD}axiom{RESET}")
    
    return text

def get_bad_reason(final_code):
    """
    Get the reason why a trajectory is bad (excluding comments).
    """
    reasons = []
    
    # Filter out comment lines
    non_comment_code = filter_comments(final_code)
    
    if "sorry" in non_comment_code:
        reasons.append("contains 'sorry'")
    if "SMTSorry" in non_comment_code:
        reasons.append("contains 'SMTSorry'")
    
    axiom_count = non_comment_code.count("axiom")
    if axiom_count > 1:
        reasons.append(f"'axiom' appears {axiom_count} times (>1)")
    
    return ", ".join(reasons)

def has_bad_patterns(final_code):
    """
    Check if final_code has bad patterns (excluding comments):
    - More than 2 occurrences of "axiom"
    - Contains "sorry"
    - Contains "SMTSorry"
    
    Ignores lines that are comments (starting with --)
    """
    if final_code is None:
        return False
    
    # Filter out comment lines
    non_comment_code = filter_comments(final_code)
    
    # Check for "sorry" or "SMTSorry"
    if "sorry" in non_comment_code or "SMTSorry" in non_comment_code:
        return True
    
    # Check for more than 2 occurrences of "axiom"
    if non_comment_code.count("axiom") > 2:
        return True
    
    return False

def scan_folder(folder_path):
    """
    Scan all .jsonl files in a folder and count bad trajectories that are passing.
    """
    folder = Path(folder_path)
    total_bad = 0
    total_lines = 0
    total_passing = 0
    bad_files = {}
    bad_trajectories = []  # Store all bad trajectories for detailed display
    
    # Find all .jsonl files
    jsonl_files = list(folder.glob("*.jsonl"))
    
    if not jsonl_files:
        print(f"No .jsonl files found in {folder_path}")
        return
    
    print(f"Scanning {len(jsonl_files)} .jsonl file(s)...\n")
    
    for jsonl_file in jsonl_files:
        bad_count = 0
        line_count = 0
        passing_count = 0
        
        try:
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        line_count += 1
                        
                        # Navigate to outcomes
                        outcomes = data.get('outcomes', {})
                        final_code = outcomes.get('final_code')
                        pass_judged = outcomes.get('pass_judged', False)
                        
                        # Only flag as bad if it's passing AND has bad patterns
                        if pass_judged:
                            passing_count += 1
                            total_passing += 1
                            
                            if has_bad_patterns(final_code):
                                bad_count += 1
                                total_bad += 1
                                
                                # Store bad trajectory info
                                bad_trajectories.append({
                                    'file': jsonl_file.name,
                                    'line': line_num,
                                    'final_code': final_code,
                                    'reason': get_bad_reason(final_code)
                                })
                    
                    except json.JSONDecodeError as e:
                        print(f"  Warning: Could not parse line {line_num} in {jsonl_file.name}: {e}")
        
        except Exception as e:
            print(f"Error reading {jsonl_file.name}: {e}")
            continue
        
        total_lines += line_count
        
        if bad_count > 0:
            bad_files[jsonl_file.name] = {'bad': bad_count, 'passing': passing_count, 'total': line_count}
            print(f"📁 {jsonl_file.name}: {bad_count} bad passing / {passing_count} passing / {line_count} total")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total files scanned: {len(jsonl_files)}")
    print(f"Total lines processed: {total_lines}")
    print(f"Total passing trajectories: {total_passing}")
    print(f"{RED}{BOLD}Total bad PASSING trajectories: {total_bad}{RESET}")
    print(f"Files with bad passing trajectories: {len(bad_files)}")
    
    if bad_files:
        print(f"\n{RED}{BOLD}⚠️  BAD PASSING TRAJECTORIES DETECTED!{RESET}")
        print("\nBreakdown by file:")
        for filename, counts in bad_files.items():
            print(f"  - {filename}: {counts['bad']} bad passing / {counts['passing']} passing / {counts['total']} total")
        
        # Show detailed bad trajectories
        print("\n" + "="*60)
        print("DETAILED BAD PASSING TRAJECTORIES")
        print("="*60)
        
        for i, traj in enumerate(bad_trajectories, 1):
            print(f"\n{BOLD}[{i}] {traj['file']} - Line {traj['line']}{RESET}")
            print(f"{GREEN}{BOLD}Status:{RESET} {GREEN}PASSING ✓{RESET}")
            print(f"{RED}{BOLD}Issue:{RESET} {traj['reason']}")
            print(f"{BOLD}Content:{RESET}")
            
            # Truncate if too long
            final_code_str = str(traj['final_code'])
            display_code = final_code_str
            
            # Highlight and display
            highlighted = highlight_keywords(display_code)
            print(f"  {highlighted}")
            print("-" * 60)
        
        for filename, counts in bad_files.items():
            print(f"  - {filename}: {counts['bad']} bad passing / {counts['passing']} passing / {counts['total']} total")
    else:
        print(f"\n{GREEN}✅ No bad passing trajectories found!{RESET}")

def main():
    parser = argparse.ArgumentParser(
        description="Detect bad PASSING trajectories in .jsonl files based on final_code content (excluding comments)."
    )
    parser.add_argument(
        "folder_path",
        type=str,
        help="Path to the folder containing .jsonl files"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.folder_path):
        print(f"Error: Folder '{args.folder_path}' does not exist!")
        exit(1)
    elif not os.path.isdir(args.folder_path):
        print(f"Error: '{args.folder_path}' is not a folder!")
        exit(1)
    else:
        scan_folder(args.folder_path)

if __name__ == "__main__":
    main()
