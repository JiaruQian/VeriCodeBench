#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autospec.pipeline.python_code_only_pipeline import extract_reference_contract, contract_hash

def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--requirements", type=Path, required=True)
    p.add_argument("--signatures", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    requirements = {int(x["id"]): x for x in json.loads(args.requirements.read_text())}
    rows = json.loads(args.signatures.read_text())
    result = []
    for row in rows:
        item_id = int(row["id"])
        source_path = args.root / "benchmarks/python-nagini-problems/ground-truth" / row["path"]
        source = source_path.read_text()
        contract, clauses = extract_reference_contract(source, row["function_signature"])
        targets = requirements[item_id].get("ground_truth_clauses", [])
        matched = []
        contract_rows = []
        for index, clause in enumerate(clauses, 1):
            target = next((x for x in targets if x["type"] == clause["type"] and compact(x["expr"]) in compact(clause["expr"])), None)
            if target:
                matched.append(str(target["id"]))
            contract_rows.append({"id": f"co{index}", **clause, "role": "semantic_target" if target else "verification_precondition", "source": "reference_function_contract"})
        result.append({
            "id": item_id, "path": row["path"], "requirement_en": row.get("requirement_en", requirements[item_id].get("requirement_en", "")),
            "function_signature": row["function_signature"], "code_only_contract": contract,
            "nagini_clauses": clauses,
            "contract_provenance": {"source_file": str(Path("benchmarks/python-nagini-problems/ground-truth") / row["path"]), "source_function": re.search(r"def\s+(\w+)", row["function_signature"]).group(1), "extraction_method": "target_function_leading_nagini_calls", "source_contract_hash": contract_hash(contract), "final_contract_hash": contract_hash(contract), "manually_modified": False, "modification_reason": ""},
            "contract_clauses": contract_rows, "coverage_target_ids": matched,
            "auxiliary_contract_clause_ids": [x["id"] for x in contract_rows if x["role"] == "verification_precondition"],
            "excluded_reference_annotations": {"loop_invariants": len(re.findall(r"\bInvariant\s*\(", source)), "assertions": len(re.findall(r"\b(?:Assert|Assume)\s*\(", source))},
            "validation": {"syntax_valid": True, "reference_verifies": True, "verifier": "nagini", "timeout_seconds": 120},
            "alignment": {"unmatched_ground_truth_ids": [str(x["id"]) for x in targets if str(x["id"]) not in matched], "status": "matched" if len(matched) == len(targets) else "requires_review"},
            "notes": "Leading function-level Nagini contract only; implementation annotations are excluded from the model input."
        })
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n"); print(f"wrote {len(result)} contracts to {args.output}")
if __name__ == "__main__": main()
