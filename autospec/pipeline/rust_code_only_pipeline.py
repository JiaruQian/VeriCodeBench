"""Frozen-contract utilities for the Rust/Verus code-only benchmark."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .rust_requirement_pipeline import (
    _build_verus_contract,
    _enforce_rust_contract,
)


IMPLEMENTATION_ANNOTATION = re.compile(
    r"(?m)^\s*(?:invariant|decreases|assert|assume|proof\s+fn|spec\s+fn)\b|\bghost\b"
)


@dataclass(frozen=True)
class RustCodeOnlyItem:
    id: int
    path: str
    requirement: str
    function_signature: str
    code_only_contract: str
    verus_clauses: list[dict[str, str]]
    provenance: dict[str, Any]


def normalize_contract(text: str) -> str:
    return " ".join(text.strip().split())


def contract_hash(text: str) -> str:
    return hashlib.sha256(normalize_contract(text).encode()).hexdigest()


def _function_name(signature: str) -> str:
    match = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", signature)
    if not match:
        raise ValueError(f"cannot parse Rust function signature: {signature}")
    return match.group(1)


def _target_header_span(source: str, function_name: str) -> tuple[int, int]:
    masked = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", lambda match: " " * len(match.group(0)), source)
    declarations = list(
        re.finditer(
            rf"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+{re.escape(function_name)}\b",
            masked,
        )
    )
    if len(declarations) != 1:
        raise ValueError(
            f"expected one definition of {function_name}, found {len(declarations)}"
        )
    declaration = declarations[0]
    body = re.search(r"\{", masked[declaration.start() :])
    if not body:
        raise ValueError(f"target function {function_name} has no standalone body opener")
    return declaration.start(), declaration.start() + body.start()


def _split_clause_block(text: str) -> list[str]:
    clauses: list[str] = []
    start = 0
    paren = bracket = brace = 0
    for index, char in enumerate(text):
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
        elif char == "," and paren == bracket == brace == 0:
            expression = " ".join(text[start:index].split())
            if expression:
                clauses.append(expression)
            start = index + 1
    tail = " ".join(text[start:].split()).rstrip(",")
    if tail:
        clauses.append(tail)
    return clauses


def extract_reference_contract(
    source: str,
    signature_hint: str,
) -> tuple[str, str, list[dict[str, str]], str]:
    """Extract only the target function header and interface-level clauses."""
    function_name = _function_name(signature_hint)
    start, body_start = _target_header_span(source, function_name)
    header = source[start:body_start].strip()
    markers = list(re.finditer(r"(?m)^\s*(requires|ensures)\s*$", header))
    if not markers:
        raise ValueError(f"target function {function_name} has no Verus contract")

    raw_signature = " ".join(header[: markers[0].start()].split())
    raw_signature = re.sub(r"^pub(?:\([^)]*\))?\s+", "", raw_signature)
    function_signature = raw_signature.rstrip(";") + ";"
    clauses: list[dict[str, str]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(header)
        for expression in _split_clause_block(header[marker.end() : end]):
            clauses.append({"type": marker.group(1), "expr": expression})
    contract = _build_verus_contract(clauses)
    if IMPLEMENTATION_ANNOTATION.search(contract):
        raise ValueError(f"implementation annotation leaked into contract for {function_name}")
    return function_signature, contract, clauses, function_name


def _normalized_clauses(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    clauses: list[dict[str, str]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        kind = str(row.get("type", "")).strip().lower()
        expression = str(row.get("expr", "")).strip().rstrip(",")
        if kind in {"requires", "ensures"} and expression:
            clauses.append({"type": kind, "expr": expression})
    return clauses


def load_rust_code_only_contracts(path: Path) -> list[RustCodeOnlyItem]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array")
    seen: set[int] = set()
    items: list[RustCodeOnlyItem] = []
    for row in rows:
        item_id = int(row["id"])
        signature = str(row["function_signature"]).strip()
        contract = str(row["code_only_contract"]).strip()
        clauses = _normalized_clauses(row.get("verus_clauses"))
        if item_id in seen:
            raise ValueError(f"duplicate Rust code-only id: {item_id}")
        if not signature.endswith(";"):
            raise ValueError(f"id={item_id} signature must end with ';'")
        if not clauses or _build_verus_contract(clauses) != contract:
            raise ValueError(f"id={item_id} contract text and structured clauses differ")
        if IMPLEMENTATION_ANNOTATION.search(contract):
            raise ValueError(f"id={item_id} implementation annotation leaked")
        seen.add(item_id)
        items.append(
            RustCodeOnlyItem(
                id=item_id,
                path=str(row["path"]),
                requirement=str(row.get("requirement_en") or row.get("requirement") or ""),
                function_signature=signature,
                code_only_contract=contract,
                verus_clauses=clauses,
                provenance=dict(row.get("contract_provenance") or {}),
            )
        )
    return items


def enforce_oracle_contract(
    source: str,
    signature: str,
    contract: str,
    clauses: list[dict[str, str]],
) -> tuple[str, dict[str, Any]]:
    enforced, rewritten = _enforce_rust_contract(source, signature, clauses)
    actual_signature, actual_contract, actual_clauses, _ = extract_reference_contract(
        enforced, signature
    )
    signature_match = normalize_contract(actual_signature) == normalize_contract(signature)
    contract_match = (
        normalize_contract(actual_contract) == normalize_contract(contract)
        and actual_clauses == clauses
    )
    if not signature_match or not contract_match:
        raise ValueError("failed to enforce canonical Rust oracle signature/contract")
    return enforced, {
        "enforced": True,
        "rewritten": rewritten,
        "signature_match": signature_match,
        "contract_match": contract_match,
        "canonical_contract_hash": contract_hash(contract),
        "source_contract_hash": contract_hash(actual_contract),
    }
