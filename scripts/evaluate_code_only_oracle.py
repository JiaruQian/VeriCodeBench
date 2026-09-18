#!/usr/bin/env python3
"""Check preservation of frozen C code-only oracle contracts.

This is intentionally separate from requirement entailment: oracle preservation is
an artifact consistency property and must not depend on the C-to-Z3 translator.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def normalize_contract(text: str) -> str:
    return " ".join(text.strip().split())


def digest(text: str) -> str:
    return hashlib.sha256(normalize_contract(text).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate frozen C oracle contracts.")
    parser.add_argument("--oracle-file", type=Path, default=Path("benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json"))
    parser.add_argument("--specs-dir", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--task-id", type=int, default=None)
    args = parser.parse_args()

    oracle_rows = json.loads(args.oracle_file.read_text())
    if args.task_id is not None:
        oracle_rows = [row for row in oracle_rows if int(row["id"]) == args.task_id]
    results: list[dict[str, Any]] = []
    for row in oracle_rows:
        spec_file = args.specs_dir / Path(row["path"]).with_suffix(".json")
        expected_signature = str(row["function_signature"]).strip()
        expected_contract = str(row["code_only_contract"]).strip()
        result: dict[str, Any] = {
            "id": int(row["id"]),
            "path": row["path"],
            "spec_file": str(spec_file),
            "oracle_contract_hash": digest(expected_contract),
            "status": "ok",
            "signature_match": False,
            "contract_match": False,
        }
        if not spec_file.exists():
            result.update(status="missing_spec", error="spec artifact not found")
        else:
            artifact = json.loads(spec_file.read_text())
            actual_signature = str(artifact.get("function_signature", "")).strip()
            actual_contract = str(artifact.get("code_only_contract") or artifact.get("acsl_block") or "").strip()
            result["signature_match"] = actual_signature == expected_signature
            result["contract_match"] = normalize_contract(actual_contract) == normalize_contract(expected_contract)
            result["artifact_contract_hash"] = digest(actual_contract)
            if not result["signature_match"] or not result["contract_match"]:
                result["status"] = "mismatch"
                result["error"] = "canonical oracle signature/contract changed"
        results.append(result)
        print(f"[TASK] id={result['id']} status={result['status']} path={result['path']}")

    checked = [r for r in results if r["status"] == "ok"]
    matched = sum(1 for r in checked if r["signature_match"] and r["contract_match"])
    report = {
        "method": "frozen_oracle_contract_consistency",
        "oracle_file": str(args.oracle_file),
        "specs_dir": str(args.specs_dir),
        "total": len(results),
        "checked": len(checked),
        "matched": matched,
        "coverage": matched / len(results) if results else 0.0,
        "results": results,
    }
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"[DONE] oracle_contract_coverage={report['coverage']:.3f} report={args.report_file}")
    if matched != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
