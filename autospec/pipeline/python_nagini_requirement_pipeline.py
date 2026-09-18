"""Pipeline: requirement -> Nagini specification -> Python code -> Nagini verification."""
from __future__ import annotations

import ast
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..llm.openai_compatible import OpenAICompatibleClient
from ..verifier.nagini import NaginiVerifier
from ..verifier.verdict import Verdict, VerdictType


PYTHON_SPEC_SYSTEM_PROMPT = """You are an expert in Python formal verification with Nagini.
Return strict JSON only."""

PYTHON_SPEC_USER_PROMPT_TEMPLATE = """Given the Python requirement below, design a minimal but useful Nagini function contract.

Requirement:
{requirement}

Function signature hint:
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Python function header ending with ':', e.g. def f(x: int) -> int:",
    "nagini_contract": "One or more Nagini contract statements, one per line, e.g. Requires(x >= 0)\\nEnsures(Result() >= 0)",
    "nagini_clauses": [
      {{"type": "requires", "expr": "x >= 0"}},
      {{"type": "ensures", "expr": "Result() >= 0"}}
    ],
    "code_annotation_hints": {{
      "loop_invariants": ["Optional Invariant(...) candidates for code generation only."]
    }},
    "notes": "Very short rationale."
  }}
- Prefer the signature hint when it is provided.
- Use Nagini syntax with `from nagini_contracts.contracts import *`.
- Include `Requires(...)`, `Ensures(...)`, permissions such as `Acc(list_pred(a))` or `Acc(dict_pred(d))`, `Old(...)`, `Result()`, and `Implies(...)` when needed.
- Always write the return value as `Result()`, never as bare `Result`.
- Do not invent helper predicates such as `is_none`; write `x is None` or `x is not None`.
- Do not use `Acc(...)` on scalar `int`, `bool`, or `Optional` parameters.
- For `List[...]` parameters use `Acc(list_pred(a))`; for `Dict[...]` parameters use `Acc(dict_pred(d))`.
- Do not use `wildcard`, quantified element permissions, `Forall`, or lambda triggers for this benchmark subset.
- Do not include the Python function body in this JSON.
"""

PYTHON_CONSTRAINT_SYSTEM_PROMPT = """You are an expert in translating Python requirements into Nagini verification constraints.
Return strict JSON only."""

PYTHON_CONSTRAINT_USER_PROMPT_TEMPLATE = """Extract structured verification constraints from the Python requirement.

Requirement:
{requirement}

Function signature hint:
{signature_hint}

Output constraints (IMPORTANT):
- Return valid JSON only (no markdown fences, no explanation).
- JSON schema:
  {{
    "function_signature": "Best-effort Python function header ending with ':'. Prefer the hint if present.",
    "preconditions": ["..."],
    "postconditions": ["..."],
    "permission_conditions": ["..."],
    "exception_freedom": ["..."],
    "invariants": ["..."],
    "notes": "Very short rationale."
  }}
- Keep each constraint atomic and testable.
- Do not emit Python type-checking constraints such as `isinstance(...)`; type hints already define parameter and return types.
- Prefer evaluator-friendly syntax: use `x is None`, `x is not None`, `Old(...)`, `Result()`, `and`, `or`, and simple comparisons.
- Preserve boundary cases exactly. For example, absolute value needs `Implies(x >= 0, Result() == x)` and `Implies(x < 0, Result() == -x)`; do not reverse an implication by writing the wrong disjunction.
- A postcondition describing a value read from an input list or dict must use its pre-state value, such as `Result() == Old(a[i])` or `Result() == Old(d[key])`.
- For mutations, include stable structural facts required by the requirement after the call, such as `key in d` or `len(a) == Old(len(a))`.
- Include list/dict permissions, index bounds, key-existence constraints, Optional/None behavior, mutation effects, and exception-freedom preconditions when relevant.
"""

PYTHON_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT = """You are an expert Nagini specification engineer.
Convert Python verification constraints into a complete Nagini function contract. Return strict JSON only."""

PYTHON_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE = """Create Nagini spec JSON using requirement + structured constraints.

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
    "function_signature": "Python function header ending with ':', e.g. def f(x: int) -> int:",
    "nagini_contract": "One or more Nagini contract statements, one per line.",
    "nagini_clauses": [
      {{"type": "requires", "expr": "..."}},
      {{"type": "ensures", "expr": "..."}}
    ],
    "code_annotation_hints": {{
      "loop_invariants": ["Optional Invariant(...) candidates for code generation only."]
    }},
    "notes": "..."
  }}
- Prefer the signature hint when it is provided.
- Use Nagini syntax only: Requires, Ensures, Acc, list_pred, dict_pred, Old, and Result(). Prefer plain boolean expressions over helper calls.
- Always write the return value as `Result()`, never as bare `Result`.
- Do not generate type-checking clauses such as `isinstance(...)`; Python type hints already define the types.
- Write implication with Nagini's legal Python syntax `Implies(condition, conclusion)`; never emit the non-Python `condition ==> conclusion` form.
- Keep each `nagini_clauses` item atomic. Do not combine unrelated constraints with top-level `and`.
- Do not invent helper predicates such as `is_none`; write `x is None` or `x is not None`.
- Do not use `Acc(...)` on scalar `int`, `bool`, or `Optional` parameters.
- For `List[...]` parameters use `Acc(list_pred(a))`; for `Dict[...]` parameters use `Acc(dict_pred(d))`.
- Do not use `wildcard`, quantified element permissions, `Forall`, or lambda triggers for this benchmark subset.
- Do not use symbolic helper syntax such as `Eq(...)`, `Not(...)`, `And(...)`, `Or(...)`, or `write(...)`; write ordinary Python boolean expressions instead.
- Do not use chained comparisons such as `lo <= x <= hi`; write `lo <= x and x <= hi`.
- For mutation postconditions, compare against pre-state values with `Old(...)`, e.g. `len(a) == Old(len(a)) + 1`.
- For every return value computed from an input list or dict, use the pre-state value in the postcondition, e.g. `Result() == Old(a[i])` and `Result() == Old(d[key])`.
- Preserve every branch boundary from the requirement exactly; check both equality boundaries and implication direction before returning JSON.
- When a mutation preserves or establishes a structural fact, state it explicitly as an `ensures`, e.g. `key in d`, `len(a) == Old(len(a))`, or a required fixed length.
- For list/dict parameters, use only `Acc(list_pred(a))` or `Acc(dict_pred(d))`; do not add element permissions such as `Acc(a[i])` or `Acc(d[key])`.
- Put loop invariants only in code_annotation_hints.
"""

PYTHON_SPEC_CHECK_SYSTEM_PROMPT = """You are a strict Python requirement/Nagini-spec alignment reviewer.
Return strict JSON only."""

PYTHON_SPEC_CHECK_USER_PROMPT_TEMPLATE = """Check whether the generated Nagini specification misses Python requirement constraints.

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
- Review against the original requirement, not only the extracted constraints; extraction may omit or invert a boundary case.
- Reject a spec that uses post-state `a[i]`/`d[key]` where the requirement refers to the input value; require `Old(...)` there.
- Check that branch conditions cover equality boundaries and that mutations explicitly preserve or establish required key/length facts.
"""

PYTHON_SPEC_REFINE_SYSTEM_PROMPT = """You refine Nagini specs to improve Python requirement alignment.
Return strict JSON only."""

PYTHON_SPEC_REFINE_USER_PROMPT_TEMPLATE = """Refine the generated Nagini specification based on alignment findings.

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
    "nagini_contract": "Requires(...)\\nEnsures(...)",
    "nagini_clauses": [{{"type": "requires", "expr": "..."}}, {{"type": "ensures", "expr": "..."}}],
    "code_annotation_hints": {{
      "loop_invariants": ["..."]
    }},
    "notes": "..."
  }}
- Keep loop invariants in code_annotation_hints, not in the function contract.
- Use only Nagini/Python subset syntax accepted by this benchmark: no `Eq(...)`, `Not(...)`, `write(...)`, `isinstance(...)`, chained comparisons, element permissions, or impossible mutation postconditions such as `len(a) == len(a) + 1`.
- Write implication as `Implies(condition, conclusion)`, never `condition ==> conclusion`, and keep each clause atomic.
- Preserve input collection reads with `Old(...)`, preserve exact branch boundaries, and keep required post-state key/length facts explicit.
- If the current specification is already valid and useful, prefer preserving it over adding risky clauses.
"""

PYTHON_CODE_SYSTEM_PROMPT = """You are an expert Python developer writing Nagini-friendly code.
Output Python source code only."""

PYTHON_CODE_USER_PROMPT_TEMPLATE = """Implement one complete Python source file from the requirement and Nagini specification.

Requirement:
{requirement}

Target function signature:
{function_signature}

Nagini function contract (must be the first statements in the function body):
{nagini_contract}

Structured contract clauses (JSON):
{nagini_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Output constraints:
- Output only complete Python source code (no markdown fences, no explanation).
- Include `from typing import Dict, List, Optional` and `from nagini_contracts.contracts import *`.
- Implement exactly one target function matching the signature and contract.
- Keep the Nagini contract as the first statements in the function body.
- Do not add tests or top-level executable code.
- Use simple Python accepted by Nagini.
- Prefer direct operations such as `return len(d)`, `return a[0]`, `return key in d`, and direct assignments over loops when the requirement is simple.
- Do not invent loop invariants; only insert `Invariant(...)` statements from the provided hints.
- Insert `Invariant(...)` statements inside loops when needed for Nagini.
"""

PYTHON_REPAIR_SYSTEM_PROMPT = """You are an expert Python/Nagini developer fixing code to satisfy Nagini verification.
Output Python source code only."""

PYTHON_REPAIR_USER_PROMPT_TEMPLATE = """Fix the Python source so that it satisfies the requirement and Nagini specification.

Requirement:
{requirement}

Target function signature:
{function_signature}

Nagini function contract:
{nagini_contract}

Structured contract clauses (JSON):
{nagini_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Nagini result:
- type: {verdict_type}
- message: {verdict_message}
- details:
{verdict_details}

Output constraints:
- Output only complete Python source code (no markdown fences, no explanation).
- Keep the target function signature and Nagini contract semantics unchanged.
- Fix implementation code and loop invariants only.
- Use simple Python accepted by Nagini.
"""

PYTHON_WYBECODER_REPAIR_ANALYSIS_SYSTEM_PROMPT = """You are a verification-guided Python/Nagini repair planner.
Return strict JSON only."""

PYTHON_WYBECODER_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE = """Analyze a failed Nagini verification attempt and produce a repair plan.

Requirement:
{requirement}

Target function signature:
{function_signature}

Frozen Nagini function contract:
{nagini_contract}

Structured contract clauses (JSON):
{nagini_clauses_json}

Code annotation hints for the function body (JSON; optional):
{code_annotation_hints_json}

Current code:
{code}

Nagini result:
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
        "name": "Short stable name, e.g. postcondition_result or permission_returned",
        "kind": "syntax|contract_placement|permission|bounds_safety|key_safety|postcondition|frame|loop_invariant|exception_freedom|timeout|unknown",
        "evidence": "Relevant Nagini clue.",
        "repair_hint": "Concrete body or loop-annotation change to try."
      }}
    ],
    "global_strategy": "How to synthesize the fixes while preserving the frozen contract.",
    "risk_notes": ["Potential ways a repair could cheat or weaken semantics."]
  }}
- Treat the Nagini function contract as frozen. Do not suggest weakening or replacing it.
- Prefer Python body changes and ordinary Python expressions.
- Do not suggest unsupported Nagini helper APIs such as `Unfold`, `Fold`, `Unfolding`, `UnfoldAcc`, `FoldAcc`, `dict_set`, `dict_get`, `dict_acc`, or element permissions like `Acc(a[i])`/`Acc(d[key])`.
"""

PYTHON_WYBECODER_REPAIR_CANDIDATE_SYSTEM_PROMPT = """You are an expert Python/Nagini developer using prove-as-you-generate repair.
Output Python source code only."""

PYTHON_WYBECODER_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE = """Repair the Python/Nagini implementation using this verifier-derived plan.

Requirement:
{requirement}

Target function signature:
{function_signature}

Frozen Nagini function contract:
{nagini_contract}

Structured contract clauses (JSON):
{nagini_clauses_json}

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
- Output only complete Python source code (no markdown fences, no explanation).
- Include `from typing import Dict, List, Optional` and `from nagini_contracts.contracts import *`.
- Preserve the frozen target function signature and Nagini contract semantics.
- You may change function body logic and loop `Invariant(...)` annotations only.
- Use simple Python accepted by Nagini.
- Allowed Nagini calls in generated code are limited to the frozen `Requires(...)`/`Ensures(...)` contract plus simple `Assert(...)`, `Assume(...)`, and `Invariant(...)` when useful.
- Do not introduce unsupported helper APIs: no `Unfold`, `Fold`, `Unfolding`, `UnfoldAcc`, `FoldAcc`, `dict_set`, `dict_get`, `dict_acc`, `list_acc`, or element permissions such as `Acc(a[i])`/`Acc(d[key])`.
- Avoid hiding the algorithm in unsupported library calls or changing the specification to make proof easier.
"""


@dataclass
class PythonNaginiRequirementItem:
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
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        raise ValueError(f"No JSON object found in model output: {stripped[:500]}")
    return json.loads(match.group(0))


def _extract_python_code(text: str) -> str:
    stripped = text.strip()
    fenced = re.search(r"```(?:python|py)?\n([\s\S]*?)\n```", stripped)
    if fenced:
        return fenced.group(1).strip()
    stripped = re.sub(r"^```(?:python|py)?\s*\n?", "", stripped, count=1)
    stripped = re.sub(r"\n?```\s*$", "", stripped, count=1)
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
    hints = {"loop_invariants": []}
    if not isinstance(value, dict):
        return hints
    for key in ("loop_invariants", "invariants"):
        hints["loop_invariants"].extend(_as_list_of_str(value.get(key)))
    return hints


def _truncate_for_prompt(text: str, max_chars: int = 6000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]..."


def _function_name_from_signature(signature: str) -> str:
    match = re.search(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", signature)
    if not match:
        raise ValueError(f"function name missing in signature: {signature}")
    return match.group(1)


def _contract_lines_from_text(contract: str) -> List[str]:
    lines: List[str] = []
    for raw in contract.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("Requires(", "Ensures(")):
            lines.append(line)
    return lines


def _normalize_nagini_clauses(value: Any, contract_text: str = "") -> List[Dict[str, str]]:
    clauses: List[Dict[str, str]] = []
    if isinstance(value, list):
        for row in value:
            if not isinstance(row, dict):
                continue
            kind = str(row.get("type", "")).strip().lower()
            expr = str(row.get("expr", "")).strip()
            if kind in {"requires", "ensures"} and expr:
                clauses.append({"type": kind, "expr": expr})
    if clauses:
        return clauses

    for line in _contract_lines_from_text(contract_text):
        match = re.match(r"^(Requires|Ensures)\((.*)\)$", line)
        if match:
            clauses.append({"type": match.group(1).lower(), "expr": match.group(2).strip()})
    return clauses


def _build_nagini_contract(clauses: List[Dict[str, str]]) -> str:
    lines = []
    for clause in clauses:
        kind = str(clause.get("type", "")).strip().lower()
        expr = str(clause.get("expr", "")).strip()
        if kind == "requires" and expr:
            lines.append(f"Requires({expr})")
        elif kind == "ensures" and expr:
            lines.append(f"Ensures({expr})")
    return "\n".join(lines)


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


def _signature_param_types(signature: str) -> Dict[str, str]:
    match = re.search(r"\bdef\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*)\)\s*(?:->\s*[^:]+)?\s*:", signature)
    if not match:
        return {}
    out: Dict[str, str] = {}
    for param in _split_python_params(match.group(1)):
        if ":" not in param:
            continue
        name, typ = param.split(":", 1)
        name = name.split("=", 1)[0].strip()
        typ = typ.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            out[name] = typ
    return out


def _signature_return_type(signature: str) -> str:
    match = re.search(r"\)\s*->\s*([^:]+)\s*:", signature)
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def _is_scalar_or_optional_type(type_text: str) -> bool:
    compact = re.sub(r"\s+", "", type_text)
    return compact in {"int", "bool"} or compact.startswith("Optional[")


def _container_param_names(param_types: Dict[str, str]) -> set[str]:
    return {
        name
        for name, typ in param_types.items()
        if "List[" in typ or "Dict[" in typ
    }


def _rewrite_symbolic_none_helpers(expr: str) -> str:
    out = expr
    name = r"([A-Za-z_][A-Za-z0-9_]*)"
    out = re.sub(rf"Not\(\s*Eq\(\s*{name}\s*,\s*None\s*\)\s*\)", r"\1 is not None", out)
    out = re.sub(rf"Not\(\s*Eq\(\s*None\s*,\s*{name}\s*\)\s*\)", r"\1 is not None", out)
    out = re.sub(rf"Eq\(\s*{name}\s*,\s*None\s*\)", r"\1 is None", out)
    out = re.sub(rf"Eq\(\s*None\s*,\s*{name}\s*\)", r"\1 is None", out)
    return out


def _rewrite_chained_comparisons(expr: str) -> str:
    atom = r"(?:[A-Za-z_][A-Za-z0-9_]*|[-]?\d+|len\([^()]+\)|Result\(\))"
    op = r"(?:<=|<|>=|>)"

    def repl(match: re.Match[str]) -> str:
        left, first_op, middle, second_op, right = match.groups()
        return f"{left} {first_op} {middle} and {middle} {second_op} {right}"

    return re.sub(rf"\b({atom})\s*({op})\s*({atom})\s*({op})\s*({atom})\b", repl, expr)


def _rewrite_negative_list_indices(expr: str, param_types: Dict[str, str]) -> str:
    out = expr
    for name, typ in param_types.items():
        if "List[" in typ:
            out = re.sub(
                rf"\b{re.escape(name)}\s*\[\s*-1\s*\]",
                f"{name}[len({name}) - 1]",
                out,
            )
    return out


def _rewrite_old_scalar_params(expr: str, param_types: Dict[str, str]) -> str:
    out = expr
    for name, typ in param_types.items():
        if _is_scalar_or_optional_type(typ):
            out = re.sub(rf"\bOld\(\s*{re.escape(name)}\s*\)", name, out)
    return out


def _has_unsupported_nagini_subset_syntax(expr: str, param_types: Dict[str, str]) -> bool:
    if re.search(
        r"\b(?:Eq|Not|And|Or|write|Forall|Exists|Unfold|Fold|Unfolding|FoldAcc|UnfoldAcc)\s*\(",
        expr,
    ):
        return True
    if re.search(r"\b(?:dict_set|dict_get|dict_acc|list_acc)\s*\(", expr):
        return True
    for name in _container_param_names(param_types):
        if re.search(rf"\bAcc\(\s*{re.escape(name)}\s*\[", expr):
            return True
    if re.search(r"\b(?:list_pred|dict_pred)\([^()]+\)\s*==\s*Old\(", expr):
        return True
    if re.search(r"\bOld\(\s*(?:list_pred|dict_pred)\(", expr):
        return True
    return False


def _is_impossible_same_state_len_postcondition(expr: str, param_types: Dict[str, str]) -> bool:
    for name in _container_param_names(param_types):
        len_name = rf"len\(\s*{re.escape(name)}\s*\)"
        if re.fullmatch(rf"{len_name}\s*==\s*{len_name}\s*[+-]\s*[1-9]\d*", expr):
            return True
        if re.fullmatch(rf"{len_name}\s*[+-]\s*[1-9]\d*\s*==\s*{len_name}", expr):
            return True
    return False


def _is_out_of_range_append_index_postcondition(expr: str, param_types: Dict[str, str]) -> bool:
    for name, typ in param_types.items():
        if "List[" not in typ:
            continue
        if re.search(rf"\b{re.escape(name)}\s*\[\s*len\(\s*{re.escape(name)}\s*\)\s*\]", expr):
            return True
    return False


def _split_top_level_bool(expr: str, operator: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    token = f" {operator} "
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and expr.startswith(token, i):
            parts.append(expr[start:i].strip())
            start = i + len(token)
            i = start
            continue
        i += 1
    tail = expr[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _is_type_check_expr(expr: str) -> bool:
    stripped = expr.strip()
    return stripped.startswith("isinstance(") and stripped.endswith(")")


def _drop_type_check_conjuncts(expr: str) -> Optional[str]:
    parts = _split_top_level_bool(expr, "and")
    if len(parts) <= 1:
        return None if _is_type_check_expr(expr) else expr
    kept = [part for part in parts if not _is_type_check_expr(part)]
    if not kept:
        return None
    return " and ".join(kept)


def _strip_balanced_outer_parentheses(expr: str) -> tuple[str, bool]:
    stripped = expr.strip()
    if not (stripped.startswith("(") and stripped.endswith(")")):
        return stripped, False
    depth = 0
    for idx, ch in enumerate(stripped):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and idx != len(stripped) - 1:
                return stripped, False
    return stripped[1:-1].strip(), depth == 0


def _rewrite_implication_operator(expr: str) -> str:
    stripped = expr.strip()
    if re.fullmatch(r"Implies\s*\(.*\)", stripped):
        return stripped
    body, had_outer_parentheses = _strip_balanced_outer_parentheses(stripped)
    depth = 0
    for idx, ch in enumerate(body):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and body.startswith("==>", idx):
            left = body[:idx].strip()
            right = body[idx + 3 :].strip()
            if left and right:
                return f"Implies({left}, {right})"
    return f"({body})" if had_outer_parentheses else stripped


def _unsupported_wybecoder_candidate_reason(code_text: str) -> Optional[str]:
    unsupported_call = re.search(
        r"\b(Unfold|Fold|Unfolding|UnfoldAcc|FoldAcc|dict_set|dict_get|dict_acc|list_acc)\s*\(",
        code_text,
    )
    if unsupported_call:
        return f"unsupported helper call: {unsupported_call.group(1)}"
    element_acc = re.search(r"\bAcc\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\[", code_text)
    if element_acc:
        return "unsupported element permission"
    symbolic_helper = re.search(r"\b(Eq|Not|And|Or|write)\s*\(", code_text)
    if symbolic_helper:
        return f"unsupported symbolic helper: {symbolic_helper.group(1)}"
    return None


def _normalize_nagini_expr_for_subset(expr: str, param_types: Dict[str, str]) -> Optional[str]:
    out = expr.strip()
    if not out:
        return None

    out = re.sub(r"\bResult\b(?!\s*\()", "Result()", out)
    out = re.sub(r"\bis_none\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", r"\1 is None", out)
    out = re.sub(r"\bis_some\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", r"\1 is not None", out)
    out = _rewrite_symbolic_none_helpers(out)
    out = _rewrite_implication_operator(out)
    out = _drop_type_check_conjuncts(out)
    if out is None:
        return None
    out = _rewrite_chained_comparisons(out)
    out = _rewrite_negative_list_indices(out, param_types)
    out = _rewrite_old_scalar_params(out, param_types)
    out = re.sub(
        r"Result\(\)\s*==\s*not\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"Result() == (not \1)",
        out,
    )
    out = re.sub(r"\bwildcard\b", "1/2", out)

    for name, typ in param_types.items():
        if "Dict[" in typ:
            out = re.sub(rf"\blist_pred\(\s*{re.escape(name)}\s*\)", f"dict_pred({name})", out)

    if _has_unsupported_nagini_subset_syntax(out, param_types):
        return None
    if _is_impossible_same_state_len_postcondition(out, param_types):
        return None
    if _is_out_of_range_append_index_postcondition(out, param_types):
        return None
    if re.search(r"\bForall\b|\blambda\b|\[\[", out):
        return None

    out = re.sub(r"Acc\(\s*(list_pred\([^)]+\)|dict_pred\([^)]+\))\s*,\s*1\s*/\s*2\s*\)", r"Acc(\1)", out)

    for name, typ in param_types.items():
        if _is_scalar_or_optional_type(typ):
            out = re.sub(
                rf"\s*(?:and|or)\s*Acc\(\s*{re.escape(name)}\s*(?:,\s*[^()]*)?\)",
                "",
                out,
            )
            out = re.sub(
                rf"Acc\(\s*{re.escape(name)}\s*(?:,\s*[^()]*)?\)\s*(?:and|or)\s*",
                "",
                out,
            )
            if re.fullmatch(rf"Acc\(\s*{re.escape(name)}\s*(?:,\s*[^()]*)?\)", out):
                return None
            if typ in {"int", "bool"}:
                out = re.sub(
                    rf"\s*(?:and|or)\s*{re.escape(name)}\s+is\s+not\s+None",
                    "",
                    out,
                )
                out = re.sub(
                    rf"{re.escape(name)}\s+is\s+not\s+None\s*(?:and|or)\s*",
                    "",
                    out,
                )
                if re.fullmatch(rf"{re.escape(name)}\s+is\s+not\s+None", out):
                    return None

    bare_pred = re.fullmatch(r"(list_pred|dict_pred)\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", out)
    if bare_pred:
        pred, name = bare_pred.groups()
        if name in param_types:
            out = f"Acc({pred}({name}))"

    if "Acc(" in out and "Implies(" in out:
        return None
    if _is_impossible_same_state_len_postcondition(out, param_types):
        return None
    if _is_out_of_range_append_index_postcondition(out, param_types):
        return None
    return out.strip() or None


def _sanitize_nagini_clauses_for_subset(
    clauses: List[Dict[str, str]],
    function_signature: str,
) -> tuple[List[Dict[str, str]], List[Dict[str, str]], Dict[str, Any]]:
    param_types = _signature_param_types(function_signature)
    return_type = _signature_return_type(function_signature)
    sanitized: List[Dict[str, str]] = []
    removed: List[Dict[str, str]] = []
    rewritten: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for clause in clauses:
        kind = str(clause.get("type", "")).strip().lower()
        expr = str(clause.get("expr", "")).strip()
        normalized = _normalize_nagini_expr_for_subset(expr, param_types)
        if kind == "ensures" and return_type in {"None", "NoneType"} and normalized and "Result()" in normalized:
            removed.append({"type": kind, "expr": expr})
            continue
        if kind not in {"requires", "ensures"} or not normalized:
            removed.append({"type": kind, "expr": expr})
            continue
        normalized_parts = _split_top_level_bool(normalized, "and")
        if kind == "ensures" and any(part.startswith("Acc(") for part in normalized_parts):
            normalized_parts = [part for part in normalized_parts if not part.startswith("Acc(")] or normalized_parts
        if len(normalized_parts) > 1 or normalized != expr:
            rewritten.append({"type": kind, "expr": expr, "normalized_expr": " and ".join(normalized_parts)})
        for normalized_part in normalized_parts:
            key = (kind, re.sub(r"\s+", "", normalized_part))
            if key in seen:
                continue
            seen.add(key)
            sanitized.append({"type": kind, "expr": normalized_part})

    def has_clause(kind: str, expr: str) -> bool:
        norm = re.sub(r"\s+", "", expr)
        return any(
            c["type"] == kind and re.sub(r"\s+", "", c["expr"]) == norm
            for c in sanitized
        )

    inferred_requires: List[Dict[str, str]] = []
    inferred_ensures: List[Dict[str, str]] = []
    all_expr_text = "\n".join(c["expr"] for c in sanitized)
    for name, typ in param_types.items():
        pred = ""
        if "List[" in typ:
            pred = f"list_pred({name})"
        elif "Dict[" in typ:
            pred = f"dict_pred({name})"
        if not pred:
            continue
        uses_container = bool(
            re.search(rf"\blen\(\s*{re.escape(name)}\s*\)", all_expr_text)
            or re.search(rf"\b{re.escape(name)}\s*\[", all_expr_text)
            or re.search(rf"\bin\s+{re.escape(name)}\b", all_expr_text)
            or pred in all_expr_text
        )
        if uses_container:
            acc = f"Acc({pred})"
            if not has_clause("requires", acc):
                inferred_requires.append({"type": "requires", "expr": acc})
            if not has_clause("ensures", acc):
                inferred_ensures.append({"type": "ensures", "expr": acc})

    normalized_sanitized: List[Dict[str, str]] = []
    for clause in sanitized:
        kind = clause["type"]
        expr = clause["expr"]
        if kind == "ensures":
            expr = re.sub(
                r"Result\(\)\s*==\s*([A-Za-z_][A-Za-z0-9_]*\s*\[[^\]]+\])$",
                r"Result() == Old(\1)",
                expr,
            )
        normalized_sanitized.append({"type": kind, "expr": expr})

    def dependency_rank(clause: Dict[str, str]) -> int:
        expr = clause["expr"]
        if expr.startswith("Acc("):
            return 0
        has_index_access = any(
            re.search(rf"\b{re.escape(name)}\s*\[", expr)
            for name in _container_param_names(param_types)
        )
        has_structure = any(
            re.search(rf"\blen\(\s*{re.escape(name)}\s*\)", expr)
            or re.search(rf"\bin\s+{re.escape(name)}\b", expr)
            for name in _container_param_names(param_types)
        )
        if has_structure and not has_index_access:
            return 1
        return 3 if has_index_access else 2

    ordered: List[Dict[str, str]] = []
    ordered.extend(inferred_requires)
    ordered.extend(
        sorted(
            (c for c in normalized_sanitized if c["type"] == "requires"),
            key=dependency_rank,
        )
    )
    ordered.extend(inferred_ensures)
    ordered.extend(
        sorted(
            (c for c in normalized_sanitized if c["type"] == "ensures"),
            key=dependency_rank,
        )
    )
    sanitized = ordered
    metadata = {
        "input_clause_count": len(clauses),
        "output_clause_count": len(sanitized),
        "removed_clause_count": len(removed),
        "rewritten_clause_count": len(rewritten),
        "rewritten_nagini_subset_clauses": rewritten,
    }
    return sanitized, removed, metadata


def _find_function_header_line(lines: List[str], function_name: str) -> int:
    pattern = re.compile(rf"^def\s+{re.escape(function_name)}\s*\(")
    for idx, line in enumerate(lines):
        if pattern.search(line):
            return idx
    raise ValueError(f"function declaration not found for generated function '{function_name}'")


def _enforce_nagini_contract(
    code_text: str,
    function_signature: str,
    nagini_contract: str,
) -> tuple[str, Dict[str, Any]]:
    function_name = _function_name_from_signature(function_signature)
    lines = code_text.splitlines()
    header_idx = _find_function_header_line(lines, function_name)
    indent = "    "
    insert_idx = header_idx + 1
    removed = 0
    while insert_idx < len(lines):
        stripped = lines[insert_idx].strip()
        if not stripped:
            insert_idx += 1
            continue
        if stripped.startswith(("Requires(", "Ensures(")):
            del lines[insert_idx]
            removed += 1
            continue
        break
    contract_lines = [indent + line for line in _contract_lines_from_text(nagini_contract)]
    lines[insert_idx:insert_idx] = contract_lines
    filtered_lines: List[str] = []
    removed_invalid_invariants = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Invariant(") and re.search(
            r"\bwildcard\b|\bForall\b|\blambda\b|\[\[|list_pred\(\s*d\s*\)",
            stripped,
        ):
            removed_invalid_invariants += 1
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines).rstrip() + "\n", {
        "function_name": function_name,
        "action": "replaced" if removed else "inserted",
        "removed_contract_lines": removed,
        "removed_invalid_invariants": removed_invalid_invariants,
        "changed": True,
    }


def _prepare_python_artifact(
    raw_code: str,
    function_signature: str,
    nagini_contract: str,
    filename: str,
) -> tuple[str, Dict[str, Any]]:
    extracted_code = _extract_python_code(raw_code)
    code_text, contract_enforcement = _enforce_nagini_contract(
        code_text=extracted_code,
        function_signature=function_signature,
        nagini_contract=nagini_contract,
    )
    try:
        ast.parse(code_text, filename=filename)
    except SyntaxError as exc:
        location = f"line {exc.lineno}, column {exc.offset}" if exc.lineno else "unknown location"
        raise ValueError(
            f"deterministic Python artifact validation failed at {location}: {exc.msg}"
        ) from exc
    return code_text, {
        "enabled": True,
        "code_extraction_changed": extracted_code.strip() != raw_code.strip(),
        "canonical_contract_enforced": True,
        "ast_parse_valid": True,
        "contract_enforcement": contract_enforcement,
    }


def load_python_nagini_requirements(
    requirements_file: Path,
    signature_file: Optional[Path] = None,
) -> List[PythonNaginiRequirementItem]:
    """Load Python/Nagini requirement entries and optional dataset signature hints."""
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
    items: List[PythonNaginiRequirementItem] = []
    for obj in raw:
        if "id" not in obj or "path" not in obj:
            raise ValueError(f"Invalid requirement entry: {obj}")
        req_text = obj.get("requirement_zh") or obj.get("requirement_en") or obj.get("requirement")
        if not req_text:
            raise ValueError(f"Requirement text missing for entry: {obj}")
        rid = int(obj["id"])
        items.append(
            PythonNaginiRequirementItem(
                id=rid,
                path=str(obj["path"]),
                requirement=str(req_text),
                signature_hint=str(obj.get("function_signature") or signature_by_id.get(rid, "")),
            )
        )
    return items


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


class PythonNaginiRequirementToCodePipeline:
    """End-to-end Python/Nagini generation pipeline."""

    def __init__(
        self,
        llm_client: OpenAICompatibleClient,
        output_dir: Path,
        verify_timeout: int = 120,
        skip_verify: bool = False,
        logger: Optional[Callable[[str], None]] = None,
        nagini_bin: str = "nagini",
        enable_constraint_extraction: bool = True,
        spec_self_check_rounds: int = 1,
        enable_code_repair: bool = True,
        code_repair_max_iter: int = 3,
        code_repair_strategy: str = "simple",
        wybecoder_candidates: int = 3,
        reuse_artifacts_from: Optional[Path] = None,
        pipeline_variant: str = "enhanced",
        enhancement_method: Optional[str] = None,
    ):
        self.llm_client = llm_client
        self.output_dir = output_dir
        self.skip_verify = skip_verify
        self.logger = logger
        self.verifier = NaginiVerifier(timeout=verify_timeout, nagini_cmd=nagini_bin)
        self.enable_constraint_extraction = enable_constraint_extraction
        self.spec_self_check_rounds = max(0, spec_self_check_rounds)
        self.enable_code_repair = enable_code_repair
        self.code_repair_max_iter = max(0, code_repair_max_iter)
        if code_repair_strategy not in {"simple", "wybecoder"}:
            raise ValueError(f"Unsupported code_repair_strategy: {code_repair_strategy}")
        self.code_repair_strategy = code_repair_strategy
        self.wybecoder_candidates = max(1, wybecoder_candidates)
        self.reuse_artifacts_from = reuse_artifacts_from
        self.pipeline_variant = pipeline_variant
        self.enhancement_method = enhancement_method

    def _log(self, message: str) -> None:
        if self.logger:
            self.logger(message)

    def run(
        self,
        requirements: List[PythonNaginiRequirementItem],
        resume: bool = False,
    ) -> Dict[str, Any]:
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
            "language": "python",
            "verifier": "nagini",
            "pipeline_variant": self.pipeline_variant,
            "enhancement_method": self.enhancement_method,
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

    def _extract_constraints(self, item: PythonNaginiRequirementItem) -> Dict[str, Any]:
        prompt = PYTHON_CONSTRAINT_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            signature_hint=item.signature_hint or "(none)",
        )
        raw = self.llm_client.chat(PYTHON_CONSTRAINT_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        return {
            "function_signature": str(data.get("function_signature", "")).strip(),
            "preconditions": _as_list_of_str(data.get("preconditions")),
            "postconditions": _as_list_of_str(data.get("postconditions")),
            "permission_conditions": _as_list_of_str(data.get("permission_conditions")),
            "exception_freedom": _as_list_of_str(data.get("exception_freedom")),
            "invariants": _as_list_of_str(data.get("invariants")),
            "notes": str(data.get("notes", "")).strip(),
            "raw_model_output": raw,
        }

    def _generate_direct_spec(self, item: PythonNaginiRequirementItem) -> Dict[str, Any]:
        prompt = PYTHON_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            signature_hint=item.signature_hint or "(none)",
        )
        raw = self.llm_client.chat(PYTHON_SPEC_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        data["raw_model_output"] = raw
        return data

    def _constraints_to_spec(
        self,
        item: PythonNaginiRequirementItem,
        constraints: Dict[str, Any],
        signature_hint: str,
    ) -> Dict[str, Any]:
        prompt = PYTHON_CONSTRAINT_TO_SPEC_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
            signature_hint=signature_hint or "(none)",
        )
        raw = self.llm_client.chat(PYTHON_CONSTRAINT_TO_SPEC_SYSTEM_PROMPT, prompt)
        data = _extract_json_object(raw)
        data["raw_model_output"] = raw
        return data

    def _fallback_to_direct_spec(
        self,
        item: PythonNaginiRequirementItem,
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

    def _spec_sanitization_preview(
        self,
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> Dict[str, Any]:
        function_signature = signature_fallback.strip() or str(
            spec_json.get("function_signature", "")
        ).strip()
        nagini_contract = str(
            spec_json.get("nagini_contract") or spec_json.get("contract") or ""
        ).strip()
        clauses = _normalize_nagini_clauses(
            spec_json.get("nagini_clauses"),
            contract_text=nagini_contract,
        )
        clauses = [
            {"type": c["type"], "expr": c["expr"]}
            for c in clauses
            if c["type"] in {"requires", "ensures"} and c["expr"]
        ]
        if not function_signature or not clauses:
            return {
                "valid_preview": False,
                "input_clause_count": len(clauses),
                "output_clause_count": 0,
                "removed_clause_count": len(clauses),
                "rewritten_clause_count": 0,
            }
        sanitized, removed, metadata = _sanitize_nagini_clauses_for_subset(
            clauses,
            function_signature=function_signature,
        )
        return {
            "valid_preview": bool(sanitized),
            "removed_invalid_nagini_subset_clauses": removed,
            **metadata,
        }

    def _should_fallback_after_refinement(
        self,
        initial_preview: Dict[str, Any],
        refined_preview: Dict[str, Any],
    ) -> bool:
        if not refined_preview.get("valid_preview"):
            return True
        initial_out = int(initial_preview.get("output_clause_count") or 0)
        refined_out = int(refined_preview.get("output_clause_count") or 0)
        refined_removed = int(refined_preview.get("removed_clause_count") or 0)
        refined_rewritten = int(refined_preview.get("rewritten_clause_count") or 0)
        if refined_out < initial_out:
            return True
        if refined_removed >= 2:
            return True
        if refined_removed > 0 and refined_rewritten > 0:
            return True
        return False

    def _check_and_refine_spec(
        self,
        item: PythonNaginiRequirementItem,
        constraints: Dict[str, Any],
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        rounds: List[Dict[str, Any]] = []
        current_spec = spec_json
        best_spec = spec_json
        final_aligned = False
        fallback_to_initial_spec = False
        initial_preview = self._spec_sanitization_preview(
            spec_json,
            signature_fallback=signature_fallback,
        )

        for round_idx in range(1, self.spec_self_check_rounds + 1):
            check_prompt = PYTHON_SPEC_CHECK_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
            )
            check_raw = self.llm_client.chat(PYTHON_SPEC_CHECK_SYSTEM_PROMPT, check_prompt)
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

            refine_prompt = PYTHON_SPEC_REFINE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                constraints_json=json.dumps(constraints, ensure_ascii=False, indent=2),
                spec_json=json.dumps(current_spec, ensure_ascii=False, indent=2),
                check_json=json.dumps(check, ensure_ascii=False, indent=2),
            )
            refine_raw = self.llm_client.chat(PYTHON_SPEC_REFINE_SYSTEM_PROMPT, refine_prompt)
            current_spec = _extract_json_object(refine_raw)
            current_spec["raw_model_output"] = refine_raw
            refined_preview = self._spec_sanitization_preview(
                current_spec,
                signature_fallback=signature_fallback,
            )
            round_info["refined_sanitization_preview"] = refined_preview
            if self._should_fallback_after_refinement(initial_preview, refined_preview):
                fallback_to_initial_spec = True
                round_info["refinement_rejected"] = True
                round_info["rejection_reason"] = "refined spec failed Python/Nagini subset safety preview"
                best_spec = spec_json
                rounds.append(round_info)
                break
            round_info["refined"] = True
            rounds.append(round_info)

        if not final_aligned and best_spec is spec_json and any(r.get("refined") for r in rounds):
            fallback_to_initial_spec = True

        return best_spec, {
            "rounds": rounds,
            "final_aligned": final_aligned,
            "max_rounds": self.spec_self_check_rounds,
            "fallback_to_initial_spec": fallback_to_initial_spec,
            "initial_sanitization_preview": initial_preview,
        }

    def _validate_spec_fields(
        self,
        spec_json: Dict[str, Any],
        signature_fallback: str = "",
    ) -> tuple[str, str, List[Dict[str, str]], str, Dict[str, List[str]], Dict[str, Any]]:
        function_signature = signature_fallback.strip() or str(
            spec_json.get("function_signature", "")
        ).strip()
        nagini_contract = str(
            spec_json.get("nagini_contract") or spec_json.get("contract") or ""
        ).strip()
        notes = str(spec_json.get("notes", "")).strip()
        code_annotation_hints = _normalize_code_annotation_hints(
            spec_json.get("code_annotation_hints")
        )
        clauses = _normalize_nagini_clauses(
            spec_json.get("nagini_clauses"),
            contract_text=nagini_contract,
        )
        clauses = [
            {"type": c["type"], "expr": c["expr"]}
            for c in clauses
            if c["type"] in {"requires", "ensures"} and c["expr"]
        ]
        if not function_signature:
            raise ValueError("function_signature is empty after generation/refinement.")
        if not function_signature.rstrip().endswith(":"):
            raise ValueError(f"function_signature must end with ':': {function_signature}")
        if not clauses:
            raise ValueError("nagini_clauses must contain at least one requires/ensures clause.")
        clauses, removed_clauses, sanitization_metadata = _sanitize_nagini_clauses_for_subset(
            clauses,
            function_signature=function_signature,
        )
        if not clauses:
            raise ValueError("all generated Nagini clauses were rejected by subset sanitizer.")
        nagini_contract = _build_nagini_contract(clauses)
        postprocessing = {
            "removed_invalid_nagini_subset_clauses": removed_clauses,
            **sanitization_metadata,
        }
        return (
            function_signature,
            nagini_contract,
            clauses,
            notes,
            code_annotation_hints,
            postprocessing,
        )

    def _copy_reused_artifacts(
        self,
        item: PythonNaginiRequirementItem,
        specs_dir: Path,
        code_dir: Path,
    ) -> tuple[Path, Path, Dict[str, Any], str]:
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
        nagini_contract = str(spec_out.get("nagini_contract", "")).strip()
        nagini_clauses = _normalize_nagini_clauses(
            spec_out.get("nagini_clauses"),
            contract_text=nagini_contract,
        )
        if not function_signature:
            raise ValueError(f"reused spec missing function_signature: {spec_file}")
        if not nagini_clauses:
            raise ValueError(f"reused spec missing Nagini clauses: {spec_file}")

        code_text = code_file.read_text()
        code_text, contract_enforcement = _enforce_nagini_contract(
            code_text=code_text,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
        )
        code_file.write_text(code_text)
        spec_out["reuse_contract_enforcement"] = contract_enforcement
        return spec_file, code_file, spec_out, code_text

    def _run_one(self, item: PythonNaginiRequirementItem, specs_dir: Path, code_dir: Path) -> Dict[str, Any]:
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
            nagini_contract = str(spec_out.get("nagini_contract", "")).strip()
            nagini_clauses = _normalize_nagini_clauses(
                spec_out.get("nagini_clauses"),
                contract_text=nagini_contract,
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
                    "enabled": True,
                    "initial_generation": spec_out.get("reuse_contract_enforcement"),
                    "repair_attempts": [],
                },
                "enhanced": {
                    "enable_constraint_extraction": False,
                    "spec_self_check_rounds": 0,
                    "enable_code_repair": self.enable_code_repair,
                    "code_repair_max_iter": self.code_repair_max_iter,
                    "code_repair_strategy": self.code_repair_strategy,
                    "wybecoder_candidates": self.wybecoder_candidates,
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
                nagini_contract=nagini_contract,
                nagini_clauses=nagini_clauses,
                code_annotation_hints=code_annotation_hints,
                result=result,
            )
            return result

        constraints: Optional[Dict[str, Any]] = None
        signature_fallback = item.signature_hint

        if self.enable_constraint_extraction:
            try:
                self._log(f"[id={item.id}] stage=constraint_extraction start")
                constraints = self._extract_constraints(item)
                signature_fallback = item.signature_hint or constraints.get("function_signature", "")
                self._log(f"[id={item.id}] stage=constraint_extraction done")

                self._log(f"[id={item.id}] stage=constraint_to_spec start")
                initial_spec = self._constraints_to_spec(
                    item=item,
                    constraints=constraints,
                    signature_hint=signature_fallback,
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
                    "permission_conditions": [],
                    "exception_freedom": [],
                    "invariants": [],
                    "notes": "Constraint extraction failed; direct spec fallback was used.",
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
                            signature_fallback=signature_fallback,
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
                "reason": "constraint extraction module disabled",
                "rounds": [],
                "final_aligned": None,
                "max_rounds": 0,
            }
            self._log(f"[id={item.id}] stage=spec_generation done mode=direct")

        try:
            (
                function_signature,
                nagini_contract,
                nagini_clauses,
                notes,
                code_annotation_hints,
                spec_postprocessing,
            ) = self._validate_spec_fields(spec_json, signature_fallback=signature_fallback)
        except ValueError as exc:
            if self.enable_constraint_extraction and not alignment_info.get("fallback_to_direct_spec"):
                spec_json, fallback_alignment = self._fallback_to_direct_spec(
                    item=item,
                    reason=str(exc),
                    stage="spec_validation",
                )
                (
                    function_signature,
                    nagini_contract,
                    nagini_clauses,
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
            "language": "python",
            "verifier": "nagini",
            "pipeline_variant": self.pipeline_variant,
            "enhancement_method": self.enhancement_method,
            "requirement": item.requirement,
            "signature_hint": item.signature_hint,
            "function_signature": function_signature,
            "nagini_contract": nagini_contract,
            "nagini_clauses": nagini_clauses,
            "code_annotation_hints": code_annotation_hints,
            "notes": notes,
            "constraints": constraints,
            "alignment_check": alignment_info,
            "raw_model_output": spec_json.get("raw_model_output", ""),
            "spec_postprocessing": spec_postprocessing,
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
                "reuse_artifacts_from": str(self.reuse_artifacts_from)
                if self.reuse_artifacts_from is not None
                else None,
            },
        }
        spec_file = specs_dir / Path(item.path).with_suffix(".json")
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(spec_out, ensure_ascii=False, indent=2))
        self._log(f"[id={item.id}] stage=spec_generation done spec_file={spec_file}")

        self._log(f"[id={item.id}] stage=code_generation start")
        code_prompt = PYTHON_CODE_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
            nagini_clauses_json=json.dumps(nagini_clauses, ensure_ascii=False, indent=2),
            code_annotation_hints_json=json.dumps(
                code_annotation_hints,
                ensure_ascii=False,
                indent=2,
            ),
        )
        code_raw = self.llm_client.chat(PYTHON_CODE_SYSTEM_PROMPT, code_prompt)
        code_file = code_dir / Path(item.path)
        code_text, artifact_postprocessing = _prepare_python_artifact(
            raw_code=code_raw,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
            filename=str(code_file),
        )
        initial_contract_enforcement = artifact_postprocessing["contract_enforcement"]
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
            "deterministic_artifact_postprocessing": artifact_postprocessing,
            "enhanced": {
                "enable_constraint_extraction": self.enable_constraint_extraction,
                "spec_self_check_rounds": self.spec_self_check_rounds,
                "enable_code_repair": self.enable_code_repair,
                "code_repair_max_iter": self.code_repair_max_iter,
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
            nagini_contract=nagini_contract,
            nagini_clauses=nagini_clauses,
            code_annotation_hints=code_annotation_hints,
            result=result,
        )
        return result

    def _verify_with_optional_repair(
        self,
        item: PythonNaginiRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        nagini_contract: str,
        nagini_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        result: Dict[str, Any],
    ) -> None:
        report_dir = self.output_dir / "reports"
        repair_history: List[Dict[str, Any]] = []

        self._log(f"[id={item.id}] stage=verify start")
        verdict = self.verifier.verify(code_file)
        initial_code_text = code_text
        initial_verdict = verdict
        repair_limit = self.code_repair_max_iter if self.enable_code_repair else 0
        for attempt in range(1, repair_limit + 1):
            if verdict.is_valid():
                break
            details = verdict.details or ""
            detail_path = report_dir / Path(item.path).with_suffix(f".repair{attempt - 1}.nagini.log")
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
                if self.code_repair_strategy == "wybecoder":
                    (
                        code_text,
                        verdict,
                        strategy_info,
                        contract_enforcement,
                    ) = self._build_wybecoder_repair(
                        item=item,
                        code_file=code_file,
                        code_text=code_text,
                        function_signature=function_signature,
                        nagini_contract=nagini_contract,
                        nagini_clauses=nagini_clauses,
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
                        nagini_contract=nagini_contract,
                        nagini_clauses=nagini_clauses,
                        code_annotation_hints=code_annotation_hints,
                        verdict=verdict,
                        details=details,
                    )
                    code_text, contract_enforcement = _enforce_nagini_contract(
                        code_text=code_text,
                        function_signature=function_signature,
                        nagini_contract=nagini_contract,
                    )
                    code_file.write_text(code_text)
                    history_entry["simple"] = strategy_info
                    verdict = self.verifier.verify(code_file)
                result.setdefault("contract_enforcement", {}).setdefault(
                    "repair_attempts", []
                ).append(
                    {
                        "attempt": attempt,
                        **contract_enforcement,
                    }
                )
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

        repair_fallback: Optional[Dict[str, Any]] = None
        if repair_history and not verdict.is_valid():
            repair_fallback = {
                "restored_initial_code_after_failed_repairs": True,
                "discarded_final_candidate_type": verdict.verdict_type.value,
                "discarded_final_candidate_message": verdict.message,
            }
            code_text = initial_code_text
            code_file.write_text(initial_code_text)
            verdict = initial_verdict
            self._log(
                f"[id={item.id}] stage=code_repair all_attempts_failed "
                "fallback=initial_code"
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
        if repair_fallback is not None:
            verification["repair_fallback"] = repair_fallback
        if verdict.details:
            verify_log = report_dir / Path(item.path).with_suffix(".nagini.log")
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
        item: PythonNaginiRequirementItem,
        code_text: str,
        function_signature: str,
        nagini_contract: str,
        nagini_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> tuple[str, Dict[str, Any]]:
        repair_prompt = PYTHON_REPAIR_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
            nagini_clauses_json=json.dumps(nagini_clauses, ensure_ascii=False, indent=2),
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
        repaired_raw = self.llm_client.chat(PYTHON_REPAIR_SYSTEM_PROMPT, repair_prompt)
        return _extract_python_code(repaired_raw), {
            "strategy": "simple",
            "raw_model_output": repaired_raw,
        }

    def _wybecoder_repair_plan(
        self,
        item: PythonNaginiRequirementItem,
        code_text: str,
        function_signature: str,
        nagini_contract: str,
        nagini_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
    ) -> Dict[str, Any]:
        plan_prompt = PYTHON_WYBECODER_REPAIR_ANALYSIS_USER_PROMPT_TEMPLATE.format(
            requirement=item.requirement,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
            nagini_clauses_json=json.dumps(nagini_clauses, ensure_ascii=False, indent=2),
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
            PYTHON_WYBECODER_REPAIR_ANALYSIS_SYSTEM_PROMPT,
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
                        "repair_hint": "Repair the implementation and loop annotations.",
                    }
                ],
                "global_strategy": "Use the Nagini output directly to repair the function.",
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
                    "repair_hint": "Repair the implementation and loop annotations.",
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
            "Try an alternative Nagini-friendly implementation while preserving the frozen contract."
        )
        return focuses

    def _build_wybecoder_repair(
        self,
        item: PythonNaginiRequirementItem,
        code_file: Path,
        code_text: str,
        function_signature: str,
        nagini_contract: str,
        nagini_clauses: List[Dict[str, str]],
        code_annotation_hints: Dict[str, List[str]],
        verdict: Any,
        details: str,
        attempt: int,
    ) -> tuple[str, Any, Dict[str, Any], Dict[str, Any]]:
        plan = self._wybecoder_repair_plan(
            item=item,
            code_text=code_text,
            function_signature=function_signature,
            nagini_contract=nagini_contract,
            nagini_clauses=nagini_clauses,
            code_annotation_hints=code_annotation_hints,
            verdict=verdict,
            details=details,
        )
        candidate_count = self.wybecoder_candidates
        focuses = self._candidate_focuses(plan)
        candidate_records: List[Dict[str, Any]] = []
        best_code = code_text
        best_verdict = verdict
        best_contract_enforcement: Dict[str, Any] = {"changed": False}

        for candidate_idx in range(1, candidate_count + 1):
            focus = focuses[(candidate_idx - 1) % len(focuses)]
            self._log(
                f"[id={item.id}] stage=wybecoder_repair attempt={attempt} "
                f"candidate={candidate_idx}/{candidate_count}"
            )
            candidate_prompt = PYTHON_WYBECODER_REPAIR_CANDIDATE_USER_PROMPT_TEMPLATE.format(
                requirement=item.requirement,
                function_signature=function_signature,
                nagini_contract=nagini_contract,
                nagini_clauses_json=json.dumps(nagini_clauses, ensure_ascii=False, indent=2),
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
                PYTHON_WYBECODER_REPAIR_CANDIDATE_SYSTEM_PROMPT,
                candidate_prompt,
            )
            candidate_code = _extract_python_code(raw)
            unsupported_reason = _unsupported_wybecoder_candidate_reason(candidate_code)
            if unsupported_reason:
                candidate_records.append(
                    {
                        "candidate": candidate_idx,
                        "focus": focus,
                        "valid": False,
                        "type": VerdictType.INVALID.value,
                        "message": f"Rejected before Nagini: {unsupported_reason}",
                        "rejected_before_verify": True,
                        "rejection_reason": unsupported_reason,
                        "raw_model_output": raw,
                    }
                )
                continue
            candidate_code, contract_enforcement = _enforce_nagini_contract(
                code_text=candidate_code,
                function_signature=function_signature,
                nagini_contract=nagini_contract,
            )
            unsupported_reason = _unsupported_wybecoder_candidate_reason(candidate_code)
            if unsupported_reason:
                candidate_records.append(
                    {
                        "candidate": candidate_idx,
                        "focus": focus,
                        "valid": False,
                        "type": VerdictType.INVALID.value,
                        "message": f"Rejected before Nagini: {unsupported_reason}",
                        "rejected_before_verify": True,
                        "rejection_reason": unsupported_reason,
                        "contract_enforcement": contract_enforcement,
                        "raw_model_output": raw,
                    }
                )
                continue
            code_file.write_text(candidate_code)
            candidate_verdict = self.verifier.verify(code_file)
            candidate_records.append(
                {
                    "candidate": candidate_idx,
                    "focus": focus,
                    "valid": candidate_verdict.is_valid(),
                    "type": candidate_verdict.verdict_type.value,
                    "message": candidate_verdict.message,
                    "contract_enforcement": contract_enforcement,
                    "raw_model_output": raw,
                }
            )
            best_code = candidate_code
            best_verdict = candidate_verdict
            best_contract_enforcement = contract_enforcement
            if candidate_verdict.is_valid():
                break

        code_file.write_text(best_code)
        if not candidate_records or all(r.get("rejected_before_verify") for r in candidate_records):
            best_verdict = Verdict(
                verdict_type=VerdictType.INVALID,
                message="All WybeCoder repair candidates were rejected by Python/Nagini subset precheck",
                details=None,
            )
        return best_code, best_verdict, {
            "strategy": "wybecoder",
            "plan": plan,
            "candidates": candidate_records,
        }, best_contract_enforcement
