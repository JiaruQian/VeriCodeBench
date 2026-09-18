#!/usr/bin/env python3
"""Summarize benchmark metrics at problem level.

Metrics:
1) code validity rate: whether generated code verifies against generated spec
2) requirement coverage x/n: whether generated spec covers requirement ground truth
3) joint success: code is valid AND requirement coverage is complete (x == n)
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from scripts.evaluate_constraint_entailment import (
    _build_rust_canonical_map,
    _canonicalize_by_signature,
    _extract_raw_rust_return_name,
    _normalize_logic_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build per-problem and aggregate benchmark metrics."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/req2code"),
        help="Pipeline output directory containing reports/results.json and constraint_entailment.json.",
    )
    parser.add_argument(
        "--results-file",
        type=Path,
        default=None,
        help="Optional override for code verification report.",
    )
    parser.add_argument(
        "--entailment-file",
        type=Path,
        default=None,
        help="Optional override for requirement coverage report.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Optional output path. Default: <output-dir>/reports/benchmark_summary.json",
    )
    return parser.parse_args()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text())


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _extract_contract_block(source: str) -> str:
    match = re.search(r"/\*@([\s\S]*?)\*/", source)
    return match.group(0) if match else ""


def _only_whitespace_or_line_comments(source: str) -> bool:
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("//"):
            return False
    return True


def _method_name_from_signature(signature: str) -> str:
    header = signature.strip().rstrip(";")
    paren_idx = header.find("(")
    if paren_idx < 0:
        return ""
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", header[:paren_idx])
    return names[-1] if names else ""


def _find_method_declaration_start(code: str, method_name: str) -> int:
    if not method_name:
        return -1
    pattern = re.compile(rf"\b{re.escape(method_name)}\s*\(")
    for match in pattern.finditer(code):
        line_start = code.rfind("\n", 0, match.start()) + 1
        line_prefix = code[line_start:match.start()]
        if "=" in line_prefix or "." in line_prefix:
            continue
        brace_idx = code.find("{", match.end())
        semicolon_idx = code.find(";", match.end())
        if brace_idx < 0:
            continue
        if semicolon_idx >= 0 and semicolon_idx < brace_idx:
            continue
        return line_start
    return -1


def _extract_target_method_contract(source: str, function_signature: str) -> str:
    method_name = _method_name_from_signature(function_signature)
    method_start = _find_method_declaration_start(source, method_name)
    if method_start < 0:
        return _extract_contract_block(source)

    contract_start: int | None = None
    contract_end = method_start
    while True:
        before_contract = source[:contract_end]
        contract_match: re.Match[str] | None = None
        for match in re.finditer(r"/\*@[\s\S]*?\*/\s*", before_contract):
            if not _only_whitespace_or_line_comments(source[match.end() : contract_end]):
                continue
            contract_match = match
        if not contract_match:
            break
        contract_start = contract_match.start()
        contract_end = contract_match.start()
    return source[contract_start:method_start] if contract_start is not None else ""


def _normalize_contract_expr(expr: str) -> str:
    out = expr.strip()
    out = out.replace("\\strictly_nothing", "\\nothing")
    out = re.sub(r"\s+", "", out.lower())
    return out


def _extract_jml_clauses(contract_block: str) -> List[Dict[str, str]]:
    body = contract_block.replace("/*@", "").replace("*/", "")
    keywords = r"requires|ensures|assignable|assigns|signals_only|signals"
    keyword_re = re.compile(rf"^\s*@?\s*({keywords})\b\s*(.*)$")
    clauses: List[Dict[str, str]] = []
    current_type = ""
    current_parts: List[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^\*+\s?", "", line).strip()
        if not line:
            continue
        match = keyword_re.match(line)
        if match:
            if current_type and current_parts:
                expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
                clauses.append({"type": current_type, "expr": expr})
            current_type = match.group(1).strip()
            current_parts = [match.group(2).strip()]
        elif current_type:
            current_parts.append(line)

        if current_type and line.endswith(";"):
            expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
            clauses.append({"type": current_type, "expr": expr})
            current_type = ""
            current_parts = []

    if current_type and current_parts:
        expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
        clauses.append({"type": current_type, "expr": expr})

    return clauses


def _canonical_contract_clauses(contract_block: str) -> List[tuple[str, str]]:
    return [
        (str(clause["type"]).strip().lower(), _normalize_contract_expr(clause["expr"]))
        for clause in _extract_jml_clauses(contract_block)
    ]


def _java_contract_consistency(row: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
    if not enabled:
        return {"checked": False, "consistent": True}
    if row.get("status") != "ok":
        return {"checked": False, "consistent": True, "reason": "generation_not_ok"}

    spec_file_text = str(row.get("spec_file", "")).strip()
    code_file_text = str(row.get("code_file", "")).strip()
    if not spec_file_text or not code_file_text:
        return {
            "checked": True,
            "consistent": False,
            "reason": "missing_spec_or_code_file_path",
        }

    spec_file = _resolve_path(spec_file_text)
    code_file = _resolve_path(code_file_text)
    if not spec_file.exists() or not code_file.exists():
        return {
            "checked": True,
            "consistent": False,
            "reason": "missing_spec_or_code_file",
        }

    try:
        spec_json = json.loads(spec_file.read_text())
        spec_block = str(spec_json.get("jml_block") or spec_json.get("acsl_block") or "")
        function_signature = str(spec_json.get("function_signature", ""))
        code_block = _extract_target_method_contract(code_file.read_text(), function_signature)
        spec_clauses = _canonical_contract_clauses(spec_block)
        code_clauses = _canonical_contract_clauses(code_block)
        if spec_clauses == code_clauses:
            return {"checked": True, "consistent": True}
        return {
            "checked": True,
            "consistent": False,
            "reason": "jml_contract_clauses_differ",
            "spec_clause_count": len(spec_clauses),
            "code_clause_count": len(code_clauses),
        }
    except Exception as exc:
        return {
            "checked": True,
            "consistent": False,
            "reason": f"contract_check_error: {exc}",
        }


def _split_rust_contract_expressions(text: str) -> List[str]:
    expressions: List[str] = []
    start = 0
    paren = bracket = brace = generic = 0
    idx = 0
    while idx < len(text):
        char = text[idx]
        if char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "{":
            brace += 1
        elif char == "}":
            brace = max(0, brace - 1)
        elif char == "<" and idx >= 2 and text[idx - 2 : idx] == "::":
            generic += 1
        elif char == ">" and generic:
            generic -= 1
        elif char == "," and paren == bracket == brace == generic == 0:
            expression = text[start:idx].strip()
            if expression:
                expressions.append(expression)
            start = idx + 1
        idx += 1
    tail = text[start:].strip()
    if tail:
        expressions.append(tail)
    return expressions


def _extract_rust_code_clauses(code: str, function_signature: str) -> List[Dict[str, str]]:
    name_match = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", function_signature)
    if not name_match:
        return []
    function_name = name_match.group(1)
    declaration = re.search(
        rf"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+{re.escape(function_name)}\b",
        code,
    )
    if not declaration:
        return []
    tail = code[declaration.start() :]
    body = re.search(r"(?m)^\s*\{\s*$", tail)
    if not body:
        return []
    header = tail[: body.start()]
    keywords = list(re.finditer(r"(?m)^\s*(requires|ensures)\b", header))
    clauses: List[Dict[str, str]] = []
    for idx, match in enumerate(keywords):
        end = keywords[idx + 1].start() if idx + 1 < len(keywords) else len(header)
        blob = header[match.end() : end].strip()
        clauses.extend(
            {"type": match.group(1), "expr": expression}
            for expression in _split_rust_contract_expressions(blob)
        )
    return clauses


def _canonical_rust_clause_set(
    clauses: List[Dict[str, str]],
    signature: str,
    raw_return_name: str | None = None,
) -> set[tuple[str, str]]:
    mapping = _build_rust_canonical_map(
        signature,
        extra_return_names=[raw_return_name] if raw_return_name else None,
    )
    canonical: set[tuple[str, str]] = set()
    for clause in clauses:
        kind = str(clause.get("type", "")).strip().lower()
        expression = str(clause.get("expr", "")).strip().rstrip(",").strip()
        if kind not in {"requires", "ensures"} or not expression:
            continue
        normalized = _canonicalize_by_signature(
            expression,
            mapping,
            pre_state=(kind == "requires"),
        )
        normalized = _normalize_logic_text(normalized)
        if kind == "requires" and normalized in {"true", "1", "(true)", "(1)"}:
            continue
        canonical.add((kind, normalized))
    return canonical


def _rust_contract_consistency(row: Dict[str, Any], enabled: bool) -> Dict[str, Any]:
    if not enabled:
        return {"checked": False, "consistent": True}
    if row.get("status") != "ok":
        return {"checked": False, "consistent": True, "reason": "generation_not_ok"}
    spec_file = _resolve_path(str(row.get("spec_file", "")))
    code_file = _resolve_path(str(row.get("code_file", "")))
    if not spec_file.is_file() or not code_file.is_file():
        return {"checked": True, "consistent": False, "reason": "missing_spec_or_code_file"}
    try:
        spec = json.loads(spec_file.read_text())
        signature = str(spec.get("function_signature", "")).strip()
        spec_clauses = spec.get("verus_clauses") or []
        code_clauses = _extract_rust_code_clauses(code_file.read_text(), signature)
        raw_return_name = _extract_raw_rust_return_name(spec)
        canonical_spec = _canonical_rust_clause_set(spec_clauses, signature, raw_return_name)
        canonical_code = _canonical_rust_clause_set(code_clauses, signature, raw_return_name)
        if canonical_spec == canonical_code:
            return {"checked": True, "consistent": True}
        return {
            "checked": True,
            "consistent": False,
            "reason": "verus_contract_clauses_differ",
            "spec_clause_count": len(canonical_spec),
            "code_clause_count": len(canonical_code),
            "missing_from_code": sorted(canonical_spec - canonical_code),
            "extra_in_code": sorted(canonical_code - canonical_spec),
        }
    except Exception as exc:
        return {"checked": True, "consistent": False, "reason": f"contract_check_error: {exc}"}


def main() -> None:
    args = parse_args()
    results_file = args.results_file or (args.output_dir / "reports" / "results.json")
    entailment_file = args.entailment_file or (
        args.output_dir / "reports" / "constraint_entailment.json"
    )
    report_file = args.report_file or (args.output_dir / "reports" / "benchmark_summary.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    results = _load_json(results_file)
    entailment = _load_json(entailment_file)

    code_rows = results.get("results", [])
    entail_rows = entailment.get("results", [])
    entail_by_id = {int(r["id"]): r for r in entail_rows if "id" in r}
    java_contract_check_enabled = (
        str(results.get("language", "")).lower() == "java"
        and str(results.get("verifier", "")).lower() == "openjml"
    )
    rust_contract_check_enabled = (
        str(results.get("language", "")).lower() == "rust"
        and str(results.get("verifier", "")).lower() == "verus"
    )

    per_problem: List[Dict[str, Any]] = []
    valid_count = 0
    contract_mismatch_count = 0
    coverage_x_total = 0
    coverage_n_total = 0
    joint_success_count = 0
    joint_success_problem_ids: List[int] = []

    for row in code_rows:
        rid = int(row.get("id"))
        path = str(row.get("path", ""))
        verification = row.get("verification", {})
        code_valid = bool(verification.get("valid", False))
        contract_consistency: Dict[str, Any] = {}
        if java_contract_check_enabled:
            contract_consistency = _java_contract_consistency(row, enabled=True)
            if contract_consistency.get("checked") and not contract_consistency.get("consistent"):
                contract_mismatch_count += 1
                code_valid = False
        elif rust_contract_check_enabled:
            contract_consistency = _rust_contract_consistency(row, enabled=True)
            if contract_consistency.get("checked") and not contract_consistency.get("consistent"):
                contract_mismatch_count += 1
                code_valid = False
        if code_valid:
            valid_count += 1

        entail_row = entail_by_id.get(rid, {})
        cov_x = int(entail_row.get("requirement_coverage_x", 0))
        cov_n = int(entail_row.get("requirement_coverage_n", 0))
        cov_ratio = (cov_x / cov_n) if cov_n > 0 else 0.0
        coverage_x_total += cov_x
        coverage_n_total += cov_n
        requirement_fully_covered = cov_n > 0 and cov_x == cov_n
        joint_success = code_valid and requirement_fully_covered
        if joint_success:
            joint_success_count += 1
            joint_success_problem_ids.append(rid)

        problem_report = {
            "id": rid,
            "path": path,
            "code_valid": code_valid,
            "requirement_coverage_x": cov_x,
            "requirement_coverage_n": cov_n,
            "requirement_coverage_ratio": cov_ratio,
            "requirement_fully_covered": requirement_fully_covered,
            "joint_success": joint_success,
        }
        if java_contract_check_enabled or rust_contract_check_enabled:
            problem_report["contract_consistency"] = contract_consistency
        per_problem.append(problem_report)

    total = len(per_problem)
    valid_rate = (valid_count / total) if total > 0 else 0.0
    requirement_coverage_micro = (
        coverage_x_total / coverage_n_total if coverage_n_total > 0 else 0.0
    )
    requirement_coverage_macro = (
        sum(float(r["requirement_coverage_ratio"]) for r in per_problem) / total if total > 0 else 0.0
    )
    joint_success_rate = (joint_success_count / total) if total > 0 else 0.0

    report = {
        "metrics_definition": {
            "code_validity_rate": "count(code_valid=true)/num_problems",
            "requirement_coverage": "x/n per problem, x=matched units, n=total units",
            "joint_success": (
                "count(code_valid=true AND requirement_coverage_x==requirement_coverage_n)"
                "/num_problems"
            ),
        },
        "summary": {
            "num_problems": total,
            "code_valid_count": valid_count,
            "code_validity_rate": valid_rate,
            "requirement_coverage_x_total": coverage_x_total,
            "requirement_coverage_n_total": coverage_n_total,
            "requirement_coverage_micro": requirement_coverage_micro,
            "requirement_coverage_macro": requirement_coverage_macro,
            "joint_success_count": joint_success_count,
            "joint_success_rate": joint_success_rate,
            "joint_success_problem_ids": joint_success_problem_ids,
        },
        "per_problem": per_problem,
    }
    if java_contract_check_enabled or rust_contract_check_enabled:
        report["summary"]["contract_mismatch_count"] = contract_mismatch_count
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] benchmark summary: {report_file}")
    print(
        f"[INFO] code_validity_rate={valid_rate:.4f} "
        f"requirement_coverage_macro={requirement_coverage_macro:.4f} "
        f"joint_success_rate={joint_success_rate:.4f}"
    )


if __name__ == "__main__":
    main()
