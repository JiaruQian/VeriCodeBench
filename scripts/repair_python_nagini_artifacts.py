#!/usr/bin/env python3
"""Repair existing Python/Nagini artifacts without calling an LLM."""
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autospec.pipeline.python_nagini_requirement_pipeline import (
    _build_nagini_contract,
    _container_param_names,
    _enforce_nagini_contract,
    _extract_python_code,
    _normalize_nagini_clauses,
    _rewrite_implication_operator,
    _signature_param_types,
    _signature_return_type,
)
from autospec.verifier.nagini import NaginiVerifier


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy and deterministically repair Python/Nagini output artifacts."
    )
    parser.add_argument("--source-output-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--verify",
        choices=["none", "failed", "all"],
        default="failed",
        help="Which repaired artifacts to verify with Nagini.",
    )
    parser.add_argument("--verify-timeout", type=int, default=120)
    parser.add_argument("--nagini-bin", default="nagini")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def _remap_path(path_text: str, source_dir: Path, output_dir: Path) -> str:
    if not path_text:
        return path_text
    path = Path(path_text)
    resolved_path = path if path.is_absolute() else path.resolve()
    try:
        relative = resolved_path.relative_to(source_dir)
    except ValueError:
        return path_text
    return str(output_dir / relative)


def _repair_one(
    row: Dict[str, Any],
    source_dir: Path,
    output_dir: Path,
) -> Dict[str, Any]:
    repaired = dict(row)
    for key in ("spec_file", "code_file"):
        repaired[key] = _remap_path(str(repaired.get(key) or ""), source_dir, output_dir)
    verification = dict(repaired.get("verification") or {})
    verification["details_file"] = _remap_path(
        str(verification.get("details_file") or ""), source_dir, output_dir
    )
    if verification:
        repaired["verification"] = verification

    spec_file_text = str(repaired.get("spec_file") or "")
    code_file_text = str(repaired.get("code_file") or "")
    if not spec_file_text or not code_file_text:
        repaired["offline_repair"] = {
            "repaired": False,
            "reason": "missing_spec_or_code_artifact",
        }
        return repaired
    spec_file = Path(spec_file_text)
    code_file = Path(code_file_text)
    if not spec_file.is_file() or not code_file.is_file():
        repaired["offline_repair"] = {
            "repaired": False,
            "reason": "missing_spec_or_code_artifact",
        }
        return repaired

    spec = json.loads(spec_file.read_text())
    signature = str(spec.get("function_signature") or "").strip()
    original_contract = str(spec.get("nagini_contract") or "").strip()
    clauses = _normalize_nagini_clauses(
        spec.get("nagini_clauses"), contract_text=original_contract
    )
    param_types = _signature_param_types(signature)
    return_type = _signature_return_type(signature)
    removed = []
    sanitized = []
    seen = set()
    for clause in clauses:
        kind = str(clause.get("type") or "").strip().lower()
        expr = _rewrite_implication_operator(str(clause.get("expr") or "").strip())
        expr = re.sub(
            r"Result\(\)\s*==\s*not\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"Result() == (not \1)",
            expr,
        )
        if kind == "ensures" and return_type in {"None", "NoneType"} and "Result()" in expr:
            removed.append({"type": kind, "expr": expr})
            continue
        key = (kind, "".join(expr.split()))
        if kind in {"requires", "ensures"} and expr and key not in seen:
            seen.add(key)
            sanitized.append({"type": kind, "expr": expr})

    container_names = _container_param_names(param_types)
    def dependency_rank(clause: Dict[str, str]) -> int:
        expr = clause["expr"]
        if expr.startswith("Acc("):
            return 0
        has_index = any(f"{name}[" in "".join(expr.split()) for name in container_names)
        has_structure = any(
            f"len({name})" in "".join(expr.split()) or f"in{name}" in "".join(expr.split())
            for name in container_names
        )
        if has_structure and not has_index:
            return 1
        return 3 if has_index else 2

    sanitized = sorted(
        (clause for clause in sanitized if clause["type"] == "requires"),
        key=dependency_rank,
    ) + sorted(
        (clause for clause in sanitized if clause["type"] == "ensures"),
        key=dependency_rank,
    )
    metadata = {
        "input_clause_count": len(clauses),
        "output_clause_count": len(sanitized),
        "removed_clause_count": len(removed),
    }
    if not sanitized:
        repaired["offline_repair"] = {
            "repaired": False,
            "reason": "no_valid_contract_clauses_after_sanitization",
        }
        return repaired

    contract = _build_nagini_contract(sanitized)
    code_text = _extract_python_code(code_file.read_text())
    code_text, enforcement = _enforce_nagini_contract(
        code_text=code_text,
        function_signature=signature,
        nagini_contract=contract,
    )
    ast.parse(code_text, filename=str(code_file))

    spec["nagini_clauses"] = sanitized
    spec["nagini_contract"] = contract
    spec["offline_repair"] = {
        "source_output_dir": str(source_dir),
        "contract_changed": contract != original_contract,
        "removed_clauses": removed,
        "sanitization": metadata,
        "contract_enforcement": enforcement,
    }
    spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")
    code_file.write_text(code_text)
    repaired["spec_file"] = str(spec_file)
    repaired["code_file"] = str(code_file)
    repaired["contract_enforcement"] = {
        "enabled": True,
        "offline_repair": enforcement,
    }
    repaired["offline_repair"] = {
        "repaired": True,
        "contract_changed": contract != original_contract,
        "removed_clause_count": len(removed),
    }
    return repaired


def main() -> None:
    args = parse_args()
    source_dir = args.source_output_dir.resolve()
    output_dir = args.output_dir.resolve()
    if source_dir == output_dir:
        raise SystemExit("source and output directories must differ")
    if output_dir.exists():
        if not args.overwrite:
            raise SystemExit(f"output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    shutil.copytree(source_dir, output_dir)

    results_file = output_dir / "reports" / "results.json"
    report = json.loads(results_file.read_text())
    repaired_rows = []
    repair_errors = []
    for row in report.get("results", []):
        try:
            repaired_rows.append(_repair_one(row, source_dir, output_dir))
        except Exception as exc:
            failed_row = dict(row)
            failed_row["offline_repair"] = {"repaired": False, "reason": str(exc)}
            repaired_rows.append(failed_row)
            repair_errors.append({"id": row.get("id"), "error": str(exc)})

    verifier = NaginiVerifier(timeout=args.verify_timeout, nagini_cmd=args.nagini_bin)
    for row in repaired_rows:
        if not (row.get("offline_repair") or {}).get("repaired"):
            continue
        previous_valid = bool((row.get("verification") or {}).get("valid"))
        should_verify = args.verify == "all" or (args.verify == "failed" and not previous_valid)
        if not should_verify:
            continue
        code_file = Path(str(row["code_file"]))
        verdict = verifier.verify(code_file)
        details_file = output_dir / "reports" / Path(str(row["path"])).with_suffix(".nagini.log")
        details_file.parent.mkdir(parents=True, exist_ok=True)
        details_file.write_text(verdict.details or verdict.message)
        row["status"] = "ok"
        row["verification"] = {
            "valid": verdict.is_valid(),
            "type": verdict.verdict_type.value,
            "message": verdict.message,
            "repair_attempts": 0,
            "code_repair_enabled": False,
            "code_repair_strategy": "offline_deterministic",
            "details_file": str(details_file),
        }

    report["results"] = repaired_rows
    report["processed"] = len(repaired_rows)
    report["verified"] = sum(1 for row in repaired_rows if row.get("verification"))
    report["passed"] = sum(
        1 for row in repaired_rows if (row.get("verification") or {}).get("valid")
    )
    report["offline_repair"] = {
        "source_output_dir": str(source_dir),
        "verify_mode": args.verify,
        "repaired_count": sum(
            1 for row in repaired_rows if (row.get("offline_repair") or {}).get("repaired")
        ),
        "errors": repair_errors,
    }
    results_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[INFO] output={output_dir} repaired={report['offline_repair']['repaired_count']} "
        f"passed={report['passed']} errors={len(repair_errors)}"
    )


if __name__ == "__main__":
    main()
