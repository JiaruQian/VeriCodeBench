#!/usr/bin/env python3
"""Validate frozen Rust/Verus code-only oracle artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.pipeline.rust_code_only_pipeline import (
    contract_hash,
    extract_reference_contract,
    load_rust_code_only_contracts,
    normalize_contract,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate frozen Rust oracle contracts.")
    parser.add_argument(
        "--oracle-file",
        type=Path,
        default=Path(
            "benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json"
        ),
    )
    parser.add_argument("--specs-dir", type=Path, required=True)
    parser.add_argument("--code-dir", type=Path)
    parser.add_argument("--report-file", type=Path, required=True)
    parser.add_argument("--task-id", type=int)
    args = parser.parse_args()

    items = load_rust_code_only_contracts(args.oracle_file)
    if args.task_id is not None:
        items = [item for item in items if item.id == args.task_id]
    results: list[dict[str, Any]] = []
    for item in items:
        spec_file = args.specs_dir / Path(item.path).with_suffix(".json")
        result: dict[str, Any] = {
            "id": item.id,
            "path": item.path,
            "spec_file": str(spec_file),
            "oracle_contract_hash": contract_hash(item.code_only_contract),
            "status": "ok",
            "signature_match": False,
            "contract_match": False,
            "clauses_match": False,
            "source_contract_match": None,
        }
        if not spec_file.exists():
            result.update(status="missing_spec", error="spec artifact not found")
        else:
            artifact = json.loads(spec_file.read_text())
            actual_signature = str(artifact.get("function_signature") or "")
            actual_contract = str(
                artifact.get("code_only_contract") or artifact.get("verus_contract") or ""
            )
            result["signature_match"] = normalize_contract(actual_signature) == normalize_contract(
                item.function_signature
            )
            result["contract_match"] = normalize_contract(actual_contract) == normalize_contract(
                item.code_only_contract
            )
            result["clauses_match"] = artifact.get("verus_clauses") == item.verus_clauses
            result["artifact_contract_hash"] = contract_hash(actual_contract)
            if not all(
                result[key] for key in ("signature_match", "contract_match", "clauses_match")
            ):
                result.update(
                    status="mismatch",
                    error="canonical oracle signature/contract changed in spec artifact",
                )

        if args.code_dir is not None and result["status"] == "ok":
            code_file = args.code_dir / item.path
            result["code_file"] = str(code_file)
            if not code_file.exists():
                result.update(status="missing_code", error="code artifact not found")
            else:
                try:
                    signature, contract, clauses, _ = extract_reference_contract(
                        code_file.read_text(), item.function_signature
                    )
                    result["source_contract_match"] = (
                        normalize_contract(signature)
                        == normalize_contract(item.function_signature)
                        and normalize_contract(contract)
                        == normalize_contract(item.code_only_contract)
                        and clauses == item.verus_clauses
                    )
                except Exception as exc:
                    result["source_contract_match"] = False
                    result["source_contract_error"] = str(exc)
                if not result["source_contract_match"]:
                    result.update(
                        status="mismatch",
                        error="verified Rust source does not contain the canonical oracle contract",
                    )
        results.append(result)
        print(f"[TASK] id={item.id} status={result['status']} path={item.path}")

    matched = sum(result["status"] == "ok" for result in results)
    report = {
        "method": "frozen_rust_oracle_contract_consistency",
        "oracle_file": str(args.oracle_file),
        "specs_dir": str(args.specs_dir),
        "code_dir": str(args.code_dir) if args.code_dir else None,
        "total": len(results),
        "matched": matched,
        "coverage": matched / len(results) if results else 0.0,
        "results": results,
    }
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"[DONE] oracle_contract_coverage={report['coverage']:.3f} report={args.report_file}")
    raise SystemExit(0 if matched == len(results) else 1)


if __name__ == "__main__":
    main()
