"""Pipeline: requirement -> ACSL specification -> C code -> verification."""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..llm.openai_compatible import OpenAICompatibleClient
from ..verifier.frama_c import FramaCVerifier


SPEC_SYSTEM_PROMPT = """You are an expert in ACSL specification design for C code.
Return strict JSON only."""

SPEC_USER_PROMPT_TEMPLATE = """Given the requirement below, design a minimal but useful ACSL function specification.

Requirement:
{requirement}

Function signature hint (must use exactly if provided):
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "C function signature without body, e.g. int foo(int *a, int n);",
    "acsl_block": "A full ACSL block in /*@ ... */ format for the function.",
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_assigns": ["Optional loop assigns candidates for code generation only."],
      "loop_variants": ["Optional loop variant candidates for code generation only."]
    }},
    "notes": "Very short rationale."
  }}
- The signature must be compatible with Frama-C/WP and plain C.
- If the signature hint is non-empty, copy it exactly into function_signature.
- Include requires/assigns/ensures in the ACSL block.
- The ACSL block is a function contract only. Do not put loop invariant, loop assigns,
  or loop variant clauses inside acsl_block.
- If loop annotations may help the future implementation verify, put them only in
  code_annotation_hints. They will be inserted inside the generated C function near loops.
- Do not invent unsupported ACSL logic predicates such as \\integer. C parameters already
  have C types; use \valid/\valid_read for pointer validity when needed.
"""


CODE_SYSTEM_PROMPT = """You are an expert C developer writing verification-friendly code.
Output C code only."""

CODE_USER_PROMPT_TEMPLATE = """Implement a single C function from the requirement and ACSL specification.

Requirement:
{requirement}

Function signature:
{function_signature}

ACSL block (must remain directly above the function):
{acsl_block}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Output constraints:
- Output only complete C source code (no markdown fences, no explanation).
- Keep exactly one function implementation that matches the signature.
- Keep the ACSL block directly above the function.
- Do not change the function contract in the ACSL block.
- Use code_annotation_hints, when helpful, as statement annotations inside the function body.
  Loop invariants/assigns/variants must appear immediately before the loop they describe,
  never in the function contract.
- Do not add main().
- Use simple loops/branches and avoid advanced library dependencies.
"""

CONSTRAINT_SYSTEM_PROMPT = """You are an expert in translating requirements into verification constraints.
Return strict JSON only."""

CONSTRAINT_USER_PROMPT_TEMPLATE = """Extract structured verification constraints from the requirement.

Requirement:
{requirement}

Function signature hint (must use exactly if provided):
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Best-effort C function signature without body; end with ';'. If the hint above is non-empty, copy it exactly.",
    "preconditions": ["..."],
    "postconditions": ["..."],
    "invariants": ["..."],
    "notes": "Very short rationale."
  }}
- Keep each constraint atomic and testable.
- Prefer concise mathematical/logical wording.
"""

CONSTRAINT_TO_SPEC_SYSTEM_PROMPT = """You are an expert ACSL specification engineer.
Convert constraints into a complete ACSL contract. Return strict JSON only."""

CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE = """Create ACSL spec JSON using requirement + structured constraints.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Function signature hint (can be empty):
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "C function signature without body, e.g. int foo(int *a, int n);",
    "acsl_block": "A full ACSL block in /*@ ... */ format for the function.",
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_assigns": ["Optional loop assigns candidates for code generation only."],
      "loop_variants": ["Optional loop variant candidates for code generation only."]
    }},
    "notes": "Very short rationale."
  }}
- Keep ACSL as complete as possible and aligned with constraints.
- If the signature hint is non-empty, copy it exactly into function_signature.
- Include requires/assigns/ensures in ACSL.
- The ACSL block is a function contract only. Do not put loop invariant, loop assigns,
  or loop variant clauses inside acsl_block.
- If loop annotations are needed for verification, put candidates only in code_annotation_hints.
- Do not invent unsupported ACSL logic predicates such as \\integer. C parameters already
  have C types; use \valid/\valid_read for pointer validity when needed.
"""

SPEC_CHECK_SYSTEM_PROMPT = """You are a strict requirement-spec alignment reviewer.
Return strict JSON only."""

SPEC_CHECK_USER_PROMPT_TEMPLATE = """Check whether generated specification misses requirement constraints.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Generated specification (JSON):
{spec_json}

Output constraints (IMPORTANT):
- Return valid JSON only.
- JSON schema:
  {{
    "is_aligned": true,
    "missing_constraints": ["..."],
    "inconsistent_items": ["..."],
    "refinement_hints": ["..."],
    "notes": "Very short rationale."
  }}
- If everything is covered, use empty arrays.
"""

SPEC_REFINE_SYSTEM_PROMPT = """You refine ACSL specs to improve requirement alignment.
Return strict JSON only."""

SPEC_REFINE_USER_PROMPT_TEMPLATE = """Refine the generated specification based on alignment findings.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Current specification (JSON):
{spec_json}

Alignment findings (JSON):
{check_json}

Output constraints (IMPORTANT):
- Return valid JSON only.
- Same schema:
  {{
    "function_signature": "...",
    "acsl_block": "/*@ ... */",
    "code_annotation_hints": {{
      "loop_invariants": ["..."],
      "loop_assigns": ["..."],
      "loop_variants": ["..."]
    }},
    "notes": "..."
  }}
- Keep acsl_block as a function contract only. Move any loop invariant/assigns/variant
  suggestions to code_annotation_hints instead of placing them in acsl_block.
"""

CODE_REPAIR_SYSTEM_PROMPT = """You are an expert C developer fixing code to satisfy ACSL verification.
Output C code only."""

CODE_REPAIR_USER_PROMPT_TEMPLATE = """Fix the C function so that it satisfies requirement and ACSL specification.

Requirement:
{requirement}

Function signature:
{function_signature}

ACSL block:
{acsl_block}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verification result:
- type: {verdict_type}
- message: {verdict_message}
- details:
{verdict_details}

Output constraints:
- Output only complete C source code (no markdown fences, no explanation).
- Keep exactly one function implementation matching the signature.
- Keep ACSL block directly above the function.
- Do not change the function contract in the ACSL block.
- Use code_annotation_hints, when helpful, as statement annotations inside the function body.
  Loop invariants/assigns/variants must appear immediately before the loop they describe,
  never in the function contract.
- Prefer minimal, verification-friendly fixes.
"""

WYBECODER_REPAIR_ANALYSIS_SYSTEM_PROMPT = """You are a verification-guided C/ACSL repair planner.
Return strict JSON only."""

WYBECODER_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze a failed Frama-C/WP verification attempt and produce a repair plan.

Requirement:
{requirement}

Function signature:
{function_signature}

ACSL block:
{acsl_block}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verification result:
- type: {verdict_type}
- message: {verdict_message}
- details:
{verdict_details}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "failure_summary": "Concise explanation of why verification failed.",
    "subgoals": [
      {{
        "name": "Short stable name, e.g. postcondition_result or loop_preservation",
        "kind": "syntax|contract_placement|memory_safety|postcondition|loop_invariant|loop_assigns|loop_variant|overflow|timeout|unknown",
        "evidence": "Relevant verifier clue.",
        "repair_hint": "Concrete body/annotation change to try."
      }}
    ],
    "global_strategy": "How to synthesize the fixes while preserving the function contract.",
    "risk_notes": ["Potential ways a repair could cheat or weaken semantics."]
  }}
- Treat the ACSL function contract as frozen. Do not suggest weakening or replacing it.
- Prefer body changes and statement-level annotations such as loop invariant/assigns/variant.
- Keep the plan language-agnostic enough that it can later be reused by Java/JML and Rust/Verus backends.
"""

WYBECODER_REPAIR_CANDIDATE_SYSTEM_PROMPT = """You are an expert C developer using prove-as-you-generate repair.
Output C code only."""

WYBECODER_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE = """Repair the C implementation using this verifier-derived plan.

Requirement:
{requirement}

Function signature:
{function_signature}

Frozen ACSL block (must remain directly above the function):
{acsl_block}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verifier-derived repair plan (JSON):
{repair_plan_json}

Candidate policy:
- This is candidate {candidate_index} of {candidate_count}.
- Candidate focus: {candidate_focus}

Output constraints:
- Output only complete C source code (no markdown fences, no explanation).
- Keep exactly one function implementation matching the signature.
- Keep the frozen ACSL block directly above the function.
- Do not change, weaken, reorder into a different contract, or delete clauses from the ACSL block.
- You may change method body logic, helper-free local computation, and statement-level loop annotations.
- Prefer explicit loops, simple mutable variables, and verification-friendly control flow.
- Avoid hiding the algorithm in library calls or changing the specification to make proof easier.
"""

REQ_DECOMP_SYSTEM_PROMPT = """You decompose software requirements into atomic testable clauses.
Return strict JSON only."""

REQ_DECOMP_USER_PROMPT_TEMPLATE = """Decompose the requirement into atomic clauses for coverage evaluation.

Requirement:
{requirement}

Output constraints (IMPORTANT):
- Return valid JSON only.
- JSON schema:
  {{
    "clauses": ["Atomic clause 1", "Atomic clause 2"],
    "notes": "Very short rationale."
  }}
- Each clause must be specific, non-overlapping, and independently checkable.
- Avoid implementation details not implied by the requirement.
"""

SPEC_CLAUSE_SYSTEM_PROMPT = """You extract semantic clauses from ACSL contracts.
Return strict JSON only."""

SPEC_CLAUSE_USER_PROMPT_TEMPLATE = """Extract semantic clauses from this ACSL block for requirement coverage matching.

Function signature:
{function_signature}

ACSL block:
{acsl_block}

Output constraints (IMPORTANT):
- Return valid JSON only.
- JSON schema:
  {{
    "clauses": ["Clause 1", "Clause 2"],
    "notes": "Very short rationale."
  }}
- Clauses should capture meaning of requires/assigns/ensures and other contract constraints.
- Keep clauses atomic and concise.
"""

CLAUSE_MATCH_SYSTEM_PROMPT = """You are a strict semantic judge for requirement-spec clause matching.
Return strict JSON only."""

CLAUSE_MATCH_USER_PROMPT_TEMPLATE = """Decide whether specification clause sj semantically covers requirement clause ci.

Requirement clause ci:
{requirement_clause}

Specification clause sj:
{spec_clause}

Question:
Does sj express ci?

Output constraints (IMPORTANT):
- Return valid JSON only.
- JSON schema:
  {{
    "match": 0,
    "reason": "One short sentence."
  }}
- Use binary decision only: 1 means covered, 0 means not covered.
- Be strict and avoid optimistic matching.
"""


@dataclass
class RequirementItem:
    """Single requirement unit."""

    id: int
    path: str
    requirement: str
    signature_hint: str = ""


def _clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = _clean_text(text)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", stripped):
        try:
            obj, _ = decoder.raw_decode(stripped[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"No JSON object found in model output: {stripped[:500]}")


def _chat_json_with_retries(
    llm_client: OpenAICompatibleClient,
    system_prompt: str,
    user_prompt: str,
) -> tuple[Dict[str, Any], str]:
    config = getattr(llm_client, "config", None)
    retries = max(0, int(getattr(config, "retry_on_connection_error", 0)))
    delay = max(0, int(getattr(config, "retry_delay_seconds", 0)))
    last_error: Optional[Exception] = None

    for attempt in range(retries + 1):
        raw = llm_client.chat(system_prompt, user_prompt)
        try:
            return _extract_json_object(raw), raw
        except ValueError as exc:
            last_error = exc
            if attempt >= retries:
                raise
            if delay:
                time.sleep(delay)

    raise RuntimeError(f"Failed to parse JSON response: {last_error}")


def _extract_c_code(text: str) -> str:
    stripped = _clean_text(text)
    if not stripped:
        raise ValueError("No C code found in model output.")
    fenced = re.search(r"```c\n([\s\S]*?)\n```", stripped)
    if fenced:
        return fenced.group(1).strip()
    if stripped.startswith("```"):
        generic = re.search(r"```\n([\s\S]*?)\n```", stripped)
        if generic:
            return generic.group(1).strip()
    return stripped


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        return lowered in {"true", "yes", "1"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _as_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_code_annotation_hints(value: Any) -> Dict[str, List[str]]:
    hints = {
        "loop_invariants": [],
        "loop_assigns": [],
        "loop_variants": [],
    }
    if not isinstance(value, dict):
        return hints

    aliases = {
        "loop_invariants": ["loop_invariants", "invariants"],
        "loop_assigns": ["loop_assigns", "assigns"],
        "loop_variants": ["loop_variants", "variants"],
    }
    for canonical, keys in aliases.items():
        for key in keys:
            items = _as_list_of_str(value.get(key))
            if items:
                hints[canonical].extend(items)
    return hints


def _strip_acsl_clause_prefix(text: str, prefix: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^\s*(?:/\*@|//@|@|\*)\s*", "", stripped)
    stripped = re.sub(r"\s*\*/\s*$", "", stripped)
    stripped = stripped.strip()
    pattern = rf"^{re.escape(prefix)}\b\s*"
    stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
    return stripped.strip().rstrip(";").strip()


def _sanitize_contract_and_hints(
    acsl_block: str,
    hints: Dict[str, List[str]],
) -> tuple[str, Dict[str, List[str]], List[Dict[str, str]]]:
    """Keep statement-level loop annotations out of function contracts."""
    normalized_hints = _normalize_code_annotation_hints(hints)
    moved: List[Dict[str, str]] = []
    lines = acsl_block.splitlines()
    kept_lines: List[str] = []
    loop_prefix_map = {
        "loop invariant": "loop_invariants",
        "loop assigns": "loop_assigns",
        "loop variant": "loop_variants",
    }
    inline_loop_pattern = re.compile(
        r"\b(loop\s+(?:invariant|assigns|variant)\b\s*.*?;)",
        flags=re.IGNORECASE,
    )

    for line in lines:
        working_line = line
        for inline_match in list(inline_loop_pattern.finditer(line)):
            inline_clause = inline_match.group(1).strip()
            lowered_inline = inline_clause.lower()
            for prefix, key in loop_prefix_map.items():
                if lowered_inline.startswith(prefix):
                    cleaned = _strip_acsl_clause_prefix(inline_clause, prefix)
                    if cleaned:
                        normalized_hints[key].append(cleaned)
                        moved.append(
                            {
                                "from": "acsl_block",
                                "to": key,
                                "clause": cleaned,
                            }
                        )
                    working_line = working_line.replace(inline_clause, "")
                    break

        clause_text = re.sub(r"^\s*(?:/\*@|//@|@|\*)\s*", "", working_line).strip()
        lowered = clause_text.lower()
        target_key: Optional[str] = None
        matched_prefix = ""
        for prefix, key in loop_prefix_map.items():
            if lowered.startswith(prefix):
                target_key = key
                matched_prefix = prefix
                break

        if target_key:
            cleaned = _strip_acsl_clause_prefix(clause_text, matched_prefix)
            if cleaned:
                normalized_hints[target_key].append(cleaned)
                moved.append(
                    {
                        "from": "acsl_block",
                        "to": target_key,
                        "clause": cleaned,
                    }
                )
            continue
        kept_lines.append(working_line.rstrip())

    cleaned_block = "\n".join(kept_lines).strip()
    cleaned_block = re.sub(r"\s+;\s*(?=\*/)", " ", cleaned_block)
    return cleaned_block, normalized_hints, moved


def _to_binary_match(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "matched"}:
            return 1
    return 0


def _truncate_for_prompt(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


def _load_signature_hints(signature_file: Optional[Path]) -> Dict[int, str]:
    if not signature_file or not signature_file.exists():
        return {}
    raw = json.loads(signature_file.read_text())
    hints: Dict[int, str] = {}
    for obj in raw:
        if "id" in obj and obj.get("function_signature"):
            hints[int(obj["id"])] = str(obj["function_signature"]).strip()
    return hints


def _load_attempted_results(reports_dir: Path) -> Dict[int, Dict[str, Any]]:
    """Load all previously processed task results (any status) for resume bookkeeping."""
    for name in ("results.partial.json", "results.json"):
        path = reports_dir / name
        if not path.exists():
            continue
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        return {
            int(item["id"]): item
            for item in report.get("results", [])
            if "id" in item
        }
    return {}


def _load_resume_results(reports_dir: Path) -> Dict[int, Dict[str, Any]]:
    return {
        item_id: item
        for item_id, item in _load_attempted_results(reports_dir).items()
        if item.get("status") == "ok"
    }


def _format_id_ranges(ids: List[int]) -> str:
    """Collapse a sorted list of ids into compact ranges, e.g. [2,3,4,7] -> '2-4,7'."""
    if not ids:
        return ""
    ordered = sorted(set(ids))
    ranges: List[str] = []
    start = prev = ordered[0]
    for current in ordered[1:]:
        if current == prev + 1:
            prev = current
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = current
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(ranges)


def load_requirements(path: Path, signature_file: Optional[Path] = None) -> List[RequirementItem]:
    """Load requirement entries from JSON."""
    raw = json.loads(path.read_text())
    signature_hints = _load_signature_hints(signature_file)
    items: List[RequirementItem] = []
    for obj in raw:
        if "id" not in obj or "path" not in obj:
            raise ValueError(f"Invalid requirement entry: {obj}")
        req_text = obj.get("requirement_zh") or obj.get("requirement_en") or obj.get("requirement")
        if not req_text:
            raise ValueError(f"Requirement text missing for entry: {obj}")
        item_id = int(obj["id"])
        signature_hint = str(obj.get("function_signature") or signature_hints.get(item_id, "")).strip()
        items.append(
            RequirementItem(
                id=item_id,
                path=str(obj["path"]),
                requirement=str(req_text),
                signature_hint=signature_hint,
            )
        )
    return items


class RequirementToCodePipeline:
    """End-to-end requirement-driven generation pipeline."""

    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
    ):
        self.llm_client = llm_client
        self.output_dir = output_dir
        self.skip_verify = skip_verify
        self.verifier = FramaCVerifier(timeout=verify_timeout)
        self.logger = logger

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)

    def _build_report(self, results: List[Dict[str, Any]], total: int, processed: int) -> Dict[str, Any]:
        passed = sum(1 for r in results if r.get("verification", {}).get("valid") is True)
        attempted = sum(1 for r in results if "verification" in r)
        return {
            "total": total,
            "processed": processed,
            "verified": attempted,
            "passed": passed,
            "results": results,
        }

    def run(self, requirements: List[RequirementItem], resume: bool = False) -> Dict[str, Any]:
        """Run generation+verification for all requirements."""
        specs_dir = self.output_dir / "specs"
        code_dir = self.output_dir / "code"
        reports_dir = self.output_dir / "reports"
        specs_dir.mkdir(parents=True, exist_ok=True)
        code_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        if resume:
            attempted_results = _load_attempted_results(reports_dir)
            resume_results = {
                item_id: item
                for item_id, item in attempted_results.items()
                if item.get("status") == "ok"
            }
            retry_ids = sorted(i for i in attempted_results if i not in resume_results)
            skipped_ids = sorted(resume_results)
            self._log(
                f"[RESUME] loaded {len(attempted_results)} previously processed task(s) "
                f"from {reports_dir}"
            )
            self._log(
                f"[RESUME] {len(skipped_ids)} ok will be skipped"
                + (f" (ids: {_format_id_ranges(skipped_ids)})" if skipped_ids else "")
            )
            self._log(
                f"[RESUME] {len(retry_ids)} failed will be retried"
                + (f" (ids: {_format_id_ranges(retry_ids)})" if retry_ids else "")
            )
            first_pending = next(
                (item.id for item in requirements if item.id not in resume_results),
                None,
            )
            if first_pending is None:
                self._log("[RESUME] all tasks already completed; nothing new to run")
            else:
                self._log(f"[RESUME] first task needing work: id={first_pending}")
        else:
            resume_results = {}
        results: List[Dict[str, Any]] = []
        total = len(requirements)
        for idx, item in enumerate(requirements, start=1):
            self._log("=" * 72)
            self._log(f"[TASK {idx}/{total}] id={item.id} path={item.path}")
            self._log(f"[TASK {idx}/{total}] requirement: {item.requirement}")
            result: Dict[str, Any] = {
                "id": item.id,
                "path": item.path,
                "requirement": item.requirement,
                "status": "ok",
            }
            if item.id in resume_results:
                result = resume_results[item.id]
                results.append(result)
                self._log(f"[TASK {idx}/{total}] status=ok resumed=true")
            else:
                try:
                    result.update(self._run_one(item, specs_dir, code_dir))
                    self._log(f"[TASK {idx}/{total}] status=ok")
                except Exception as exc:  # keep batch processing resilient
                    result["status"] = "error"
                    result["error"] = str(exc)
                    self._log(f"[TASK {idx}/{total}] status=error error={exc}")
                results.append(result)

            # Write an incremental report after each task so progress is visible/recoverable.
            interim_report = self._build_report(results=results, total=total, processed=idx)
            interim_report_path = reports_dir / "results.partial.json"
            interim_report_path.write_text(json.dumps(interim_report, ensure_ascii=False, indent=2))
            self._log(
                f"[TASK {idx}/{total}] partial_report={interim_report_path} "
                f"(processed={idx}, verified={interim_report['verified']}, passed={interim_report['passed']})"
            )

        report = self._build_report(results=results, total=total, processed=len(results))
        report_path = reports_dir / "results.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self._log("=" * 72)
        self._log(
            f"[DONE] total={report['total']} processed={report['processed']} "
            f"verified={report['verified']} passed={report['passed']}"
        )
        self._log(f"[DONE] report={report_path}")
        return {"report_path": str(report_path), "report": report}

    def _run_one(self, item: RequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
        self._log(f"[id={item.id}] stage=spec_generation start")
        spec_prompt = SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            signature_hint=item.signature_hint,
        )
        spec_json, spec_raw = _chat_json_with_retries(
            self.llm_client,
            SPEC_SYSTEM_PROMPT,
            spec_prompt,
        )

        function_signature = item.signature_hint or _clean_text(spec_json.get("function_signature"))
        acsl_block = _clean_text(spec_json.get("acsl_block"))
        code_annotation_hints = _normalize_code_annotation_hints(
            spec_json.get("code_annotation_hints")
        )
        acsl_block, code_annotation_hints, moved_loop_annotations = _sanitize_contract_and_hints(
            acsl_block,
            code_annotation_hints,
        )
        notes = _clean_text(spec_json.get("notes"))

        if not function_signature.endswith(";"):
            raise ValueError(f"function_signature must end with ';': {function_signature}")
        if "/*@" not in acsl_block or "*/" not in acsl_block:
            raise ValueError("acsl_block must be a full /*@ ... */ block.")

        spec_out = {
            "id": item.id,
            "path": item.path,
            "requirement": item.requirement,
            "function_signature": function_signature,
            "acsl_block": acsl_block,
            "code_annotation_hints": code_annotation_hints,
            "moved_loop_annotations": moved_loop_annotations,
            "notes": notes,
            "raw_model_output": spec_raw,
        }
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_out, ensure_ascii=False, indent=2))
        self._log(f"[id={item.id}] stage=spec_generation done spec_file={spec_file}")

        self._log(f"[id={item.id}] stage=code_generation start")
        code_prompt = CODE_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
        )
        code_raw = self.llm_client.chat(CODE_SYSTEM_PROMPT, code_prompt)
        code_text = _extract_c_code(code_raw)
        code_file = code_dir / Path(item.path)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text(code_text)
        self._log(f"[id={item.id}] stage=code_generation done code_file={code_file}")

        one_result: Dict[str, Any] = {
            "spec_file": str(spec_file),
            "code_file": str(code_file),
        }
        if self.skip_verify:
            self._log(f"[id={item.id}] stage=verify skipped")
            return one_result

        self._log(f"[id={item.id}] stage=verify start")
        verdict = self.verifier.verify(code_file)
        one_result["verification"] = {
            "valid": verdict.is_valid(),
            "type": verdict.verdict_type.value,
            "message": verdict.message,
        }
        if verdict.details:
            verify_log = self.output_dir / "reports" / Path(item.path).with_suffix(".verify.log")
            verify_log.parent.mkdir(parents=True, exist_ok=True)
            verify_log.write_text(verdict.details)
            one_result["verification"]["details_file"] = str(verify_log)
        self._log(
            f"[id={item.id}] stage=verify done valid={one_result['verification']['valid']} "
            f"type={one_result['verification']['type']}"
        )
        return one_result


class EnhancedRequirementToCodePipeline(RequirementToCodePipeline):
    """Incremental enhancement over baseline pipeline for ablation-friendly comparison."""

    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
        spec_self_check_rounds: int = 1,
        code_repair_max_iter: int = 3,
        enable_spec_evaluation: bool = False,
        enable_constraint_extraction: bool = True,
        enable_code_repair: bool = True,
        code_repair_strategy: str = "simple",
        wybecoder_candidates: int = 3,
        reuse_artifacts_from: Optional[Path] = None,
    ):
        super().__init__(
            llm_client=llm_client,
            output_dir=output_dir,
            verify_timeout=verify_timeout,
            skip_verify=skip_verify,
            logger=logger,
        )
        self.spec_self_check_rounds = max(0, spec_self_check_rounds)
        self.code_repair_max_iter = max(0, code_repair_max_iter)
        self.enable_spec_evaluation = enable_spec_evaluation
        self.enable_constraint_extraction = enable_constraint_extraction
        self.enable_code_repair = enable_code_repair
        if code_repair_strategy not in {"simple", "wybecoder"}:
            raise ValueError(f"Unsupported code_repair_strategy: {code_repair_strategy}")
        self.code_repair_strategy = code_repair_strategy
        self.wybecoder_candidates = max(1, wybecoder_candidates)
        self.reuse_artifacts_from = reuse_artifacts_from

    def _extract_constraints(self, requirement: str, signature_hint: str = "") -> Dict[str, Any]:
        prompt = CONSTRAINT_USER_PROMPT_TEMPLATE.format(
            requirement=requirement,
            signature_hint=signature_hint,
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            CONSTRAINT_SYSTEM_PROMPT,
            prompt,
        )
        return {
            "function_signature": _clean_text(data.get("function_signature")),
            "preconditions": _as_list_of_str(data.get("preconditions")),
            "postconditions": _as_list_of_str(data.get("postconditions")),
            "invariants": _as_list_of_str(data.get("invariants")),
            "notes": _clean_text(data.get("notes")),
            "raw_model_output": raw,
        }

    def _generate_direct_spec(self, requirement: str, signature_hint: str = "") -> Dict[str, Any]:
        prompt = SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=requirement,
            signature_hint=signature_hint,
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            SPEC_SYSTEM_PROMPT,
            prompt,
        )
        data["raw_model_output"] = raw
        return data

    def _constraints_to_spec(
        self,
        requirement: str,
        constraints: Dict[str, Any],
        signature_hint: str = "",
    ) -> Dict[str, Any]:
        prompt = CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=requirement,
            constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
            signature_hint=signature_hint,
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            CONSTRAINT_TO_SPEC_SYSTEM_PROMPT,
            prompt,
        )
        data["raw_model_output"] = raw
        return data

    def _check_and_refine_spec(
        self,
        requirement: str,
        constraints: Dict[str, Any],
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        rounds: List[Dict[str, Any]] = []
        current_spec = spec_json
        final_aligned = False
        fallback_to_initial_spec = False

        for round_idx in range(1, self.spec_self_check_rounds + 1):
            check_prompt = SPEC_CHECK_USER_PROMPT_TEMPLATE.format(
                requirement=requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
            )
            check, check_raw = _chat_json_with_retries(
                self.llm_client,
                SPEC_CHECK_SYSTEM_PROMPT,
                check_prompt,
            )
            is_aligned = _to_bool(check.get("is_aligned"))
            missing_constraints = _as_list_of_str(check.get("missing_constraints"))
            inconsistent_items = _as_list_of_str(check.get("inconsistent_items"))
            refinement_hints = _as_list_of_str(check.get("refinement_hints"))
            round_info: Dict[str, Any] = {
                "round": round_idx,
                "is_aligned": is_aligned,
                "missing_constraints": missing_constraints,
                "inconsistent_items": inconsistent_items,
                "refinement_hints": refinement_hints,
                "notes": _clean_text(check.get("notes")),
                "raw_check_output": check_raw,
            }

            if is_aligned or (not missing_constraints and not inconsistent_items):
                final_aligned = True
                rounds.append(round_info)
                break

            refine_prompt = SPEC_REFINE_USER_PROMPT_TEMPLATE.format(
                requirement=requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
                check_json=json.dumps(check, ensure_ascii=False, indent=2),
            )
            refined_spec, refine_raw = _chat_json_with_retries(
                self.llm_client,
                SPEC_REFINE_SYSTEM_PROMPT,
                refine_prompt,
            )
            refined_spec["raw_model_output"] = refine_raw
            try:
                self._validate_spec_fields(refined_spec, signature_fallback=signature_fallback)
            except ValueError as exc:
                fallback_to_initial_spec = True
                round_info["refined_rejected"] = True
                round_info["rejection_reason"] = str(exc)
                rounds.append(round_info)
                break
            current_spec = refined_spec
            round_info["refined"] = True
            rounds.append(round_info)

        return current_spec, {
            "rounds": rounds,
            "final_aligned": final_aligned,
            "max_rounds": self.spec_self_check_rounds,
            "fallback_to_initial_spec": fallback_to_initial_spec,
        }

    def _validate_spec_fields(
        self,
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> tuple[str, str, str, Dict[str, List[str]], List[Dict[str, str]]]:
        function_signature = _clean_text(signature_fallback) or _clean_text(
            spec_json.get("function_signature")
        )
        acsl_block = _clean_text(spec_json.get("acsl_block"))
        code_annotation_hints = _normalize_code_annotation_hints(
            spec_json.get("code_annotation_hints")
        )
        acsl_block, code_annotation_hints, moved_loop_annotations = _sanitize_contract_and_hints(
            acsl_block,
            code_annotation_hints,
        )
        notes = _clean_text(spec_json.get("notes"))

        if not function_signature:
            raise ValueError("function_signature is empty after generation/refinement.")
        if not function_signature.endswith(";"):
            raise ValueError(f"function_signature must end with ';': {function_signature}")
        if "/*@" not in acsl_block or "*/" not in acsl_block:
            raise ValueError("acsl_block must be a full /*@ ... */ block.")
        return function_signature, acsl_block, notes, code_annotation_hints, moved_loop_annotations

    def _decompose_requirement_clauses(self, requirement: str) -> Dict[str, Any]:
        prompt = REQ_DECOMP_USER_PROMPT_TEMPLATE.format(requirement=requirement)
        data, raw = _chat_json_with_retries(
            self.llm_client,
            REQ_DECOMP_SYSTEM_PROMPT,
            prompt,
        )
        return {
            "clauses": _as_list_of_str(data.get("clauses")),
            "notes": _clean_text(data.get("notes")),
            "raw_model_output": raw,
        }

    def _extract_spec_clauses(self, function_signature: str, acsl_block: str) -> Dict[str, Any]:
        prompt = SPEC_CLAUSE_USER_PROMPT_TEMPLATE.format(
            function_signature=function_signature,
            acsl_block=acsl_block,
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            SPEC_CLAUSE_SYSTEM_PROMPT,
            prompt,
        )
        return {
            "clauses": _as_list_of_str(data.get("clauses")),
            "notes": _clean_text(data.get("notes")),
            "raw_model_output": raw,
        }

    def _judge_clause_match(self, requirement_clause: str, spec_clause: str) -> Dict[str, Any]:
        prompt = CLAUSE_MATCH_USER_PROMPT_TEMPLATE.format(
            requirement_clause=requirement_clause,
            spec_clause=spec_clause,
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            CLAUSE_MATCH_SYSTEM_PROMPT,
            prompt,
        )
        return {
            "match": _to_binary_match(data.get("match")),
            "reason": _clean_text(data.get("reason")),
            "raw_model_output": raw,
        }

    def _evaluate_spec_against_requirement(
        self, requirement: str, function_signature: str, acsl_block: str
    ) -> Dict[str, Any]:
        decomp = self._decompose_requirement_clauses(requirement)
        extracted = self._extract_spec_clauses(function_signature, acsl_block)
        req_clauses = decomp["clauses"]
        spec_clauses = extracted["clauses"]

        n = len(req_clauses)
        m = len(spec_clauses)
        matrix: List[List[int]] = []
        positive_pairs: List[Dict[str, Any]] = []

        for i, ci in enumerate(req_clauses):
            row: List[int] = []
            for j, sj in enumerate(spec_clauses):
                judge = self._judge_clause_match(requirement_clause=ci, spec_clause=sj)
                is_match = 1 if judge["match"] == 1 else 0
                row.append(is_match)
                if is_match == 1:
                    positive_pairs.append(
                        {
                            "requirement_clause_index": i,
                            "spec_clause_index": j,
                            "requirement_clause": ci,
                            "spec_clause": sj,
                            "reason": judge["reason"],
                        }
                    )
            matrix.append(row)

        matched_req_indices = sorted(
            i for i in range(n) if m > 0 and any(matrix[i][j] == 1 for j in range(m))
        )
        matched_spec_indices = sorted(
            j for j in range(m) if n > 0 and any(matrix[i][j] == 1 for i in range(n))
        )
        unmatched_req_indices = [i for i in range(n) if i not in matched_req_indices]
        unmatched_spec_indices = [j for j in range(m) if j not in matched_spec_indices]

        coverage = (len(matched_req_indices) / n) if n > 0 else 0.0
        extra = (len(unmatched_spec_indices) / m) if m > 0 else 0.0

        return {
            "enabled": True,
            "method": "llm_judge_binary",
            "requirement_decomposition": decomp,
            "spec_clause_extraction": extracted,
            "requirement_clauses": req_clauses,
            "spec_clauses": spec_clauses,
            "match_matrix": matrix,
            "positive_pairs": positive_pairs,
            "coverage": coverage,
            "extra": extra,
            "stats": {
                "n_requirement_clauses": n,
                "m_spec_clauses": m,
                "matched_requirement_clauses": len(matched_req_indices),
                "unmatched_requirement_clauses": len(unmatched_req_indices),
                "unmatched_spec_clauses": len(unmatched_spec_indices),
                "pairwise_judgements": n * m,
            },
            "matched_requirement_indices": matched_req_indices,
            "unmatched_requirement_indices": unmatched_req_indices,
            "matched_spec_indices": matched_spec_indices,
            "unmatched_spec_indices": unmatched_spec_indices,
        }

    def _build_report(self, results: List[Dict[str, Any]], total: int, processed: int) -> Dict[str, Any]:
        report = super()._build_report(results=results, total=total, processed=processed)
        eval_items = []
        for r in results:
            spec_eval = r.get("spec_evaluation")
            if not isinstance(spec_eval, dict):
                continue
            if spec_eval.get("enabled") is not True:
                continue
            if "coverage" in spec_eval and "extra" in spec_eval:
                eval_items.append(spec_eval)

        if not eval_items:
            return report

        avg_coverage = sum(float(x.get("coverage", 0.0)) for x in eval_items) / len(eval_items)
        avg_extra = sum(float(x.get("extra", 0.0)) for x in eval_items) / len(eval_items)
        report["spec_evaluation"] = {
            "method": "llm_judge_binary",
            "evaluated_tasks": len(eval_items),
            "avg_coverage": avg_coverage,
            "avg_extra": avg_extra,
        }
        return report

    def _copy_reused_artifacts(
        self,
        item: RequirementItem,
        specs_dir: Path,
        code_dir: Path,
    ) -> tuple[Path, Path, Dict[str, Any], str]:
        if self.reuse_artifacts_from is None:
            raise ValueError("reuse_artifacts_from is not configured")

        source_specs_dir = self.reuse_artifacts_from / "specs"
        source_code_dir = self.reuse_artifacts_from / "code"
        source_spec_file = source_specs_dir / Path(item.path).with_suffix(".json")
        source_code_file = source_code_dir / Path(item.path)
        if not source_spec_file.exists():
            raise FileNotFoundError(f"reused spec artifact not found: {source_spec_file}")
        if not source_code_file.exists():
            raise FileNotFoundError(f"reused code artifact not found: {source_code_file}")

        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        code_file = code_dir / Path(item.path)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_spec_file, spec_file)
        shutil.copy2(source_code_file, code_file)

        spec_out = json.loads(spec_file.read_text())
        code_text = code_file.read_text()
        return spec_file, code_file, spec_out, code_text

    def _build_simple_repair(
        self,
        item: RequirementItem,
        code_text: str,
        function_signature: str,
        acsl_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> tuple[str, Dict[str, Any]]:
        repair_prompt = CODE_REPAIR_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
            code=code_text,
            verdict_type=verdict.verdict_type.value,
            verdict_message=verdict.message,
            verdict_details=_truncate_for_prompt(details, max_chars=5000),
        )
        repaired_raw = self.llm_client.chat(CODE_REPAIR_SYSTEM_PROMPT, repair_prompt)
        return _extract_c_code(repaired_raw), {
            "strategy": "simple",
            "raw_model_output": repaired_raw,
        }

    def _wybecoder_repair_plan(
        self,
        item: RequirementItem,
        code_text: str,
        function_signature: str,
        acsl_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> Dict[str, Any]:
        plan_prompt = WYBECODER_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
            code=code_text,
            verdict_type=verdict.verdict_type.value,
            verdict_message=verdict.message,
            verdict_details=_truncate_for_prompt(details, max_chars=7000),
        )
        raw = self.llm_client.chat(WYBECODER_REPAIR_ANALYSIS_SYSTEM_PROMPT, plan_prompt)
        try:
            plan = _extract_json_object(raw)
        except Exception as exc:
            return {
                "failure_summary": "Failed to parse structured repair plan.",
                "subgoals": [
                    {
                        "name": "whole_function",
                        "kind": "unknown",
                        "evidence": verdict.message,
                        "repair_hint": "Repair the implementation and statement-level annotations.",
                    }
                ],
                "global_strategy": "Use the verifier output directly to repair the function.",
                "risk_notes": ["Repair planning output was not valid JSON."],
                "raw_model_output": raw,
                "parse_error": str(exc),
            }
        subgoals = []
        for idx, subgoal in enumerate(plan.get("subgoals", []), start=1):
            if not isinstance(subgoal, dict):
                continue
            subgoals.append(
                {
                    "name": str(subgoal.get("name", f"subgoal_{idx}")).strip()
                    or f"subgoal_{idx}",
                    "kind": str(subgoal.get("kind", "unknown")).strip() or "unknown",
                    "evidence": str(subgoal.get("evidence", "")).strip(),
                    "repair_hint": str(subgoal.get("repair_hint", "")).strip(),
                }
            )
        if not subgoals:
            subgoals = [
                {
                    "name": "whole_function",
                    "kind": "unknown",
                    "evidence": verdict.message,
                    "repair_hint": "Repair the implementation and statement-level annotations.",
                }
            ]
        return {
            "failure_summary": str(plan.get("failure_summary", "")).strip(),
            "subgoals": subgoals,
            "global_strategy": str(plan.get("global_strategy", "")).strip(),
            "risk_notes": _as_list_of_str(plan.get("risk_notes")),
            "raw_model_output": raw,
        }

    def _candidate_focuses(self, plan: Dict[str, Any]) -> List[str]:
        focuses = [
            "Synthesize all verifier-derived subgoal hints into one minimal repair."
        ]
        for subgoal in plan.get("subgoals", []):
            if not isinstance(subgoal, dict):
                continue
            name = str(subgoal.get("name", "subgoal")).strip() or "subgoal"
            kind = str(subgoal.get("kind", "unknown")).strip() or "unknown"
            hint = str(subgoal.get("repair_hint", "")).strip()
            focuses.append(f"Prioritize {name} ({kind}): {hint}")
        focuses.append(
            "Try an alternative verification-friendly implementation while preserving the frozen contract."
        )
        return focuses

    def _build_wybecoder_repair(
        self,
        item: RequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        acsl_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
        attempt: int,
    ) -> tuple[str, Any, Dict[str, Any]]:
        plan = self._wybecoder_repair_plan(
            item=item,
            code_text=code_text,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints=code_annotation_hints,
            verdict=verdict,
            details=details,
        )
        candidate_count = self.wybecoder_candidates
        focuses = self._candidate_focuses(plan)
        candidate_records: List[Dict[str, Any]] = []
        best_code = code_text
        best_verdict = verdict

        for candidate_idx in range(1, candidate_count + 1):
            focus = focuses[(candidate_idx - 1) % len(focuses)]
            self._log(
                f"[id={item.id}] stage=wybecoder_repair attempt={attempt} "
                f"candidate={candidate_idx}/{candidate_count}"
            )
            candidate_prompt = WYBECODER_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                function_signature=function_signature,
                acsl_block=acsl_block,
                code_annotation_hints_json=json.dumps(
                    code_annotation_hints,
                    ensure_ascii=False,
                    indent=2,
                ),
                code=code_text,
                repair_plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
                candidate_index=candidate_idx,
                candidate_count=candidate_count,
                candidate_focus=focus,
            )
            raw = self.llm_client.chat(
                WYBECODER_REPAIR_CANDIDATE_SYSTEM_PROMPT,
                candidate_prompt,
            )
            candidate_code = _extract_c_code(raw)
            code_file.write_text(candidate_code)
            candidate_verdict = self.verifier.verify(code_file)
            candidate_record = {
                "candidate": candidate_idx,
                "focus": focus,
                "valid": candidate_verdict.is_valid(),
                "type": candidate_verdict.verdict_type.value,
                "message": candidate_verdict.message,
                "raw_model_output": raw,
            }
            candidate_records.append(candidate_record)
            best_code = candidate_code
            best_verdict = candidate_verdict
            if candidate_verdict.is_valid():
                break

        code_file.write_text(best_code)
        return best_code, best_verdict, {
            "strategy": "wybecoder",
            "plan": plan,
            "candidates": candidate_records,
        }

    def _verify_with_optional_repair(
        self,
        item: RequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        acsl_block: str,
        code_annotation_hints: Dict[str, List[str]],
    ) -> Dict[str, Any]:
        verify_report_dir = self.output_dir / "reports"
        verify_report_dir.mkdir(parents=True, exist_ok=True)
        repair_history: List[Dict[str, Any]] = []

        self._log(f"[id={item.id}] stage=verify start")
        verdict = self.verifier.verify(code_file)

        effective_repair_max_iter = self.code_repair_max_iter if self.enable_code_repair else 0
        for attempt in range(1, effective_repair_max_iter + 1):
            if verdict.is_valid():
                break
            details = verdict.details or ""
            detail_path = (
                verify_report_dir / Path(item.path).with_suffix(f".repair{attempt - 1}.verify.log")
            )
            if details:
                detail_path.parent.mkdir(parents=True, exist_ok=True)
                detail_path.write_text(details)

            self._log(
                f"[id={item.id}] stage=code_repair attempt={attempt}/{effective_repair_max_iter} "
                f"strategy={self.code_repair_strategy} trigger_type={verdict.verdict_type.value}"
            )
            history_entry: Dict[str, Any] = {
                "attempt": attempt,
                "strategy": self.code_repair_strategy,
                "before_type": verdict.verdict_type.value,
                "before_message": verdict.message,
                "details_file": str(detail_path) if details else None,
            }
            try:
                if self.code_repair_strategy == "wybecoder":
                    code_text, verdict, strategy_info = self._build_wybecoder_repair(
                        item=item,
                        code_file=code_file,
                        code_text=code_text,
                        function_signature=function_signature,
                        acsl_block=acsl_block,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                        attempt=attempt,
                    )
                    history_entry["wybecoder"] = strategy_info
                else:
                    code_text, strategy_info = self._build_simple_repair(
                        item=item,
                        code_text=code_text,
                        function_signature=function_signature,
                        acsl_block=acsl_block,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                    )
                    code_file.write_text(code_text)
                    history_entry["simple"] = strategy_info
                    verdict = self.verifier.verify(code_file)
                history_entry["after_type"] = verdict.verdict_type.value
                history_entry["after_message"] = verdict.message
                history_entry["after_valid"] = verdict.is_valid()
            except Exception as exc:
                code_file.write_text(code_text)
                history_entry["repair_failed"] = True
                history_entry["fallback_to_unchanged_code"] = True
                history_entry["error"] = str(exc)
                history_entry["after_type"] = verdict.verdict_type.value
                history_entry["after_message"] = verdict.message
                history_entry["after_valid"] = verdict.is_valid()
                repair_history.append(history_entry)
                self._log(
                    f"[id={item.id}] stage=code_repair attempt={attempt} "
                    f"error={exc} fallback=unchanged_code"
                )
                break
            repair_history.append(history_entry)
            self._log(
                f"[id={item.id}] stage=code_repair attempt={attempt} "
                f"result_valid={verdict.is_valid()} result_type={verdict.verdict_type.value}"
            )

        verification = {
            "valid": verdict.is_valid(),
            "type": verdict.verdict_type.value,
            "message": verdict.message,
            "repair_attempts": len(repair_history),
            "code_repair_enabled": self.enable_code_repair,
            "code_repair_strategy": self.code_repair_strategy,
        }
        if repair_history:
            verification["repair_history"] = repair_history
        if verdict.details:
            verify_log = verify_report_dir / Path(item.path).with_suffix(".verify.log")
            verify_log.parent.mkdir(parents=True, exist_ok=True)
            verify_log.write_text(verdict.details)
            verification["details_file"] = str(verify_log)

        self._log(
            f"[id={item.id}] stage=verify done valid={verification['valid']} "
            f"type={verification['type']} repairs={verification['repair_attempts']}"
        )
        return verification

    def _run_one(self, item: RequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
        if self.reuse_artifacts_from is not None:
            self._log(
                f"[id={item.id}] stage=reuse_artifacts start "
                f"source={self.reuse_artifacts_from}"
            )
            spec_file, code_file, spec_out, code_text = self._copy_reused_artifacts(
                item=item,
                specs_dir=specs_dir,
                code_dir=code_dir,
            )
            function_signature = _clean_text(spec_out.get("function_signature"))
            acsl_block = _clean_text(spec_out.get("acsl_block"))
            code_annotation_hints = _normalize_code_annotation_hints(
                spec_out.get("code_annotation_hints")
            )
            if not function_signature:
                raise ValueError(f"reused spec missing function_signature: {spec_file}")
            if "/*@" not in acsl_block or "*/" not in acsl_block:
                raise ValueError(f"reused spec missing ACSL contract: {spec_file}")
            self._log(
                f"[id={item.id}] stage=reuse_artifacts done "
                f"spec_file={spec_file} code_file={code_file}"
            )

            one_result: Dict[str, Any] = {
                "spec_file": str(spec_file),
                "code_file": str(code_file),
                "enhanced": {
                    "enable_constraint_extraction": False,
                    "spec_self_check_rounds": 0,
                    "enable_code_repair": self.enable_code_repair,
                    "code_repair_max_iter": self.code_repair_max_iter,
                    "code_repair_strategy": self.code_repair_strategy,
                    "wybecoder_candidates": self.wybecoder_candidates,
                    "enable_spec_evaluation": False,
                    "reuse_artifacts_from": str(self.reuse_artifacts_from),
                    "generation_skipped_due_to_reuse": True,
                },
                "reused_artifacts": {
                    "source_output_dir": str(self.reuse_artifacts_from),
                    "source_spec_file": str(
                        self.reuse_artifacts_from / "specs" / Path(item.path).with_suffix(".json")
                    ),
                    "source_code_file": str(self.reuse_artifacts_from / "code" / Path(item.path)),
                },
                "spec_evaluation": spec_out.get(
                    "spec_evaluation",
                    {
                        "enabled": False,
                        "method": "llm_judge_binary",
                    },
                ),
            }
            if self.skip_verify:
                self._log(f"[id={item.id}] stage=verify skipped")
                return one_result

            one_result["verification"] = self._verify_with_optional_repair(
                item=item,
                code_file=code_file,
                code_text=code_text,
                function_signature=function_signature,
                acsl_block=acsl_block,
                code_annotation_hints=code_annotation_hints,
            )
            return one_result

        constraints: Optional[Dict[str, Any]] = None
        signature_fallback = item.signature_hint

        if self.enable_constraint_extraction:
            self._log(f"[id={item.id}] stage=constraint_extraction start")
            constraints = self._extract_constraints(
                item.requirement,
                signature_hint=item.signature_hint,
            )
            signature_fallback = item.signature_hint or _clean_text(
                constraints.get("function_signature")
            )
            self._log(f"[id={item.id}] stage=constraint_extraction done")

            self._log(f"[id={item.id}] stage=constraint_to_spec start")
            initial_spec = self._constraints_to_spec(
                requirement=item.requirement,
                constraints=constraints,
                signature_hint=signature_fallback,
            )
            self._log(f"[id={item.id}] stage=constraint_to_spec done")

            if self.spec_self_check_rounds > 0:
                self._log(f"[id={item.id}] stage=spec_self_check start")
                try:
                    final_spec, alignment_info = self._check_and_refine_spec(
                        requirement=item.requirement,
                        constraints=constraints,
                        spec_json=initial_spec,
                        signature_fallback=signature_fallback,
                    )
                except Exception as exc:
                    final_spec = initial_spec
                    alignment_info = {
                        "enabled": True,
                        "rounds": [],
                        "final_aligned": None,
                        "max_rounds": self.spec_self_check_rounds,
                        "fallback_to_initial_spec": True,
                        "error": str(exc),
                    }
                    self._log(
                        f"[id={item.id}] stage=spec_self_check error={exc} "
                        "fallback=initial_spec"
                    )
                self._log(
                    f"[id={item.id}] stage=spec_self_check done "
                    f"final_aligned={alignment_info.get('final_aligned')}"
                )
            else:
                final_spec = initial_spec
                alignment_info = {
                    "enabled": False,
                    "reason": "spec_self_check_rounds is 0",
                    "rounds": [],
                    "final_aligned": None,
                    "max_rounds": self.spec_self_check_rounds,
                }
                self._log(f"[id={item.id}] stage=spec_self_check skipped")
        else:
            self._log(f"[id={item.id}] stage=spec_generation start mode=direct")
            final_spec = self._generate_direct_spec(
                item.requirement,
                signature_hint=item.signature_hint,
            )
            alignment_info = {
                "enabled": False,
                "reason": "constraint extraction module disabled",
                "rounds": [],
                "final_aligned": None,
                "max_rounds": 0,
            }
            self._log(f"[id={item.id}] stage=spec_generation done mode=direct")

        (
            function_signature,
            acsl_block,
            notes,
            code_annotation_hints,
            moved_loop_annotations,
        ) = self._validate_spec_fields(
            final_spec,
            signature_fallback=signature_fallback,
        )
        if moved_loop_annotations:
            self._log(
                f"[id={item.id}] stage=spec_generation moved_loop_annotations="
                f"{len(moved_loop_annotations)}"
            )

        spec_evaluation: Dict[str, Any]
        if self.enable_spec_evaluation:
            self._log(f"[id={item.id}] stage=spec_evaluation start")
            try:
                spec_evaluation = self._evaluate_spec_against_requirement(
                    requirement=item.requirement,
                    function_signature=function_signature,
                    acsl_block=acsl_block,
                )
                self._log(
                    f"[id={item.id}] stage=spec_evaluation done "
                    f"coverage={spec_evaluation.get('coverage', 0.0):.3f} "
                    f"extra={spec_evaluation.get('extra', 0.0):.3f}"
                )
            except Exception as exc:
                spec_evaluation = {
                    "enabled": True,
                    "method": "llm_judge_binary",
                    "error": str(exc),
                }
                self._log(f"[id={item.id}] stage=spec_evaluation error={exc}")
        else:
            spec_evaluation = {
                "enabled": False,
                "method": "llm_judge_binary",
            }

        spec_out = {
            "id": item.id,
            "path": item.path,
            "requirement": item.requirement,
            "function_signature": function_signature,
            "acsl_block": acsl_block,
            "code_annotation_hints": code_annotation_hints,
            "moved_loop_annotations": moved_loop_annotations,
            "notes": notes,
            "constraints": constraints,
            "alignment_check": alignment_info,
            "spec_evaluation": spec_evaluation,
            "raw_model_output": final_spec.get("raw_model_output", ""),
            "enhanced_modules": {
                "constraint_extraction": self.enable_constraint_extraction,
                "spec_self_check_rounds": (
                    self.spec_self_check_rounds if self.enable_constraint_extraction else 0
                ),
                "code_repair": self.enable_code_repair,
                "code_repair_max_iter": (
                    self.code_repair_max_iter if self.enable_code_repair else 0
                ),
                "code_repair_strategy": self.code_repair_strategy,
                "wybecoder_candidates": (
                    self.wybecoder_candidates
                    if self.enable_code_repair and self.code_repair_strategy == "wybecoder"
                    else 0
                ),
                "spec_evaluation": self.enable_spec_evaluation,
            },
        }
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_out, ensure_ascii=False, indent=2))
        self._log(f"[id={item.id}] stage=spec_generation done spec_file={spec_file}")

        self._log(f"[id={item.id}] stage=code_generation start")
        code_prompt = CODE_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
        )
        code_raw = self.llm_client.chat(CODE_SYSTEM_PROMPT, code_prompt)
        code_text = _extract_c_code(code_raw)
        code_file = code_dir / Path(item.path)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text(code_text)
        self._log(f"[id={item.id}] stage=code_generation done code_file={code_file}")

        one_result: Dict[str, Any] = {
            "spec_file": str(spec_file),
            "code_file": str(code_file),
            "enhanced": {
                "enable_constraint_extraction": self.enable_constraint_extraction,
                "spec_self_check_rounds": self.spec_self_check_rounds,
                "enable_code_repair": self.enable_code_repair,
                "code_repair_max_iter": self.code_repair_max_iter,
                "code_repair_strategy": self.code_repair_strategy,
                "wybecoder_candidates": self.wybecoder_candidates,
                "enable_spec_evaluation": self.enable_spec_evaluation,
            },
            "spec_evaluation": spec_evaluation,
        }
        if self.skip_verify:
            self._log(f"[id={item.id}] stage=verify skipped")
            return one_result

        one_result["verification"] = self._verify_with_optional_repair(
            item=item,
            code_file=code_file,
            code_text=code_text,
            function_signature=function_signature,
            acsl_block=acsl_block,
            code_annotation_hints=code_annotation_hints,
        )
        return one_result
