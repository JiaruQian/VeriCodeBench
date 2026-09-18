"""Frozen Nagini oracle contracts for Python code-only evaluation."""
from __future__ import annotations

import ast, hashlib, json, re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .python_nagini_requirement_pipeline import (
    PythonNaginiRequirementItem, PythonNaginiRequirementToCodePipeline,
    PYTHON_CODE_SYSTEM_PROMPT, PYTHON_CODE_USER_PROMPT_TEMPLATE,
    _extract_python_code, _enforce_nagini_contract,
)

IMPLEMENTATION_ANNOTATION = re.compile(r"\b(?:Invariant|Assert|Assume)\s*\(", re.I)

@dataclass(frozen=True)
class PythonCodeOnlyItem:
    id: int; path: str; requirement: str; function_signature: str
    code_only_contract: str; nagini_clauses: list[dict[str, str]]; provenance: dict[str, Any]

def normalize_contract(text: str) -> str:
    return "\n".join(x.strip() for x in text.strip().splitlines() if x.strip())

def contract_hash(text: str) -> str:
    return hashlib.sha256(normalize_contract(text).encode()).hexdigest()

def _contract_from_clauses(clauses: list[dict[str, str]]) -> str:
    return "\n".join(f"{c['type'].title()}({c['expr']})" for c in clauses)

def _normalized_clauses(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list): return []
    return [{"type": str(x["type"]).lower(), "expr": str(x["expr"]).strip()}
            for x in value if isinstance(x, dict) and str(x.get("type", "")).lower() in {"requires", "ensures"} and str(x.get("expr", "")).strip()]

def load_python_code_only_contracts(path: Path) -> list[PythonCodeOnlyItem]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list): raise ValueError(f"{path} must contain a JSON array")
    seen: set[int] = set(); items = []
    for row in rows:
        item_id = int(row["id"]); signature = str(row["function_signature"]).strip(); contract = str(row["code_only_contract"]).strip(); clauses = _normalized_clauses(row.get("nagini_clauses"))
        if item_id in seen: raise ValueError(f"duplicate Python code-only id: {item_id}")
        if not signature.endswith(":") or not clauses or normalize_contract(_contract_from_clauses(clauses)) != normalize_contract(contract): raise ValueError(f"invalid Python oracle entry id={item_id}")
        if IMPLEMENTATION_ANNOTATION.search(contract): raise ValueError(f"id={item_id} implementation annotation leaked")
        seen.add(item_id); items.append(PythonCodeOnlyItem(item_id, str(row["path"]), str(row.get("requirement_en", "")), signature, contract, clauses, dict(row.get("contract_provenance") or {})))
    return items

def extract_reference_contract(source: str, signature: str) -> tuple[str, list[dict[str, str]]]:
    tree = ast.parse(source); match = re.search(r"\bdef\s+([A-Za-z_]\w*)\s*\(", signature)
    if not match: raise ValueError(f"cannot parse function signature: {signature}")
    name = match.group(1); functions = [x for x in ast.walk(tree) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == name]
    if len(functions) != 1: raise ValueError(f"expected one definition of {name}, found {len(functions)}")
    clauses = []
    for node in functions[0].body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call) or not isinstance(node.value.func, ast.Name): break
        kind = node.value.func.id.lower()
        if kind not in {"requires", "ensures"} or len(node.value.args) != 1: break
        clauses.append({"type": kind, "expr": ast.unparse(node.value.args[0])})
    if not clauses: raise ValueError(f"no leading Nagini contract for {name}")
    contract = _contract_from_clauses(clauses)
    if IMPLEMENTATION_ANNOTATION.search(contract): raise ValueError(f"implementation annotation leaked into contract for {name}")
    return contract, clauses

class PythonCodeOnlyContractPipeline(PythonNaginiRequirementToCodePipeline):
    def __init__(self, *, contracts: list[PythonCodeOnlyItem], **kwargs: Any):
        super().__init__(spec_self_check_rounds=0, enable_constraint_extraction=False, **kwargs); self.contracts = {x.id: x for x in contracts}
    def _build_report(self, results: list[dict[str, Any]], total: int, processed: int) -> dict[str, Any]:
        report = super()._build_report(results, total, processed); report["task_type"] = "code_only_oracle_contract"; report["contract_mismatch_count"] = sum(not x.get("contract_enforcement", {}).get("contract_match", True) for x in results); report["initial_passed"] = sum(x.get("verification", {}).get("initial_valid") is True for x in results); return report
    def _run_one(self, item: PythonNaginiRequirementItem, specs_dir: Path, code_dir: Path) -> dict[str, Any]:
        oracle = self.contracts[item.id]; signature, contract = oracle.function_signature, oracle.code_only_contract; spec_file = specs_dir / Path(oracle.path).with_suffix(".json"); code_file = code_dir / oracle.path; spec_file.parent.mkdir(parents=True, exist_ok=True); code_file.parent.mkdir(parents=True, exist_ok=True)
        hints = {"loop_invariants": []}; spec = {"id": oracle.id, "path": oracle.path, "language": "python", "verifier": "nagini", "requirement": oracle.requirement, "function_signature": signature, "nagini_contract": contract, "nagini_clauses": oracle.nagini_clauses, "code_only_contract": contract, "code_annotation_hints": hints, "contract_provenance": oracle.provenance, "task_type": "code_only_oracle_contract"}; spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
        reused = self.reuse_artifacts_from is not None
        if reused:
            old_spec = self.reuse_artifacts_from / "specs" / Path(oracle.path).with_suffix(".json"); old_code = self.reuse_artifacts_from / "code" / oracle.path
            if not old_spec.exists() or not old_code.exists(): raise FileNotFoundError(f"missing reused artifacts for id={oracle.id}")
            if normalize_contract(str(json.loads(old_spec.read_text()).get("code_only_contract", ""))) != normalize_contract(contract): raise ValueError(f"reused oracle contract mismatch for id={oracle.id}")
            code_file.write_text(old_code.read_text())
        else:
            prompt = PYTHON_CODE_USER_PROMPT_TEMPLATE.format(requirement=oracle.requirement, function_signature=signature, nagini_contract=contract, nagini_clauses_json=json.dumps(oracle.nagini_clauses, indent=2), code_annotation_hints_json=json.dumps(hints, indent=2)); code_file.write_text(_extract_python_code(self.llm_client.chat(PYTHON_CODE_SYSTEM_PROMPT, prompt)))
        code_text, enforcement = _enforce_nagini_contract(code_file.read_text(), signature, contract); code_file.write_text(code_text); result = {"spec_file": str(spec_file), "code_file": str(code_file), "task_type": "code_only_oracle_contract", "reused_artifacts": reused, "contract_enforcement": enforcement}
        if not self.skip_verify: self._verify_with_optional_repair(item=item, code_file=code_file, code_text=code_text, function_signature=signature, nagini_contract=contract, nagini_clauses=oracle.nagini_clauses, code_annotation_hints=hints, result=result); result["verification"]["initial_valid"] = not result["verification"].get("repair_history") and result["verification"].get("valid") is True
        return result

def as_requirement_items(items: list[PythonCodeOnlyItem]) -> list[PythonNaginiRequirementItem]:
    return [PythonNaginiRequirementItem(x.id, x.path, x.requirement, x.function_signature) for x in items]
