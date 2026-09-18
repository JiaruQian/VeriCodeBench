"""C code-only pipeline with a frozen oracle ACSL function contract."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .requirement_pipeline import (
    CODE_SYSTEM_PROMPT,
    CODE_USER_PROMPT_TEMPLATE,
    EnhancedRequirementToCodePipeline,
    RequirementItem,
    _clean_text,
    _extract_c_code,
)


@dataclass(frozen=True)
class CodeOnlyItem:
    id: int
    path: str
    requirement: str
    function_signature: str
    code_only_contract: str
    provenance: Dict[str, Any]


def load_code_only_contracts(path: Path) -> List[CodeOnlyItem]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain a JSON array")
    items: List[CodeOnlyItem] = []
    seen_ids: set[int] = set()
    for row in raw:
        item_id = int(row["id"])
        signature = _clean_text(row.get("function_signature"))
        contract = _clean_text(row.get("code_only_contract"))
        if item_id in seen_ids:
            raise ValueError(f"duplicate code-only id: {item_id}")
        if not signature.endswith(";"):
            raise ValueError(f"id={item_id} function_signature must end with ';'")
        if not contract.startswith("/*@") or not contract.endswith("*/"):
            raise ValueError(f"id={item_id} code_only_contract must be a full ACSL block")
        if re.search(r"\b(?:loop\s+(?:invariant|assigns|variant)|assert|ghost)\b", contract, re.I):
            raise ValueError(f"id={item_id} oracle contract contains implementation annotation")
        seen_ids.add(item_id)
        items.append(
            CodeOnlyItem(
                id=item_id,
                path=str(row["path"]),
                requirement=_clean_text(row.get("requirement_en") or row.get("requirement")),
                function_signature=signature,
                code_only_contract=contract,
                provenance=dict(row.get("contract_provenance") or {}),
            )
        )
    return items


def _function_name(signature: str) -> str:
    match = re.search(r"([A-Za-z_]\w*)\s*\([^;]*\)\s*;\s*$", signature, re.S)
    if not match:
        raise ValueError(f"cannot parse function signature: {signature}")
    return match.group(1)


def enforce_oracle_contract(source: str, signature: str, contract: str) -> tuple[str, Dict[str, Any]]:
    name = _function_name(signature)
    definition_pattern = re.compile(
        rf"^[ \t]*[A-Za-z_]\w*[\w \t*]*\b{re.escape(name)}\s*\([^{{}};]*\)\s*\{{",
        re.M | re.S,
    )
    definitions = list(definition_pattern.finditer(source))
    if len(definitions) != 1:
        raise ValueError(f"expected one definition for {name}, found {len(definitions)}")
    definition = definitions[0]
    prefix = source[: definition.start()]
    adjacent = re.search(r"/\*@.*?\*/\s*$", prefix, re.S)
    replaced = adjacent is not None
    if adjacent:
        prefix = prefix[: adjacent.start()]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    enforced = prefix + contract.strip() + "\n" + source[definition.start():]
    verify_def = list(definition_pattern.finditer(enforced))[0]
    verify_prefix = enforced[: verify_def.start()]
    verify_block = re.search(r"/\*@.*?\*/\s*$", verify_prefix, re.S)
    if not verify_block or verify_block.group(0).strip() != contract.strip():
        raise ValueError(f"failed to enforce oracle contract for {name}")
    digest = hashlib.sha256(contract.strip().encode()).hexdigest()
    return enforced, {
        "enforced": True,
        "target_function": name,
        "model_contract_replaced": replaced,
        "canonical_contract_hash": digest,
        "source_contract_hash": digest,
        "contract_match": True,
    }


class CodeOnlyContractPipeline(EnhancedRequirementToCodePipeline):
    """Generate and repair C implementations under fixed oracle contracts."""

    def __init__(
        self,
        *,
        contracts: List[CodeOnlyItem],
        llm_client: Any,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
        enable_code_repair: bool = False,
        code_repair_max_iter: int = 3,
        code_repair_strategy: str = "simple",
        vgcr_candidates: int = 3,
        reuse_artifacts_from: Optional[Path] = None,
    ):
        super().__init__(
            llm_client=llm_client,
            output_dir=output_dir,
            verify_timeout=verify_timeout,
            skip_verify=skip_verify,
            logger=logger,
            spec_self_check_rounds=0,
            code_repair_max_iter=code_repair_max_iter,
            enable_spec_evaluation=False,
            enable_cgs=False,
            enable_code_repair=enable_code_repair,
            code_repair_strategy=code_repair_strategy,
            vgcr_candidates=vgcr_candidates,
            reuse_artifacts_from=reuse_artifacts_from,
        )
        self.contracts = {item.id: item for item in contracts}
        self._active_signature = ""
        self._active_contract = ""
        underlying_verify = self.verifier.verify

        def enforcing_verify(code_file: Path) -> Any:
            code, _ = enforce_oracle_contract(
                code_file.read_text(), self._active_signature, self._active_contract
            )
            code_file.write_text(code)
            return underlying_verify(code_file)

        self.verifier.verify = enforcing_verify  # type: ignore[method-assign]

    def _build_report(self, results: List[Dict[str, Any]], total: int, processed: int) -> Dict[str, Any]:
        report = super()._build_report(results, total, processed)
        report["task_type"] = "code_only_oracle_contract"
        report["contract_mismatch_count"] = sum(
            1 for row in results if row.get("contract_enforcement", {}).get("contract_match") is False
        )
        report["initial_passed"] = sum(
            1 for row in results if row.get("verification", {}).get("initial_valid") is True
        )
        return report

    def _run_one(self, item: RequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
        oracle = self.contracts.get(item.id)
        if oracle is None:
            raise ValueError(f"missing oracle contract for id={item.id}")
        function_signature = oracle.function_signature
        acsl_block = oracle.code_only_contract
        self._active_signature = function_signature
        self._active_contract = acsl_block

        spec_file = specs_dir / Path(oracle.path).with_suffix(".json")
        code_file = code_dir / Path(oracle.path)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        spec_out = {
            "id": oracle.id,
            "path": oracle.path,
            "requirement": oracle.requirement,
            "function_signature": function_signature,
            "acsl_block": acsl_block,
            "code_only_contract": acsl_block,
            "code_annotation_hints": {"loop_invariants": [], "loop_assigns": [], "loop_variants": []},
            "contract_provenance": oracle.provenance,
            "task_type": "code_only_oracle_contract",
        }
        spec_file.write_text(json.dumps(spec_out, ensure_ascii=False, indent=2))

        reused = self.reuse_artifacts_from is not None
        if reused:
            source_code = self.reuse_artifacts_from / "code" / oracle.path
            source_spec = self.reuse_artifacts_from / "specs" / Path(oracle.path).with_suffix(".json")
            if not source_code.exists() or not source_spec.exists():
                raise FileNotFoundError(f"missing reused artifacts for id={item.id}")
            source_spec_data = json.loads(source_spec.read_text())
            if _clean_text(source_spec_data.get("acsl_block")) != acsl_block:
                raise ValueError(f"reused oracle contract mismatch for id={item.id}")
            shutil.copy2(source_code, code_file)
            code_text = code_file.read_text()
        else:
            prompt = CODE_USER_PROMPT_TEMPLATE.format(
                requirement=oracle.requirement,
                function_signature=function_signature,
                acsl_block=acsl_block,
                code_annotation_hints_json=json.dumps(spec_out["code_annotation_hints"], indent=2),
            )
            raw = self.llm_client.chat(CODE_SYSTEM_PROMPT, prompt)
            code_text = _extract_c_code(raw)
            code_file.write_text(code_text)

        code_text, enforcement = enforce_oracle_contract(code_text, function_signature, acsl_block)
        code_file.write_text(code_text)
        result: Dict[str, Any] = {
            "spec_file": str(spec_file),
            "code_file": str(code_file),
            "task_type": "code_only_oracle_contract",
            "contract_enforcement": enforcement,
            "reused_artifacts": reused,
        }
        if self.skip_verify:
            return result
        verification = self._verify_with_optional_repair(
            item=item,
            code_file=code_file,
            code_text=code_file.read_text(),
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints=spec_out["code_annotation_hints"],
        )
        repair_history = verification.get("repair_history") or []
        if repair_history:
            verification["initial_valid"] = False
            verification["initial_type"] = repair_history[0].get("before_type", "unknown")
        else:
            verification["initial_valid"] = verification.get("valid") is True
            verification["initial_type"] = verification.get("type", "unknown")
        result["verification"] = verification
        _, final_enforcement = enforce_oracle_contract(code_file.read_text(), function_signature, acsl_block)
        result["contract_enforcement"] = final_enforcement
        return result


def as_requirement_items(items: List[CodeOnlyItem]) -> List[RequirementItem]:
    return [
        RequirementItem(id=item.id, path=item.path, requirement=item.requirement, signature_hint=item.function_signature)
        for item in items
    ]
