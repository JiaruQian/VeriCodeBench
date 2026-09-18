"""Rust/Verus code-only pipeline with frozen function contracts."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .rust_code_only_pipeline import (
    RustCodeOnlyItem,
    enforce_oracle_contract,
    normalize_contract,
)
from .rust_requirement_pipeline import (
    RUST_CODE_SYSTEM_PROMPT,
    RUST_CODE_USER_PROMPT_TEMPLATE,
    RustRequirementItem,
    RustRequirementToCodePipeline,
    _extract_rust_code,
)


class RustCodeOnlyContractPipeline(RustRequirementToCodePipeline):
    def __init__(self, *, contracts: list[RustCodeOnlyItem], **kwargs: Any):
        super().__init__(
            enable_cgs=False,
            spec_self_check_rounds=0,
            pipeline_variant="code_only",
            enhancement_method=None,
            **kwargs,
        )
        self.contracts = {item.id: item for item in contracts}

    def _build_report(
        self,
        results: list[dict[str, Any]],
        total: int,
        processed: int,
    ) -> dict[str, Any]:
        report = super()._build_report(results, total, processed)
        report["task_type"] = "code_only_oracle_contract"
        report["contract_mismatch_count"] = sum(
            not result.get("contract_enforcement", {}).get("contract_match", True)
            for result in results
        )
        report["initial_passed"] = sum(
            result.get("verification", {}).get("initial_valid") is True
            for result in results
        )
        return report

    def _run_one(
        self,
        item: RustRequirementItem,
        specs_dir: Path,
        code_dir: Path,
    ) -> dict[str, Any]:
        oracle = self.contracts.get(item.id)
        if oracle is None:
            raise ValueError(f"missing Rust oracle contract for id={item.id}")
        signature = oracle.function_signature
        contract = oracle.code_only_contract
        clauses = oracle.verus_clauses
        hints = {"loop_invariants": [], "loop_variants": []}
        spec_file = specs_dir / Path(oracle.path).with_suffix(".json")
        code_file = code_dir / oracle.path
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        spec = {
            "id": oracle.id,
            "path": oracle.path,
            "language": "rust",
            "verifier": "verus",
            "requirement": oracle.requirement,
            "function_signature": signature,
            "verus_contract": contract,
            "code_only_contract": contract,
            "verus_clauses": clauses,
            "code_annotation_hints": hints,
            "contract_provenance": oracle.provenance,
            "task_type": "code_only_oracle_contract",
        }
        spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2))

        reused = self.reuse_artifacts_from is not None
        if reused:
            old_spec_file = (
                self.reuse_artifacts_from
                / "specs"
                / Path(oracle.path).with_suffix(".json")
            )
            old_code_file = self.reuse_artifacts_from / "code" / oracle.path
            if not old_spec_file.exists() or not old_code_file.exists():
                raise FileNotFoundError(f"missing reused artifacts for id={oracle.id}")
            old_spec = json.loads(old_spec_file.read_text())
            old_contract = str(
                old_spec.get("code_only_contract") or old_spec.get("verus_contract") or ""
            )
            old_signature = str(old_spec.get("function_signature") or "")
            if (
                normalize_contract(old_contract) != normalize_contract(contract)
                or normalize_contract(old_signature) != normalize_contract(signature)
                or old_spec.get("verus_clauses") != clauses
            ):
                raise ValueError(f"reused Rust oracle contract mismatch for id={oracle.id}")
            shutil.copy2(old_code_file, code_file)
            code_text = code_file.read_text()
        else:
            prompt = RUST_CODE_USER_PROMPT_TEMPLATE.format(
                requirement=oracle.requirement,
                function_signature=signature,
                verus_contract=contract,
                verus_clauses_json=json.dumps(clauses, ensure_ascii=False, indent=2),
                code_annotation_hints_json=json.dumps(hints, ensure_ascii=False, indent=2),
            )
            raw = self.llm_client.chat(RUST_CODE_SYSTEM_PROMPT, prompt)
            raw_file = self.output_dir / "reports" / Path(oracle.path).with_suffix(".raw.txt")
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            raw_file.write_text(raw)
            code_text = _extract_rust_code(raw)

        code_text, initial_enforcement = enforce_oracle_contract(
            code_text, signature, contract, clauses
        )
        code_file.write_text(code_text)
        result: dict[str, Any] = {
            "spec_file": str(spec_file),
            "code_file": str(code_file),
            "task_type": "code_only_oracle_contract",
            "reused_artifacts": reused,
            "raw_response_file": str(raw_file) if not reused else None,
            "contract_enforcement": {
                "enabled": True,
                "initial_generation": initial_enforcement,
                "contract_match": True,
            },
        }
        if not self.skip_verify:
            self._verify_with_optional_repair(
                item=item,
                code_file=code_file,
                code_text=code_text,
                function_signature=signature,
                verus_contract=contract,
                verus_clauses=clauses,
                code_annotation_hints=hints,
                result=result,
            )
            verification = result["verification"]
            history = verification.get("repair_history") or []
            verification["initial_valid"] = verification["valid"] if not history else False
            verification["initial_type"] = (
                verification["type"] if not history else history[0].get("before_type", "unknown")
            )

        final_code, final_enforcement = enforce_oracle_contract(
            code_file.read_text(), signature, contract, clauses
        )
        code_file.write_text(final_code)
        result["contract_enforcement"]["final"] = final_enforcement
        result["contract_enforcement"]["contract_match"] = True
        return result


def as_rust_requirement_items(
    items: list[RustCodeOnlyItem],
) -> list[RustRequirementItem]:
    return [
        RustRequirementItem(
            id=item.id,
            path=item.path,
            requirement=item.requirement,
            signature_hint=item.function_signature,
        )
        for item in items
    ]
