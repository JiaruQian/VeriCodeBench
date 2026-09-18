#!/usr/bin/env python3
"""Constraint Entailment Framework (CEF): evaluate generated specs against manual
language-specific ground-truth specs."""
from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from z3 import (  # type: ignore
        And,
        Bool,
        BoolRef,
        BoolVal,
        If,
        Int,
        IntVal,
        Not,
        Or,
        Solver,
        unsat,
    )

    HAS_Z3 = True
except Exception:
    HAS_Z3 = False


REQUIRES_KINDS = {"pre", "requires"}
POST_KINDS = {"post", "ensures"}
FRAME_KINDS = {"frame", "assigns", "assignable"}
EXCEPTION_KINDS = {"signals", "signals_only", "exceptional_behavior"}


def _normalize_kind(kind: str) -> str:
    return kind.strip().lower()


def _entailment_direction_for_kind(kind: str) -> str:
    norm = _normalize_kind(kind)
    if norm in REQUIRES_KINDS:
        return "req_entails_spec"
    return "spec_entails_req"


def _candidate_clause_types_for_kind(kind: str) -> set[str]:
    norm = _normalize_kind(kind)
    if norm in REQUIRES_KINDS:
        return {"requires"}
    if norm in POST_KINDS:
        return {"ensures"}
    if norm in FRAME_KINDS:
        # Frame constraints may be expressed via explicit assigns clauses
        # or via strong ensures clauses in some generated specs.
        return {"assigns", "assignable", "ensures"}
    if norm in EXCEPTION_KINDS:
        return {"signals", "signals_only", "ensures"}
    return {"requires", "ensures", "assigns", "assignable", "signals", "signals_only"}


def _extract_param_names(signature: str) -> List[str]:
    m = re.search(r"\((.*)\)", signature)
    if not m:
        return []
    params_blob = m.group(1).strip()
    if not params_blob or params_blob == "void":
        return []
    params = [p.strip() for p in params_blob.split(",") if p.strip()]
    if not params:
        return []
    c_keywords = {
        "const",
        "volatile",
        "restrict",
        "unsigned",
        "signed",
        "short",
        "long",
        "int",
        "float",
        "double",
        "char",
        "void",
        "struct",
        "union",
        "enum",
        "static",
        "extern",
        "register",
        "inline",
        "_bool",
        "bool",
    }
    names: List[str] = []
    for param in params:
        if "..." in param:
            continue
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", param)
        if not tokens:
            continue
        name = tokens[-1]
        if name.lower() in c_keywords:
            continue
        names.append(name)
    return names


def _build_param_canonical_map(signature: str) -> Dict[str, str]:
    names = _extract_param_names(signature)
    return {name: f"arg{idx}" for idx, name in enumerate(names)}


def _build_java_canonical_map(signature: str) -> Dict[str, str]:
    mapping = _build_param_canonical_map(signature)
    if re.search(r"\bboolean\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", signature):
        mapping["result"] = "bool_result"
    return mapping


def _extract_java_getter_aliases(helper_declarations: str) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    getter_re = re.compile(
        r"\b(?:public\s+|protected\s+|private\s+)?"
        r"[A-Za-z_][A-Za-z0-9_<>,\[\]]*\s+"
        r"(get[A-Z][A-Za-z0-9_]*)\s*\(\s*\)\s*"
        r"\{\s*return\s+(?:this\.)?([A-Za-z_][A-Za-z0-9_]*)\s*;\s*\}"
    )
    for match in getter_re.finditer(helper_declarations):
        aliases[match.group(1)] = match.group(2)
    return aliases


def _normalize_java_surface_expr(
    expr: str,
    getter_aliases: Optional[Dict[str, str]] = None,
) -> str:
    out = re.sub(
        r"\(\s*(?:byte|short|int|long|char|float|double|boolean)\s*\)",
        "",
        expr,
    )
    aliases = getter_aliases or {}

    def replace_getter(match: re.Match[str]) -> str:
        method_name = match.group(2)
        field_name = aliases.get(method_name)
        if field_name is None:
            return match.group(0)
        return f"{match.group(1)}.{field_name}"

    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.(get[A-Z][A-Za-z0-9_]*)\(\)",
        replace_getter,
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.length\(\)",
        r"\1_length",
        out,
    )
    out = re.sub(
        r"\b(Integer|Long|Short|Byte|Character)\.([A-Z_][A-Z0-9_]*)\b",
        r"\1_\2",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b",
        r"\1_\2",
        out,
    )
    out = re.sub(
        r"'([^'\\])'",
        lambda m: str(ord(m.group(1))),
        out,
    )
    return out


def _split_rust_params(params_blob: str) -> List[str]:
    params: List[str] = []
    start = 0
    angle = 0
    paren = 0
    bracket = 0
    for idx, ch in enumerate(params_blob):
        if ch == "<":
            angle += 1
        elif ch == ">":
            angle = max(0, angle - 1)
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "," and angle == 0 and paren == 0 and bracket == 0:
            part = params_blob[start:idx].strip()
            if part:
                params.append(part)
            start = idx + 1
    tail = params_blob[start:].strip()
    if tail:
        params.append(tail)
    return params


def _extract_rust_params_blob(signature: str) -> str:
    match = re.search(r"\bfn\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", signature)
    if not match:
        return ""
    start = match.end() - 1
    depth = 0
    for idx in range(start, len(signature)):
        ch = signature[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return signature[start + 1 : idx]
    return ""


def _extract_rust_param_names(signature: str) -> List[str]:
    params_blob = _extract_rust_params_blob(signature)
    if not params_blob:
        return []
    names: List[str] = []
    for param in _split_rust_params(params_blob):
        if ":" not in param:
            continue
        name = param.split(":", 1)[0].strip()
        name = name.lstrip("&").strip()
        if name in {"self", "mut self", ""}:
            continue
        if name.startswith("mut "):
            name = name[4:].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
    return names


def _extract_rust_return_name(signature: str) -> Optional[str]:
    match = re.search(r"->\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", signature)
    if match:
        return match.group(1)
    return None


def _build_rust_canonical_map(
    signature: str,
    extra_return_names: Optional[List[str]] = None,
) -> Dict[str, str]:
    param_names = _extract_rust_param_names(signature)
    mapping = {name: f"arg{idx}" for idx, name in enumerate(param_names)}
    # Ground-truth Rust clauses use `r`; older generated artifacts often use
    # `result`, `res`, or `ret`. Treat these as the same return value for
    # clause coverage unless they are actual parameter names.
    for alias in ["r", "result", "res", "ret"]:
        if alias not in param_names:
            mapping[alias] = "ret"
    return_name = _extract_rust_return_name(signature)
    if return_name and return_name not in param_names:
        mapping[return_name] = "ret"
    for alias in extra_return_names or []:
        if alias and alias not in param_names:
            mapping[alias] = "ret"
    return mapping


def _extract_raw_rust_return_name(spec: Dict[str, Any]) -> Optional[str]:
    raw = str(spec.get("raw_model_output") or "").strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        match = re.search(r'"function_signature"\s*:\s*"([^"]+)"', raw)
        if not match:
            return None
        return _extract_rust_return_name(match.group(1))
    if not isinstance(obj, dict):
        return None
    return _extract_rust_return_name(str(obj.get("function_signature") or ""))


def _split_python_params(params_blob: str) -> List[str]:
    params: List[str] = []
    start = 0
    bracket = 0
    for idx, ch in enumerate(params_blob):
        if ch in "([":
            bracket += 1
        elif ch in ")]":
            bracket = max(0, bracket - 1)
        elif ch == "," and bracket == 0:
            part = params_blob[start:idx].strip()
            if part:
                params.append(part)
            start = idx + 1
    tail = params_blob[start:].strip()
    if tail:
        params.append(tail)
    return params


def _extract_python_param_names(signature: str) -> List[str]:
    match = re.search(r"\bdef\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*(?:->\s*[^:]+)?\s*:", signature)
    if not match:
        return []
    names: List[str] = []
    for param in _split_python_params(match.group(1)):
        if not param or param.startswith("*"):
            continue
        name = param.split(":", 1)[0].split("=", 1)[0].strip()
        if name in {"self", "cls"}:
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
    return names


def _build_python_canonical_map(signature: str) -> Dict[str, str]:
    match = re.search(
        r"\bdef\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*(?:->\s*([^:]+))?\s*:",
        signature,
    )
    param_types: Dict[str, str] = {}
    return_type = ""
    if match:
        for param in _split_python_params(match.group(1)):
            if not param or param.startswith("*"):
                continue
            declaration = param.split("=", 1)[0].strip()
            if ":" not in declaration:
                continue
            name, annotation = declaration.split(":", 1)
            param_types[name.strip()] = annotation.strip()
        return_type = str(match.group(2) or "").strip()

    mapping = {
        name: f"bool_arg{idx}" if param_types.get(name) == "bool" else f"arg{idx}"
        for idx, name in enumerate(_extract_python_param_names(signature))
    }
    result_name = "bool_ret" if return_type == "bool" else "ret"
    mapping["Result"] = result_name
    mapping["result"] = result_name
    return mapping


def _normalize_verus_surface_expr(expr: str) -> str:
    out = expr.strip().rstrip(";").rstrip(",").strip()
    # The benchmark's Rust ground truth mixes ordinary Rust views (`v.len()`,
    # `v[i]`) with Verus sequence views (`v@.len()`, `v@[i]`). For coverage
    # matching, normalize these surface spellings before exact/SMT checks.
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)@\.", r"\1.", out)
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)@\s*\[", r"\1[", out)
    out = re.sub(r"\bold\(([^()]+)@\.len\(\)\)", r"old(\1).len()", out)
    out = re.sub(r"\bold\(([^()]+)\.len\(\)\)", r"old(\1).len()", out)
    out = re.sub(r"\bold\(([^()]+)@\)", r"old(\1)", out)
    out = re.sub(r"\bfinal\(([^()]+)\)\.", r"\1.", out)
    out = re.sub(r"\bfinal\(([^()]+)\)\s*\[", r"\1[", out)
    out = re.sub(r"\bold\(([^()]+)\)@", r"old(\1)", out)
    out = re.sub(r"\bfinal\(([^()]+)\)@", r"\1", out)
    out = re.sub(r"\bfinal\(([^()]+)@\)", r"\1", out)
    out = re.sub(r"\bfinal\(([^()]+)\)", r"\1", out)
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)@(?![A-Za-z0-9_])", r"\1", out)
    out = out.replace("=~=", "==")
    out = re.sub(r"#\s*\[\s*trigger\s*\]\s*", "", out)
    out = re.sub(r"\bNone\s*::\s*<[^>]+>", "None", out)
    out = re.sub(r"\b(?:Option|Result)::(Some|None|Ok|Err)\b", r"\1", out)
    out = re.sub(r"\b(Some|Ok|Err)\s*::\s*<[^>]+>", r"\1", out)
    out = re.sub(r"\bu64::MAX\b", str((1 << 64) - 1), out)
    out = re.sub(r"\busize::MAX\b", str((1 << 64) - 1), out)
    out = re.sub(
        r"\b([0-9]+)(?:u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|isize)\b",
        r"\1",
        out,
    )
    for variant in ("Some", "None", "Ok", "Err"):
        out = re.sub(
            rf"\b([A-Za-z_][A-Za-z0-9_]*)\.is_{variant}\(\)",
            rf"\1 is {variant}",
            out,
        )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_some\(\)", r"\1 is Some", out
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_none\(\)", r"\1 is None", out
    )
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_ok\(\)", r"\1 is Ok", out)
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_err\(\)", r"\1 is Err", out)
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.get_(Some|Ok|Err)_0\(\)",
        r"\1->\2_0",
        out,
    )
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.unwrap\(\)", r"\1->Some_0", out)
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.unwrap_err\(\)", r"\1->Err_0", out)
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*(Some|Ok|Err)\(([^()]*)\)",
        r"\1 is \2 && \1->\2_0 == \3",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*Err\(\s*\(\s*\)\s*\)",
        r"\1 is Err",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*None\b",
        r"\1 is None",
        out,
    )
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*true\b", r"\1", out)
    out = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*==\s*false\b", r"!\1", out)
    out = re.sub(
        r"!\s*([A-Za-z_][A-Za-z0-9_]*)\.is_empty\(\)",
        r"\1.len() != 0",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_empty\(\)\s*==\s*true\b",
        r"\1.len() == 0",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_empty\(\)\s*==\s*false\b",
        r"\1.len() != 0",
        out,
    )
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\.is_empty\(\)",
        r"\1.len() == 0",
        out,
    )
    out = re.sub(r"\s+as\s+int\b", "", out)
    out = re.sub(
        r"\s+as\s+(?:u8|u16|u32|u64|u128|usize|i8|i16|i32|i64|i128|isize)\b",
        "",
        out,
    )
    out = re.sub(
        r"\bforall\s*\|\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*usize\s*\|",
        r"forall|\1:int|",
        out,
    )
    out = re.sub(
        r"\b0\s*<=\s*([A-Za-z_][A-Za-z0-9_]*)\s*&&\s*\1\s*<\s*([^&=]+)",
        r"0 <= \1 < \2",
        out,
    )
    out = re.sub(
        r"\b([^&=]+?)\s*<=\s*([A-Za-z_][A-Za-z0-9_]*)\s*&&\s*\2\s*<\s*([^&=]+)",
        r"\1 <= \2 < \3",
        out,
    )
    rust_if = re.compile(r"if\s+([^{}]+?)\s*\{\s*([^{}]+?)\s*\}\s*else\s*\{\s*([^{}]+?)\s*\}")
    while True:
        rewritten = rust_if.sub(r"ite(\1, \2, \3)", out)
        if rewritten == out:
            break
        out = rewritten
    return out


def _canonicalize_by_signature(
    expr: str,
    mapping: Dict[str, str],
    pre_state: bool = False,
) -> str:
    if pre_state:
        expr = re.sub(r"\bold\(([^()]+)\)", r"\1", expr)
        expr = re.sub(r"\bfinal\(([^()]+)\)", r"\1", expr)
    expr = _normalize_verus_surface_expr(expr)
    if not mapping:
        return expr
    escaped = sorted((re.escape(k) for k in mapping.keys()), key=len, reverse=True)
    if not escaped:
        return expr
    pattern = re.compile(r"\b(" + "|".join(escaped) + r")\b")
    return _normalize_verus_surface_expr(pattern.sub(lambda m: mapping[m.group(1)], expr))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Constraint Entailment Framework (CEF): evaluate whether generated contract "
            "clauses cover manual ground-truth contract clauses."
        )
    )
    parser.add_argument(
        "--language",
        choices=["c", "java", "rust", "python", "auto"],
        default="auto",
        help="Spec language. auto detects from generated spec JSON fields.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/req2code"),
        help="Pipeline output directory containing specs/ and reports/.",
    )
    parser.add_argument(
        "--specs-dir",
        type=Path,
        default=None,
        help="Optional override for specs directory (default: <output-dir>/specs).",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=None,
        help="Optional report path (default: <output-dir>/reports/cef.json).",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        default=None,
        help="Evaluate one task id only.",
    )
    parser.add_argument(
        "--ground-truth-spec-file",
        type=Path,
        default=Path(
            "benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json"
        ),
        help=(
            "Manual ground-truth contract clauses for requirement coverage evaluation."
        ),
    )
    parser.add_argument(
        "--max-combo-size",
        type=int,
        default=5,
        help="Max number of ACSL clauses conjuncted when searching entailment subsets.",
    )
    parser.add_argument(
        "--max-combination-trials",
        type=int,
        default=2000,
        help="Safety cap for number of clause-subset entailment checks per target.",
    )
    return parser.parse_args()


def _rewrite_implies_call_expr(expr: str) -> str:
    out = expr
    while True:
        starts = [match.start() for match in re.finditer(r"\bImplies\s*\(", out)]
        if not starts:
            return out
        start = starts[-1]
        open_idx = out.find("(", start)
        depth = 0
        close_idx = -1
        comma_idx = -1
        for idx in range(open_idx, len(out)):
            ch = out[idx]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    close_idx = idx
                    break
            elif ch == "," and depth == 1 and comma_idx < 0:
                comma_idx = idx
        if close_idx < 0 or comma_idx < 0:
            return out
        left = out[open_idx + 1 : comma_idx].strip()
        right = out[comma_idx + 1 : close_idx].strip()
        if not left or not right:
            return out
        out = out[:start] + f"({left} ==> {right})" + out[close_idx + 1 :]


def _split_top_level_bool_expr(text: str, operator: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    token = f" {operator} "
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(token, i):
            parts.append(text[start:i].strip())
            start = i + len(token)
            i = start
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _is_type_check_expr_eval(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("isinstance(") and stripped.endswith(")")


def _drop_type_check_conjuncts_eval(text: str) -> str:
    parts = _split_top_level_bool_expr(text, "and")
    if len(parts) <= 1:
        return "1" if _is_type_check_expr_eval(text) else text
    kept = [part for part in parts if not _is_type_check_expr_eval(part)]
    return " and ".join(kept) if kept else "1"


def _sanitize_expr(text: str) -> str:
    expr = text.strip()
    expr = _rewrite_implies_call_expr(expr)
    expr = _drop_type_check_conjuncts_eval(expr)
    expr = re.sub(r"\bResult\s*\(\s*\)", "result", expr)
    expr = re.sub(r"\b(ret|result)\s*\(\s*\)", "result", expr)
    expr = re.sub(r"\bbool_ret\s*\(\s*\)", "bool_ret", expr)
    expr = expr.replace("\\result", "result")
    expr = expr.replace("\\null", "0")
    expr = expr.replace("\\strictly_nothing", "nothing")
    expr = expr.replace("\\nothing", "nothing")
    expr = expr.replace("\\true", "1")
    expr = expr.replace("\\false", "0")
    expr = expr.replace("<==>", "==")
    expr = re.sub(r"\\at\(([^,]+),\s*Pre\)", r"\\old(\1)", expr)
    expr = re.sub(r"\\at\(([^,]+),\s*Post\)", r"\1", expr)
    expr = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\.length\b", r"\1_length", expr)
    expr = re.sub(
        r"\b(Integer|Long|Short|Byte|Character)\.([A-Z_][A-Z0-9_]*)\b",
        r"\1_\2",
        expr,
    )
    expr = re.sub(r"\b[A-Z][A-Za-z0-9_]*Exception\b", "1", expr)
    expr = re.sub(
        r"\bOld\(\s*len\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)",
        r"old_len_\1",
        expr,
    )
    expr = re.sub(
        r"\bOld\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        r"bool_old_member_\1_\2",
        expr,
    )
    expr = re.sub(
        r"\blen\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        r"len_\1",
        expr,
    )
    expr = re.sub(r"\bis\s+not\s+None\b", "!= 0", expr)
    expr = re.sub(r"\bis\s+None\b", "== 0", expr)
    expr = re.sub(r"\bis\b", "==", expr)
    expr = re.sub(r"\bNone\b", "0", expr)
    expr = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+not\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        r"!bool_member_\1_\2",
        expr,
    )
    expr = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s+in\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        r"bool_member_\1_\2",
        expr,
    )
    expr = re.sub(r"\band\b", "&&", expr)
    expr = re.sub(r"\bor\b", "||", expr)
    expr = re.sub(r"\bnot\b", "!", expr)

    def _norm_idx(idx: str) -> str:
        out = re.sub(r"\\result", "result", idx.strip())
        out = re.sub(r"[^A-Za-z0-9_]", "_", out)
        out = re.sub(r"_+", "_", out).strip("_")
        return out or "idx"

    def _norm_atom(atom: str, prefix: str = "") -> str:
        t = atom.strip()
        m = re.fullmatch(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)", t)
        if m:
            return f"{prefix}deref_{m.group(1)}"
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*([^\]]+)\s*\]", t)
        if m:
            arr = m.group(1)
            idx = _norm_idx(m.group(2))
            return f"{prefix}{arr}_{idx}"
        m = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t)
        if m:
            return f"{prefix}{t}"
        t = re.sub(r"[^A-Za-z0-9_]", "_", t)
        t = re.sub(r"_+", "_", t).strip("_")
        return f"{prefix}{t or 'term'}"

    # Handle \old(atom)-style forms before general deref/index rewrites.
    old_pat = re.compile(r"\\old\(([^()]+)\)")
    while True:
        m = old_pat.search(expr)
        if not m:
            break
        expr = expr[: m.start()] + _norm_atom(m.group(1), prefix="old_") + expr[m.end() :]

    old_py_pat = re.compile(r"\bOld\(([^()]+)\)")
    while True:
        m = old_py_pat.search(expr)
        if not m:
            break
        expr = expr[: m.start()] + _norm_atom(m.group(1), prefix="old_") + expr[m.end() :]

    def _replace_unary_deref(src: str) -> str:
        # Replace unary pointer dereference (*p) but keep binary multiplication (a * b).
        # We inspect the previous non-space character before '*' to disambiguate:
        # - unary deref: start of expr, or after delimiters/operators like '(', ',', '&&', '||', etc.
        # - multiplication: typically after identifier/number/')]'.
        pat = re.compile(r"\*\s*([A-Za-z_][A-Za-z0-9_]*)")
        out: List[str] = []
        last = 0
        for m in pat.finditer(src):
            star_idx = m.start()
            prev_non_space: Optional[str] = None
            i = star_idx - 1
            while i >= 0:
                ch = src[i]
                if not ch.isspace():
                    prev_non_space = ch
                    break
                i -= 1

            is_unary = prev_non_space is None or (
                not prev_non_space.isalnum() and prev_non_space not in {"_", ")", "]"}
            )
            out.append(src[last:star_idx])
            if is_unary:
                out.append(f"deref_{m.group(1)}")
            else:
                out.append(m.group(0))
            last = m.end()
        out.append(src[last:])
        return "".join(out)

    expr = _replace_unary_deref(expr)

    def _arr_repl(m: re.Match[str]) -> str:
        arr = m.group(1)
        idx = _norm_idx(m.group(2))
        return f"{arr}_{idx}"

    expr = re.sub(r"([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*([^\]]+)\s*\]", _arr_repl, expr)
    expr = re.sub(r"\\[A-Za-z_][A-Za-z0-9_]*\(([^()]*)\)", r"\1", expr)
    expr = re.sub(r"\\([A-Za-z_][A-Za-z0-9_]*)", r"\1", expr)
    expr = re.sub(r"\s+", " ", expr)
    return expr.strip()


def _normalize_contract_clause_expr(clause_type: str, expr: str) -> str:
    """Normalize syntactic JML forms that are awkward for clause-level matching."""
    kind = clause_type.strip().lower()
    if kind == "signals":
        m = re.match(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+[A-Za-z_][A-Za-z0-9_]*\s*\)\s*(.*)$", expr)
        if m:
            exception_type = m.group(1)
            condition = m.group(2).strip()
            if condition in {"", "true", "\\true"}:
                return exception_type
            return f"{condition} ==> {exception_type}"
    if kind == "signals_only":
        return expr.replace(",", " || ")
    return expr


def _extract_contract_clauses(contract_block: str, language: str = "auto") -> List[Dict[str, str]]:
    body = contract_block
    body = body.replace("/*@", "").replace("*/", "")
    if language == "c":
        keywords = r"requires|ensures|assigns"
    elif language == "java":
        keywords = r"requires|ensures|assignable|assigns|signals_only|signals"
    elif language == "rust":
        keywords = r"requires|ensures"
    else:
        keywords = r"requires|ensures|assignable|assigns|signals_only|signals"

    keyword_re = re.compile(rf"^\s*@?\s*({keywords})\b\s*(.*)$")
    clauses: List[Dict[str, str]] = []
    current_type: Optional[str] = None
    current_parts: List[str] = []

    def clause_terminated(text: str) -> bool:
        semicolon_count = text.count(";")
        binder_count = len(re.findall(r"\\(?:forall|exists)\\s+[^;]+;", text))
        return semicolon_count > binder_count

    for raw_line in body.splitlines():
        line = raw_line.strip()
        line = re.sub(r"//.*$", "", line).strip()
        line = re.sub(r"^\*+\s?", "", line).strip()
        line = re.sub(r"^@\s*", "", line).strip()
        if not line:
            continue
        m = keyword_re.match(line)
        if m:
            if current_type and current_parts:
                expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
                expr = _normalize_contract_clause_expr(current_type, expr)
                clauses.append({"type": current_type, "expr": expr})
            current_type = m.group(1).strip()
            current_parts = [m.group(2).strip()]
        elif current_type:
            current_parts.append(line)

        if current_type and clause_terminated(line):
            expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
            expr = _normalize_contract_clause_expr(current_type, expr)
            clauses.append({"type": current_type, "expr": expr})
            current_type = None
            current_parts = []
    if current_type and current_parts:
        expr = re.sub(r"\s+", " ", " ".join(current_parts)).strip().rstrip(";").strip()
        expr = _normalize_contract_clause_expr(current_type, expr)
        clauses.append({"type": current_type, "expr": expr})

    if clauses:
        return clauses

    pattern = re.compile(rf"(?:^|\n)\s*@?\s*({keywords})\s+(.+?);", re.DOTALL)
    for m in pattern.finditer(body):
        clause_type = m.group(1).strip()
        clause_expr = re.sub(r"\s+", " ", m.group(2)).strip()
        clause_expr = _normalize_contract_clause_expr(clause_type, clause_expr)
        clauses.append({"type": clause_type, "expr": clause_expr})
    return clauses


def _extract_verus_clauses_from_spec(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    """Read Verus clauses from a Rust spec artifact.

    Rust/Verus contracts live in the function signature rather than a standalone
    comment block, so the Rust pipeline stores canonical structured clauses in
    `verus_clauses`. This parser keeps a fallback for older/generated artifacts
    that only provide `verus_contract`.
    """
    raw_clauses = spec.get("verus_clauses")
    clauses: List[Dict[str, str]] = []
    if isinstance(raw_clauses, list):
        for row in raw_clauses:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("type", "")).strip().lower()
            expr = str(row.get("expr", "")).strip().rstrip(",").strip()
            if kind in {"requires", "ensures"} and expr:
                clauses.append({"type": kind, "expr": expr})
    if clauses:
        return clauses

    contract = str(spec.get("verus_contract") or spec.get("contract") or "").strip()
    if contract:
        clauses = _extract_contract_clauses(contract, language="rust")
    return clauses


def _extract_nagini_clauses_from_spec(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    """Read Nagini clauses from a Python spec artifact."""
    raw_clauses = spec.get("nagini_clauses")
    clauses: List[Dict[str, str]] = []
    if isinstance(raw_clauses, list):
        for row in raw_clauses:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("type", "")).strip().lower()
            expr = str(row.get("expr", "")).strip()
            if kind in {"requires", "ensures"} and expr:
                clauses.append({"type": kind, "expr": expr})
    if clauses:
        return clauses

    contract = str(spec.get("nagini_contract") or spec.get("contract") or "").strip()
    for raw in contract.splitlines():
        line = raw.strip()
        match = re.match(r"^(Requires|Ensures)\((.*)\)$", line)
        if match:
            clauses.append(
                {
                    "type": match.group(1).lower(),
                    "expr": match.group(2).strip(),
                }
            )
    return clauses


TOKEN_RE = re.compile(
    r"\s*("
    r"==>|&&|\|\||<=|>=|==|!=|//|[()!<>+\-*/%]"
    r"|,"
    r"|[A-Za-z_][A-Za-z0-9_]*"
    r"|[0-9]+"
    r")"
)


class ExprParser:
    def __init__(self, text: str):
        self.raw = _sanitize_expr(text)
        self.tokens = self._tokenize(self.raw)
        self.idx = 0
        self.vars: Dict[str, Any] = {}

    def _tokenize(self, text: str) -> List[str]:
        out: List[str] = []
        pos = 0
        while pos < len(text):
            m = TOKEN_RE.match(text, pos)
            if not m:
                raise ValueError(f"unsupported token near: {text[pos:pos+30]}")
            out.append(m.group(1))
            pos = m.end()
        return out

    def _peek(self) -> Optional[str]:
        if self.idx >= len(self.tokens):
            return None
        return self.tokens[self.idx]

    def _eat(self, tok: str) -> bool:
        if self._peek() == tok:
            self.idx += 1
            return True
        return False

    def _expect(self, tok: str) -> None:
        if not self._eat(tok):
            raise ValueError(f"expected '{tok}', got '{self._peek()}'")

    def _var(self, name: str):
        if name not in self.vars:
            if name.startswith("bool_"):
                self.vars[name] = Bool(name)
            else:
                self.vars[name] = Int(name)
        return self.vars[name]

    def parse(self):
        node = self._parse_implies()
        if self._peek() is not None:
            raise ValueError(f"unexpected token: {self._peek()}")
        return node

    def _parse_implies(self):
        left = self._parse_or()
        if self._eat("==>"):
            right = self._parse_implies()
            return Or(Not(left), right)
        return left

    def _parse_or(self):
        left = self._parse_and()
        while self._eat("||"):
            right = self._parse_and()
            left = Or(left, right)
        return left

    def _parse_and(self):
        left = self._parse_cmp()
        while self._eat("&&"):
            right = self._parse_cmp()
            left = And(left, right)
        return left

    def _parse_cmp(self):
        left = self._parse_add()
        tok = self._peek()
        if tok in {"==", "!=", "<=", ">=", "<", ">"}:
            self.idx += 1
            right = self._parse_add()
            if tok == "==":
                return left == right
            if tok == "!=":
                return left != right
            if tok == "<=":
                return left <= right
            if tok == ">=":
                return left >= right
            if tok == "<":
                return left < right
            return left > right
        return left

    def _parse_add(self):
        left = self._parse_mul()
        while True:
            if self._eat("+"):
                left = left + self._parse_mul()
            elif self._eat("-"):
                left = left - self._parse_mul()
            else:
                return left

    def _parse_mul(self):
        left = self._parse_unary()
        while True:
            if self._eat("*"):
                left = left * self._parse_unary()
            elif self._eat("//"):
                left = left / self._parse_unary()
            elif self._eat("/"):
                left = left / self._parse_unary()
            elif self._eat("%"):
                left = left % self._parse_unary()
            else:
                return left

    def _parse_unary(self):
        if self._eat("!"):
            return Not(self._parse_unary())
        if self._eat("-"):
            return -self._parse_unary()
        return self._parse_primary()

    def _parse_primary(self):
        tok = self._peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok == "(":
            self.idx += 1
            inner = self._parse_implies()
            self._expect(")")
            return inner
        self.idx += 1
        if tok.isdigit():
            return IntVal(int(tok))
        if tok in {"True", "true"}:
            return BoolVal(True)
        if tok in {"False", "false"}:
            return BoolVal(False)
        if tok == "ite":
            self._expect("(")
            cond = self._parse_implies()
            self._expect(",")
            then_expr = self._parse_implies()
            self._expect(",")
            else_expr = self._parse_implies()
            self._expect(")")
            return If(cond, then_expr, else_expr)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tok):
            return self._var(tok)
        raise ValueError(f"invalid primary token: {tok}")


def _is_bool_expr(expr: Any) -> bool:
    return isinstance(expr, BoolRef)


def _normalize_commutative_equality_text(text: str) -> str:
    atom = (
        r"(?:\\result|\\old\([^()]+\)|"
        r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?)"
    )
    pattern = re.compile(rf"({atom})\s*(==|!=)\s*({atom})")

    def reorder(match: re.Match[str]) -> str:
        left = re.sub(r"\s+", "", match.group(1))
        right = re.sub(r"\s+", "", match.group(3))
        if right < left:
            left, right = right, left
        return f"{left}{match.group(2)}{right}"

    return pattern.sub(reorder, text)


def _normalize_logic_text(text: str) -> str:
    text = text.replace("\\result", "result")
    text = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\s*:\s*(?=result|\\forall|\\exists)", "", text)
    # Normalize C/ACSL chained comparisons so `0 <= x < n` and
    # `0 <= x && x < n` have the same entailment representation.
    chain = re.fullmatch(r"\s*([^&|;]+?)\s*(<=|<|>=|>)\s*([^&|;]+?)\s*(<=|<|>=|>)\s*([^&|;]+?)\s*", text)
    if chain:
        left, op1, middle, op2, right = chain.groups()
        text = f"({left} {op1} {middle}) && ({middle} {op2} {right})"
    quantified = re.match(
        r"^(\s*\(?\s*\\(?:forall|exists)\s+(?:int|integer)\s+)"
        r"([A-Za-z_][A-Za-z0-9_]*)(\s*;[\s\S]*)$",
        text,
    )
    if quantified:
        body = re.sub(
            rf"\b{re.escape(quantified.group(2))}\b",
            "__bound0",
            quantified.group(3),
        )
        text = quantified.group(1) + "__bound0" + body
    if text.count("==") == 1:
        lhs, rhs = text.split("==", 1)
        atom = r"(?:[A-Za-z_][A-Za-z0-9_]*|[-+]?\d+)"
        if re.fullmatch(rf"\s*{atom}\s*", lhs) and re.fullmatch(rf"\s*{atom}\s*", rhs):
            text = _normalize_commutative_equality_text(text)
    expr = _sanitize_expr(_normalize_verus_surface_expr(text))
    expr = re.sub(r"\s+", "", expr.lower())
    while re.search(r"\(([^()]+)\)", expr):
        expr = re.sub(r"\(([^()]+)\)", r"\1", expr)
    return expr


def _is_java_ground_truth(args: argparse.Namespace) -> bool:
    if args.language == "java":
        return True
    return "java-problems" in str(args.ground_truth_spec_file)


def _is_missing_spec_denominator_ground_truth(args: argparse.Namespace) -> bool:
    return True


def _empty_ground_truth_result(
    gt_row: Dict[str, Any],
    status: str,
    spec_file: Path,
    ground_truth_file: Path,
) -> Dict[str, Any]:
    gt_clauses = gt_row.get("ground_truth_clauses", [])
    if not isinstance(gt_clauses, list):
        gt_clauses = []

    gt_total = 0
    pre_total = 0
    post_frame_total = 0
    for gt_clause in gt_clauses:
        target_expr = str(gt_clause.get("expr", "")).strip()
        target_type = str(gt_clause.get("type", "")).strip()
        if not target_expr:
            continue
        gt_total += 1
        kind_norm = _normalize_kind(target_type)
        if kind_norm in REQUIRES_KINDS:
            pre_total += 1
        elif kind_norm in POST_KINDS or kind_norm in FRAME_KINDS or kind_norm in EXCEPTION_KINDS:
            post_frame_total += 1

    return {
        "id": int(gt_row["id"]),
        "path": str(gt_row["path"]),
        "spec_file": str(spec_file),
        "ground_truth_file": str(ground_truth_file),
        "status": status,
        "ground_truth_total": gt_total,
        "ground_truth_matched": 0,
        "ground_truth_coverage": 0.0,
        "pre_total": pre_total,
        "pre_matched": 0,
        "pre_admissibility": 0.0,
        "pre_overconstraint": 1.0 if pre_total > 0 else 0.0,
        "post_frame_total": post_frame_total,
        "post_frame_matched": 0,
        "post_frame_coverage": 0.0,
        "target_matches": [],
        "requirement_coverage_x": 0,
        "requirement_coverage_n": gt_total,
        "requirement_coverage_ratio": 0.0,
    }


def _split_top_level_and(text: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif i + 1 < len(text) and text[i : i + 2] == "&&" and depth == 0:
            parts.append(text[start:i].strip())
            start = i + 2
            i += 1
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _split_top_level_source_and(text: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    token = " and "
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(token, i):
            parts.append(text[start:i].strip())
            start = i + len(token)
            i = start
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _expand_candidate_clause(clause: Dict[str, str]) -> List[Dict[str, str]]:
    expr = str(clause.get("expr", "")).strip()
    kind = str(clause.get("type", "")).strip()
    if not expr:
        return []
    rust_match = re.fullmatch(
        r"match\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{([\s\S]*)\}",
        expr,
    )
    if rust_match:
        subject = rust_match.group(1)
        arms: List[str] = []
        start = 0
        paren = bracket = brace = angle = 0
        body = rust_match.group(2)
        for idx, char in enumerate(body):
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
            elif char == "<" and idx >= 2 and body[idx - 2 : idx] == "::":
                angle += 1
            elif char == ">" and angle:
                angle -= 1
            elif char == "," and paren == bracket == brace == angle == 0:
                if body[start:idx].strip():
                    arms.append(body[start:idx].strip())
                start = idx + 1
        if body[start:].strip():
            arms.append(body[start:].strip())

        expanded_match: List[Dict[str, str]] = []
        seen_variants: set[str] = set()
        wildcard_bodies: List[str] = []
        for arm in arms:
            arm_match = re.fullmatch(r"(.+?)\s*=>\s*([\s\S]+)", arm)
            if not arm_match:
                continue
            pattern = arm_match.group(1).strip()
            arm_expr = arm_match.group(2).strip()
            variant_match = re.fullmatch(
                r"(?:(?:Option|Result)::)?(Some|None|Ok|Err)(?:\(([^)]*)\))?",
                pattern,
            )
            if pattern == "_":
                wildcard_bodies.append(arm_expr)
                continue
            if not variant_match:
                continue
            variant = variant_match.group(1)
            seen_variants.add(variant)
            binder = str(variant_match.group(2) or "").strip()
            if binder and binder != "_":
                arm_expr = re.sub(
                    rf"\b{re.escape(binder)}\b",
                    f"{subject}->{variant}_0",
                    arm_expr,
                )
            expanded_match.append(
                {"type": kind, "expr": f"{subject} is {variant} ==> {arm_expr}"}
            )
        complement = {"Some": "None", "None": "Some", "Ok": "Err", "Err": "Ok"}
        if len(seen_variants) == 1:
            other = complement[next(iter(seen_variants))]
            expanded_match.extend(
                {"type": kind, "expr": f"{subject} is {other} ==> {arm_expr}"}
                for arm_expr in wildcard_bodies
            )
        if expanded_match:
            expanded_match.append({"type": kind, "expr": expr})
            return expanded_match

    parts = _split_top_level_and(expr)
    if len(parts) <= 1:
        parts = _split_top_level_source_and(expr)
    if len(parts) <= 1:
        return [{"type": kind, "expr": expr}]
    expanded = [{"type": kind, "expr": part} for part in parts]
    expanded.append({"type": kind, "expr": expr})
    return expanded


def _try_parse(expr: str) -> Tuple[Optional[Any], Optional[str]]:
    try:
        parser = ExprParser(expr)
        ast_expr = parser.parse()
        return ast_expr, None
    except Exception as exc:
        return None, str(exc)


def _entails(lhs_expr: str, rhs_expr: str) -> Tuple[bool, str]:
    lhs_norm = _normalize_logic_text(lhs_expr)
    rhs_norm = _normalize_logic_text(rhs_expr)
    if lhs_norm == rhs_norm:
        return True, "exact_match"
    for conj in _split_top_level_and(lhs_expr):
        if _normalize_logic_text(conj) == rhs_norm:
            return True, "matched_conjunct"

    if not HAS_Z3:
        return False, "z3_unavailable"

    lhs_ast, lhs_err = _try_parse(_normalize_logic_text(lhs_expr))
    rhs_ast, rhs_err = _try_parse(_normalize_logic_text(rhs_expr))
    if lhs_ast is None or rhs_ast is None:
        err = f"parse_failed(lhs={lhs_err}, rhs={rhs_err})"
        return False, err
    if not _is_bool_expr(lhs_ast) or not _is_bool_expr(rhs_ast):
        return False, "non_boolean_expression"

    solver = Solver()
    solver.add(And(lhs_ast, Not(rhs_ast)))
    result = solver.check()
    if result == unsat:
        return True, "smt_unsat"
    return False, "smt_sat_or_unknown"


def _strip_outer_parens(text: str) -> str:
    out = text.strip()
    while out.startswith("(") and out.endswith(")"):
        depth = 0
        wraps_all = True
        for idx, char in enumerate(out):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and idx != len(out) - 1:
                    wraps_all = False
                    break
        if not wraps_all or depth != 0:
            break
        out = out[1:-1].strip()
    return out


def _split_top_level_token(text: str, token: str) -> List[str]:
    parts: List[str] = []
    start = 0
    paren = bracket = brace = 0
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
        elif paren == bracket == brace == 0 and text.startswith(token, idx):
            parts.append(text[start:idx].strip())
            start = idx + len(token)
            idx = start
            continue
        idx += 1
    parts.append(text[start:].strip())
    return [part for part in parts if part]


def _normalize_rust_guard(text: str) -> str:
    out = _strip_outer_parens(_normalize_verus_surface_expr(text))
    out = re.sub(r"!\s*\(\s*(.+?)\s*==\s*0\s*\)", r"\1 != 0", out)
    out = re.sub(r"!\s*\(\s*(.+?)\s*>\s*([0-9]+)\s*\)", r"\1 <= \2", out)
    out = re.sub(r"!\s*\(\s*(.+?)\s*>=\s*([0-9]+)\s*\)", r"\1 < \2", out)
    out = re.sub(r"!\s*\(\s*(.+?)\s*<\s*([0-9]+)\s*\)", r"\1 >= \2", out)
    out = re.sub(r"!\s*\(\s*(.+?)\s*<=\s*([0-9]+)\s*\)", r"\1 > \2", out)
    return re.sub(r"\s+", "", out).lower()


def _normalize_rust_fact(text: str) -> str:
    out = _strip_outer_parens(_normalize_verus_surface_expr(text))
    return re.sub(r"\s+", "", out).lower()


def _split_rust_implication(text: str) -> tuple[str, str]:
    stripped = _strip_outer_parens(text)
    if stripped.startswith(("forall|", "exists|")):
        return "", stripped
    parts = _split_top_level_token(stripped, "==>")
    if len(parts) >= 2:
        return parts[0], " ==> ".join(parts[1:])
    return "", stripped


def _split_ite_expression(text: str) -> Optional[tuple[str, str, str]]:
    stripped = _strip_outer_parens(text)
    if not stripped.startswith("ite(") or not stripped.endswith(")"):
        return None
    parts = _split_top_level_token(stripped[4:-1], ",")
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def _rust_guarded_facts(
    clauses: List[Dict[str, str]],
) -> List[tuple[str, str, int]]:
    facts: List[tuple[str, str, int]] = []
    for index, clause in enumerate(clauses):
        expression = str(clause.get("expr_eval", clause.get("expr", ""))).strip()
        ite = _split_ite_expression(expression)
        guarded_expressions: List[tuple[str, str]]
        if ite:
            condition, then_expr, else_expr = ite
            guarded_expressions = [(condition, then_expr), (f"!({condition})", else_expr)]
        else:
            guard, consequent = _split_rust_implication(expression)
            guarded_expressions = [(guard, consequent)]
        for guard, consequent in guarded_expressions:
            atoms = (
                [consequent]
                if _strip_outer_parens(consequent).startswith(("forall|", "exists|"))
                else _split_top_level_token(consequent, "&&")
            )
            for atom in atoms:
                normalized_atom = _normalize_verus_surface_expr(atom)
                constructor = re.fullmatch(
                    r"([A-Za-z_][A-Za-z0-9_]*)\s*==\s*(Some|Ok|Err)\(([\s\S]*)\)",
                    normalized_atom,
                )
                expanded_atoms = [normalized_atom]
                if constructor:
                    subject, variant, payload = constructor.groups()
                    expanded_atoms = [f"{subject} is {variant}"]
                    if payload.strip() != "()":
                        expanded_atoms.append(
                            f"{subject}->{variant}_0 == {payload.strip()}"
                        )
                for expanded_atom in expanded_atoms:
                    facts.append(
                        (
                            _normalize_rust_guard(guard),
                            _normalize_rust_fact(expanded_atom),
                            index,
                        )
                    )
    return facts


def _rust_frame_fact(
    facts: set[str],
    post: str,
    bound: str,
    excluded_index: Optional[str] = None,
) -> bool:
    for fact in facts:
        match = re.fullmatch(r"forall\|([a-z_][a-z0-9_]*):int\|(.+)", fact)
        if not match:
            continue
        variable = match.group(1)
        body = match.group(2)
        if f"0<={variable}<{bound}" not in body:
            continue
        if f"{post}[{variable}]==old({post})[{variable}]" not in body:
            continue
        if excluded_index is not None and f"{variable}!={excluded_index}" not in body:
            continue
        return True
    return False


def _rust_sequence_fact_supported(
    target: str,
    facts: set[str],
    guard: str,
) -> bool:
    update = re.fullmatch(
        r"(arg[0-9]+)==old\(\1\)\.update\(([^,]+),(.+)\)",
        target,
    )
    if update:
        post, index, value = update.groups()
        return (
            f"{post}.len()==old({post}).len()" in facts
            and f"{post}[{index}]=={value}" in facts
            and _rust_frame_fact(facts, post, f"{post}.len()", excluded_index=index)
        )

    push = re.fullmatch(r"(arg[0-9]+)==old\(\1\)((?:\.push\([^()]*\))+)", target)
    if push:
        post, suffix = push.groups()
        values = re.findall(r"\.push\(([^()]*)\)", suffix)
        if len(values) == 1 and f"old({post}).len()==0" in guard:
            if f"{post}==seq![{values[0]}]" in facts:
                return True
        length_suffix = "" if not values else f"+{len(values)}"
        if f"{post}.len()==old({post}).len(){length_suffix}" not in facts:
            return False
        for offset, value in enumerate(values):
            position = f"old({post}).len()" + (f"+{offset}" if offset else "")
            if f"{post}[{position}]=={value}" not in facts:
                return False
        return _rust_frame_fact(facts, post, f"old({post}).len()")

    subrange = re.fullmatch(
        r"(arg[0-9]+)==old\(\1\)\.(?:subrange\(0,old\(\1\)\.len\(\)-1\)|drop_last\(\))",
        target,
    )
    if subrange:
        post = subrange.group(1)
        return (
            f"{post}.len()==old({post}).len()-1" in facts
            and _rust_frame_fact(facts, post, f"{post}.len()")
        )

    unchanged = re.fullmatch(r"(arg[0-9]+)==old\(\1\)", target)
    if unchanged:
        post = unchanged.group(1)
        if target in facts:
            return True
        return (
            f"{post}.len()==old({post}).len()" in facts
            and _rust_frame_fact(facts, post, f"old({post}).len()")
        )
    return False


def _match_rust_semantic_clause(
    target_expr: str,
    clauses: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    target_guard_raw, target_consequent = _split_rust_implication(target_expr)
    target_guard = _normalize_rust_guard(target_guard_raw)
    target_atoms = [
        _normalize_rust_fact(atom)
        for atom in _split_top_level_token(target_consequent, "&&")
    ]
    guarded_facts = _rust_guarded_facts(clauses)
    matching_rows = [row for row in guarded_facts if row[0] == target_guard]
    if not matching_rows:
        return None
    facts = {row[1] for row in matching_rows}
    for atom in target_atoms:
        if atom in facts:
            continue
        if not _rust_sequence_fact_supported(atom, facts, target_guard):
            return None
    indices = sorted({row[2] for row in matching_rows})
    return {
        "matched": True,
        "reason": "rust_guarded_sequence_entailment",
        "matched_clause_expr": " && ".join(clauses[idx]["expr"] for idx in indices),
        "matched_clause_expr_eval": " && ".join(
            clauses[idx].get("expr_eval", clauses[idx]["expr"]) for idx in indices
        ),
        "matched_clause_type": f"rust_semantic_combo[{','.join(str(idx) for idx in indices)}]",
        "matched_clause_indices": indices,
        "combination_size": len(indices),
        "trials": 1,
        "entailment_direction": "spec_entails_req",
        "entailment_lhs": " && ".join(sorted(facts)),
        "entailment_rhs": target_expr,
    }


def _find_entailing_subset(
    clauses: List[Dict[str, str]],
    target_expr: str,
    direction: str,
    max_combo_size: int,
    max_combination_trials: int,
) -> Dict[str, Any]:
    if not clauses:
        return {
            "matched": False,
            "reason": "no_entailing_clause",
            "matched_clause_expr": "",
            "matched_clause_expr_eval": "",
            "matched_clause_type": "",
            "matched_clause_indices": [],
            "combination_size": 0,
            "trials": 0,
        }

    n = len(clauses)
    max_k = max(1, min(max_combo_size, n))
    trials = 0
    best_reason = "no_entailing_clause"
    best_expr = ""
    best_expr_eval = ""

    for k in range(1, max_k + 1):
        for idxs in itertools.combinations(range(n), k):
            trials += 1
            if trials > max_combination_trials:
                return {
                    "matched": False,
                    "reason": f"combination_budget_exceeded({max_combination_trials})",
                    "matched_clause_expr": "",
                    "matched_clause_expr_eval": "",
                    "matched_clause_type": "",
                    "matched_clause_indices": [],
                    "combination_size": 0,
                    "trials": trials - 1,
                }

            exprs = [clauses[i]["expr"] for i in idxs]
            exprs_eval = [clauses[i].get("expr_eval", clauses[i]["expr"]) for i in idxs]
            if k == 1:
                combo_expr = exprs[0]
                combo_expr_eval = exprs_eval[0]
            else:
                combo_expr = " && ".join(f"({e})" for e in exprs)
                combo_expr_eval = " && ".join(f"({e})" for e in exprs_eval)

            if direction == "req_entails_spec":
                lhs_expr = target_expr
                rhs_expr = combo_expr_eval
            else:
                lhs_expr = combo_expr_eval
                rhs_expr = target_expr
            ok, reason = _entails(lhs_expr, rhs_expr)
            if ok:
                return {
                    "matched": True,
                    "reason": reason,
                    "matched_clause_expr": combo_expr,
                    "matched_clause_type": (
                        clauses[idxs[0]]["type"]
                        if k == 1
                        else f"combo[{','.join(str(i) for i in idxs)}]"
                    ),
                    "matched_clause_indices": list(idxs),
                    "combination_size": k,
                    "trials": trials,
                    "entailment_direction": direction,
                    "entailment_lhs": lhs_expr,
                    "entailment_rhs": rhs_expr,
                    "matched_clause_expr_eval": combo_expr_eval,
                }

            if best_reason == "no_entailing_clause":
                best_reason = reason
                best_expr = combo_expr
                best_expr_eval = combo_expr_eval

    return {
        "matched": False,
        "reason": best_reason,
        "matched_clause_expr": best_expr,
        "matched_clause_expr_eval": best_expr_eval,
        "matched_clause_type": "",
        "matched_clause_indices": [],
        "combination_size": 0,
        "trials": trials,
        "entailment_direction": direction,
        "entailment_lhs": "",
        "entailment_rhs": "",
    }


def _match_exception_clause(
    target_expr: str,
    candidate_clauses: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    exception_names = set(re.findall(r"\b[A-Z][A-Za-z0-9_]*Exception\b", target_expr))
    if not exception_names:
        return None
    for idx, clause in enumerate(candidate_clauses):
        expr = clause.get("expr", "")
        if any(name in expr for name in exception_names):
            return {
                "matched": True,
                "reason": "matched_exception_type",
                "matched_clause_expr": expr,
                "matched_clause_expr_eval": clause.get("expr_eval", expr),
                "matched_clause_type": clause.get("type", ""),
                "matched_clause_indices": [idx],
                "combination_size": 1,
                "trials": 1,
                "entailment_direction": "spec_entails_req",
                "entailment_lhs": expr,
                "entailment_rhs": target_expr,
            }
    return None


def _load_ground_truth_specs(path: Path) -> Dict[int, Dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("ground-truth spec file must be a JSON array")
    out: Dict[int, Dict[str, Any]] = {}
    for row in data:
        try:
            rid = int(row.get("id"))
        except Exception:
            continue
        out[rid] = row
    return out


def _get_spec_file(specs_dir: Path, rel_path: str) -> Path:
    return specs_dir / Path(rel_path).with_suffix(".json")


def _build_summary(
    results: List[Dict[str, Any]],
    has_z3: bool,
    include_non_ok_ground_truth: bool = False,
) -> Dict[str, Any]:
    ok_items = [r for r in results if r.get("status") == "ok"]
    coverage_items = results if include_non_ok_ground_truth else ok_items
    total = len(results)
    evaluated = len(ok_items)
    missing_specs = sum(1 for r in results if r.get("status") == "missing_spec")
    errors = sum(1 for r in results if r.get("status") == "error")
    gt_total = sum(int(r.get("ground_truth_total", 0)) for r in coverage_items)
    gt_matched = sum(int(r.get("ground_truth_matched", 0)) for r in coverage_items)
    gt_coverage = (gt_matched / gt_total) if gt_total > 0 else 0.0
    pre_total = sum(int(r.get("pre_total", 0)) for r in coverage_items)
    pre_matched = sum(int(r.get("pre_matched", 0)) for r in coverage_items)
    pre_admissibility = (pre_matched / pre_total) if pre_total > 0 else 0.0
    pre_overconstraint = 1.0 - pre_admissibility if pre_total > 0 else 0.0
    post_frame_total = sum(int(r.get("post_frame_total", 0)) for r in coverage_items)
    post_frame_matched = sum(int(r.get("post_frame_matched", 0)) for r in coverage_items)
    post_frame_coverage = (
        post_frame_matched / post_frame_total if post_frame_total > 0 else 0.0
    )
    macro_avg_requirement_coverage = (
        sum(float(r.get("ground_truth_coverage", 0.0)) for r in coverage_items)
        / len(coverage_items)
        if coverage_items
        else 0.0
    )
    return {
        "method": "manual_ground_truth_spec_entailment_v4_rust_semantic",
        "solver": "z3" if has_z3 else "none",
        "total_expected": total,
        "evaluated": evaluated,
        "missing_specs": missing_specs,
        "errors": errors,
        "ground_truth_spec_clauses_total": gt_total,
        "ground_truth_spec_clauses_matched": gt_matched,
        "ground_truth_spec_micro_coverage": gt_coverage,
        "pre_total": pre_total,
        "pre_matched": pre_matched,
        "pre_admissibility": pre_admissibility,
        "pre_overconstraint": pre_overconstraint,
        "post_frame_total": post_frame_total,
        "post_frame_matched": post_frame_matched,
        "post_frame_coverage": post_frame_coverage,
        "macro_avg_requirement_coverage": macro_avg_requirement_coverage,
    }


def main() -> None:
    args = parse_args()
    specs_dir = args.specs_dir or (args.output_dir / "specs")
    report_file = args.report_file or (args.output_dir / "reports" / "cef.json")
    report_file.parent.mkdir(parents=True, exist_ok=True)

    ground_truth_file = args.ground_truth_spec_file
    ground_truth_map = _load_ground_truth_specs(ground_truth_file)
    if not ground_truth_map:
        raise SystemExit(f"no ground-truth specs found in {ground_truth_file}")

    dataset = [ground_truth_map[rid] for rid in sorted(ground_truth_map)]

    if args.task_id is not None:
        dataset = [row for row in dataset if int(row.get("id", -1)) == args.task_id]
        if not dataset:
            raise SystemExit(f"task id {args.task_id} not found in {ground_truth_file}")

    results: List[Dict[str, Any]] = []
    include_missing_ground_truth = _is_missing_spec_denominator_ground_truth(args)
    for idx, gt_row in enumerate(dataset, start=1):
        rid = int(gt_row["id"])
        rel_path = str(gt_row["path"])
        spec_file = _get_spec_file(specs_dir, rel_path)
        result: Dict[str, Any] = {
            "id": rid,
            "path": rel_path,
            "spec_file": str(spec_file),
            "ground_truth_file": str(ground_truth_file),
        }
        print(f"[TASK {idx}/{len(dataset)}] id={rid} path={rel_path}")

        if not spec_file.exists():
            if include_missing_ground_truth:
                result = _empty_ground_truth_result(
                    gt_row=gt_row,
                    status="missing_spec",
                    spec_file=spec_file,
                    ground_truth_file=ground_truth_file,
                )
            else:
                result["status"] = "missing_spec"
            results.append(result)
            print(f"[TASK {idx}/{len(dataset)}] status=missing_spec")
            continue

        try:
            spec = json.loads(spec_file.read_text())
            oracle_contract_mode = bool(
                spec.get("task_type") == "code_only_oracle_contract"
                or spec.get("code_only_contract")
            )
            spec_language = args.language
            if spec_language == "auto":
                spec_language = str(spec.get("language") or "").strip().lower() or "c"
            if spec_language == "rust":
                clauses_raw = _extract_verus_clauses_from_spec(spec)
            elif spec_language == "python":
                clauses_raw = _extract_nagini_clauses_from_spec(spec)
            else:
                contract_block = str(spec.get("jml_block") or spec.get("acsl_block") or "").strip()
                if not contract_block:
                    raise ValueError("contract block missing in spec file")
                clauses_raw = _extract_contract_clauses(contract_block, language=spec_language)
            if not clauses_raw:
                raise ValueError("contract clauses missing in spec file")

            gt_signature = str(gt_row.get("function_signature", "")).strip()
            spec_signature = str(spec.get("function_signature", "")).strip() or gt_signature
            if spec_language == "rust":
                raw_return_name = _extract_raw_rust_return_name(spec)
                gt_param_map = _build_rust_canonical_map(gt_signature)
                spec_param_map = _build_rust_canonical_map(
                    spec_signature,
                    extra_return_names=[raw_return_name] if raw_return_name else None,
                )
                canonicalization_basis = (
                    "rust_function_signature_parameter_position_and_return_alias"
                )
            elif spec_language == "python":
                gt_param_map = _build_python_canonical_map(gt_signature)
                spec_param_map = _build_python_canonical_map(spec_signature)
                canonicalization_basis = (
                    "python_function_signature_parameter_position_and_result_alias"
                )
            elif spec_language == "java":
                gt_param_map = _build_java_canonical_map(gt_signature)
                spec_param_map = _build_java_canonical_map(spec_signature)
                canonicalization_basis = (
                    "java_function_signature_parameter_position_and_result_type"
                )
            else:
                gt_param_map = _build_param_canonical_map(gt_signature)
                spec_param_map = _build_param_canonical_map(spec_signature)
                canonicalization_basis = "function_signature_parameter_position"

            java_getter_aliases = (
                _extract_java_getter_aliases(
                    str(spec.get("helper_declarations") or "")
                )
                if spec_language == "java"
                else {}
            )

            clauses: List[Dict[str, str]] = []
            seen_clause_keys: set[tuple[str, str]] = set()
            for clause in clauses_raw:
                for expanded_clause in _expand_candidate_clause(clause):
                    clause_type = str(expanded_clause.get("type", "")).strip()
                    clause_expr = str(expanded_clause.get("expr", "")).strip()
                    key = (clause_type, re.sub(r"\s+", "", clause_expr))
                    if key in seen_clause_keys:
                        continue
                    seen_clause_keys.add(key)
                    clause_expr_eval = _canonicalize_by_signature(
                        clause_expr,
                        spec_param_map,
                        pre_state=(clause_type == "requires"),
                    )
                    if spec_language == "java":
                        clause_expr_eval = _normalize_java_surface_expr(
                            clause_expr_eval,
                            getter_aliases=java_getter_aliases,
                        )
                    clauses.append(
                        {
                            "type": clause_type,
                            "expr": clause_expr,
                            "expr_eval": clause_expr_eval,
                        }
                    )

            gt_clauses = gt_row.get("ground_truth_clauses", [])
            if not isinstance(gt_clauses, list):
                raise ValueError("ground_truth_clauses must be a list")

            target_matches: List[Dict[str, Any]] = []
            gt_total = 0
            gt_matched = 0
            pre_total = 0
            pre_matched = 0
            post_frame_total = 0
            post_frame_matched = 0

            for gt_clause in gt_clauses:
                target_expr = str(gt_clause.get("expr", "")).strip()
                target_type = str(gt_clause.get("type", "")).strip()
                if not target_expr:
                    continue

                kind_norm = _normalize_kind(target_type)
                direction = _entailment_direction_for_kind(kind_norm)
                if oracle_contract_mode and kind_norm in REQUIRES_KINDS:
                    # Oracle contracts may add verifier-safety preconditions
                    # (overflow, validity, termination).  For code-only
                    # semantic coverage, require the oracle to imply the
                    # manual target instead of penalizing these auxiliaries.
                    direction = "spec_entails_req"
                candidate_types = _candidate_clause_types_for_kind(kind_norm)
                target_expr_eval = _canonicalize_by_signature(
                    target_expr,
                    gt_param_map,
                    pre_state=(kind_norm in REQUIRES_KINDS),
                )
                if spec_language == "java":
                    target_expr_eval = _normalize_java_surface_expr(target_expr_eval)
                candidate_clauses = [c for c in clauses if c.get("type") in candidate_types]

                gt_total += 1
                if kind_norm in REQUIRES_KINDS:
                    pre_total += 1
                elif kind_norm in POST_KINDS or kind_norm in FRAME_KINDS or kind_norm in EXCEPTION_KINDS:
                    post_frame_total += 1

                match: Dict[str, Any] = {
                    "ground_truth_clause_type": target_type,
                    "ground_truth_clause_expr": target_expr,
                    "ground_truth_clause_eval": target_expr_eval,
                    "entailment_direction": direction,
                    "candidate_clause_types": sorted(candidate_types),
                    "candidate_clause_count": len(candidate_clauses),
                    "matched": False,
                }
                if not candidate_clauses:
                    match["reason"] = "no_candidate_clause_type"
                    target_matches.append(match)
                    continue

                search = None
                if kind_norm in EXCEPTION_KINDS:
                    search = _match_exception_clause(target_expr, candidate_clauses)
                if search is None:
                    search = _find_entailing_subset(
                        clauses=candidate_clauses,
                        target_expr=target_expr_eval,
                        direction=direction,
                        max_combo_size=args.max_combo_size,
                        max_combination_trials=args.max_combination_trials,
                    )
                if (
                    not search["matched"]
                    and spec_language == "rust"
                    and direction == "spec_entails_req"
                ):
                    semantic_search = _match_rust_semantic_clause(
                        target_expr_eval,
                        candidate_clauses,
                    )
                    if semantic_search is not None:
                        search = semantic_search
                match["entailment_trials"] = int(search["trials"])
                if search["matched"]:
                    match["matched"] = True
                    match["matched_clause"] = search["matched_clause_expr"]
                    match["matched_clause_type"] = search["matched_clause_type"]
                    match["matched_clause_indices"] = search["matched_clause_indices"]
                    match["combination_size"] = int(search["combination_size"])
                    match["reason"] = str(search["reason"])
                    match["matched_clause_eval"] = search.get("matched_clause_expr_eval", "")
                    match["entailment_lhs"] = search.get("entailment_lhs", "")
                    match["entailment_rhs"] = search.get("entailment_rhs", "")
                    gt_matched += 1
                    if kind_norm in REQUIRES_KINDS:
                        pre_matched += 1
                    elif kind_norm in POST_KINDS or kind_norm in FRAME_KINDS or kind_norm in EXCEPTION_KINDS:
                        post_frame_matched += 1
                else:
                    match["reason"] = str(search["reason"])
                    match["closest_clause_eval"] = search.get("matched_clause_expr_eval", "")
                    if search["matched_clause_expr"]:
                        match["closest_clause"] = search["matched_clause_expr"]
                target_matches.append(match)

            ground_truth_coverage = (gt_matched / gt_total) if gt_total > 0 else 0.0
            pre_admissibility = (pre_matched / pre_total) if pre_total > 0 else 0.0
            pre_overconstraint = 1.0 - pre_admissibility if pre_total > 0 else 0.0
            post_frame_coverage = (
                post_frame_matched / post_frame_total if post_frame_total > 0 else 0.0
            )

            result.update(
                {
                    "status": "ok",
                    "language": spec_language,
                    "n_contract_clauses": len(clauses),
                    "contract_clauses": clauses,
                    "n_acsl_clauses": len(clauses),
                    "acsl_clauses": clauses,
                    "ground_truth_total": gt_total,
                    "ground_truth_matched": gt_matched,
                    "ground_truth_coverage": ground_truth_coverage,
                    "pre_total": pre_total,
                    "pre_matched": pre_matched,
                    "pre_admissibility": pre_admissibility,
                    "pre_overconstraint": pre_overconstraint,
                    "post_frame_total": post_frame_total,
                    "post_frame_matched": post_frame_matched,
                    "post_frame_coverage": post_frame_coverage,
                    "canonicalization": {
                        "enabled": True,
                        "basis": canonicalization_basis,
                        "ground_truth_signature": gt_signature,
                        "spec_signature": spec_signature,
                        "ground_truth_param_map": gt_param_map,
                        "spec_param_map": spec_param_map,
                        "spec_raw_return_name": (
                            raw_return_name if spec_language == "rust" else None
                        ),
                    },
                    "target_matches": target_matches,
                    "requirement_coverage_x": gt_matched,
                    "requirement_coverage_n": gt_total,
                    "requirement_coverage_ratio": ground_truth_coverage,
                }
            )
            print(
                f"[TASK {idx}/{len(dataset)}] status=ok "
                f"ground_truth={gt_matched}/{gt_total} "
                f"pre={pre_matched}/{pre_total} "
                f"post_frame={post_frame_matched}/{post_frame_total} "
                f"coverage={ground_truth_coverage:.3f}"
            )
        except Exception as exc:
            if include_missing_ground_truth:
                result = _empty_ground_truth_result(
                    gt_row=gt_row,
                    status="error",
                    spec_file=spec_file,
                    ground_truth_file=ground_truth_file,
                )
                result["error"] = str(exc)
            else:
                result["status"] = "error"
                result["error"] = str(exc)
            print(f"[TASK {idx}/{len(dataset)}] status=error error={exc}")
        results.append(result)

    report = {
        "summary": _build_summary(
            results,
            has_z3=HAS_Z3,
            include_non_ok_ground_truth=include_missing_ground_truth,
        ),
        "results": results,
    }
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[INFO] report={report_file}")


if __name__ == "__main__":
    main()
