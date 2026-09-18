#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Extract transformed CLEVER `.lean` files under `data/clever` into a single JSONL file.

Produces `data/clever.jsonl` with one JSON object per line. Each object has keys:
- id: filename without extension
- description: natural language description (from the NL Description block)
- lean_code: the file content with metadata blocks removed (all benchmark sections preserved)
- loom_header: content of the Imports benchmark block (string)
- tags: list of tag tokens (e.g. ["clever_fixed","nl_fixed","easy"]) extracted from the Tags block
- metadata: dict mapping metadata block name -> block content (strings)

This script is resilient to minor variations in spacing and comment prefixes.
"""

import re
import json
from pathlib import Path
from src.utils import extract_benchmark_blocks, clean_description


ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / 'data' / 'clever'
OUTPUT_FILE = ROOT / 'data' / 'clever.jsonl'

def extract_metadata_blocks(text):
    # Matches: -- metadata @start Name\n ...content... \n-- metadata @end Name
    pattern = re.compile(r'-- metadata @start\s+([^\n]+)\n(.*?)(?:\n-- metadata @end \1)', re.DOTALL)
    blocks = {m.group(1).strip(): m.group(2).rstrip() for m in pattern.finditer(text)}
    return blocks

def extract_tags_from_block(tags_block_text: str):
    if not tags_block_text:
        return []
    tags = []
    for line in tags_block_text.splitlines():
        # Remove leading comment markers like '--' and whitespace
        s = re.sub(r'^\s*--\s*', '', line).strip()
        if not s:
            continue
        # split by whitespace into tokens
        tokens = [t.strip() for t in re.split(r'\s+', s) if t.strip()]
        tags.extend(tokens)
    # normalize tokens: remove empty and dedupe while preserving order
    seen = set()
    normalized = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            normalized.append(t)
    return normalized


def remove_metadata_blocks(text: str):
    # remove metadata blocks entirely so lean_code stays clean
    # Use a robust pattern that doesn't rely on backreferences in the pattern
    text = re.sub(r'-- metadata @start[\s\S]*?-- metadata @end[^\n]*', '', text)
    return text.strip()


def process_file(path: Path):
    text = path.read_text(encoding='utf-8')
    benchmarks = extract_benchmark_blocks(text)
    metadata = extract_metadata_blocks(text)

    description = clean_description(benchmarks.get('Natural Language Description', ''))

    # loom_header is the Imports block content if present
    loom_header = benchmarks.get('Imports', '').strip()

    tags = extract_tags_from_block(benchmarks.get('Tags', ''))

    # lean_code: file text with metadata blocks removed
    lean_code = remove_metadata_blocks(text)

    # id: filename without extension
    _id = path.stem

    return {
        'id': _id,
        'description': description,
        'lean_code': lean_code,
        'loom_header': loom_header,
        'tags': tags,
        'metadata': metadata,
    }


def main():
    files = list(INPUT_DIR.rglob('*.lean'))
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with OUTPUT_FILE.open('w', encoding='utf-8') as out:
        for p in sorted(files):
            try:
                item = process_file(p)
                out.write(json.dumps(item, ensure_ascii=False) + '\n')
                count += 1
            except Exception as e:
                print(f"Error processing {p}: {e}")
    print(f"Wrote {count} entries to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
