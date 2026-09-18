"""Pipeline: requirement -> Verus specification -> Rust code -> Verus verification."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..llm.openai_compatible import OpenAICompatibleClient
from ..verifier.verus import VerusVerifier


RUST_SPEC_SYSTEM_PROMPT = """You are an expert in Rust verification with Verus.
Return strict JSON only."""

RUST_SPEC_USER_PROMPT_TEMPLATE = """Given the Rust requirement below, design a minimal but useful Verus function specification.

Requirement:
{requirement}

Function signature hint:
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Verus/Rust function signature without body; end with ';', e.g. pub fn f(x: u64) -> (r: u64);",
    "verus_contract": "Verus requires/ensures clauses for the function signature, without the function body.",
    "verus_clauses": [
      {{"type": "requires", "expr": "x < u64::MAX"}},
      {{"type": "ensures", "expr": "r == x + 1"}}
    ],
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_variants": ["Optional decreases candidates for code generation only."]
    }},
    "notes": "Very short rationale."
  }}
- Prefer the signature hint when it is provided.
- Use safe Rust and Verus syntax compatible with `use vstd::prelude::*; verus! {{ ... }}`.
- Include preconditions for arithmetic overflow, vector/slice bounds, and panic freedom when needed.
- Use `old(x)` and `final(x)` for mutable references, `v@` for ghost sequence views, and named return values.
- For Vec/slice contracts, spell lengths and elements as `v@.len()` and `v@[i as int]`; never invent view members such as `v@.r()` or `v@.result()`.
- Use Verus datatype syntax such as `o.is_Some()`, `o.get_Some_0()`, `r.is_Ok()`, and `r.get_Ok_0()` for Option/Result clauses.
- Rust references, slices, and Vec references are already non-null and memory-safe; do not write `null`, `pointer_valid`, `valid`, `wf`, `well_formed`, `fully_owned`, `independent_of`, or `panics`.
- Do not include the Rust function body in this JSON.
"""

RUST_CONSTRAINT_SYSTEM_PROMPT = """You are an expert in translating Rust requirements into Verus verification constraints.
Return strict JSON only."""

RUST_CONSTRAINT_USER_PROMPT_TEMPLATE = """Extract structured verification constraints from the Rust requirement.

Requirement:
{requirement}

Function signature hint:
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Best-effort Verus/Rust function signature without body; end with ';'. Prefer the hint if present.",
    "preconditions": ["..."],
    "postconditions": ["..."],
    "panic_freedom": ["..."],
    "mutation_frame": ["..."],
    "invariants": ["..."],
    "notes": "Very short rationale."
  }}
- Keep each constraint atomic and testable.
- Include ownership/borrowing, vector/slice bounds, Option/Result variant behavior, arithmetic overflow, and mutation effects when relevant.
- Express Rust memory safety using ordinary Rust/Verus facts only. Do not emit C/Viper-style constraints such as nullness, pointer validity, heap ownership predicates, `panics`, `wf`, or `well_formed`.
"""

RUST_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT = """You are an expert Verus specification engineer.
Convert Rust verification constraints into a complete Verus function contract. Return strict JSON only."""

RUST_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE = """Create Verus spec JSON using requirement + structured constraints.

Requirement:
{requirement}

Structured constraints (JSON):
{constraints_json}

Function signature hint:
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Verus/Rust function signature without body; end with ';', e.g. pub fn f(x: u64) -> (r: u64);",
    "verus_contract": "Verus requires/ensures clauses for the function signature, without the function body.",
    "verus_clauses": [
      {{"type": "requires", "expr": "..."}},
      {{"type": "ensures", "expr": "..."}}
    ],
    "code_annotation_hints": {{
      "loop_invariants": ["Optional loop invariant candidates for code generation only."],
      "loop_variants": ["Optional decreases candidates for code generation only."]
    }},
    "notes": "Very short rationale."
  }}
- Prefer the signature hint when it is provided.
- Use Verus `requires` and `ensures`; do not invent ACSL or JML syntax.
- If the function returns a value, use a named return in the signature such as `-> (r: u64);` and refer to that name in every `ensures`.
- Translate every functional precondition, return-value case, mutation effect, and unchanged-region constraint into an explicit atomic `requires` or `ensures` clause. Do not leave functional constraints only in notes or code hints.
- For Vec/slice contracts, spell lengths and elements as `v@.len()` and `v@[i as int]`; use `old(v)@`/`final(v)@` for mutable pre/post-state and never invent view members such as `v@.r()` or `v@.result()`.
- Use Verus datatype syntax such as `o.is_Some()`, `o.get_Some_0()`, `r.is_Ok()`, and `r.get_Ok_0()` for Option/Result clauses.
- Ownership, borrowing, panic freedom, and immutable-by-value frame facts are implicit when they add no functional restriction; do not invent `no_unwind` or tautological frame clauses for them.
- Do not write `null`, `pointer_valid`, `valid`, `wf`, `well_formed`, `fully_owned`, `independent_of`, or `panics`; these are not valid for this benchmark's Verus subset.
- Put loop annotations only in code_annotation_hints.
"""

RUST_SPEC_CHECK_SYSTEM_PROMPT = """You are a strict Rust requirement/Verus-spec alignment reviewer.
Return strict JSON only."""

RUST_SPEC_CHECK_USER_PROMPT_TEMPLATE = """Check whether the generated Verus specification misses Rust requirement constraints.

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
- Judge coverage by the requirement's functional behavior. Do not report implicit Rust ownership, immutable-parameter frames, or a separate `no_unwind` clause as missing.
- Reject any invented Vec/slice view member (for example `v@.r()`), any dropped return-value case, or any dropped mutation/unchanged-region constraint.
"""

RUST_SPEC_REFINE_SYSTEM_PROMPT = """You refine Verus specs to improve Rust requirement alignment.
Return strict JSON only."""

RUST_SPEC_REFINE_USER_PROMPT_TEMPLATE = """Refine the generated Verus specification based on alignment findings.

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
    "verus_contract": "...",
    "verus_clauses": [{{"type": "requires", "expr": "..."}}, {{"type": "ensures", "expr": "..."}}],
    "code_annotation_hints": {{
      "loop_invariants": ["..."],
      "loop_variants": ["..."]
    }},
    "notes": "..."
  }}
- Keep loop annotations in code_annotation_hints, not in the function contract.
- Keep the same Verus subset: named returns, `v@` sequence views, `old`/`final` for mutable references, and no `null`, pointer-validity, heap-ownership, `wf`, `well_formed`, or `panics` predicates.
- Preserve every correct functional clause from the current specification. Refinement may add or correct clauses, but must not delete a return-value case, mutation effect, or unchanged-region constraint.
- For Vec/slice contracts use only `v@.len()`, `v@[i as int]`, and `old(v)@`/`final(v)@`; never invent members such as `v@.r()` or `v@.result()`.
- Do not add `no_unwind` or tautological immutable-parameter frame clauses.
"""

RUST_CODE_SYSTEM_PROMPT = """You are an expert Rust developer writing Verus-friendly code.
Output Rust source code only."""

RUST_CODE_USER_PROMPT_TEMPLATE = """Implement one complete Rust/Verus source file from the requirement and Verus specification.

Requirement:
{requirement}

Target function signature:
{function_signature}

Verus contract clauses to keep on the target function:
{verus_contract}

Structured contract clauses (JSON):
{verus_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Output constraints:
- Output only complete Rust source code (no markdown fences, no explanation).
- Include `use vstd::prelude::*;`, a single `verus! {{ ... }}` block, and `fn main() {{}}` outside the block.
- Implement exactly one public target function matching the signature and contract.
- Keep the target function's `requires` and `ensures` semantics unchanged.
- Use safe Rust only; do not use `unsafe`.
- Use simple loops/branches and Verus-compatible standard library operations.
- Insert loop invariants and decreases clauses when needed for Verus.
"""

RUST_REPAIR_SYSTEM_PROMPT = """You are an expert Rust/Verus developer fixing code to satisfy Verus verification.
Output Rust source code only."""

RUST_REPAIR_USER_PROMPT_TEMPLATE = """Fix the Rust/Verus source so that it satisfies the requirement and Verus specification.

Requirement:
{requirement}

Target function signature:
{function_signature}

Verus contract clauses:
{verus_contract}

Structured contract clauses (JSON):
{verus_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verus result:
- type: {verdict_type}
- message: {verdict_message}
- details:
{verdict_details}

Output constraints:
- Output only complete Rust source code (no markdown fences, no explanation).
- Keep `use vstd::prelude::*;`, a `verus! {{ ... }}` block, and `fn main() {{}}`.
- Keep the target function's requires/ensures contract semantics unchanged.
- Fix implementation code, helper proof code, and loop annotations only.
- Use safe Rust only; do not use `unsafe`.
- Prefer minimal, Verus-friendly fixes.
"""

RUST_VGCR_REPAIR_ANALYSIS_SYSTEM_PROMPT = """You are a verification-guided Rust/Verus repair planner.
Return strict JSON only."""

RUST_VGCR_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze a failed Verus verification attempt and produce a repair plan.

Requirement:
{requirement}

Target function signature:
{function_signature}

Frozen Verus contract clauses:
{verus_contract}

Structured contract clauses (JSON):
{verus_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Verus result:
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
        "name": "Short stable name, e.g. postcondition_result or loop_invariant_preservation",
        "kind": "syntax|contract_placement|bounds_safety|postcondition|frame|loop_invariant|loop_variant|overflow|termination|timeout|unknown",
        "evidence": "Relevant Verus clue.",
        "repair_hint": "Concrete body/helper/proof/loop-annotation change to try."
      }}
    ],
    "global_strategy": "How to synthesize the fixes while preserving the frozen contract.",
    "risk_notes": ["Potential ways a repair could cheat or weaken semantics."]
  }}
- Treat the Verus function contract as frozen. Do not suggest weakening or replacing it.
- Prefer Rust body changes, helper proof code, and loop annotations.
"""

RUST_VGCR_REPAIR_CANDIDATE_SYSTEM_PROMPT = """You are an expert Rust/Verus developer using prove-as-you-generate repair.
Output Rust source code only."""

RUST_VGCR_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE = """Repair the Rust/Verus implementation using this verifier-derived plan.

Requirement:
{requirement}

Target function signature:
{function_signature}

Frozen Verus contract clauses:
{verus_contract}

Structured contract clauses (JSON):
{verus_clauses_json}

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
- Output only complete Rust source code (no markdown fences, no explanation).
- Keep `use vstd::prelude::*;`, a single `verus! {{ ... }}` block, and `fn main() {{}}`.
- Preserve the frozen target function contract semantics.
- You may change function body logic, helper proof code, and loop annotations.
- Use safe Rust only; do not use `unsafe`.
- Prefer explicit loops, simple expressions, and Verus-friendly control flow.
- Avoid hiding the algorithm in library calls or changing the specification to make proof easier.
"""


@dataclass
class RustRequirementItem:
    id: int
    path: str
    requirement: str
    signature_hint: str = ""


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


def _extract_rust_code(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:rust|rs)?\n([\s\S]*?)\n```", stripped)
    if fenced:
        return fenced.group(1).strip()
    return stripped


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
    hints = {"loop_invariants": [], "loop_variants": []}
    if not isinstance(value, dict):
        return hints
    aliases = {
        "loop_invariants": ["loop_invariants", "invariants"],
        "loop_variants": ["loop_variants", "variants", "decreases"],
    }
    for canonical, keys in aliases.items():
        for key in keys:
            hints[canonical].extend(_as_list_of_str(value.get(key)))
    return hints


def _normalize_verus_clauses(value: Any, contract_text: str = "") -> List[Dict[str, str]]:
    clauses: List[Dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("type", "")).strip().lower()
            expr = str(row.get("expr", "")).strip().rstrip(",")
            if kind in {"requires", "ensures"} and expr:
                clauses.append({"type": kind, "expr": expr})
    if clauses:
        return clauses

    current = ""
    for raw in contract_text.splitlines():
        line = raw.strip().rstrip(",")
        if not line:
            continue
        m = re.match(r"^(requires|ensures)\b\s*(.*)$", line)
        if m:
            current = m.group(1)
            rest = m.group(2).strip().rstrip(",")
            if rest:
                clauses.append({"type": current, "expr": rest})
            continue
        if current:
            clauses.append({"type": current, "expr": line})
    return clauses


RUST_DISALLOWED_SPEC_PATTERNS = [
    r"\bnull\b",
    r"\bpanics\b",
    r"\.pointer_valid\s*\(",
    r"\.valid\s*\(",
    r"\.wf\s*\(",
    r"\.well_formed\s*\(",
    r"\.fully_owned\s*\(",
    r"\.independent_of\s*\(",
    r"\.allocated\s*\(",
    r"@\.(?:r|result)\s*\(",
]


def _has_disallowed_verus_expr(expr: str) -> bool:
    return any(re.search(pattern, expr) for pattern in RUST_DISALLOWED_SPEC_PATTERNS)


def _spec_has_disallowed_verus_items(spec_json: Dict[str, Any]) -> bool:
    contract = str(spec_json.get("verus_contract") or "")
    if _has_disallowed_verus_expr(contract):
        return True
    for clause in _normalize_verus_clauses(spec_json.get("verus_clauses"), contract):
        if _has_disallowed_verus_expr(clause["expr"]):
            return True
    return False


def _ensure_signature_semicolon(signature: str) -> tuple[str, bool]:
    stripped = signature.strip()
    if not stripped:
        return stripped, False
    if stripped.endswith(";"):
        return stripped, False
    return stripped.rstrip("{").strip() + ";", True


def _normalize_rust_return_signature(
    signature: str,
    return_name: str = "r",
) -> tuple[str, Optional[str], Dict[str, Any]]:
    signature, semicolon_added = _ensure_signature_semicolon(signature)
    diagnostics: Dict[str, Any] = {"semicolon_added": semicolon_added}
    if not signature:
        return signature, None, diagnostics

    named = re.search(r"->\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", signature)
    if named:
        diagnostics["return_was_named"] = True
        return signature, named.group(1), diagnostics

    unnamed = re.search(r"->\s*([^;]+);$", signature)
    if not unnamed:
        diagnostics["return_was_named"] = False
        return signature, None, diagnostics

    return_type = unnamed.group(1).strip()
    if not return_type or return_type == "()":
        diagnostics["return_was_named"] = False
        return signature, None, diagnostics

    normalized = signature[: unnamed.start()] + f"-> ({return_name}: {return_type});"
    diagnostics["return_was_named"] = False
    diagnostics["return_name_inserted"] = return_name
    diagnostics["original_return_type"] = return_type
    return normalized, return_name, diagnostics


def _extract_rust_return_name(signature: str) -> Optional[str]:
    match = re.search(r"->\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", signature)
    if match:
        return match.group(1)
    return None


def _normalize_rust_return_expr(
    expr: str,
    return_name: Optional[str],
    return_aliases: Optional[List[str]] = None,
    parameter_names: Optional[List[str]] = None,
) -> str:
    out = expr.strip().rstrip(",").strip()
    if not return_name:
        return out
    parameters = set(parameter_names or [])
    aliases = [name for name in ["result", "res", "ret"] if name not in parameters]
    if return_aliases:
        aliases.extend(return_aliases)
    for alias in sorted(set(aliases), key=len, reverse=True):
        if alias and alias != return_name:
            out = re.sub(rf"\b{re.escape(alias)}\b", return_name, out)
    return out


def _extract_rust_parameters(signature: str) -> Dict[str, str]:
    match = re.search(r"\bfn\s+[A-Za-z_][A-Za-z0-9_]*\s*\(", signature)
    if not match:
        return {}
    start = match.end() - 1
    depth = 0
    end = -1
    for idx in range(start, len(signature)):
        if signature[idx] == "(":
            depth += 1
        elif signature[idx] == ")":
            depth -= 1
            if depth == 0:
                end = idx
                break
    if end < 0:
        return {}

    blob = signature[start + 1 : end]
    parts: List[str] = []
    part_start = 0
    angle = paren = bracket = 0
    for idx, char in enumerate(blob):
        if char == "<":
            angle += 1
        elif char == ">":
            angle = max(0, angle - 1)
        elif char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "," and angle == paren == bracket == 0:
            parts.append(blob[part_start:idx].strip())
            part_start = idx + 1
    parts.append(blob[part_start:].strip())

    parameters: Dict[str, str] = {}
    for part in parts:
        if ":" not in part:
            continue
        name, type_text = part.split(":", 1)
        name = name.strip().removeprefix("mut ").strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            parameters[name] = type_text.strip()
    return parameters


def _normalize_rust_state_expr(expr: str, signature: str, clause_type: str) -> str:
    out = expr.strip()
    parameters = _extract_rust_parameters(signature)
    for name, type_text in parameters.items():
        is_reference = type_text.startswith("&")
        is_mutable_reference = bool(re.match(r"&\s*mut\b", type_text))
        if is_reference and not is_mutable_reference:
            out = re.sub(rf"\b(?:old|final)\(\s*{re.escape(name)}\s*\)", name, out)
            continue
        if not is_mutable_reference or clause_type != "ensures":
            continue

        placeholders: Dict[str, str] = {}

        def protect(match: re.Match[str]) -> str:
            key = f"__RUST_STATE_{len(placeholders)}__"
            placeholders[key] = match.group(0)
            return key

        out = re.sub(
            rf"\b(?:old|final)\(\s*{re.escape(name)}\s*\)",
            protect,
            out,
        )
        out = re.sub(rf"\*\s*{re.escape(name)}\b", f"*final({name})", out)
        out = re.sub(rf"\b{re.escape(name)}\b", f"final({name})", out)
        for key, value in placeholders.items():
            out = out.replace(key, value)
    usize_parameters = {
        name for name, type_text in parameters.items() if type_text.strip() == "usize"
    }
    collection_parameters = {
        name
        for name, type_text in parameters.items()
        if "Vec<" in type_text or "[" in type_text
    }
    for name in collection_parameters:
        base = rf"(?:old\(\s*{re.escape(name)}\s*\)|final\(\s*{re.escape(name)}\s*\)|{re.escape(name)})"

        def normalize_index(match: re.Match[str]) -> str:
            collection = match.group(1)
            index = match.group(2).strip()
            if index in usize_parameters:
                index = f"{index} as int"
            view = collection if collection.endswith("@") else f"{collection}@"
            return f"{view}[{index}]"

        out = re.sub(rf"\b({base}@?)\s*\[\s*([^\]]+)\s*\]", normalize_index, out)
    return out


def _is_tautological_clause(expr: str) -> bool:
    if "==>" in expr or "<==>" in expr:
        return False
    match = re.fullmatch(r"\s*\(?\s*(.+?)\s*\)?\s*==\s*\(?\s*(.+?)\s*\)?\s*", expr)
    if not match:
        return False
    left = re.sub(r"\s+", "", match.group(1))
    right = re.sub(r"\s+", "", match.group(2))
    return left == right


def _enforce_rust_contract(
    code_text: str,
    function_signature: str,
    verus_clauses: List[Dict[str, str]],
) -> tuple[str, bool]:
    name_match = re.search(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", function_signature)
    if not name_match:
        raise ValueError("canonical Rust function signature has no function name")
    function_name = name_match.group(1)
    declaration = re.search(
        rf"(?m)^(?P<indent>\s*)(?P<visibility>pub(?:\([^)]*\))?\s+)?fn\s+{re.escape(function_name)}\b",
        code_text,
    )
    if not declaration:
        raise ValueError(f"generated Rust code is missing target function: {function_name}")
    body_match = re.search(r"\{", code_text[declaration.start() :])
    if not body_match:
        raise ValueError(f"generated Rust target function has no standalone body opener: {function_name}")
    body_start = declaration.start() + body_match.start()

    signature = function_signature.strip().rstrip(";").strip()
    signature = re.sub(r"^(?:pub(?:\([^)]*\))?\s+)?", "", signature)
    visibility = declaration.group("visibility") or ""
    lines = [f"{declaration.group('indent')}{visibility}{signature}"]
    for kind in ("requires", "ensures"):
        expressions = [row["expr"] for row in verus_clauses if row.get("type") == kind]
        if not expressions:
            continue
        lines.append(f"{declaration.group('indent')}    {kind}")
        lines.extend(
            f"{declaration.group('indent')}        {expression},"
            for expression in expressions
        )
    replacement = "\n".join(lines) + "\n"
    enforced = code_text[: declaration.start()] + replacement + code_text[body_start:]
    return enforced, enforced != code_text


def _build_verus_contract(clauses: List[Dict[str, str]]) -> str:
    requires = [c["expr"] for c in clauses if c["type"] == "requires"]
    ensures = [c["expr"] for c in clauses if c["type"] == "ensures"]
    parts: List[str] = []
    if requires:
        parts.append("requires " + ", ".join(requires))
    if ensures:
        parts.append("ensures " + ", ".join(ensures))
    return "\n".join(parts)


def _truncate_for_prompt(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


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


def load_rust_requirements(
    requirements_file: Path,
    signature_file: Optional[Path] = None,
) -> List[RustRequirementItem]:
    """Load Rust requirement entries and optional dataset-provided signature hints."""
    signature_by_id: Dict[int, str] = {}
    if signature_file and signature_file.exists():
        raw_sigs = json.loads(signature_file.read_text())
        if isinstance(raw_sigs, list):
            for row in raw_sigs:
                try:
                    signature_by_id[int(row["id"])] = str(row.get("function_signature", "")).strip()
                except Exception:
                    continue

    raw = json.loads(requirements_file.read_text())
    items: List[RustRequirementItem] = []
    for obj in raw:
        if "id" not in obj or "path" not in obj:
            raise ValueError(f"Invalid requirement entry: {obj}")
        req_text = obj.get("requirement_zh") or obj.get("requirement_en") or obj.get("requirement")
        if not req_text:
            raise ValueError(f"Requirement text missing for entry: {obj}")
        rid = int(obj["id"])
        items.append(
            RustRequirementItem(
                id=rid,
                path=str(obj["path"]),
                requirement=str(req_text),
                signature_hint=str(obj.get("function_signature") or signature_by_id.get(rid, "")),
            )
        )
    return items


class RustRequirementToCodePipeline:
    """End-to-end Rust/Verus generation pipeline."""

    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
        verus_bin: str = "verus",
        enable_cgs: bool = True,
        spec_self_check_rounds: int = 1,
        enable_code_repair: bool = True,
        code_repair_max_iter: int = 3,
        code_repair_strategy: str = "simple",
        vgcr_candidates: int = 3,
        reuse_artifacts_from: Optional[Path] = None,
        pipeline_variant: str = "enhanced",
        enhancement_method: Optional[str] = None,
    ):
        self.llm_client = llm_client
        self.output_dir = output_dir
        self.skip_verify = skip_verify
        self.logger = logger
        self.verifier = VerusVerifier(timeout=verify_timeout, verus_cmd=verus_bin)
        self.enable_cgs = enable_cgs
        self.spec_self_check_rounds = max(0, spec_self_check_rounds)
        self.enable_code_repair = enable_code_repair
        self.code_repair_max_iter = max(0, code_repair_max_iter)
        if code_repair_strategy not in {"simple", "vgcr"}:
            raise ValueError(f"Unsupported code_repair_strategy: {code_repair_strategy}")
        self.code_repair_strategy = code_repair_strategy
        self.vgcr_candidates = max(1, vgcr_candidates)
        self.reuse_artifacts_from = reuse_artifacts_from
        self.pipeline_variant = pipeline_variant
        self.enhancement_method = enhancement_method

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)

    def run(self, requirements: List[RustRequirementItem], resume: bool = False) -> Dict[str, Any]:
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
            (reports_dir / "results.partial.json").write_text(
                json.dumps(interim, ensure_ascii=False, indent=2)
            )

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
            "language": "rust",
            "verifier": "verus",
            "pipeline_variant": self.pipeline_variant,
            "enhancement_method": self.enhancement_method,
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

    def _extract_constraints(self, item: RustRequirementItem) -> Dict[str, Any]:
        prompt = RUST_CONSTRAINT_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            signature_hint=item.signature_hint or "(none)",
        )
        raw = self.llm_client.chat(RUST_CONSTRAINT_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        return {
            "function_signature": str(data.get("function_signature", "")).strip(),
            "preconditions": _as_list_of_str(data.get("preconditions")),
            "postconditions": _as_list_of_str(data.get("postconditions")),
            "panic_freedom": _as_list_of_str(data.get("panic_freedom")),
            "mutation_frame": _as_list_of_str(data.get("mutation_frame")),
            "invariants": _as_list_of_str(data.get("invariants")),
            "notes": str(data.get("notes", "")).strip(),
            "raw_model_output": raw,
        }

    def _generate_direct_spec(self, item: RustRequirementItem) -> Dict[str, Any]:
        prompt = RUST_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            signature_hint=item.signature_hint or "(none)",
        )
        raw = self.llm_client.chat(RUST_SPEC_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        data["raw_model_output"] = raw
        return data

    def _constraints_to_spec(
        self,
        item: RustRequirementItem,
        constraints: Dict[str, Any],
        signature_hint: str,
    ) -> Dict[str, Any]:
        prompt = RUST_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
            signature_hint=signature_hint or "(none)",
        )
        raw = self.llm_client.chat(RUST_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        data["raw_model_output"] = raw
        return data

    def _fallback_to_direct_spec(
        self,
        item: RustRequirementItem,
        reason: str,
        stage: str,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        self._log(
            f"[id={item.id}] stage={stage} error={reason} "
            "fallback=direct_spec_generation"
        )
        self._log(f"[id={item.id}] stage=spec_generation start mode=direct_fallback")
        spec_json = self._generate_direct_spec(item)
        self._log(f"[id={item.id}] stage=spec_generation done mode=direct_fallback")
        return spec_json, {
            "enabled": False,
            "reason": f"{stage} failed; fell back to direct spec generation",
            "fallback_to_direct_spec": True,
            "fallback_stage": stage,
            "fallback_error": reason,
            "rounds": [],
            "final_aligned": None,
            "max_rounds": 0,
        }

    def _check_and_refine_spec(
        self,
        item: RustRequirementItem,
        constraints: Dict[str, Any],
        spec_json: Dict[str, Any],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        rounds: List[Dict[str, Any]] = []
        current_spec = spec_json
        best_spec = spec_json
        final_aligned = False
        fallback_to_initial_spec = False

        for round_idx in range(1, self.spec_self_check_rounds + 1):
            check_prompt = RUST_SPEC_CHECK_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
            )
            check_raw = self.llm_client.chat(RUST_SPEC_CHECK_SYSTEM_PROMPT, check_prompt)
            check = _extract_json_object(check_raw)
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
                best_spec = current_spec
                rounds.append(round_info)
                break

            refine_prompt = RUST_SPEC_REFINE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
                check_json=json.dumps(check, ensure_ascii=False, indent=2),
            )
            refine_raw = self.llm_client.chat(RUST_SPEC_REFINE_SYSTEM_PROMPT, refine_prompt)
            candidate_spec = _extract_json_object(refine_raw)
            candidate_spec["raw_model_output"] = refine_raw
            round_info["refined"] = True
            if _spec_has_disallowed_verus_items(candidate_spec):
                round_info["refined_rejected"] = True
                round_info["reject_reason"] = "refinement introduced non-Verus/Rust spec expressions"
            else:
                current_spec = candidate_spec
                best_spec = candidate_spec
            rounds.append(round_info)

        if not final_aligned and best_spec is spec_json and any(r.get("refined") for r in rounds):
            fallback_to_initial_spec = True

        return best_spec, {
            "rounds": rounds,
            "final_aligned": final_aligned,
            "max_rounds": self.spec_self_check_rounds,
            "fallback_to_initial_spec": fallback_to_initial_spec,
        }

    def _validate_spec_fields(
        self,
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> tuple[str, str, List[Dict[str, str]], str, Dict[str, List[str]], Dict[str, Any]]:
        model_signature = str(spec_json.get("function_signature", "")).strip()
        model_return_name = _extract_rust_return_name(model_signature)
        function_signature = signature_fallback.strip() or str(
            spec_json.get("function_signature", "")
        ).strip()
        verus_contract = str(spec_json.get("verus_contract") or "").strip()
        notes = str(spec_json.get("notes", "")).strip()
        code_annotation_hints = _normalize_code_annotation_hints(
            spec_json.get("code_annotation_hints")
        )
        verus_clauses = _normalize_verus_clauses(
            spec_json.get("verus_clauses"),
            contract_text=verus_contract,
        )

        if not function_signature:
            raise ValueError("function_signature is empty after generation/refinement.")
        function_signature, return_name, signature_diagnostics = _normalize_rust_return_signature(
            function_signature,
            return_name="r",
        )
        parameter_names = list(_extract_rust_parameters(function_signature))
        return_aliases = [name for name in [model_return_name] if name and name != return_name]
        filtered_clauses: List[Dict[str, str]] = []
        removed_clauses: List[Dict[str, str]] = []
        for clause in verus_clauses:
            kind = str(clause.get("type", "")).strip().lower()
            expr = _normalize_rust_return_expr(
                str(clause.get("expr", "")),
                return_name,
                return_aliases=return_aliases,
                parameter_names=parameter_names,
            )
            expr = _normalize_rust_state_expr(expr, function_signature, kind)
            if kind not in {"requires", "ensures"} or not expr:
                continue
            normalized = {"type": kind, "expr": expr}
            if _has_disallowed_verus_expr(expr):
                removed_clauses.append(normalized)
            elif _is_tautological_clause(expr):
                removed_clauses.append({**normalized, "reason": "tautological_clause"})
            else:
                filtered_clauses.append(normalized)
        verus_clauses = filtered_clauses
        verus_contract = _build_verus_contract(verus_clauses)
        postprocessing = {
            "signature": signature_diagnostics,
            "return_name": return_name,
            "return_aliases_normalized": return_aliases,
            "removed_non_verus_clauses": removed_clauses,
        }
        if not verus_clauses:
            raise ValueError("verus_clauses must contain at least one requires/ensures clause.")
        return (
            function_signature,
            verus_contract,
            verus_clauses,
            notes,
            code_annotation_hints,
            postprocessing,
        )

    def _copy_reused_artifacts(
        self,
        item: RustRequirementItem,
        specs_dir: Path,
        code_dir: Path,
    ) -> tuple[Path, Path, Dict[str, Any], str]:
        if self.reuse_artifacts_from is None:
            raise ValueError("reuse_artifacts_from is not configured")

        source_spec_file = self.reuse_artifacts_from / "specs" / Path(item.path).with_suffix(".json")
        source_code_file = self.reuse_artifacts_from / "code" / Path(item.path)
        if not source_spec_file.exists():
            raise FileNotFoundError(f"reused spec artifact not found: {source_spec_file}")
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        code_file = code_dir / Path(item.path)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        code_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_spec_file, spec_file)
        if not source_code_file.exists():
            raise FileNotFoundError(f"reused code artifact not found: {source_code_file}")
        shutil.copy2(source_code_file, code_file)

        spec_out = json.loads(spec_file.read_text())
        function_signature = str(spec_out.get("function_signature", "")).strip()
        verus_contract = str(spec_out.get("verus_contract", "")).strip()
        verus_clauses = _normalize_verus_clauses(
            spec_out.get("verus_clauses"),
            contract_text=verus_contract,
        )
        if not function_signature:
            raise ValueError(f"reused spec missing function_signature: {spec_file}")
        if not verus_clauses:
            raise ValueError(f"reused spec missing Verus clauses: {spec_file}")

        return spec_file, code_file, spec_out, code_file.read_text()

    def _run_one(self, item: RustRequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
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
            function_signature = str(spec_out.get("function_signature", "")).strip()
            verus_contract = str(spec_out.get("verus_contract", "")).strip()
            verus_clauses = _normalize_verus_clauses(
                spec_out.get("verus_clauses"),
                contract_text=verus_contract,
            )
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
                    "enabled": False,
                    "reason": "Verus contracts are part of function signatures; reused artifacts are frozen.",
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
                verus_contract=verus_contract,
                verus_clauses=verus_clauses,
                code_annotation_hints=code_annotation_hints,
                result=result,
            )
            return result

        constraints: Optional[Dict[str, Any]] = None
        signature_fallback = item.signature_hint

        if self.enable_cgs:
            try:
                self._log(f"[id={item.id}] stage=cgs start")
                constraints = self._extract_constraints(item)
                signature_fallback = item.signature_hint or constraints.get("function_signature", "")
                self._log(f"[id={item.id}] stage=cgs done")

                self._log(f"[id={item.id}] stage=constraint_to_spec start")
                initial_spec = self._constraints_to_spec(
                    item=item,
                    constraints=constraints,
                    signature_hint=signature_fallback,
                )
                if _spec_has_disallowed_verus_items(initial_spec):
                    raise ValueError(
                        "constraint-to-spec generation introduced non-Verus/Rust spec expressions"
                    )
                self._log(f"[id={item.id}] stage=constraint_to_spec done")
            except Exception as exc:
                spec_json, alignment_info = self._fallback_to_direct_spec(
                    item=item,
                    reason=str(exc),
                    stage="constraint_generation",
                )
                constraints = {
                    "function_signature": item.signature_hint,
                    "preconditions": [],
                    "postconditions": [],
                    "panic_freedom": [],
                    "mutation_frame": [],
                    "invariants": [],
                    "notes": "Constraint-Guided Specification (CGS) failed; direct spec fallback was used.",
                    "fallback_error": str(exc),
                }
                signature_fallback = item.signature_hint
            else:
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

        try:
            (
                function_signature,
                verus_contract,
                verus_clauses,
                notes,
                code_annotation_hints,
                spec_postprocessing,
            ) = self._validate_spec_fields(spec_json, signature_fallback=signature_fallback)
        except ValueError as exc:
            if self.enable_cgs and not alignment_info.get("fallback_to_direct_spec"):
                spec_json, fallback_alignment = self._fallback_to_direct_spec(
                    item=item,
                    reason=str(exc),
                    stage="spec_validation",
                )
                (
                    function_signature,
                    verus_contract,
                    verus_clauses,
                    notes,
                    code_annotation_hints,
                    spec_postprocessing,
                ) = self._validate_spec_fields(
                    spec_json,
                    signature_fallback=item.signature_hint,
                )
                fallback_alignment["previous_alignment_check"] = alignment_info
                alignment_info = fallback_alignment
                signature_fallback = item.signature_hint
            else:
                raise

        spec_out = {
            "id": item.id,
            "path": item.path,
            "language": "rust",
            "verifier": "verus",
            "pipeline_variant": self.pipeline_variant,
            "enhancement_method": self.enhancement_method,
            "requirement": item.requirement,
            "signature_hint": item.signature_hint,
            "function_signature": function_signature,
            "verus_contract": verus_contract,
            "verus_clauses": verus_clauses,
            "code_annotation_hints": code_annotation_hints,
            "notes": notes,
            "constraints": constraints,
            "alignment_check": alignment_info,
            "raw_model_output": spec_json.get("raw_model_output", ""),
            "spec_postprocessing": spec_postprocessing,
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
        code_prompt = RUST_CODE_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            verus_contract=verus_contract or "(see structured clauses)",
            verus_clauses_json=json.dumps(verus_clauses, ensure_ascii=False, indent=2),
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
        )
        code_raw = self.llm_client.chat(RUST_CODE_SYSTEM_PROMPT, code_prompt)
        code_text = _extract_rust_code(code_raw)
        code_text, contract_rewritten = _enforce_rust_contract(
            code_text,
            function_signature,
            verus_clauses,
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
                "rewritten": contract_rewritten,
                "reason": "The generated target function header is replaced with the canonical Verus contract before verification.",
            },
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
            verus_contract=verus_contract,
            verus_clauses=verus_clauses,
            code_annotation_hints=code_annotation_hints,
            result=result,
        )
        return result

    def _verify_with_optional_repair(
        self,
        item: RustRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        verus_contract: str,
        verus_clauses: List[Dict[str, str]],
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
            detail_path = report_dir / Path(item.path).with_suffix(f".repair{attempt - 1}.verus.log")
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
                    code_text, verdict, strategy_info = self._build_vgcr_repair(
                        item=item,
                        code_file=code_file,
                        code_text=code_text,
                        function_signature=function_signature,
                        verus_contract=verus_contract,
                        verus_clauses=verus_clauses,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                        attempt=attempt,
                    )
                    history_entry["vgcr"] = strategy_info
                else:
                    code_text, strategy_info = self._build_simple_repair(
                        item=item,
                        code_text=code_text,
                        function_signature=function_signature,
                        verus_contract=verus_contract,
                        verus_clauses=verus_clauses,
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
            verify_log = report_dir / Path(item.path).with_suffix(".verus.log")
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
        item: RustRequirementItem,
        code_text: str,
        function_signature: str,
        verus_contract: str,
        verus_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> tuple[str, Dict[str, Any]]:
        repair_prompt = RUST_REPAIR_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            verus_contract=verus_contract or "(see structured clauses)",
            verus_clauses_json=json.dumps(verus_clauses, ensure_ascii=False, indent=2),
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
        repaired_raw = self.llm_client.chat(RUST_REPAIR_SYSTEM_PROMPT, repair_prompt)
        repaired_code, contract_rewritten = _enforce_rust_contract(
            _extract_rust_code(repaired_raw),
            function_signature,
            verus_clauses,
        )
        return repaired_code, {
            "strategy": "simple",
            "raw_model_output": repaired_raw,
            "contract_rewritten": contract_rewritten,
        }

    def _vgcr_repair_plan(
        self,
        item: RustRequirementItem,
        code_text: str,
        function_signature: str,
        verus_contract: str,
        verus_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> Dict[str, Any]:
        plan_prompt = RUST_VGCR_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            verus_contract=verus_contract or "(see structured clauses)",
            verus_clauses_json=json.dumps(verus_clauses, ensure_ascii=False, indent=2),
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
        raw = self.llm_client.chat(
            RUST_VGCR_REPAIR_ANALYSIS_SYSTEM_PROMPT,
            plan_prompt,
        )
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
                        "repair_hint": "Repair the implementation, helper proof code, and loop annotations.",
                    }
                ],
                "global_strategy": "Use the Verus output directly to repair the function.",
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
                    "repair_hint": "Repair the implementation, helper proof code, and loop annotations.",
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
            "Try an alternative Verus-friendly implementation while preserving the frozen contract."
        )
        return focuses

    def _build_vgcr_repair(
        self,
        item: RustRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        verus_contract: str,
        verus_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
        attempt: int,
    ) -> tuple[str, Any, Dict[str, Any]]:
        plan = self._vgcr_repair_plan(
            item=item,
            code_text=code_text,
            function_signature=function_signature,
            verus_contract=verus_contract,
            verus_clauses=verus_clauses,
            code_annotation_hints=code_annotation_hints,
            verdict=verdict,
            details=details,
        )
        candidate_count = self.vgcr_candidates
        focuses = self._candidate_focuses(plan)
        candidate_records: List[Dict[str, Any]] = []
        best_code = code_text
        best_verdict = verdict

        for candidate_idx in range(1, candidate_count + 1):
            focus = focuses[(candidate_idx - 1) % len(focuses)]
            self._log(
                f"[id={item.id}] stage=vgcr_repair attempt={attempt} "
                f"candidate={candidate_idx}/{candidate_count}"
            )
            candidate_prompt = RUST_VGCR_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                function_signature=function_signature,
                verus_contract=verus_contract or "(see structured clauses)",
                verus_clauses_json=json.dumps(verus_clauses, ensure_ascii=False, indent=2),
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
                RUST_VGCR_REPAIR_CANDIDATE_SYSTEM_PROMPT,
                candidate_prompt,
            )
            candidate_code, contract_rewritten = _enforce_rust_contract(
                _extract_rust_code(raw),
                function_signature,
                verus_clauses,
            )
            code_file.write_text(candidate_code)
            candidate_verdict = self.verifier.verify(code_file)
            candidate_records.append(
                {
                    "candidate": candidate_idx,
                    "focus": focus,
                    "valid": candidate_verdict.is_valid(),
                    "type": candidate_verdict.verdict_type.value,
                    "message": candidate_verdict.message,
                    "raw_model_output": raw,
                    "contract_rewritten": contract_rewritten,
                }
            )
            best_code = candidate_code
            best_verdict = candidate_verdict
            if candidate_verdict.is_valid():
                break

        code_file.write_text(best_code)
        return best_code, best_verdict, {
            "strategy": "vgcr",
            "plan": plan,
            "candidates": candidate_records,
        }
