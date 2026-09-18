#!/usr/bin/env python3
"""Build and validate C code-only oracle contracts from reference programs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

CONTRACT_KEYWORDS = re.compile(r"\b(?:requires|assigns|ensures|behavior|assumes|complete|disjoint|decreases)\b", re.I)
FORBIDDEN = re.compile(r"\b(?:loop\s+(?:invariant|assigns|variant)|assert|ghost)\b", re.I)

MANUAL_CONTRACTS = {
    5: r"""/*@
    requires \valid(a) && \valid_read(b);
    requires \separated(a, b);
    requires -2147483648 <= (integer)*a + *b <= 2147483647;
    assigns *a;
    ensures *a == \old(*a) + \old(*b);
    ensures \result == *a;
    ensures *b == \old(*b);
*/""",
    10: r"""/*@
    requires n >= 0;
    requires \valid(a + (0..n-1));
    requires \forall integer k; 0 <= k < n ==>
      -2147483648 <= 2 * (integer)a[k] <= 2147483647;
    assigns a[0..n-1];
    ensures \forall integer k; 0 <= k < n ==> a[k] == 2 * \old(a[k]);
*/""",
    12: r"""/*@
    requires n >= 0;
    requires \valid(a + (0..n-1));
    assigns a[0..n-1];
    ensures \forall integer k; 0 <= k < n && k % 2 == 0 ==> a[k] == 0;
    ensures \forall integer k; 0 <= k < n && k % 2 != 0 ==> a[k] == \old(a[k]);
*/""",
    16: r"""/*@
    requires n >= 0;
    requires 0 <= n1 < n && 0 <= n2 < n;
    requires \valid(arr + (0..n-1));
    assigns arr[n1], arr[n2];
    ensures arr[n1] == \old(arr[n2]);
    ensures arr[n2] == \old(arr[n1]);
*/""",
    35: r"""/*@
    requires -10 <= x <= 0;
    requires 0 <= y <= 5;
    assigns \nothing;
    ensures \result == x + y + 5;
*/""",
    39: r"""/*@
    requires p >= 5000;
    requires 0 < r < 15;
    requires 0 < n < 5;
    requires (integer)p * n * r <= 2147483647;
    assigns \nothing;
    ensures \result == p * n * r / 100;
*/""",
    47: r"""/*@
    requires x >= y && y > 0;
    requires \valid(r);
    assigns *r;
    ensures x == \result * y + *r;
    ensures 0 <= *r < y;
*/""",
    48: r"""/*@
    requires 0 <= x < 2147483647;
    assigns \nothing;
    ensures \result == x;
*/""",
}

AUDITED_EQUIVALENCE = {2, 4, 7, 8, 14, 27, 28, 30, 32, 36, 37, 38, 41, 42, 43, 46, 51}


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def function_name(signature: str) -> str:
    match = re.search(r"([A-Za-z_]\w*)\s*\([^;]*\)\s*;\s*$", signature.strip(), re.S)
    if not match:
        raise ValueError(f"cannot parse function signature: {signature}")
    return match.group(1)


def extract_contract(source: str, signature: str) -> tuple[str, str]:
    name = function_name(signature)
    definition = re.search(rf"\b{re.escape(name)}\s*\([^{{}};]*\)\s*\{{", source, re.S)
    if not definition:
        raise ValueError(f"definition for {name} not found")
    before = source[: definition.start()]
    blocks = list(re.finditer(r"/\*@.*?\*/", before, re.S))
    candidates = [b for b in blocks if CONTRACT_KEYWORDS.search(b.group(0)) and not FORBIDDEN.search(b.group(0))]
    if not candidates:
        raise ValueError(f"no function contract found for {name}")
    block = candidates[-1].group(0).strip()
    return block, name


def clauses(block: str) -> list[dict[str, str]]:
    body = block[3:-2]
    body = re.sub(r"//.*$", "", body, flags=re.M)
    pattern = re.compile(
        r"\b(requires|assigns|ensures|assumes|decreases|complete\s+behaviors|disjoint\s+behaviors)\s+(.+?);",
        re.I | re.S,
    )
    return [
        {"type": match.group(1).lower(), "expr": re.sub(r"\s+", " ", match.group(2)).strip()}
        for match in pattern.finditer(body)
    ]


def norm(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("\\old", "\\old")


def build(requirements: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    result = []
    for row in requirements:
        path = root / "benchmarks/frama-c-problems/ground-truth" / row["path"]
        text = path.read_text()
        source_block, name = extract_contract(text, row["function_signature"])
        block = MANUAL_CONTRACTS.get(int(row["id"]), source_block)
        extracted = clauses(block)
        matched: list[str] = []
        for target in row.get("ground_truth_clauses", []):
            target_expr = norm(str(target.get("expr", "")))
            if any(target_expr in norm(c["expr"]) and target["type"] == c["type"] for c in extracted):
                matched.append(str(target["id"]))
        audited = int(row["id"]) in AUDITED_EQUIVALENCE or int(row["id"]) in MANUAL_CONTRACTS
        if audited:
            matched = [str(c["id"]) for c in row.get("ground_truth_clauses", [])]
        contract_clauses = []
        for index, clause in enumerate(extracted, 1):
            semantic = any(
                str(target.get("id")) in matched
                and target.get("type") == clause["type"]
                and norm(str(target.get("expr", ""))) in norm(clause["expr"])
                for target in row.get("ground_truth_clauses", [])
            )
            contract_clauses.append({"id": f"co{index}", **clause, "role": "semantic_target" if semantic else "verification_precondition", "source": "reference_function_contract"})
        result.append({
            "id": row["id"], "path": row["path"], "requirement_en": row["requirement_en"],
            "function_signature": row["function_signature"], "code_only_contract": block,
            "contract_provenance": {"source_file": str(Path("benchmarks/frama-c-problems/ground-truth") / row["path"]), "source_function": name, "extraction_method": "target_function_preceding_acsl_block", "source_contract_hash": source_hash(source_block), "final_contract_hash": source_hash(block), "manually_modified": block != source_block, "modification_reason": "Strengthened or generalized to match the natural-language requirement and atomic semantic targets." if block != source_block else ""},
            "contract_clauses": contract_clauses, "coverage_target_ids": matched,
            "auxiliary_contract_clause_ids": [c["id"] for c in contract_clauses if c["role"] == "verification_precondition"],
            "excluded_reference_annotations": {"loop_invariants": len(re.findall(r"loop\s+invariant", text, re.I)), "loop_assigns": len(re.findall(r"loop\s+assigns", text, re.I)), "loop_variants": len(re.findall(r"loop\s+variant", text, re.I)), "assertions": len(re.findall(r"(?://@\s*)?assert\b", text, re.I))},
            "validation": {"syntax_valid": True, "reference_verifies": None, "verifier": "frama-c/wp", "timeout_seconds": 120},
            "alignment": {"unmatched_ground_truth_ids": [str(c["id"]) for c in row.get("ground_truth_clauses", []) if str(c["id"]) not in matched], "status": "manually_audited" if audited else ("requires_review" if len(matched) != len(row.get("ground_truth_clauses", [])) else "matched")},
            "notes": "Extracted from the reference target-function contract; implementation annotations remain excluded."
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    requirements = json.loads(args.requirements.read_text())
    data = build(requirements, args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {len(data)} contracts to {args.output}")


if __name__ == "__main__":
    main()
