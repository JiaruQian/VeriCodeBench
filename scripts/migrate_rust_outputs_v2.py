#!/usr/bin/env python3
"""Create corrected Rust benchmark output copies and re-evaluate them offline."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.pipeline.rust_requirement_pipeline import (
    _build_verus_contract,
    _enforce_rust_contract,
    _extract_json_object,
    _extract_rust_parameters,
    _extract_rust_return_name,
    _has_disallowed_verus_expr,
    _is_tautological_clause,
    _normalize_rust_return_expr,
    _normalize_rust_state_expr,
    _normalize_verus_clauses,
)
from autospec.verifier.verus import VerusVerifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recover canonical Rust specs, lock code contracts, rerun Verus, and rebuild metrics."
    )
    parser.add_argument("output_dirs", nargs="+", type=Path)
    parser.add_argument("--suffix", default="-offline-v2")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--verus-bin", default="verus")
    parser.add_argument("--verify-timeout", type=int, default=120)
    parser.add_argument(
        "--ground-truth-spec-file",
        type=Path,
        default=Path(
            "benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json"
        ),
    )
    return parser.parse_args()


def _recover_model_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    raw = str(spec.get("raw_model_output") or "").strip()
    if raw:
        try:
            recovered = _extract_json_object(raw)
            if _normalize_verus_clauses(
                recovered.get("verus_clauses"),
                str(recovered.get("verus_contract") or ""),
            ):
                return recovered
        except Exception:
            pass
    return spec


def _migrate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    recovered = _recover_model_spec(spec)
    signature = str(spec.get("function_signature") or "").strip()
    if not signature:
        signature = str(recovered.get("function_signature") or "").strip()
    return_name = _extract_rust_return_name(signature)
    model_return_name = _extract_rust_return_name(
        str(recovered.get("function_signature") or "")
    )
    parameters = list(_extract_rust_parameters(signature))
    aliases = [
        name
        for name in [model_return_name]
        if name and name != return_name and name not in parameters
    ]
    clauses = _normalize_verus_clauses(
        recovered.get("verus_clauses"),
        str(recovered.get("verus_contract") or ""),
    )
    migrated: List[Dict[str, str]] = []
    removed: List[Dict[str, str]] = []
    for clause in clauses:
        kind = str(clause.get("type", "")).strip().lower()
        expression = _normalize_rust_return_expr(
            str(clause.get("expr", "")),
            return_name,
            return_aliases=aliases,
            parameter_names=parameters,
        )
        expression = _normalize_rust_state_expr(expression, signature, kind)
        normalized = {"type": kind, "expr": expression}
        if kind not in {"requires", "ensures"} or not expression:
            continue
        if _has_disallowed_verus_expr(expression):
            removed.append({**normalized, "reason": "disallowed_verus_expression"})
        elif _is_tautological_clause(expression):
            removed.append({**normalized, "reason": "tautological_clause"})
        else:
            migrated.append(normalized)
    migration_error = ""
    if not migrated:
        migrated = _normalize_verus_clauses(
            spec.get("verus_clauses"),
            str(spec.get("verus_contract") or ""),
        )
        migration_error = "all recovered clauses were unsupported; preserved original canonical clauses"

    updated = dict(spec)
    updated["function_signature"] = signature
    updated["verus_clauses"] = migrated
    updated["verus_contract"] = _build_verus_contract(migrated)
    updated["offline_migration_v2"] = {
        "recovered_from_raw_model_output": recovered is not spec,
        "parameter_aware_return_aliases": aliases,
        "removed_clauses": removed,
        "contract_locked_to_code": True,
        "migration_error": migration_error,
    }
    return updated


def _copy_missing_reused_spec(
    destination: Path,
    relative_path: str,
    reuse_source: str,
) -> None:
    target = destination / "specs" / Path(relative_path).with_suffix(".json")
    if target.exists() or not reuse_source:
        return
    source = Path(reuse_source) / "specs" / Path(relative_path).with_suffix(".json")
    if source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _migrate_output(source: Path, args: argparse.Namespace) -> Path:
    destination = source.with_name(source.name + args.suffix)
    if destination.exists():
        if not args.overwrite:
            raise FileExistsError(f"destination already exists: {destination}")
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

    results_file = destination / "reports" / "results.json"
    report = json.loads(results_file.read_text())
    reuse_source = str(report.get("enhanced_modules", {}).get("reuse_artifacts_from") or "")
    verifier = VerusVerifier(timeout=args.verify_timeout, verus_cmd=args.verus_bin)
    passed = 0
    verified = 0

    for row in report.get("results", []):
        relative_path = str(row.get("path", ""))
        _copy_missing_reused_spec(destination, relative_path, reuse_source)
        spec_file = destination / "specs" / Path(relative_path).with_suffix(".json")
        code_file = destination / "code" / relative_path
        row["spec_file"] = str(spec_file)
        row["code_file"] = str(code_file)
        if not spec_file.is_file():
            row["status"] = "error"
            row["error"] = f"offline migration: missing spec artifact: {spec_file}"
            row["verification"] = {"valid": False, "type": "missing", "message": row["error"]}
            continue

        spec = _migrate_spec(json.loads(spec_file.read_text()))
        spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
        if not code_file.is_file():
            row["status"] = "error"
            row["error"] = f"offline migration: missing code artifact: {code_file}"
            row["verification"] = {"valid": False, "type": "missing", "message": row["error"]}
            continue

        enforcement_error = ""
        try:
            code, rewritten = _enforce_rust_contract(
                code_file.read_text(),
                str(spec["function_signature"]),
                list(spec["verus_clauses"]),
            )
            code_file.write_text(code)
            row["contract_enforcement"] = {
                "enabled": True,
                "rewritten": rewritten,
                "reason": "offline_v2 canonical contract lock",
            }
        except Exception as exc:
            enforcement_error = f"offline contract enforcement failed: {exc}"
            row["status"] = "error"
            row["error"] = enforcement_error

        if args.skip_verify:
            row["verification"] = {
                "valid": False,
                "type": "skipped",
                "message": "offline migration skipped Verus verification",
            }
            continue

        verified += 1
        verdict = verifier.verify(code_file)
        details_file = destination / "reports" / Path(relative_path).with_suffix(
            ".offline-v2.verus.log"
        )
        details_file.parent.mkdir(parents=True, exist_ok=True)
        if verdict.details:
            details_file.write_text(verdict.details)
        valid = verdict.is_valid()
        if valid:
            passed += 1
        row["status"] = "error" if enforcement_error else "ok"
        if not enforcement_error:
            row.pop("error", None)
        row["verification"] = {
            "valid": valid,
            "type": verdict.verdict_type.value,
            "message": verdict.message,
            "repair_attempts": row.get("verification", {}).get("repair_attempts", 0),
            "code_repair_enabled": row.get("verification", {}).get(
                "code_repair_enabled", False
            ),
            "code_repair_strategy": row.get("verification", {}).get(
                "code_repair_strategy", "simple"
            ),
            "details_file": str(details_file),
            "offline_reverified": True,
        }

    report["verified"] = verified
    report["passed"] = passed
    report["offline_migration_v2"] = {
        "source_output_dir": str(source),
        "destination_output_dir": str(destination),
        "contract_locked": True,
        "verus_reverified": not args.skip_verify,
    }
    results_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_constraint_entailment.py",
            "--language",
            "rust",
            "--ground-truth-spec-file",
            str(args.ground_truth_spec_file),
            "--output-dir",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/summarize_req2code_benchmark.py",
            "--output-dir",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return destination


def main() -> None:
    args = parse_args()
    for source in args.output_dirs:
        destination = _migrate_output(source, args)
        print(f"[INFO] migrated {source} -> {destination}")


if __name__ == "__main__":
    main()
