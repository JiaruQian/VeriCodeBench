#!/usr/bin/env python3
"""Construct Rust/Verus code-only oracle contracts from reference functions."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.pipeline.rust_code_only_pipeline import extract_reference_contract


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def normalize_expression(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().rstrip(",;"))


def normalize_signature(text: str) -> str:
    normalized = " ".join(text.strip().split())
    normalized = re.sub(r"^pub(?:\([^)]*\))?\s+", "", normalized)
    normalized = re.sub(
        r"->\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*:\s*(.+)\)\s*;?$", r"-> \1", normalized
    )
    return normalized.rstrip(";")


def build(
    requirements: list[dict[str, Any]],
    source_root: Path,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in requirements:
        source_file = source_root / row["path"]
        source = source_file.read_text()
        signature, contract, clauses, function_name = extract_reference_contract(
            source, str(row["function_signature"])
        )
        if normalize_signature(signature) != normalize_signature(str(row["function_signature"])):
            raise ValueError(f"id={row['id']} reference signature does not match dataset")

        targets = row.get("ground_truth_clauses") or []
        matched_target_ids: list[str] = []
        clause_target_ids: dict[int, list[str]] = {index: [] for index in range(len(clauses))}
        for target in targets:
            target_type = str(target.get("type", "")).strip().lower()
            target_expr = normalize_expression(str(target.get("expr", "")))
            matches = [
                index
                for index, clause in enumerate(clauses)
                if clause["type"] == target_type
                and normalize_expression(clause["expr"]) == target_expr
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"id={row['id']} target={target.get('id')} maps to {len(matches)} clauses"
                )
            target_id = str(target["id"])
            matched_target_ids.append(target_id)
            clause_target_ids[matches[0]].append(target_id)

        contract_clauses = []
        for index, clause in enumerate(clauses, start=1):
            target_ids = clause_target_ids[index - 1]
            contract_clauses.append(
                {
                    "id": f"co{index}",
                    **clause,
                    "role": "semantic_target" if target_ids else "verification_precondition",
                    "source": "reference_function_contract",
                    "coverage_target_ids": target_ids,
                }
            )
        result.append(
            {
                "id": int(row["id"]),
                "path": row["path"],
                "category": row.get("category", ""),
                "requirement_en": row["requirement_en"],
                "function_signature": signature,
                "code_only_contract": contract,
                "verus_clauses": clauses,
                "contract_provenance": {
                    "source_file": str(
                        Path("benchmarks/rust-verus-problems/ground-truth") / row["path"]
                    ),
                    "source_function": function_name,
                    "extraction_method": "target_function_verus_header",
                    "source_contract_hash": digest(contract),
                    "final_contract_hash": digest(contract),
                    "manually_modified": False,
                    "modification_reason": "",
                },
                "contract_clauses": contract_clauses,
                "coverage_target_ids": matched_target_ids,
                "auxiliary_contract_clause_ids": [
                    clause["id"]
                    for clause in contract_clauses
                    if clause["role"] == "verification_precondition"
                ],
                "excluded_reference_annotations": {
                    "loop_invariants": len(re.findall(r"(?m)^\s*invariant\s*$", source)),
                    "loop_variants": len(re.findall(r"(?m)^\s*decreases\b", source)),
                    "assertions": len(re.findall(r"(?m)^\s*assert\s*\(", source)),
                    "proof_functions": len(re.findall(r"(?m)^\s*proof\s+fn\b", source)),
                },
                "validation": {
                    "syntax_valid": True,
                    "reference_verifies": True,
                    "verifier": "verus",
                    "timeout_seconds": 120,
                },
                "alignment": {
                    "unmatched_ground_truth_ids": [],
                    "status": "exact_reference_clause_match",
                },
                "notes": (
                    "Extracted from the reference target-function header; all body-level "
                    "invariants, decreases clauses, assertions, and proof code are excluded."
                ),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--requirements",
        type=Path,
        default=Path(
            "benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json"
        ),
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("benchmarks/rust-verus-problems/ground-truth"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json"
        ),
    )
    args = parser.parse_args()
    requirements = json.loads(args.requirements.read_text())
    data = build(requirements, args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(data)} Rust code-only contracts to {args.output}")


if __name__ == "__main__":
    main()
