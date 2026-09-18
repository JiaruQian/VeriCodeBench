"""Pipeline: requirement -> JML specification -> Java code -> OpenJML verification."""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..llm.openai_compatible import OpenAICompatibleClient
from ..verifier.openjml import OpenJMLVerifier


JAVA_SPEC_SYSTEM_PROMPT = """You are an expert in JML specification design for Java code.
Return strict JSON only."""

JAVA_SPEC_USER_PROMPT_TEMPLATE = """Given the Java requirement below, design a minimal but useful JML method specification.

Requirement:
{requirement}

Required Java class name:
{class_name}

Function signature hint:
{signature_hint}

Fixed Java type context (use exactly; "(none)" when not needed):
{type_context}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Java method signature without body, e.g. public static int f(int[] a);",
    "jml_block": "A full JML block in /*@ ... @*/ format for the method.",
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_assigns": ["Optional loop_assigns candidates for code generation only."],
      "loop_variants": ["Optional decreases candidates for code generation only."]
    }},
    "helper_declarations": "Optional nested helper classes or model declarations needed by the method.",
    "notes": "Very short rationale."
  }}
- Prefer the signature hint when it is provided.
- When type context is provided, preserve its field names, visibility, and direct field access exactly. Do not replace fields with getters/setters or invent an alternative helper API.
- Use OpenJML-compatible JML. Include requires, assignable, ensures, and exceptional behavior when needed.
- Keep independent preconditions and postconditions as separate JML clauses. Use the narrowest frame allowed by the requirement; do not widen an element/range frame to the whole array.
- The JML block is a method contract only. Put loop annotations only in code_annotation_hints.
- Use Java integer overflow preconditions when arithmetic could overflow.
- Do not include the Java method body in this JSON.
"""

JAVA_CONSTRAINT_SYSTEM_PROMPT = """You are an expert in translating Java requirements into verification constraints.
Return strict JSON only."""

JAVA_CONSTRAINT_USER_PROMPT_TEMPLATE = """Extract structured verification constraints from the Java requirement.

Requirement:
{requirement}

Required Java class name:
{class_name}

Function signature hint:
{signature_hint}

Fixed Java type context (use exactly; "(none)" when not needed):
{type_context}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Best-effort Java method signature without body; end with ';'. Prefer the hint if present.",
    "preconditions": ["..."],
    "postconditions": ["..."],
    "frame_conditions": ["..."],
    "exceptional_behaviors": ["..."],
    "invariants": ["..."],
    "helper_declarations": "Optional nested helper classes needed by the method.",
    "notes": "Very short rationale."
  }}
- Keep each constraint atomic and testable.
- Include nullability, bounds, frame, object invariant, integer overflow, and exception constraints when relevant.
- When type context is provided, preserve its exact field names and direct field access. Do not invent getters, setters, replacement field names, or a different helper representation.
- Preserve the narrowest mutation frame stated by the requirement (individual fields/elements/ranges rather than the whole object or array).
"""

JAVA_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT = """You are an expert JML specification engineer.
Convert Java verification constraints into a complete OpenJML-compatible JML contract. Return strict JSON only."""

JAVA_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE = """Create JML spec JSON using requirement + structured constraints.

Requirement:
{requirement}

Required Java class name:
{class_name}

Structured constraints (JSON):
{constraints_json}

Function signature hint:
{signature_hint}

Fixed Java type context (use exactly; "(none)" when not needed):
{type_context}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Java method signature without body, e.g. public static int f(int[] a);",
    "jml_block": "A full JML block in /*@ ... @*/ format for the method.",
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_assigns": ["Optional loop_assigns candidates for code generation only."],
      "loop_variants": ["Optional decreases candidates for code generation only."]
    }},
    "helper_declarations": "Optional nested helper classes or model declarations needed by the method.",
    "notes": "Very short rationale."
  }}
- Prefer the signature hint when it is provided.
- When type context is provided, copy it verbatim into helper_declarations and use its exact fields in JML. Do not invent getters/setters or rename fields.
- Include requires, assignable, ensures, and exceptional behavior when needed.
- Emit independent constraints as separate JML clauses and keep frames as narrow as the structured constraints permit.
- The JML block is a method contract only. Put loop annotations only in code_annotation_hints.
- Use OpenJML-compatible syntax: assignable, signals_only, signals, \\old, \\result, \\forall, \\exists.
- Avoid OpenJML-fragile clauses: do not use accessible, reads, pure normal_behavior, signals_only \\nothing, signals false, signals (Exception e) false, or unsupported operators such as \\numof.
"""

JAVA_SPEC_CHECK_SYSTEM_PROMPT = """You are a strict Java requirement/JML-spec alignment reviewer.
Return strict JSON only."""

JAVA_SPEC_CHECK_USER_PROMPT_TEMPLATE = """Check whether the generated JML specification misses Java requirement constraints.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Generated specification (JSON):
{spec_json}

Fixed Java type context:
{type_context}

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
- Reject renamed helper fields/accessors, widened mutation frames, combined constraints that obscure atomic requirements, and conditional weakenings of unconditional requirements.
"""

JAVA_SPEC_REFINE_SYSTEM_PROMPT = """You refine JML specs to improve Java requirement alignment.
Return strict JSON only."""

JAVA_SPEC_REFINE_USER_PROMPT_TEMPLATE = """Refine the generated JML specification based on alignment findings.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Current specification (JSON):
{spec_json}

Alignment findings (JSON):
{check_json}

Fixed Java type context:
{type_context}

Output constraints (IMPORTANT):
- Return valid JSON only.
- Same schema:
  {{
    "function_signature": "...",
    "jml_block": "/*@ ... @*/",
    "code_annotation_hints": {{
      "loop_invariants": ["..."],
      "loop_assigns": ["..."],
      "loop_variants": ["..."]
    }},
    "helper_declarations": "...",
    "notes": "..."
  }}
- Keep jml_block as a method contract only. Move loop annotations to code_annotation_hints.
- Preserve exact type-context field names/direct access, atomic clauses, narrow frames, and unconditional requirement guarantees.
- Do not add accessible/read-frame clauses, pure normal_behavior modifiers, no-exception signals clauses in normal cases, or unsupported operators such as \\numof.
"""

JAVA_CODE_SYSTEM_PROMPT = """You are an expert Java developer writing OpenJML-friendly code.
Output Java source code only."""

JAVA_CODE_USER_PROMPT_TEMPLATE = """Implement one complete Java source file from the requirement and JML specification.

Requirement:
{requirement}

Required public class name:
{class_name}

Method signature:
{function_signature}

JML method contract (must remain directly above the method):
{jml_block}

Helper declarations to include inside the class if needed:
{helper_declarations}

Code annotation hints for the method body (JSON; optional):
{code_annotation_hints_json}

Output constraints:
- Output only complete Java source code (no markdown fences, no explanation).
- The file must define exactly one public top-level class named {class_name}.
- Put helper declarations, if any, inside that class.
- Keep the JML method contract directly above the method.
- Do not change the JML method contract.
- Do not add a main method.
- Use simple Java 21 code and avoid external libraries.
- Insert loop invariants, loop_assigns, and decreases annotations before loops when needed for OpenJML.
"""

JAVA_REPAIR_SYSTEM_PROMPT = """You are an expert Java/OpenJML developer fixing code to satisfy JML verification.
Output Java source code only."""

JAVA_REPAIR_USER_PROMPT_TEMPLATE = """Fix the Java source so that it satisfies the requirement and JML specification.

Requirement:
{requirement}

Required public class name:
{class_name}

Method signature:
{function_signature}

JML method contract:
{jml_block}

Code annotation hints for the method body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

OpenJML result:
- type: {verdict_type}
- message: {verdict_message}
- details:
{verdict_details}

Output constraints:
- Output only complete Java source code (no markdown fences, no explanation).
- Define exactly one public top-level class named {class_name}.
- Keep the JML method contract directly above the method.
- Do not change the method contract.
- Fix only Java implementation code, helper declarations, and loop annotations.
- Prefer minimal, OpenJML-friendly fixes.
"""

JAVA_VGCR_REPAIR_ANALYSIS_SYSTEM_PROMPT = """You are a verification-guided Java/JML repair planner.
Return strict JSON only."""

JAVA_VGCR_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze a failed OpenJML verification attempt and produce a repair plan.

Requirement:
{requirement}

Required public class name:
{class_name}

Method signature:
{function_signature}

Frozen JML method contract:
{jml_block}

Code annotation hints for the method body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

OpenJML result:
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
        "kind": "syntax|contract_placement|null_safety|bounds_safety|postcondition|exceptional_behavior|frame|loop_invariant|loop_assigns|loop_variant|overflow|timeout|unknown",
        "evidence": "Relevant OpenJML clue.",
        "repair_hint": "Concrete body/helper/loop-annotation change to try."
      }}
    ],
    "global_strategy": "How to synthesize the fixes while preserving the method contract.",
    "risk_notes": ["Potential ways a repair could cheat or weaken semantics."]
  }}
- Treat the JML method contract as frozen. Do not suggest weakening or replacing it.
- Prefer Java body changes, helper code, and statement-level loop annotations.
"""

JAVA_VGCR_REPAIR_CANDIDATE_SYSTEM_PROMPT = """You are an expert Java/OpenJML developer using prove-as-you-generate repair.
Output Java source code only."""

JAVA_VGCR_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE = """Repair the Java implementation using this verifier-derived plan.

Requirement:
{requirement}

Required public class name:
{class_name}

Method signature:
{function_signature}

Frozen JML method contract (must remain directly above the method):
{jml_block}

Code annotation hints for the method body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verifier-derived repair plan (JSON):
{repair_plan_json}

Candidate policy:
- This is candidate {candidate_index} of {candidate_count}.
- Candidate focus: {candidate_focus}

Output constraints:
- Output only complete Java source code (no markdown fences, no explanation).
- Define exactly one public top-level class named {class_name}.
- Keep the frozen JML method contract directly above the method.
- Do not change, weaken, reorder into a different contract, or delete clauses from the JML block.
- You may change method body logic, helper code, and statement-level loop annotations.
- Prefer explicit loops, simple mutable variables, and OpenJML-friendly control flow.
- Avoid hiding the algorithm in library calls or changing the specification to make proof easier.
"""


@dataclass
class JavaRequirementItem:
    id: int
    path: str
    requirement: str
    class_name: str
    signature_hint: str = ""
    type_context: str = ""


def _extract_json_object(text: str) -> Dict[str, Any]:
    stripped = text.strip()
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


def _extract_java_code(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:java)?\n([\s\S]*?)\n```", stripped)
    if fenced:
        return fenced.group(1).strip()
    class_match = re.search(r"\bpublic\s+class\s+[A-Za-z_][A-Za-z0-9_]*\b", stripped)
    if class_match:
        start = class_match.start()
        brace_start = stripped.find("{", class_match.end())
        if brace_start >= 0:
            depth = 0
            in_string: Optional[str] = None
            escaped = False
            for idx in range(brace_start, len(stripped)):
                ch = stripped[idx]
                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == in_string:
                        in_string = None
                    continue
                if ch in {"'", '"'}:
                    in_string = ch
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return stripped[start : idx + 1].strip()
    return stripped


def _sanitize_java_jml_block(jml_block: str) -> tuple[str, List[str]]:
    changes: List[str] = []
    lines = jml_block.splitlines()
    sanitized_lines: List[str] = []
    clause_buffer: List[str] = []

    def clause_text(buffer: List[str]) -> str:
        text = "\n".join(buffer)
        text = re.sub(r"/\*@", "", text)
        text = re.sub(r"@\*/", "", text)
        text = re.sub(r"(?m)^\s*\*?\s*@?\s*", "", text)
        return text.strip()

    def flush_clause() -> None:
        nonlocal clause_buffer
        if not clause_buffer:
            return
        text = clause_text(clause_buffer)
        lowered = text.lower()
        if lowered.startswith(("accessible ", "reads ")):
            changes.append("removed read-frame clause")
            clause_buffer = []
            return
        if lowered in {
            "signals_only \\nothing;",
            "signals false;",
            "signals (exception e) false;",
        }:
            changes.append("removed no-exception signals clause")
            clause_buffer = []
            return
        if "\\numof" in text:
            changes.append("removed unsupported \\numof clause")
            clause_buffer = []
            return
        sanitized_lines.extend(clause_buffer)
        clause_buffer = []

    for line in lines:
        text = clause_text([line])
        if re.search(r"\b(public\s+|protected\s+|private\s+)?pure\s+normal_behavior\b", text):
            line = line.replace("pure normal_behavior", "normal_behavior")
            changes.append("removed pure modifier from normal_behavior")
        clause_buffer.append(line)
        if text.endswith(";") or text in {"/*@", "@*/"} or "*/" in line:
            flush_clause()
    flush_clause()
    return "\n".join(sanitized_lines).strip(), changes


def _sanitize_code_annotation_hints(
    hints: Dict[str, List[str]],
) -> tuple[Dict[str, List[str]], List[str]]:
    changes: List[str] = []
    sanitized = {key: list(values) for key, values in hints.items()}
    variants: List[str] = []
    for item in sanitized.get("loop_variants", []):
        cleaned = re.sub(r"^\s*(decreases|loop_decreases)\s+", "", item).strip()
        cleaned = cleaned.rstrip(";").strip()
        if cleaned != item:
            changes.append("normalized loop variant hint")
        if cleaned:
            variants.append(cleaned)
    sanitized["loop_variants"] = variants

    assigns: List[str] = []
    for item in sanitized.get("loop_assigns", []):
        cleaned = re.sub(r"^\s*(assignable|loop_assigns|loop_assignable)\s+", "", item).strip()
        cleaned = cleaned.rstrip(";").strip()
        if cleaned != item:
            changes.append("normalized loop assigns hint")
        if cleaned:
            assigns.append(cleaned)
    sanitized["loop_assigns"] = assigns
    return sanitized, changes


def _sanitize_generated_java_code(code_text: str) -> tuple[str, List[str]]:
    changes: List[str] = []
    sanitized = code_text

    def rewrite_block(match: re.Match[str]) -> str:
        nonlocal changes
        block = match.group(0)
        suffix = sanitized[match.end() : match.end() + 120]
        if "for" not in suffix and "while" not in suffix:
            return block
        updated = re.sub(r"(?m)^(\s*(?:@\s*)?)assignable\b", r"\1loop_assigns", block)
        updated = re.sub(r"(?m)^(\s*(?:@\s*)?)decreases\b", r"\1loop_decreases", updated)
        updated = re.sub(r"(?m)^(\s*(?:@\s*)?)maintaining\b", r"\1loop_invariant", updated)
        if updated != block:
            changes.append("rewrote Java block loop annotation keywords")
        return updated

    sanitized = re.sub(r"/\*@[\s\S]*?@\*/", rewrite_block, sanitized)

    line_replacements = [
        (r"(?m)^(\s*//@\s*)assignable\b", r"\1loop_assigns"),
        (r"(?m)^(\s*//@\s*)decreases\b", r"\1loop_decreases"),
        (r"(?m)^(\s*//@\s*)maintaining\b", r"\1loop_invariant"),
    ]
    for pattern, repl in line_replacements:
        updated = re.sub(pattern, repl, sanitized)
        if updated != sanitized:
            changes.append("rewrote Java line loop annotation keyword")
            sanitized = updated
    return sanitized, changes


def _method_name_from_signature(signature: str) -> str:
    header = signature.strip().rstrip(";")
    paren_idx = header.find("(")
    if paren_idx < 0:
        raise ValueError(f"method signature has no parameter list: {signature}")
    prefix = header[:paren_idx].strip()
    names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", prefix)
    if not names:
        raise ValueError(f"method name missing in signature: {signature}")
    return names[-1]


def _find_method_declaration_start(code: str, method_name: str) -> int:
    pattern = re.compile(rf"\b{re.escape(method_name)}\s*\(")
    for match in pattern.finditer(code):
        line_start = code.rfind("\n", 0, match.start()) + 1
        line_prefix = code[line_start:match.start()]
        if "=" in line_prefix or "." in line_prefix:
            continue
        brace_idx = code.find("{", match.end())
        semicolon_idx = code.find(";", match.end())
        next_newline_idx = code.find("\n", match.end())
        if brace_idx < 0:
            continue
        if semicolon_idx >= 0 and semicolon_idx < brace_idx:
            continue
        if next_newline_idx >= 0 and next_newline_idx < brace_idx:
            declaration = code[line_start:brace_idx]
            if ")" not in declaration:
                continue
        return line_start
    raise ValueError(f"method declaration not found for generated method '{method_name}'")


def _normalize_contract_for_compare(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _enforce_jml_contract(
    code_text: str,
    function_signature: str,
    jml_block: str,
) -> tuple[str, Dict[str, Any]]:
    method_name = _method_name_from_signature(function_signature)
    method_start = _find_method_declaration_start(code_text, method_name)
    contract_start: Optional[int] = None
    contract_end = method_start

    while True:
        before_contract = code_text[:contract_end]
        contract_match: Optional[re.Match[str]] = None
        for match in re.finditer(r"/\*@[\s\S]*?\*/\s*", before_contract):
            if code_text[match.end() : contract_end].strip():
                continue
            contract_match = match
        if not contract_match:
            break
        contract_start = contract_match.start()
        contract_end = contract_match.start()

    canonical_block = jml_block.strip() + "\n"
    if contract_start is not None:
        previous_contract = code_text[contract_start:method_start].strip()
        changed = _normalize_contract_for_compare(previous_contract) != _normalize_contract_for_compare(
            jml_block
        )
        enforced = (
            code_text[:contract_start]
            + canonical_block
            + code_text[method_start:]
        )
        action = "replaced"
    else:
        changed = True
        enforced = code_text[:method_start] + canonical_block + code_text[method_start:]
        action = "inserted"

    return enforced, {
        "method_name": method_name,
        "action": action,
        "changed": changed,
    }


def _as_list_of_str(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if isinstance(value, (int, float)):
        return value != 0
    return False


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
        "loop_assigns": ["loop_assigns", "assigns", "loop_assignable"],
        "loop_variants": ["loop_variants", "variants", "decreases"],
    }
    for canonical, keys in aliases.items():
        for key in keys:
            hints[canonical].extend(_as_list_of_str(value.get(key)))
    return hints


def _truncate_for_prompt(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


def _class_name_from_path(path: str) -> str:
    return Path(path).stem


def _load_resume_results(reports_dir: Path) -> Dict[int, Dict[str, Any]]:
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
            if item.get("status") == "ok" and "id" in item
        }
    return {}


def load_java_requirements(
    requirements_file: Path,
    signature_file: Optional[Path] = None,
) -> List[JavaRequirementItem]:
    """Load Java requirements and optional dataset-provided interface hints."""
    signature_by_id: Dict[int, str] = {}
    type_context_by_id: Dict[int, str] = {}
    if signature_file and signature_file.exists():
        raw_sigs = json.loads(signature_file.read_text())
        if isinstance(raw_sigs, list):
            for row in raw_sigs:
                try:
                    row_id = int(row["id"])
                    signature_by_id[row_id] = str(row.get("function_signature", "")).strip()
                    type_context_by_id[row_id] = str(row.get("type_context", "")).strip()
                except Exception:
                    continue

    raw = json.loads(requirements_file.read_text())
    items: List[JavaRequirementItem] = []
    for obj in raw:
        if "id" not in obj or "path" not in obj:
            raise ValueError(f"Invalid requirement entry: {obj}")
        req_text = obj.get("requirement_zh") or obj.get("requirement_en") or obj.get("requirement")
        if not req_text:
            raise ValueError(f"Requirement text missing for entry: {obj}")
        rid = int(obj["id"])
        rel_path = str(obj["path"])
        items.append(
            JavaRequirementItem(
                id=rid,
                path=rel_path,
                requirement=str(req_text),
                class_name=str(obj.get("class_name") or _class_name_from_path(rel_path)),
                signature_hint=str(obj.get("function_signature") or signature_by_id.get(rid, "")),
                type_context=str(obj.get("type_context") or type_context_by_id.get(rid, "")),
            )
        )
    return items


class JavaRequirementToCodePipeline:
    """End-to-end Java/JML/OpenJML generation pipeline."""

    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
        openjml_bin: str = "openjml",
        openjml_solver: Optional[str] = None,
        enable_cgs: bool = True,
        spec_self_check_rounds: int = 1,
        enable_code_repair: bool = True,
        code_repair_max_iter: int = 3,
        code_repair_strategy: str = "simple",
        vgcr_candidates: int = 3,
        reuse_artifacts_from: Optional[Path] = None,
    ):
        self.llm_client = llm_client
        self.output_dir = output_dir
        self.skip_verify = skip_verify
        self.logger = logger
        self.verifier = OpenJMLVerifier(
            timeout=verify_timeout,
            openjml_cmd=openjml_bin,
            solver=openjml_solver,
        )
        self.enable_cgs = enable_cgs
        self.spec_self_check_rounds = max(0, spec_self_check_rounds)
        self.enable_code_repair = enable_code_repair
        self.code_repair_max_iter = max(0, code_repair_max_iter)
        if code_repair_strategy not in {"simple", "vgcr"}:
            raise ValueError(f"Unsupported code_repair_strategy: {code_repair_strategy}")
        self.code_repair_strategy = code_repair_strategy
        self.vgcr_candidates = max(1, vgcr_candidates)
        self.reuse_artifacts_from = reuse_artifacts_from

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)

    def run(self, requirements: List[JavaRequirementItem], resume: bool = False) -> Dict[str, Any]:
        specs_dir = self.output_dir / "specs"
        code_dir = self.output_dir / "code"
        reports_dir = self.output_dir / "reports"
        specs_dir.mkdir(parents=True, exist_ok=True)
        code_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        resume_results = _load_resume_results(reports_dir) if resume else {}
        results: List[Dict[str, Any]] = []
        total = len(requirements)
        for idx, item in enumerate(requirements, start=1):
            self._log("=" * 72)
            self._log(f"[TASK {idx}/{total}] id={item.id} path={item.path}")
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
                except Exception as exc:
                    result["status"] = "error"
                    result["error"] = str(exc)
                    self._log(f"[TASK {idx}/{total}] status=error error={exc}")
                results.append(result)

            interim = self._build_report(results, total=total, processed=idx)
            partial_path = reports_dir / "results.partial.json"
            partial_path.write_text(json.dumps(interim, ensure_ascii=False, indent=2))

        report = self._build_report(results, total=total, processed=len(results))
        report_path = reports_dir / "results.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        self._log("=" * 72)
        self._log(
            f"[DONE] total={report['total']} processed={report['processed']} "
            f"verified={report['verified']} passed={report['passed']}"
        )
        self._log(f"[DONE] report={report_path}")
        return {"report_path": str(report_path), "report": report}

    def _build_report(self, results: List[Dict[str, Any]], total: int, processed: int) -> Dict[str, Any]:
        verified = sum(1 for r in results if "verification" in r)
        passed = sum(1 for r in results if r.get("verification", {}).get("valid") is True)
        return {
            "language": "java",
            "verifier": "openjml",
            "enhanced_modules": {
                "cgs": self.enable_cgs,
                "spec_self_check_rounds": (
                    self.spec_self_check_rounds if self.enable_cgs else 0
                ),
                "code_repair": self.enable_code_repair,
                "code_repair_max_iter": (
                    self.code_repair_max_iter if self.enable_code_repair else 0
                ),
                "code_repair_strategy": self.code_repair_strategy,
                "vgcr_candidates": (
                    self.vgcr_candidates
                    if self.enable_code_repair and self.code_repair_strategy == "vgcr"
                    else 0
                ),
                "reuse_artifacts_from": str(self.reuse_artifacts_from)
                if self.reuse_artifacts_from is not None
                else None,
            },
            "total": total,
            "processed": processed,
            "verified": verified,
            "passed": passed,
            "results": results,
        }

    def _extract_constraints(self, item: JavaRequirementItem) -> Dict[str, Any]:
        prompt = JAVA_CONSTRAINT_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            signature_hint=item.signature_hint or "(none)",
            type_context=item.type_context or "(none)",
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            JAVA_CONSTRAINT_SYSTEM_PROMPT,
            prompt,
        )
        return {
            "function_signature": str(data.get("function_signature", "")).strip(),
            "preconditions": _as_list_of_str(data.get("preconditions")),
            "postconditions": _as_list_of_str(data.get("postconditions")),
            "frame_conditions": _as_list_of_str(data.get("frame_conditions")),
            "exceptional_behaviors": _as_list_of_str(data.get("exceptional_behaviors")),
            "invariants": _as_list_of_str(data.get("invariants")),
            "helper_declarations": str(data.get("helper_declarations", "")).strip(),
            "notes": str(data.get("notes", "")).strip(),
            "raw_model_output": raw,
        }

    def _generate_direct_spec(self, item: JavaRequirementItem) -> Dict[str, Any]:
        prompt = JAVA_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            signature_hint=item.signature_hint or "(none)",
            type_context=item.type_context or "(none)",
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            JAVA_SPEC_SYSTEM_PROMPT,
            prompt,
        )
        data["raw_model_output"] = raw
        return data

    def _constraints_to_spec(
        self,
        item: JavaRequirementItem,
        constraints: Dict[str, Any],
        signature_hint: str,
    ) -> Dict[str, Any]:
        prompt = JAVA_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
            signature_hint=signature_hint or "(none)",
            type_context=item.type_context or "(none)",
        )
        data, raw = _chat_json_with_retries(
            self.llm_client,
            JAVA_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT,
            prompt,
        )
        data["raw_model_output"] = raw
        return data

    def _check_and_refine_spec(
        self,
        item: JavaRequirementItem,
        constraints: Dict[str, Any],
        spec_json: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        rounds: List[Dict[str, Any]] = []
        current_spec = spec_json
        final_aligned = False

        for round_idx in range(1, self.spec_self_check_rounds + 1):
            check_prompt = JAVA_SPEC_CHECK_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
                type_context=item.type_context or "(none)",
            )
            check, check_raw = _chat_json_with_retries(
                self.llm_client,
                JAVA_SPEC_CHECK_SYSTEM_PROMPT,
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
                "notes": str(check.get("notes", "")).strip(),
                "raw_check_output": check_raw,
            }
            if is_aligned or (not missing_constraints and not inconsistent_items):
                final_aligned = True
                rounds.append(round_info)
                break

            refine_prompt = JAVA_SPEC_REFINE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
                check_json=json.dumps(check, ensure_ascii=False, indent=2),
                type_context=item.type_context or "(none)",
            )
            current_spec, refine_raw = _chat_json_with_retries(
                self.llm_client,
                JAVA_SPEC_REFINE_SYSTEM_PROMPT,
                refine_prompt,
            )
            current_spec["raw_model_output"] = refine_raw
            round_info["refined"] = True
            rounds.append(round_info)

        return current_spec, {
            "rounds": rounds,
            "final_aligned": final_aligned,
            "max_rounds": self.spec_self_check_rounds,
        }

    def _validate_spec_fields(
        self,
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
        helper_fallback: str = "",
    ) -> tuple[str, str, str, Dict[str, List[str]], str]:
        function_signature = signature_fallback.strip() or str(
            spec_json.get("function_signature", "")
        ).strip()
        jml_block = str(spec_json.get("jml_block") or spec_json.get("acsl_block") or "").strip()
        notes = str(spec_json.get("notes", "")).strip()
        code_annotation_hints = _normalize_code_annotation_hints(
            spec_json.get("code_annotation_hints")
        )
        jml_block, _ = _sanitize_java_jml_block(jml_block)
        code_annotation_hints, _ = _sanitize_code_annotation_hints(code_annotation_hints)
        helper_declarations = (
            helper_fallback.strip()
            or str(spec_json.get("helper_declarations", "")).strip()
        )

        if not function_signature:
            raise ValueError("function_signature is empty after generation/refinement.")
        if not function_signature.endswith(";"):
            raise ValueError(f"function_signature must end with ';': {function_signature}")
        if "/*@" not in jml_block or "*/" not in jml_block:
            raise ValueError("jml_block must be a full /*@ ... */ block.")
        return function_signature, jml_block, notes, code_annotation_hints, helper_declarations

    def _copy_reused_artifacts(
        self,
        item: JavaRequirementItem,
        specs_dir: Path,
        code_dir: Path,
    ) -> tuple[Path, Path, Dict[str, Any], str, Dict[str, Any]]:
        if self.reuse_artifacts_from is None:
            raise ValueError("reuse_artifacts_from is not configured")

        source_spec_file = self.reuse_artifacts_from / "specs" / Path(item.path).with_suffix(".json")
        source_code_file = self.reuse_artifacts_from / "code" / Path(item.path)
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
        function_signature = str(spec_out.get("function_signature", "")).strip()
        jml_block = str(spec_out.get("jml_block") or spec_out.get("acsl_block") or "").strip()
        if not function_signature:
            raise ValueError(f"reused spec missing function_signature: {spec_file}")
        if "/*@" not in jml_block or "*/" not in jml_block:
            raise ValueError(f"reused spec missing JML contract: {spec_file}")

        code_text = code_file.read_text()
        code_text, contract_enforcement = _enforce_jml_contract(
            code_text=code_text,
            function_signature=function_signature,
            jml_block=jml_block,
        )
        code_file.write_text(code_text)
        return spec_file, code_file, spec_out, code_text, contract_enforcement

    def _run_one(self, item: JavaRequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
        if self.reuse_artifacts_from is not None:
            self._log(
                f"[id={item.id}] stage=reuse_artifacts start "
                f"source={self.reuse_artifacts_from}"
            )
            spec_file, code_file, spec_out, code_text, contract_enforcement = self._copy_reused_artifacts(
                item=item,
                specs_dir=specs_dir,
                code_dir=code_dir,
            )
            function_signature = str(spec_out.get("function_signature", "")).strip()
            jml_block = str(spec_out.get("jml_block") or spec_out.get("acsl_block") or "").strip()
            code_annotation_hints = _normalize_code_annotation_hints(
                spec_out.get("code_annotation_hints")
            )
            self._log(
                f"[id={item.id}] stage=reuse_artifacts done "
                f"spec_file={spec_file} code_file={code_file}"
            )
            result: Dict[str, Any] = {
                "spec_file": str(spec_file),
                "code_file": str(code_file),
                "contract_enforcement": {
                    "enabled": True,
                    "initial_generation": None,
                    "reuse": contract_enforcement,
                    "repair_attempts": [],
                },
                "enhanced": {
                    "enable_cgs": False,
                    "spec_self_check_rounds": 0,
                    "enable_code_repair": self.enable_code_repair,
                    "code_repair_max_iter": self.code_repair_max_iter,
                    "code_repair_strategy": self.code_repair_strategy,
                    "vgcr_candidates": self.vgcr_candidates,
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
            }
            if self.skip_verify:
                self._log(f"[id={item.id}] stage=verify skipped")
                return result

            self._verify_with_optional_repair(
                item=item,
                code_file=code_file,
                code_text=code_text,
                function_signature=function_signature,
                jml_block=jml_block,
                code_annotation_hints=code_annotation_hints,
                result=result,
            )
            return result

        constraints: Optional[Dict[str, Any]] = None
        signature_fallback = item.signature_hint
        helper_fallback = item.type_context

        if self.enable_cgs:
            self._log(f"[id={item.id}] stage=cgs start")
            constraints = self._extract_constraints(item)
            signature_fallback = item.signature_hint or constraints.get("function_signature", "")
            helper_fallback = item.type_context or constraints.get("helper_declarations", "")
            self._log(f"[id={item.id}] stage=cgs done")

            self._log(f"[id={item.id}] stage=constraint_to_spec start")
            initial_spec = self._constraints_to_spec(
                item=item,
                constraints=constraints,
                signature_hint=signature_fallback,
            )
            self._log(f"[id={item.id}] stage=constraint_to_spec done")

            if self.spec_self_check_rounds > 0:
                self._log(f"[id={item.id}] stage=spec_self_check start")
                try:
                    spec_json, alignment_info = self._check_and_refine_spec(
                        item=item,
                        constraints=constraints,
                        spec_json=initial_spec,
                    )
                    try:
                        self._validate_spec_fields(
                            spec_json,
                            signature_fallback=signature_fallback,
                            helper_fallback=helper_fallback,
                        )
                    except ValueError as validation_exc:
                        spec_json = initial_spec
                        alignment_info["fallback_to_initial_spec"] = True
                        alignment_info["validation_error"] = str(validation_exc)
                        self._log(
                            f"[id={item.id}] stage=spec_self_check "
                            f"validation_error={validation_exc} fallback=initial_spec"
                        )
                except Exception as exc:
                    spec_json = initial_spec
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
                spec_json = initial_spec
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
            spec_json = self._generate_direct_spec(item)
            alignment_info = {
                "enabled": False,
                "reason": "constraint-guided specification (CGS) module disabled",
                "rounds": [],
                "final_aligned": None,
                "max_rounds": 0,
            }
            self._log(f"[id={item.id}] stage=spec_generation done mode=direct")

        (
            function_signature,
            jml_block,
            notes,
            code_annotation_hints,
            helper_declarations,
        ) = self._validate_spec_fields(
            spec_json,
            signature_fallback=signature_fallback,
            helper_fallback=helper_fallback,
        )
        jml_block, jml_sanitization = _sanitize_java_jml_block(jml_block)
        code_annotation_hints, hint_sanitization = _sanitize_code_annotation_hints(
            code_annotation_hints
        )

        spec_out = {
            "id": item.id,
            "path": item.path,
            "language": "java",
            "verifier": "openjml",
            "requirement": item.requirement,
            "class_name": item.class_name,
            "signature_hint": item.signature_hint,
            "type_context": item.type_context,
            "function_signature": function_signature,
            "jml_block": jml_block,
            "acsl_block": jml_block,
            "code_annotation_hints": code_annotation_hints,
            "helper_declarations": helper_declarations,
            "notes": notes,
            "constraints": constraints,
            "alignment_check": alignment_info,
            "sanitization": {
                "jml_block": jml_sanitization,
                "code_annotation_hints": hint_sanitization,
            },
            "raw_model_output": spec_json.get("raw_model_output", ""),
            "enhanced_modules": {
                "cgs": self.enable_cgs,
                "spec_self_check_rounds": (
                    self.spec_self_check_rounds if self.enable_cgs else 0
                ),
                "code_repair": self.enable_code_repair,
                "code_repair_max_iter": (
                    self.code_repair_max_iter if self.enable_code_repair else 0
                ),
                "code_repair_strategy": self.code_repair_strategy,
                "vgcr_candidates": (
                    self.vgcr_candidates
                    if self.enable_code_repair and self.code_repair_strategy == "vgcr"
                    else 0
                ),
            },
        }
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_out, ensure_ascii=False, indent=2))
        self._log(f"[id={item.id}] stage=spec_generation done spec_file={spec_file}")

        self._log(f"[id={item.id}] stage=code_generation start")
        code_prompt = JAVA_CODE_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            function_signature=function_signature,
            jml_block=jml_block,
            helper_declarations=helper_declarations or "(none)",
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
        )
        code_raw = self.llm_client.chat(JAVA_CODE_SYSTEM_PROMPT, code_prompt)
        code_text = _extract_java_code(code_raw)
        code_text, code_sanitization = _sanitize_generated_java_code(code_text)
        code_text, initial_contract_enforcement = _enforce_jml_contract(
            code_text=code_text,
            function_signature=function_signature,
            jml_block=jml_block,
        )
        code_file = code_dir / Path(item.path)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.write_text(code_text)
        self._log(f"[id={item.id}] stage=code_generation done code_file={code_file}")

        result: Dict[str, Any] = {
            "spec_file": str(spec_file),
            "code_file": str(code_file),
            "contract_enforcement": {
                "enabled": True,
                "initial_generation": initial_contract_enforcement,
                "repair_attempts": [],
            },
            "code_sanitization": code_sanitization,
            "enhanced": {
                "enable_cgs": self.enable_cgs,
                "spec_self_check_rounds": self.spec_self_check_rounds,
                "enable_code_repair": self.enable_code_repair,
                "code_repair_max_iter": self.code_repair_max_iter,
                "code_repair_strategy": self.code_repair_strategy,
                "vgcr_candidates": self.vgcr_candidates,
            },
        }
        if self.skip_verify:
            self._log(f"[id={item.id}] stage=verify skipped")
            return result

        self._verify_with_optional_repair(
            item=item,
            code_file=code_file,
            code_text=code_text,
            function_signature=function_signature,
            jml_block=jml_block,
            code_annotation_hints=code_annotation_hints,
            result=result,
        )
        return result

    def _verify_with_optional_repair(
        self,
        item: JavaRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        jml_block: str,
        code_annotation_hints: Dict[str, List[str]],
        result: Dict[str, Any],
    ) -> None:
        report_dir = self.output_dir / "reports"
        repair_history: List[Dict[str, Any]] = []

        self._log(f"[id={item.id}] stage=verify start")
        verdict = self.verifier.verify(code_file)
        repair_limit = self.code_repair_max_iter if self.enable_code_repair else 0
        for attempt in range(1, repair_limit + 1):
            if verdict.is_valid():
                break
            details = verdict.details or ""
            detail_path = report_dir / Path(item.path).with_suffix(f".repair{attempt - 1}.openjml.log")
            if details:
                detail_path.parent.mkdir(parents=True, exist_ok=True)
                detail_path.write_text(details)
            self._log(
                f"[id={item.id}] stage=code_repair attempt={attempt}/{repair_limit} "
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
                if self.code_repair_strategy == "vgcr":
                    (
                        code_text,
                        verdict,
                        strategy_info,
                        contract_enforcements,
                    ) = self._build_vgcr_repair(
                        item=item,
                        code_file=code_file,
                        code_text=code_text,
                        function_signature=function_signature,
                        jml_block=jml_block,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                        attempt=attempt,
                    )
                    history_entry["vgcr"] = strategy_info
                    contract_enforcement = (
                        contract_enforcements[-1] if contract_enforcements else {}
                    )
                    for entry in contract_enforcements:
                        result.setdefault("contract_enforcement", {}).setdefault(
                            "repair_attempts", []
                        ).append(entry)
                else:
                    code_text, strategy_info = self._build_simple_repair(
                        item=item,
                        code_text=code_text,
                        function_signature=function_signature,
                        jml_block=jml_block,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                    )
                    code_text, contract_enforcement = _enforce_jml_contract(
                        code_text=code_text,
                        function_signature=function_signature,
                        jml_block=jml_block,
                    )
                    code_file.write_text(code_text)
                    result.setdefault("contract_enforcement", {}).setdefault(
                        "repair_attempts", []
                    ).append(
                        {
                            "attempt": attempt,
                            **contract_enforcement,
                        }
                    )
                    history_entry["simple"] = strategy_info
                    verdict = self.verifier.verify(code_file)
                history_entry["contract_enforcement"] = contract_enforcement
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
            verify_log = report_dir / Path(item.path).with_suffix(".openjml.log")
            verify_log.parent.mkdir(parents=True, exist_ok=True)
            verify_log.write_text(verdict.details)
            verification["details_file"] = str(verify_log)
        result["verification"] = verification
        self._log(
            f"[id={item.id}] stage=verify done valid={verification['valid']} "
            f"type={verification['type']} repairs={verification['repair_attempts']}"
        )

    def _build_simple_repair(
        self,
        item: JavaRequirementItem,
        code_text: str,
        function_signature: str,
        jml_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> tuple[str, Dict[str, Any]]:
        repair_prompt = JAVA_REPAIR_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            function_signature=function_signature,
            jml_block=jml_block,
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
        repaired_raw = self.llm_client.chat(JAVA_REPAIR_SYSTEM_PROMPT, repair_prompt)
        repaired_code = _extract_java_code(repaired_raw)
        repaired_code, code_sanitization = _sanitize_generated_java_code(repaired_code)
        return repaired_code, {
            "strategy": "simple",
            "raw_model_output": repaired_raw,
            "code_sanitization": code_sanitization,
        }

    def _vgcr_repair_plan(
        self,
        item: JavaRequirementItem,
        code_text: str,
        function_signature: str,
        jml_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> Dict[str, Any]:
        plan_prompt = JAVA_VGCR_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            class_name=item.class_name,
            function_signature=function_signature,
            jml_block=jml_block,
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
        raw = self.llm_client.chat(JAVA_VGCR_REPAIR_ANALYSIS_SYSTEM_PROMPT, plan_prompt)
        try:
            plan = _extract_json_object(raw)
        except Exception as exc:
            return {
                "failure_summary": "Failed to parse structured repair plan.",
                "subgoals": [
                    {
                        "name": "whole_method",
                        "kind": "unknown",
                        "evidence": verdict.message,
                        "repair_hint": "Repair the implementation and statement-level annotations.",
                    }
                ],
                "global_strategy": "Use the OpenJML output directly to repair the method.",
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
                    "name": "whole_method",
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
            "Try an alternative OpenJML-friendly implementation while preserving the frozen contract."
        )
        return focuses

    def _build_vgcr_repair(
        self,
        item: JavaRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        jml_block: str,
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
        attempt: int,
    ) -> tuple[str, Any, Dict[str, Any], List[Dict[str, Any]]]:
        plan = self._vgcr_repair_plan(
            item=item,
            code_text=code_text,
            function_signature=function_signature,
            jml_block=jml_block,
            code_annotation_hints=code_annotation_hints,
            verdict=verdict,
            details=details,
        )
        candidate_count = self.vgcr_candidates
        focuses = self._candidate_focuses(plan)
        candidate_records: List[Dict[str, Any]] = []
        contract_enforcements: List[Dict[str, Any]] = []
        best_code = code_text
        best_verdict = verdict

        for candidate_idx in range(1, candidate_count + 1):
            focus = focuses[(candidate_idx - 1) % len(focuses)]
            self._log(
                f"[id={item.id}] stage=vgcr_repair attempt={attempt} "
                f"candidate={candidate_idx}/{candidate_count}"
            )
            candidate_prompt = JAVA_VGCR_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                class_name=item.class_name,
                function_signature=function_signature,
                jml_block=jml_block,
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
                JAVA_VGCR_REPAIR_CANDIDATE_SYSTEM_PROMPT,
                candidate_prompt,
            )
            candidate_code = _extract_java_code(raw)
            candidate_code, code_sanitization = _sanitize_generated_java_code(candidate_code)
            candidate_code, contract_enforcement = _enforce_jml_contract(
                code_text=candidate_code,
                function_signature=function_signature,
                jml_block=jml_block,
            )
            contract_record = {
                "attempt": attempt,
                "candidate": candidate_idx,
                **contract_enforcement,
            }
            contract_enforcements.append(contract_record)
            code_file.write_text(candidate_code)
            candidate_verdict = self.verifier.verify(code_file)
            candidate_record = {
                "candidate": candidate_idx,
                "focus": focus,
                "valid": candidate_verdict.is_valid(),
                "type": candidate_verdict.verdict_type.value,
                "message": candidate_verdict.message,
                "contract_enforcement": contract_enforcement,
                "raw_model_output": raw,
                "code_sanitization": code_sanitization,
            }
            candidate_records.append(candidate_record)
            best_code = candidate_code
            best_verdict = candidate_verdict
            if candidate_verdict.is_valid():
                break

        code_file.write_text(best_code)
        return best_code, best_verdict, {
            "strategy": "vgcr",
            "plan": plan,
            "candidates": candidate_records,
        }, contract_enforcements
