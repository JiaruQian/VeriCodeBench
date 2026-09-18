"""Java/OpenJML code-only pipeline with frozen method contracts."""
from __future__ import annotations
import json, shutil
from pathlib import Path
from typing import Any
from .java_requirement_pipeline import (
    JavaRequirementToCodePipeline, JavaRequirementItem, JAVA_CODE_SYSTEM_PROMPT,
    JAVA_CODE_USER_PROMPT_TEMPLATE, _extract_java_code, _sanitize_generated_java_code,
    _enforce_jml_contract,
)
from .java_code_only_pipeline import JavaCodeOnlyItem, load_java_code_only_contracts

class JavaCodeOnlyContractPipeline(JavaRequirementToCodePipeline):
    def __init__(self, *, contracts: list[JavaCodeOnlyItem], **kwargs: Any):
        super().__init__(spec_self_check_rounds=0, enable_constraint_extraction=False, **kwargs)
        self.contracts = {item.id: item for item in contracts}

    def _build_report(self, results: list[dict[str, Any]], total: int, processed: int) -> dict[str, Any]:
        report = super()._build_report(results, total, processed)
        report["task_type"] = "code_only_oracle_contract"
        report["contract_mismatch_count"] = sum(not r.get("contract_enforcement", {}).get("contract_match", True) for r in results)
        report["initial_passed"] = sum(r.get("verification", {}).get("initial_valid") is True for r in results)
        return report

    def _run_one(self, item: JavaRequirementItem, specs_dir: Path, code_dir: Path) -> dict[str, Any]:
        oracle = self.contracts[item.id]
        sig, contract = oracle.function_signature, oracle.code_only_contract
        spec_file = specs_dir / Path(oracle.path).with_suffix(".json")
        code_file = code_dir / oracle.path
        spec_file.parent.mkdir(parents=True, exist_ok=True); code_file.parent.mkdir(parents=True, exist_ok=True)
        spec = {"id": oracle.id, "path": oracle.path, "language": "java", "verifier": "openjml", "requirement": oracle.requirement, "class_name": oracle.class_name, "function_signature": sig, "jml_block": contract, "code_only_contract": contract, "acsl_block": contract, "code_annotation_hints": {"loop_invariants": [], "loop_assigns": [], "loop_variants": []}, "type_context": oracle.type_context, "contract_provenance": oracle.provenance, "task_type": "code_only_oracle_contract"}
        spec_file.write_text(json.dumps(spec, ensure_ascii=False, indent=2))
        reused = self.reuse_artifacts_from is not None
        if reused:
            old_spec = self.reuse_artifacts_from / "specs" / Path(oracle.path).with_suffix(".json")
            old_code = self.reuse_artifacts_from / "code" / oracle.path
            if not old_spec.exists() or not old_code.exists(): raise FileNotFoundError(f"missing reused artifacts for id={oracle.id}")
            old = json.loads(old_spec.read_text())
            if " ".join(str(old.get("code_only_contract") or old.get("jml_block", "")).split()) != " ".join(contract.split()): raise ValueError(f"reused oracle contract mismatch for id={oracle.id}")
            shutil.copy2(old_code, code_file); code_text = code_file.read_text()
        else:
            prompt = JAVA_CODE_USER_PROMPT_TEMPLATE.format(requirement=oracle.requirement, class_name=oracle.class_name, function_signature=sig, jml_block=contract, helper_declarations=oracle.type_context or "(none)", code_annotation_hints_json=json.dumps(spec["code_annotation_hints"], indent=2))
            raw = self.llm_client.chat(JAVA_CODE_SYSTEM_PROMPT, prompt); code_text = _extract_java_code(raw)
        code_text, sanitation = _sanitize_generated_java_code(code_text)
        code_text, enforcement = _enforce_jml_contract(code_text, sig, contract); code_file.write_text(code_text)
        result = {"spec_file": str(spec_file), "code_file": str(code_file), "task_type": "code_only_oracle_contract", "reused_artifacts": reused, "code_sanitization": sanitation, "contract_enforcement": {"enabled": True, "initial_generation": enforcement, "repair_attempts": []}}
        if not self.skip_verify:
            self._verify_with_optional_repair(item=item, code_file=code_file, code_text=code_text, function_signature=sig, jml_block=contract, code_annotation_hints=spec["code_annotation_hints"], result=result)
            verification = result["verification"]
            history = verification.get("repair_history") or []
            verification["initial_valid"] = verification["valid"] if not history else False
            verification["initial_type"] = verification["type"] if not history else history[0].get("before_type", "unknown")
        final_code, final_enforcement = _enforce_jml_contract(code_file.read_text(), sig, contract)
        code_file.write_text(final_code)
        result["contract_enforcement"]["final"] = final_enforcement
        result["contract_enforcement"]["contract_match"] = True
        return result

def as_java_requirement_items(items: list[JavaCodeOnlyItem]) -> list[JavaRequirementItem]:
    return [JavaRequirementItem(id=x.id, path=x.path, requirement=x.requirement, class_name=x.class_name, signature_hint=x.function_signature, type_context=x.type_context) for x in items]
