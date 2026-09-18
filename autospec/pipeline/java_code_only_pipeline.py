"""Frozen-contract utilities for the Java/OpenJML code-only benchmark."""
from __future__ import annotations
import hashlib, json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .java_requirement_pipeline import _enforce_jml_contract

@dataclass(frozen=True)
class JavaCodeOnlyItem:
    id: int; path: str; requirement: str; class_name: str; function_signature: str
    code_only_contract: str; type_context: str = ""; provenance: dict[str, Any] | None = None

def load_java_code_only_contracts(path: Path) -> list[JavaCodeOnlyItem]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list): raise ValueError(f"{path} must contain a JSON array")
    seen: set[int] = set(); out = []
    for row in rows:
        item_id = int(row["id"]); sig = str(row["function_signature"]).strip(); contract = str(row["code_only_contract"]).strip()
        if item_id in seen: raise ValueError(f"duplicate code-only id: {item_id}")
        if not sig.endswith(";"): raise ValueError(f"id={item_id} signature must end with ';'")
        if not contract.startswith("/*@") or not contract.endswith("*/"): raise ValueError(f"id={item_id} invalid JML block")
        if re.search(r"\b(?:loop_(?:invariant|assigns|decreases)|maintaining|decreases|ghost|assert)\b", contract, re.I): raise ValueError(f"id={item_id} implementation annotation leaked")
        seen.add(item_id); out.append(JavaCodeOnlyItem(item_id, str(row["path"]), str(row.get("requirement_en") or row.get("requirement") or ""), str(row.get("class_name") or Path(row["path"]).stem), sig, contract, str(row.get("type_context") or ""), dict(row.get("contract_provenance") or {})))
    return out

def enforce_oracle_contract(source: str, signature: str, contract: str) -> tuple[str, dict[str, Any]]:
    enforced, info = _enforce_jml_contract(source, signature, contract)
    info["canonical_contract_hash"] = hashlib.sha256(" ".join(contract.split()).encode()).hexdigest()
    info["contract_match"] = True
    return enforced, info
