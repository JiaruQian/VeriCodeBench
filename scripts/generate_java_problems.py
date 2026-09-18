#!/usr/bin/env python3
"""Generate the first Java/OpenJML requirement-to-code benchmark dataset."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "benchmarks" / "java-problems"

SKIPPED_UNVERIFIED = {
    "sum_even_to_n",
    "factorial_small",
    "power_small",
    "is_sorted",
    "binary_search_membership",
    "counter_constructor",
    "range_invariant_constructor",
}

CATEGORY_OVERRIDES = {
    "array_length": "array_basics",
    "is_empty": "array_basics",
    "first_element": "array_basics",
    "last_element": "array_basics",
    "get_at_index": "array_basics",
    "set_at_index": "mutable_arrays",
    "swap_two_indices": "mutable_arrays",
    "zero_prefix": "mutable_arrays",
    "fill_array": "mutable_arrays",
    "copy_array": "mutable_arrays",
    "increment_all": "mutable_arrays",
    "double_all": "mutable_arrays",
    "replace_even_indices": "mutable_arrays",
    "contains_value": "array_search",
    "first_index_of": "array_search",
    "count_value": "array_search",
    "all_even": "array_predicates",
    "any_negative": "array_predicates",
    "array_max": "array_extrema",
    "array_min": "array_extrema",
    "adjacent_swap_if_descending": "array_ordering",
    "selection_sort_three": "array_ordering",
    "max2": "scalar_arithmetic",
    "min2": "scalar_arithmetic",
    "abs_non_min": "scalar_arithmetic",
    "clamp": "scalar_arithmetic",
    "safe_add": "scalar_arithmetic",
    "safe_subtract": "scalar_arithmetic",
    "triangle_angles": "scalar_arithmetic",
    "triangle_sides": "scalar_arithmetic",
    "sum_to_n": "loop_arithmetic",
    "repeated_addition_product": "loop_arithmetic",
    "require_non_null_length": "exceptions",
    "safe_divide_exception": "exceptions",
    "bounded_index_exception": "exceptions",
    "digit_value_exception": "exceptions",
    "non_null_result": "nullability",
    "box_set_value": "object_frames",
    "box_no_mutation_read": "object_frames",
    "pair_sum_readonly": "object_frames",
    "frame_two_boxes": "object_frames",
    "counter_increment": "object_invariants",
    "counter_decrement_if_positive": "object_invariants",
    "range_contains": "object_invariants",
}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def contract(*lines: str) -> str:
    return "\n".join(["/*@"] + [f"  @ {line}" if line else "  @" for line in lines] + ["  @*/"])


def clauses(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [
        {
            "id": f"gt{i}",
            "type": typ,
            "expr": expr,
            "text": text,
            "source": "manual_jml_ground_truth",
        }
        for i, (typ, expr, text) in enumerate(items, 1)
    ]


def java_file(class_name: str, method_source: str, helpers: str = "") -> str:
    helpers_block = f"\n{helpers}\n" if helpers else ""
    return f"""public class {class_name} {{
{helpers_block}
{method_source}
}}
"""


def method(contract_text: str, signature: str, body: str) -> str:
    indented_body = "\n".join(f"    {line}" if line else "" for line in body.splitlines())
    return f"""
    {contract_text}
    public static {signature} {{
{indented_body}
    }}
"""


def build_problem(pid: int, category: str, name: str, requirement: str, signature: str,
                  contract_text: str, body: str, gt: list[dict[str, str]],
                  helpers: str = "") -> dict[str, str]:
    class_name = f"Problem{pid:03d}_{''.join(part.capitalize() for part in slug(name).split('_'))}"
    rel = Path(category) / f"{class_name}.java"
    source = java_file(class_name, method(contract_text, signature, body), helpers)
    return {
        "id": pid,
        "name": name,
        "category": category,
        "path": rel.as_posix(),
        "class_name": class_name,
        "requirement_en": requirement,
        "function_signature": f"{signature};",
        "type_context": helpers.strip(),
        "jml_contract": contract_text,
        "ground_truth_clauses": gt,
        "source": source,
    }


def main() -> None:
    problems: list[dict[str, str]] = []

    def add(category: str, name: str, requirement: str, signature: str,
            contract_text: str, body: str, gt: list[dict[str, str]],
            helpers: str = "") -> None:
        if name in SKIPPED_UNVERIFIED:
            return
        category = CATEGORY_OVERRIDES.get(name, category)
        problems.append(build_problem(len(problems) + 1, category, name, requirement,
                                      signature, contract_text, body, gt, helpers))

    # Arrays and loops, selected for Java/OpenJML rather than pointer-heavy C migration.
    add("arrays", "array_length",
        "Given a non-null integer array, return its length without modifying the array.",
        "int arrayLength(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result == a.length;"),
        "return a.length;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result == a.length", "result is array length")))

    add("arrays", "is_empty",
        "Given a non-null integer array, return true exactly when its length is zero.",
        "boolean isEmpty(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result <==> a.length == 0;"),
        "return a.length == 0;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> a.length == 0", "empty iff length is zero")))

    add("arrays", "first_element",
        "Given a non-null nonempty integer array, return its first element without modifying it.",
        "int first(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures \\result == a[0];"),
        "return a[0];",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "a.length > 0", "array is nonempty"),
                ("ensures", "\\result == a[0]", "returns first element"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("arrays", "last_element",
        "Given a non-null nonempty integer array, return its last element without modifying it.",
        "int last(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures \\result == a[a.length - 1];"),
        "return a[a.length - 1];",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "a.length > 0", "array is nonempty"),
                ("ensures", "\\result == a[a.length - 1]", "returns last element"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("arrays", "get_at_index",
        "Given a non-null integer array and a valid index, return the element at that index.",
        "int getAt(int[] a, int i)",
        contract("public normal_behavior", "requires a != null;", "requires 0 <= i && i < a.length;", "assignable \\nothing;", "ensures \\result == a[i];"),
        "return a[i];",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "0 <= i && i < a.length", "index is valid"),
                ("ensures", "\\result == a[i]", "returns indexed value"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("arrays", "set_at_index",
        "Given a non-null integer array, a valid index, and a value, store the value at the index and leave all other elements unchanged.",
        "void setAt(int[] a, int i, int v)",
        contract("public normal_behavior", "requires a != null;", "requires 0 <= i && i < a.length;", "assignable a[i];", "ensures a[i] == v;", "ensures (\\forall int k; 0 <= k && k < a.length && k != i; a[k] == \\old(a[k]));"),
        "a[i] = v;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "0 <= i && i < a.length", "index is valid"),
                ("assignable", "a[i]", "only indexed element may change"),
                ("ensures", "a[i] == v", "stores requested value"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length && k != i; a[k] == \\old(a[k]))", "other elements unchanged")))

    add("arrays", "swap_two_indices",
        "Given a non-null integer array and two valid indices, swap the two indexed elements.",
        "void swap(int[] a, int i, int j)",
        contract("public normal_behavior", "requires a != null;", "requires 0 <= i && i < a.length;", "requires 0 <= j && j < a.length;", "assignable a[i], a[j];", "ensures a[i] == \\old(a[j]);", "ensures a[j] == \\old(a[i]);"),
        "int t = a[i];\na[i] = a[j];\na[j] = t;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "0 <= i && i < a.length", "first index is valid"),
                ("requires", "0 <= j && j < a.length", "second index is valid"),
                ("assignable", "a[i], a[j]", "only selected elements may change"),
                ("ensures", "a[i] == \\old(a[j])", "first receives old second"),
                ("ensures", "a[j] == \\old(a[i])", "second receives old first")))

    add("arrays", "zero_prefix",
        "Given a non-null integer array and a valid prefix length n, set the first n elements to zero and leave the suffix unchanged.",
        "void zeroPrefix(int[] a, int n)",
        contract("public normal_behavior", "requires a != null;", "requires 0 <= n && n <= a.length;", "assignable a[0 .. n-1];", "ensures (\\forall int k; 0 <= k && k < n; a[k] == 0);", "ensures (\\forall int k; n <= k && k < a.length; a[k] == \\old(a[k]));"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= n;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] == 0);\n//@ loop_assigns i, a[0 .. n-1];\n//@ decreases n - i;\nwhile (i < n) {\n    a[i] = 0;\n    i++;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "0 <= n && n <= a.length", "prefix length is valid"),
                ("assignable", "a[0 .. n-1]", "only prefix may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < n; a[k] == 0)", "prefix is zero"),
                ("ensures", "(\\forall int k; n <= k && k < a.length; a[k] == \\old(a[k]))", "suffix unchanged")))

    add("arrays", "fill_array",
        "Given a non-null integer array and a value, set every element to that value.",
        "void fill(int[] a, int v)",
        contract("public normal_behavior", "requires a != null;", "assignable a[*];", "ensures (\\forall int k; 0 <= k && k < a.length; a[k] == v);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] == v);\n//@ loop_assigns i, a[*];\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    a[i] = v;\n    i++;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "a[*]", "array elements may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length; a[k] == v)", "all elements set to value")))

    add("arrays", "contains_value",
        "Given a non-null integer array and a target value, return true exactly when some element equals the target.",
        "boolean contains(int[] a, int target)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result <==> (\\exists int k; 0 <= k && k < a.length; a[k] == target);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] != target);\n//@ loop_assigns i;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] == target) return true;\n    i++;\n}\nreturn false;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> (\\exists int k; 0 <= k && k < a.length; a[k] == target)", "result reports target presence")))

    add("arrays", "first_index_of",
        "Given a non-null integer array and a target value, return the first target index or -1 if absent.",
        "int indexOf(int[] a, int target)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures -1 <= \\result && \\result < a.length;", "ensures \\result == -1 ==> (\\forall int k; 0 <= k && k < a.length; a[k] != target);", "ensures \\result >= 0 ==> a[\\result] == target;", "ensures \\result >= 0 ==> (\\forall int k; 0 <= k && k < \\result; a[k] != target);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] != target);\n//@ loop_assigns i;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] == target) return i;\n    i++;\n}\nreturn -1;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result == -1 ==> (\\forall int k; 0 <= k && k < a.length; a[k] != target)", "absent iff -1"),
                ("ensures", "\\result >= 0 ==> a[\\result] == target", "nonnegative result points to target"),
                ("ensures", "\\result >= 0 ==> (\\forall int k; 0 <= k && k < \\result; a[k] != target)", "returned index is first")))

    add("arrays", "count_value",
        "Given a non-null integer array and a target value, count occurrences of the target.",
        "int countValue(int[] a, int target)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures 0 <= \\result && \\result <= a.length;"),
        "int c = 0;\nint i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant 0 <= c && c <= i;\n//@ loop_assigns i, c;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] == target) c++;\n    i++;\n}\nreturn c;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "0 <= \\result && \\result <= a.length", "count is within array bounds")))

    add("arrays", "all_even",
        "Given a non-null integer array, return true exactly when every element is even.",
        "boolean allEven(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result <==> (\\forall int k; 0 <= k && k < a.length; a[k] % 2 == 0);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] % 2 == 0);\n//@ loop_assigns i;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] % 2 != 0) return false;\n    i++;\n}\nreturn true;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> (\\forall int k; 0 <= k && k < a.length; a[k] % 2 == 0)", "result reports all-even property")))

    add("arrays", "any_negative",
        "Given a non-null integer array, return true exactly when at least one element is negative.",
        "boolean anyNegative(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result <==> (\\exists int k; 0 <= k && k < a.length; a[k] < 0);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] >= 0);\n//@ loop_assigns i;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] < 0) return true;\n    i++;\n}\nreturn false;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> (\\exists int k; 0 <= k && k < a.length; a[k] < 0)", "result reports negative presence")))

    add("arrays", "array_max",
        "Given a non-null nonempty integer array, return a maximum element without modifying the array.",
        "int max(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures (\\forall int k; 0 <= k && k < a.length; \\result >= a[k]);", "ensures (\\exists int k; 0 <= k && k < a.length; \\result == a[k]);"),
        "int m = a[0];\nint i = 1;\n//@ loop_invariant 1 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; m >= a[k]);\n//@ loop_invariant (\\exists int k; 0 <= k && k < i; m == a[k]);\n//@ loop_assigns i, m;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] > m) m = a[i];\n    i++;\n}\nreturn m;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "a.length > 0", "array is nonempty"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length; \\result >= a[k])", "result is at least every element"),
                ("ensures", "(\\exists int k; 0 <= k && k < a.length; \\result == a[k])", "result is drawn from array")))

    add("arrays", "array_min",
        "Given a non-null nonempty integer array, return a minimum element without modifying the array.",
        "int min(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures (\\forall int k; 0 <= k && k < a.length; \\result <= a[k]);", "ensures (\\exists int k; 0 <= k && k < a.length; \\result == a[k]);"),
        "int m = a[0];\nint i = 1;\n//@ loop_invariant 1 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; m <= a[k]);\n//@ loop_invariant (\\exists int k; 0 <= k && k < i; m == a[k]);\n//@ loop_assigns i, m;\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (a[i] < m) m = a[i];\n    i++;\n}\nreturn m;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "a.length > 0", "array is nonempty"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length; \\result <= a[k])", "result is no greater than every element"),
                ("ensures", "(\\exists int k; 0 <= k && k < a.length; \\result == a[k])", "result is drawn from array")))

    add("arrays", "is_sorted",
        "Given a non-null integer array, return true exactly when it is sorted in nondecreasing order.",
        "boolean isSorted(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result <==> (\\forall int k; 0 <= k && k < a.length - 1; a[k] <= a[k+1]);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i - 1; a[k] <= a[k+1]);\n//@ loop_assigns i;\n//@ decreases a.length - i;\nwhile (i < a.length - 1) {\n    if (a[i] > a[i + 1]) return false;\n    i++;\n}\nreturn true;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> (\\forall int k; 0 <= k && k < a.length - 1; a[k] <= a[k+1])", "result reports sortedness")))

    add("arrays", "copy_array",
        "Given non-null source and destination arrays where the destination is long enough, copy all source elements into the destination.",
        "void copy(int[] src, int[] dst)",
        contract("public normal_behavior", "requires src != null && dst != null;", "requires dst.length >= src.length;", "assignable dst[0 .. src.length-1];", "ensures (\\forall int k; 0 <= k && k < src.length; dst[k] == src[k]);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= src.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; dst[k] == src[k]);\n//@ loop_assigns i, dst[0 .. src.length-1];\n//@ decreases src.length - i;\nwhile (i < src.length) {\n    dst[i] = src[i];\n    i++;\n}",
        clauses(("requires", "src != null && dst != null", "arrays are non-null"),
                ("requires", "dst.length >= src.length", "destination is large enough"),
                ("assignable", "dst[0 .. src.length-1]", "destination prefix may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < src.length; dst[k] == src[k])", "destination receives source contents")))

    add("arrays", "increment_all",
        "Given a non-null integer array whose elements can be safely incremented, add one to every element.",
        "void incrementAll(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires (\\forall int k; 0 <= k && k < a.length; a[k] < Integer.MAX_VALUE);", "assignable a[*];", "ensures (\\forall int k; 0 <= k && k < a.length; a[k] == \\old(a[k]) + 1);"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] == \\old(a[k]) + 1);\n//@ loop_invariant (\\forall int k; i <= k && k < a.length; a[k] == \\old(a[k]));\n//@ loop_assigns i, a[*];\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    //@ assert a[i] < Integer.MAX_VALUE;\n    a[i] = a[i] + 1;\n    i++;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "(\\forall int k; 0 <= k && k < a.length; a[k] < Integer.MAX_VALUE)", "increment cannot overflow"),
                ("assignable", "a[*]", "array elements may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length; a[k] == \\old(a[k]) + 1)", "each element incremented")))

    add("arrays", "double_all",
        "Given a non-null integer array whose elements can be safely doubled, double every element in place.",
        "void doubleAll(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires (\\forall int k; 0 <= k && k < a.length; Integer.MIN_VALUE/2 <= a[k] && a[k] <= Integer.MAX_VALUE/2);", "assignable a[*];", "ensures (\\forall int k; 0 <= k && k < a.length; a[k] == 2 * \\old(a[k]));"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i; a[k] == 2 * \\old(a[k]));\n//@ loop_invariant (\\forall int k; i <= k && k < a.length; a[k] == \\old(a[k]));\n//@ loop_assigns i, a[*];\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    //@ assert Integer.MIN_VALUE/2 <= a[i] && a[i] <= Integer.MAX_VALUE/2;\n    a[i] = 2 * a[i];\n    i++;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "(\\forall int k; 0 <= k && k < a.length; Integer.MIN_VALUE/2 <= a[k] && a[k] <= Integer.MAX_VALUE/2)", "doubling cannot overflow"),
                ("assignable", "a[*]", "array elements may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length; a[k] == 2 * \\old(a[k]))", "each element doubled")))

    add("arrays", "replace_even_indices",
        "Given a non-null integer array, set elements at even indices to zero and leave odd indices unchanged.",
        "void clearEvenIndices(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable a[*];", "ensures (\\forall int k; 0 <= k && k < a.length && k % 2 == 0; a[k] == 0);", "ensures (\\forall int k; 0 <= k && k < a.length && k % 2 != 0; a[k] == \\old(a[k]));"),
        "int i = 0;\n//@ loop_invariant 0 <= i && i <= a.length;\n//@ loop_invariant (\\forall int k; 0 <= k && k < i && k % 2 == 0; a[k] == 0);\n//@ loop_invariant (\\forall int k; 0 <= k && k < i && k % 2 != 0; a[k] == \\old(a[k]));\n//@ loop_invariant (\\forall int k; i <= k && k < a.length; a[k] == \\old(a[k]));\n//@ loop_assigns i, a[*];\n//@ decreases a.length - i;\nwhile (i < a.length) {\n    if (i % 2 == 0) a[i] = 0;\n    i++;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("assignable", "a[*]", "array elements may change"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length && k % 2 == 0; a[k] == 0)", "even indices cleared"),
                ("ensures", "(\\forall int k; 0 <= k && k < a.length && k % 2 != 0; a[k] == \\old(a[k]))", "odd indices unchanged")))

    add("arrays", "binary_search_membership",
        "Given a non-null sorted integer array and a target, return an index containing the target or -1 when it is absent.",
        "int binarySearch(int[] a, int target)",
        contract("public normal_behavior", "requires a != null;", "requires (\\forall int k; 0 <= k && k < a.length - 1; a[k] <= a[k+1]);", "assignable \\nothing;", "ensures -1 <= \\result && \\result < a.length;", "ensures \\result >= 0 ==> a[\\result] == target;", "ensures \\result == -1 ==> (\\forall int k; 0 <= k && k < a.length; a[k] != target);"),
        "int lo = 0;\nint hi = a.length - 1;\n//@ loop_invariant 0 <= lo && lo <= a.length;\n//@ loop_invariant -1 <= hi && hi < a.length;\n//@ loop_invariant lo <= hi + 1;\n//@ loop_assigns lo, hi;\n//@ decreases hi - lo + 1;\nwhile (lo <= hi) {\n    int mid = lo + (hi - lo) / 2;\n    if (a[mid] == target) return mid;\n    if (a[mid] < target) lo = mid + 1;\n    else hi = mid - 1;\n}\nreturn -1;",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "(\\forall int k; 0 <= k && k < a.length - 1; a[k] <= a[k+1])", "array is sorted"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result >= 0 ==> a[\\result] == target", "found index contains target"),
                ("ensures", "\\result == -1 ==> (\\forall int k; 0 <= k && k < a.length; a[k] != target)", "minus one means absent")))

    add("arrays", "adjacent_swap_if_descending",
        "Given a non-null integer array and a valid adjacent pair, swap the pair only if it is descending.",
        "void swapIfDescending(int[] a, int i)",
        contract("public normal_behavior", "requires a != null;", "requires 0 <= i && i + 1 < a.length;", "assignable a[i], a[i+1];", "ensures a[i] <= a[i+1];", "ensures a[i] == \\old(a[i]) || a[i] == \\old(a[i+1]);", "ensures a[i+1] == \\old(a[i]) || a[i+1] == \\old(a[i+1]);"),
        "if (a[i] > a[i + 1]) {\n    int t = a[i];\n    a[i] = a[i + 1];\n    a[i + 1] = t;\n}",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "0 <= i && i + 1 < a.length", "adjacent pair is valid"),
                ("assignable", "a[i], a[i+1]", "only adjacent pair may change"),
                ("ensures", "a[i] <= a[i+1]", "pair is ordered"),
                ("ensures", "a[i] == \\old(a[i]) || a[i] == \\old(a[i+1])", "first output is from pair"),
                ("ensures", "a[i+1] == \\old(a[i]) || a[i+1] == \\old(a[i+1])", "second output is from pair")))

    add("arrays", "selection_sort_three",
        "Given a non-null integer array of length three, sort the three elements in nondecreasing order in place.",
        "void sort3(int[] a)",
        contract("public normal_behavior", "requires a != null;", "requires a.length == 3;", "assignable a[0], a[1], a[2];", "ensures a[0] <= a[1] && a[1] <= a[2];", "ensures a[0] + a[1] + a[2] == \\old(a[0]) + \\old(a[1]) + \\old(a[2]);"),
        "if (a[0] > a[1]) { int t = a[0]; a[0] = a[1]; a[1] = t; }\nif (a[1] > a[2]) { int t = a[1]; a[1] = a[2]; a[2] = t; }\nif (a[0] > a[1]) { int t = a[0]; a[0] = a[1]; a[1] = t; }",
        clauses(("requires", "a != null", "array reference is non-null"),
                ("requires", "a.length == 3", "array has exactly three elements"),
                ("assignable", "a[0], a[1], a[2]", "three elements may change"),
                ("ensures", "a[0] <= a[1] && a[1] <= a[2]", "array is sorted"),
                ("ensures", "a[0] + a[1] + a[2] == \\old(a[0]) + \\old(a[1]) + \\old(a[2])", "sum is preserved")))

    # Scalar arithmetic and loop problems.
    arithmetic = [
        ("max2", "Given two integers, return the greater value.", "int max2(int x, int y)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result >= x && \\result >= y;", "ensures \\result == x || \\result == y;"),
         "return x >= y ? x : y;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result >= x && \\result >= y", "result is at least both inputs"), ("ensures", "\\result == x || \\result == y", "result equals an input"))),
        ("min2", "Given two integers, return the smaller value.", "int min2(int x, int y)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <= x && \\result <= y;", "ensures \\result == x || \\result == y;"),
         "return x <= y ? x : y;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <= x && \\result <= y", "result is no greater than both inputs"), ("ensures", "\\result == x || \\result == y", "result equals an input"))),
        ("abs_non_min", "Given an integer other than Integer.MIN_VALUE, return its absolute value.", "int abs(int x)",
         contract("public normal_behavior", "requires x != Integer.MIN_VALUE;", "assignable \\nothing;", "ensures \\result >= 0;", "ensures \\result == x || \\result == -x;"),
         "return x >= 0 ? x : -x;",
         clauses(("requires", "x != Integer.MIN_VALUE", "negation cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result >= 0", "result is nonnegative"), ("ensures", "\\result == x || \\result == -x", "result is absolute value"))),
        ("clamp", "Given integers x, lo, and hi with lo <= hi, clamp x into the closed interval [lo, hi].", "int clamp(int x, int lo, int hi)",
         contract("public normal_behavior", "requires lo <= hi;", "assignable \\nothing;", "ensures lo <= \\result && \\result <= hi;", "ensures (lo <= x && x <= hi) ==> \\result == x;", "ensures x < lo ==> \\result == lo;", "ensures x > hi ==> \\result == hi;"),
         "if (x < lo) return lo;\nif (x > hi) return hi;\nreturn x;",
         clauses(("requires", "lo <= hi", "bounds are ordered"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "lo <= \\result && \\result <= hi", "result is inside interval"))),
        ("safe_add", "Given two integers whose mathematical sum is inside int range, return their sum.", "int safeAdd(int x, int y)",
         contract("public normal_behavior", "requires Integer.MIN_VALUE <= (long)x + (long)y && (long)x + (long)y <= Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == x + y;"),
         "return x + y;",
         clauses(("requires", "Integer.MIN_VALUE <= (long)x + (long)y && (long)x + (long)y <= Integer.MAX_VALUE", "addition cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x + y", "returns sum"))),
        ("safe_subtract", "Given two integers whose mathematical difference is inside int range, return x minus y.", "int safeSubtract(int x, int y)",
         contract("public normal_behavior", "requires Integer.MIN_VALUE <= (long)x - (long)y && (long)x - (long)y <= Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == x - y;"),
         "return x - y;",
         clauses(("requires", "Integer.MIN_VALUE <= (long)x - (long)y && (long)x - (long)y <= Integer.MAX_VALUE", "subtraction cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x - y", "returns difference"))),
        ("triangle_angles", "Given three angles, return true exactly when all are positive and their mathematical sum is 180.", "boolean validTriangleAngles(int a, int b, int c)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b + (long)c == 180L);"),
         "return a > 0 && b > 0 && c > 0 && (long)a + (long)b + (long)c == 180L;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b + (long)c == 180L)", "result reports valid angle triangle"))),
        ("triangle_sides", "Given three side lengths, return true exactly when they satisfy the strict mathematical triangle inequality.", "boolean validTriangleSides(int a, int b, int c)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b > (long)c && (long)a + (long)c > (long)b && (long)b + (long)c > (long)a);"),
         "return a > 0 && b > 0 && c > 0 && (long)a + (long)b > (long)c && (long)a + (long)c > (long)b && (long)b + (long)c > (long)a;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a > 0 && b > 0 && c > 0 && (long)a + (long)b > (long)c && (long)a + (long)c > (long)b && (long)b + (long)c > (long)a)", "result reports valid side triangle"))),
        ("sum_to_n", "Given n between 0 and 65535, return the arithmetic sum 0 + ... + n.", "int sumToN(int n)",
         contract("public normal_behavior", "requires 0 <= n && n <= 65535;", "assignable \\nothing;", "ensures \\result == n * (n + 1) / 2;"),
         "int s = 0;\nint i = 0;\n//@ loop_invariant 0 <= i && i <= n + 1;\n//@ loop_invariant s == i * (i - 1) / 2;\n//@ loop_assigns i, s;\n//@ decreases n + 1 - i;\nwhile (i <= n) {\n    s += i;\n    i++;\n}\nreturn s;",
         clauses(("requires", "0 <= n && n <= 65535", "input range prevents overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == n * (n + 1) / 2", "returns arithmetic sum"))),
        ("sum_even_to_n", "Given n between 0 and 10000, return the sum of even numbers from 0 to n inclusive.", "int sumEvenToN(int n)",
         contract("public normal_behavior", "requires 0 <= n && n <= 10000;", "assignable \\nothing;", "ensures \\result >= 0;"),
         "int s = 0;\nint i = 0;\n//@ loop_invariant 0 <= i && i <= n + 2;\n//@ loop_invariant i % 2 == 0;\n//@ loop_invariant s >= 0;\n//@ loop_assigns i, s;\n//@ decreases n + 2 - i;\nwhile (i <= n) {\n    s += i;\n    i += 2;\n}\nreturn s;",
         clauses(("requires", "0 <= n && n <= 10000", "input range prevents overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result >= 0", "sum is nonnegative"))),
        ("factorial_small", "Given n between 0 and 12, return n factorial.", "int factorial(int n)",
         contract("public normal_behavior", "requires 0 <= n && n <= 12;", "assignable \\nothing;", "ensures \\result >= 1;"),
         "int r = 1;\nint i = 1;\n//@ loop_invariant 1 <= i && i <= n + 1;\n//@ loop_invariant r >= 1;\n//@ loop_assigns i, r;\n//@ decreases n + 1 - i;\nwhile (i <= n) {\n    r *= i;\n    i++;\n}\nreturn r;",
         clauses(("requires", "0 <= n && n <= 12", "factorial fits int"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result >= 1", "factorial is positive"))),
        ("power_small", "Given x in [-10,10] and exponent n in [0,4], return x raised to n.", "int pow(int x, int n)",
         contract("public normal_behavior", "requires -10 <= x && x <= 10;", "requires 0 <= n && n <= 4;", "assignable \\nothing;", "ensures n == 0 ==> \\result == 1;"),
         "int r = 1;\nint i = 0;\n//@ loop_invariant 0 <= i && i <= n;\n//@ loop_assigns i, r;\n//@ decreases n - i;\nwhile (i < n) {\n    r *= x;\n    i++;\n}\nreturn r;",
         clauses(("requires", "-10 <= x && x <= 10", "base is bounded"), ("requires", "0 <= n && n <= 4", "exponent is bounded"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "n == 0 ==> \\result == 1", "zero exponent returns one"))),
        ("repeated_addition_product", "Given nonnegative a and bounded b, return a*b using repeated addition.", "int multiplyByRepeatedAdd(int a, int b)",
         contract("public normal_behavior", "requires 0 <= a && a <= 10000;", "requires -10000 <= b && b <= 10000;", "assignable \\nothing;", "ensures \\result == a * b;"),
         "int r = 0;\nint i = 0;\n//@ loop_invariant 0 <= i && i <= a;\n//@ loop_invariant r == i * b;\n//@ loop_assigns i, r;\n//@ decreases a - i;\nwhile (i < a) {\n    r += b;\n    i++;\n}\nreturn r;",
         clauses(("requires", "0 <= a && a <= 10000", "iteration count is bounded and nonnegative"), ("requires", "-10000 <= b && b <= 10000", "product fits int"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a * b", "returns product"))),
    ]
    for item in arithmetic:
        add("arithmetic", *item)

    # Java-specific references, invariants, nullability, frame conditions, and exceptions.
    add("java_specific", "require_non_null_length",
        "Given an integer array, return its length when non-null and throw IllegalArgumentException when null.",
        "int requireLength(int[] a)",
        contract("public normal_behavior", "requires a != null;", "assignable \\nothing;", "ensures \\result == a.length;", "also", "public exceptional_behavior", "requires a == null;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"),
        "if (a == null) throw new IllegalArgumentException();\nreturn a.length;",
        clauses(("requires", "a != null", "normal case requires non-null array"),
                ("ensures", "\\result == a.length", "normal case returns length"),
                ("signals", "a == null ==> IllegalArgumentException", "null input throws IllegalArgumentException"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("java_specific", "safe_divide_exception",
        "Given integers x and y, return x/y when y is nonzero and division cannot overflow, and throw IllegalArgumentException when y is zero.",
        "int divide(int x, int y)",
        contract("public normal_behavior", "requires y != 0;", "requires !(x == Integer.MIN_VALUE && y == -1);", "assignable \\nothing;", "ensures \\result == x / y;", "also", "public exceptional_behavior", "requires y == 0;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"),
        "if (y == 0) throw new IllegalArgumentException();\nreturn x / y;",
        clauses(("requires", "y != 0", "normal case divisor is nonzero"),
                ("requires", "!(x == Integer.MIN_VALUE && y == -1)", "division cannot overflow"),
                ("ensures", "\\result == x / y", "normal case returns quotient"),
                ("signals", "y == 0 ==> IllegalArgumentException", "zero divisor throws IllegalArgumentException"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("java_specific", "bounded_index_exception",
        "Given an array and index, return the indexed element for valid inputs and throw IllegalArgumentException when the array is null or the index is invalid.",
        "int checkedGet(int[] a, int i)",
        contract("public normal_behavior", "requires a != null && 0 <= i && i < a.length;", "assignable \\nothing;", "ensures \\result == a[i];", "also", "public exceptional_behavior", "requires a == null || i < 0 || (a != null && i >= a.length);", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"),
        "if (a == null || i < 0 || i >= a.length) throw new IllegalArgumentException();\nreturn a[i];",
        clauses(("requires", "a != null && 0 <= i && i < a.length", "normal case has non-null array and valid index"),
                ("ensures", "\\result == a[i]", "returns indexed element"),
                ("signals", "a == null || i < 0 || i >= a.length ==> IllegalArgumentException", "bad input throws IllegalArgumentException"),
                ("assignable", "\\nothing", "does not mutate state")))

    add("java_specific", "non_null_result",
        "Given a possibly null String and a fallback non-null String, return the input when non-null, otherwise the fallback.",
        "String defaultString(String s, String fallback)",
        contract("public normal_behavior", "requires fallback != null;", "assignable \\nothing;", "ensures \\result != null;", "ensures s != null ==> \\result == s;", "ensures s == null ==> \\result == fallback;"),
        "return s != null ? s : fallback;",
        clauses(("requires", "fallback != null", "fallback is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result != null", "result is non-null"),
                ("ensures", "s != null ==> \\result == s", "non-null input returned"),
                ("ensures", "s == null ==> \\result == fallback", "fallback returned for null input")))

    add("java_specific", "box_set_value",
        "Given a non-null mutable Box and a value, update only the box value field.",
        "void setBox(Box box, int v)",
        contract("public normal_behavior", "requires box != null;", "assignable box.value;", "ensures box.value == v;"),
        "box.value = v;",
        clauses(("requires", "box != null", "box reference is non-null"),
                ("assignable", "box.value", "only box value field may change"),
                ("ensures", "box.value == v", "box field receives value")),
        helpers="    public static class Box { public int value; }")

    add("java_specific", "box_no_mutation_read",
        "Given a non-null mutable Box, return its value without modifying the box.",
        "int readBox(Box box)",
        contract("public normal_behavior", "requires box != null;", "assignable \\nothing;", "ensures \\result == box.value;"),
        "return box.value;",
        clauses(("requires", "box != null", "box reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result == box.value", "returns field value")),
        helpers="    public static class Box { public int value; }")

    add("java_specific", "counter_constructor",
        "Construct a Counter with a nonnegative initial value while preserving its invariant.",
        "Counter newCounter(int initial)",
        contract("public normal_behavior", "requires initial >= 0;", "assignable \\nothing;", "ensures \\result != null;", "ensures \\result.value == initial;"),
        "return new Counter(initial);",
        clauses(("requires", "initial >= 0", "initial counter value is nonnegative"),
                ("ensures", "\\result != null", "returns a counter object"),
                ("ensures", "\\result.value == initial", "counter stores initial value"),
                ("assignable", "\\nothing", "factory does not mutate existing state")),
        helpers="    public static class Counter {\n        //@ public invariant value >= 0;\n        public int value;\n        //@ requires initial >= 0;\n        //@ assignable value;\n        //@ ensures value == initial;\n        public Counter(int initial) { value = initial; }\n    }")

    add("java_specific", "counter_increment",
        "Given a non-null Counter whose value can be safely incremented, increment it by one.",
        "void increment(Counter c)",
        contract("public normal_behavior", "requires c != null;", "requires c.value < Integer.MAX_VALUE;", "assignable c.value;", "ensures c.value == \\old(c.value) + 1;"),
        "c.value = c.value + 1;",
        clauses(("requires", "c != null", "counter reference is non-null"),
                ("requires", "c.value < Integer.MAX_VALUE", "increment cannot overflow"),
                ("assignable", "c.value", "only counter value may change"),
                ("ensures", "c.value == \\old(c.value) + 1", "counter is incremented")),
        helpers="    public static class Counter {\n        //@ public invariant value >= 0;\n        public int value;\n    }")

    add("java_specific", "counter_decrement_if_positive",
        "Given a non-null Counter, decrement it only when its value is positive and preserve nonnegativity.",
        "void decrementIfPositive(Counter c)",
        contract("public normal_behavior", "requires c != null;", "assignable c.value;", "ensures \\old(c.value) > 0 ==> c.value == \\old(c.value) - 1;", "ensures \\old(c.value) == 0 ==> c.value == 0;", "ensures c.value >= 0;"),
        "if (c.value > 0) c.value = c.value - 1;",
        clauses(("requires", "c != null", "counter reference is non-null"),
                ("assignable", "c.value", "only counter value may change"),
                ("ensures", "\\old(c.value) > 0 ==> c.value == \\old(c.value) - 1", "positive counter decremented"),
                ("ensures", "\\old(c.value) == 0 ==> c.value == 0", "zero counter unchanged"),
                ("ensures", "c.value >= 0", "invariant-like nonnegativity preserved")),
        helpers="    public static class Counter {\n        //@ public invariant value >= 0;\n        public int value;\n    }")

    add("java_specific", "pair_sum_readonly",
        "Given a non-null Pair, return the sum of its two fields without modifying the object.",
        "int sumPair(Pair p)",
        contract("public normal_behavior", "requires p != null;", "requires Integer.MIN_VALUE <= (long)p.left + (long)p.right && (long)p.left + (long)p.right <= Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == p.left + p.right;"),
        "return p.left + p.right;",
        clauses(("requires", "p != null", "pair reference is non-null"),
                ("requires", "Integer.MIN_VALUE <= (long)p.left + (long)p.right && (long)p.left + (long)p.right <= Integer.MAX_VALUE", "field sum cannot overflow"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result == p.left + p.right", "returns field sum")),
        helpers="    public static class Pair { public int left; public int right; }")

    add("java_specific", "range_invariant_constructor",
        "Construct a Range object with low <= high and expose fields satisfying that invariant.",
        "Range newRange(int low, int high)",
        contract("public normal_behavior", "requires low <= high;", "assignable \\nothing;", "ensures \\result != null;", "ensures \\result.low == low && \\result.high == high;", "ensures \\result.low <= \\result.high;"),
        "return new Range(low, high);",
        clauses(("requires", "low <= high", "range bounds are ordered"),
                ("assignable", "\\nothing", "factory does not mutate existing state"),
                ("ensures", "\\result != null", "returns a range object"),
                ("ensures", "\\result.low == low && \\result.high == high", "fields store constructor arguments"),
                ("ensures", "\\result.low <= \\result.high", "range invariant holds")),
        helpers="    public static class Range {\n        //@ public invariant low <= high;\n        public int low;\n        public int high;\n        //@ requires low <= high;\n        //@ assignable this.low, this.high;\n        //@ ensures this.low == low && this.high == high;\n        public Range(int low, int high) { this.low = low; this.high = high; }\n    }")

    add("java_specific", "range_contains",
        "Given a non-null Range, return true exactly when x is inside its inclusive bounds.",
        "boolean contains(Range r, int x)",
        contract("public normal_behavior", "requires r != null;", "assignable \\nothing;", "ensures \\result <==> (r.low <= x && x <= r.high);"),
        "return r.low <= x && x <= r.high;",
        clauses(("requires", "r != null", "range reference is non-null"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "\\result <==> (r.low <= x && x <= r.high)", "result reports inclusive membership")),
        helpers="    public static class Range {\n        //@ public invariant low <= high;\n        public int low;\n        public int high;\n    }")

    add("java_specific", "frame_two_boxes",
        "Given two distinct non-null boxes, update the first box and leave the second box unchanged.",
        "void updateFirst(Box a, Box b, int v)",
        contract("public normal_behavior", "requires a != null && b != null;", "requires a != b;", "assignable a.value;", "ensures a.value == v;", "ensures b.value == \\old(b.value);"),
        "a.value = v;",
        clauses(("requires", "a != null && b != null", "box references are non-null"),
                ("requires", "a != b", "boxes are distinct"),
                ("assignable", "a.value", "only first box value may change"),
                ("ensures", "a.value == v", "first box updated"),
                ("ensures", "b.value == \\old(b.value)", "second box unchanged")),
        helpers="    public static class Box { public int value; }")

    add("java_specific", "digit_value_exception",
        "Given a character, return its decimal digit value when it is between '0' and '9', otherwise throw IllegalArgumentException.",
        "int digitValue(char ch)",
        contract("public normal_behavior", "requires '0' <= ch && ch <= '9';", "assignable \\nothing;", "ensures 0 <= \\result && \\result <= 9;", "ensures \\result == ch - '0';", "also", "public exceptional_behavior", "requires ch < '0' || ch > '9';", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"),
        "if (ch < '0' || ch > '9') throw new IllegalArgumentException();\nreturn ch - '0';",
        clauses(("requires", "'0' <= ch && ch <= '9'", "normal case has decimal digit character"),
                ("assignable", "\\nothing", "does not mutate state"),
                ("ensures", "0 <= \\result && \\result <= 9", "result is a digit value"),
                ("ensures", "\\result == ch - '0'", "result is character offset from zero"),
                ("signals", "ch < '0' || ch > '9' ==> IllegalArgumentException", "non-digit throws IllegalArgumentException")))

    # Additional Java/OpenJML-friendly tasks. These expand coverage without relying on
    # heavyweight quantified loop proofs in every new item.
    extra_scalar = [
        ("is_positive", "Given an integer x, return true exactly when x is positive.", "boolean isPositive(int x)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> x > 0;"),
         "return x > 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> x > 0", "result reports positivity"))),
        ("is_nonnegative", "Given an integer x, return true exactly when x is nonnegative.", "boolean isNonnegative(int x)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> x >= 0;"),
         "return x >= 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> x >= 0", "result reports nonnegativity"))),
        ("is_zero", "Given an integer x, return true exactly when x is zero.", "boolean isZero(int x)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> x == 0;"),
         "return x == 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> x == 0", "result reports zero"))),
        ("is_even", "Given an integer x, return true exactly when x is even.", "boolean isEven(int x)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> x % 2 == 0;"),
         "return x % 2 == 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> x % 2 == 0", "result reports evenness"))),
        ("same_sign_nonzero", "Given two nonzero integers, return true exactly when they have the same sign.", "boolean sameSign(int x, int y)",
         contract("public normal_behavior", "requires x != 0 && y != 0;", "assignable \\nothing;", "ensures \\result <==> ((x > 0 && y > 0) || (x < 0 && y < 0));"),
         "return (x > 0 && y > 0) || (x < 0 && y < 0);",
         clauses(("requires", "x != 0 && y != 0", "inputs are nonzero"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> ((x > 0 && y > 0) || (x < 0 && y < 0))", "result reports same sign"))),
        ("max3", "Given three integers, return a value that is at least all three and equal to one of them.", "int max3(int a, int b, int c)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result >= a && \\result >= b && \\result >= c;", "ensures \\result == a || \\result == b || \\result == c;"),
         "int m = a >= b ? a : b;\nreturn m >= c ? m : c;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result >= a && \\result >= b && \\result >= c", "result is at least every input"), ("ensures", "\\result == a || \\result == b || \\result == c", "result equals an input"))),
        ("min3", "Given three integers, return a value that is at most all three and equal to one of them.", "int min3(int a, int b, int c)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <= a && \\result <= b && \\result <= c;", "ensures \\result == a || \\result == b || \\result == c;"),
         "int m = a <= b ? a : b;\nreturn m <= c ? m : c;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <= a && \\result <= b && \\result <= c", "result is at most every input"), ("ensures", "\\result == a || \\result == b || \\result == c", "result equals an input"))),
        ("safe_negate", "Given an integer other than Integer.MIN_VALUE, return its negation.", "int safeNegate(int x)",
         contract("public normal_behavior", "requires x != Integer.MIN_VALUE;", "assignable \\nothing;", "ensures \\result == -x;"),
         "return -x;",
         clauses(("requires", "x != Integer.MIN_VALUE", "negation cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == -x", "returns negation"))),
        ("square_small", "Given x between -46340 and 46340, return x squared.", "int square(int x)",
         contract("public normal_behavior", "requires -46340 <= x && x <= 46340;", "assignable \\nothing;", "ensures \\result == x * x;", "ensures \\result >= 0;"),
         "return x * x;",
         clauses(("requires", "-46340 <= x && x <= 46340", "square fits int"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x * x", "returns square"), ("ensures", "\\result >= 0", "square is nonnegative"))),
        ("successor_safe", "Given an integer below Integer.MAX_VALUE, return its successor.", "int successor(int x)",
         contract("public normal_behavior", "requires x < Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == x + 1;"),
         "return x + 1;",
         clauses(("requires", "x < Integer.MAX_VALUE", "successor cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x + 1", "returns successor"))),
        ("predecessor_safe", "Given an integer above Integer.MIN_VALUE, return its predecessor.", "int predecessor(int x)",
         contract("public normal_behavior", "requires x > Integer.MIN_VALUE;", "assignable \\nothing;", "ensures \\result == x - 1;"),
         "return x - 1;",
         clauses(("requires", "x > Integer.MIN_VALUE", "predecessor cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x - 1", "returns predecessor"))),
        ("bounded_identity", "Given x in the closed interval [lo, hi], return x unchanged.", "int boundedIdentity(int x, int lo, int hi)",
         contract("public normal_behavior", "requires lo <= x && x <= hi;", "assignable \\nothing;", "ensures \\result == x;", "ensures lo <= \\result && \\result <= hi;"),
         "return x;",
         clauses(("requires", "lo <= x && x <= hi", "input is within bounds"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x", "returns input unchanged"), ("ensures", "lo <= \\result && \\result <= hi", "result remains within bounds"))),
        ("distance_from_zero", "Given a nonnegative integer x, return its distance from zero.", "int distanceFromZero(int x)",
         contract("public normal_behavior", "requires x >= 0;", "assignable \\nothing;", "ensures \\result == x;", "ensures \\result >= 0;"),
         "return x;",
         clauses(("requires", "x >= 0", "input is nonnegative"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x", "distance equals input"), ("ensures", "\\result >= 0", "distance is nonnegative"))),
        ("in_closed_interval", "Given x, lo, and hi with lo <= hi, return true exactly when x is inside [lo, hi].", "boolean inClosedInterval(int x, int lo, int hi)",
         contract("public normal_behavior", "requires lo <= hi;", "assignable \\nothing;", "ensures \\result <==> (lo <= x && x <= hi);"),
         "return lo <= x && x <= hi;",
         clauses(("requires", "lo <= hi", "bounds are ordered"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (lo <= x && x <= hi)", "result reports interval membership"))),
        ("strict_between", "Given x, lo, and hi with lo < hi, return true exactly when x is strictly between them.", "boolean strictlyBetween(int x, int lo, int hi)",
         contract("public normal_behavior", "requires lo < hi;", "assignable \\nothing;", "ensures \\result <==> (lo < x && x < hi);"),
         "return lo < x && x < hi;",
         clauses(("requires", "lo < hi", "bounds are strictly ordered"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (lo < x && x < hi)", "result reports strict interval membership"))),
        ("choose_first_if_true", "Given a boolean flag and two integers, return x when the flag is true and y otherwise.", "int choose(boolean flag, int x, int y)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures flag ==> \\result == x;", "ensures !flag ==> \\result == y;"),
         "return flag ? x : y;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "flag ==> \\result == x", "true flag selects first value"), ("ensures", "!flag ==> \\result == y", "false flag selects second value"))),
    ]
    for item in extra_scalar:
        add("scalar_arithmetic", *item)

    extra_boolean = [
        ("bool_and", "Given two booleans, return their conjunction.", "boolean boolAnd(boolean a, boolean b)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a && b);"), "return a && b;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a && b)", "returns conjunction"))),
        ("bool_or", "Given two booleans, return their disjunction.", "boolean boolOr(boolean a, boolean b)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a || b);"), "return a || b;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a || b)", "returns disjunction"))),
        ("bool_xor", "Given two booleans, return true exactly when they differ.", "boolean boolXor(boolean a, boolean b)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a != b);"), "return a != b;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a != b)", "returns exclusive-or"))),
        ("bool_not", "Given a boolean, return its negation.", "boolean boolNot(boolean a)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> !a;"), "return !a;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> !a", "returns negation"))),
        ("bool_implies", "Given two booleans, return true exactly when a implies b.", "boolean implies(boolean a, boolean b)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (!a || b);"), "return !a || b;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (!a || b)", "returns implication"))),
        ("both_nonzero", "Given two integers, return true exactly when both are nonzero.", "boolean bothNonzero(int x, int y)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (x != 0 && y != 0);"), "return x != 0 && y != 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (x != 0 && y != 0)", "result reports both nonzero"))),
        ("at_least_one_zero", "Given two integers, return true exactly when at least one is zero.", "boolean atLeastOneZero(int x, int y)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (x == 0 || y == 0);"), "return x == 0 || y == 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (x == 0 || y == 0)", "result reports any zero"))),
        ("all_three_positive", "Given three integers, return true exactly when all three are positive.", "boolean allThreePositive(int a, int b, int c)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> (a > 0 && b > 0 && c > 0);"), "return a > 0 && b > 0 && c > 0;",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> (a > 0 && b > 0 && c > 0)", "result reports all-positive property"))),
    ]
    for item in extra_boolean:
        add("boolean_logic", *item)

    extra_arrays = [
        ("second_element", "Given a non-null integer array of length at least two, return its second element.", "int second(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable \\nothing;", "ensures \\result == a[1];"), "return a[1];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has a second element"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[1]", "returns second element"))),
        ("penultimate_element", "Given a non-null integer array of length at least two, return its penultimate element.", "int penultimate(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable \\nothing;", "ensures \\result == a[a.length - 2];"), "return a[a.length - 2];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has a penultimate element"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[a.length - 2]", "returns penultimate element"))),
        ("first_plus_last_safe", "Given a non-null nonempty array whose first and last elements can be safely added, return their sum.", "int firstPlusLast(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "requires Integer.MIN_VALUE <= (long)a[0] + (long)a[a.length - 1] && (long)a[0] + (long)a[a.length - 1] <= Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == a[0] + a[a.length - 1];"), "return a[0] + a[a.length - 1];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("requires", "Integer.MIN_VALUE <= (long)a[0] + (long)a[a.length - 1] && (long)a[0] + (long)a[a.length - 1] <= Integer.MAX_VALUE", "endpoint sum cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[0] + a[a.length - 1]", "returns endpoint sum"))),
        ("array_has_length_at_least", "Given a non-null integer array and nonnegative n, return true exactly when the array length is at least n.", "boolean hasLengthAtLeast(int[] a, int n)",
         contract("public normal_behavior", "requires a != null;", "requires n >= 0;", "assignable \\nothing;", "ensures \\result <==> a.length >= n;"), "return a.length >= n;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "n >= 0", "threshold is nonnegative"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> a.length >= n", "result reports minimum length"))),
        ("set_first", "Given a non-null nonempty array and a value, store the value in the first element.", "void setFirst(int[] a, int v)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable a[0];", "ensures a[0] == v;"), "a[0] = v;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("assignable", "a[0]", "only first element may change"), ("ensures", "a[0] == v", "first element is updated"))),
        ("set_last", "Given a non-null nonempty array and a value, store the value in the last element.", "void setLast(int[] a, int v)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable a[a.length - 1];", "ensures a[a.length - 1] == v;"), "a[a.length - 1] = v;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("assignable", "a[a.length - 1]", "only last element may change"), ("ensures", "a[a.length - 1] == v", "last element is updated"))),
        ("increment_first_safe", "Given a non-null nonempty array whose first element can be safely incremented, increment only the first element.", "void incrementFirst(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "requires a[0] < Integer.MAX_VALUE;", "assignable a[0];", "ensures a[0] == \\old(a[0]) + 1;"), "a[0] = a[0] + 1;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("requires", "a[0] < Integer.MAX_VALUE", "increment cannot overflow"), ("assignable", "a[0]", "only first element may change"), ("ensures", "a[0] == \\old(a[0]) + 1", "first element incremented"))),
        ("copy_first_to_last", "Given a non-null array of length at least two, copy the first element into the last element.", "void copyFirstToLast(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable a[a.length - 1];", "ensures a[a.length - 1] == \\old(a[0]);"), "a[a.length - 1] = a[0];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has distinct first and last positions"), ("assignable", "a[a.length - 1]", "only last element may change"), ("ensures", "a[a.length - 1] == \\old(a[0])", "last receives old first"))),
        ("swap_first_last", "Given a non-null array of length at least two, swap the first and last elements.", "void swapFirstLast(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable a[0], a[a.length - 1];", "ensures a[0] == \\old(a[a.length - 1]);", "ensures a[a.length - 1] == \\old(a[0]);"), "int t = a[0];\na[0] = a[a.length - 1];\na[a.length - 1] = t;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has endpoints to swap"), ("assignable", "a[0], a[a.length - 1]", "only endpoints may change"), ("ensures", "a[0] == \\old(a[a.length - 1])", "first receives old last"), ("ensures", "a[a.length - 1] == \\old(a[0])", "last receives old first"))),
        ("three_array_sum_safe", "Given a non-null length-three array whose elements can be safely summed, return the sum of the three elements.", "int sum3Array(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length == 3;", "requires Integer.MIN_VALUE <= (long)a[0] + (long)a[1] && (long)a[0] + (long)a[1] <= Integer.MAX_VALUE;", "requires Integer.MIN_VALUE <= (long)(a[0] + a[1]) + (long)a[2] && (long)(a[0] + a[1]) + (long)a[2] <= Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == a[0] + a[1] + a[2];"), "return a[0] + a[1] + a[2];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length == 3", "array length is three"), ("requires", "Integer.MIN_VALUE <= (long)a[0] + (long)a[1] && (long)a[0] + (long)a[1] <= Integer.MAX_VALUE", "first addition cannot overflow"), ("requires", "Integer.MIN_VALUE <= (long)(a[0] + a[1]) + (long)a[2] && (long)(a[0] + a[1]) + (long)a[2] <= Integer.MAX_VALUE", "second addition cannot overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[0] + a[1] + a[2]", "returns three-element sum"))),
        ("first_is_zero", "Given a non-null nonempty array, return true exactly when the first element is zero.", "boolean firstIsZero(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures \\result <==> a[0] == 0;"), "return a[0] == 0;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> a[0] == 0", "result reports whether first element is zero"))),
        ("last_is_positive", "Given a non-null nonempty array, return true exactly when the last element is positive.", "boolean lastIsPositive(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length > 0;", "assignable \\nothing;", "ensures \\result <==> a[a.length - 1] > 0;"), "return a[a.length - 1] > 0;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length > 0", "array is nonempty"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> a[a.length - 1] > 0", "result reports whether last element is positive"))),
        ("middle_of_three", "Given a non-null array of length three, return its middle element.", "int middleOfThree(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length == 3;", "assignable \\nothing;", "ensures \\result == a[1];"), "return a[1];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length == 3", "array length is three"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[1]", "returns middle element"))),
        ("set_pair", "Given a non-null array with at least two elements, store x in the first element and y in the second.", "void setPair(int[] a, int x, int y)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable a[0], a[1];", "ensures a[0] == x;", "ensures a[1] == y;"), "a[0] = x;\na[1] = y;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has two elements"), ("assignable", "a[0], a[1]", "only first two elements may change"), ("ensures", "a[0] == x", "first element updated"), ("ensures", "a[1] == y", "second element updated"))),
        ("clear_first_two", "Given a non-null array with at least two elements, set its first two elements to zero.", "void clearFirstTwo(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable a[0], a[1];", "ensures a[0] == 0;", "ensures a[1] == 0;"), "a[0] = 0;\na[1] = 0;",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has two elements"), ("assignable", "a[0], a[1]", "only first two elements may change"), ("ensures", "a[0] == 0", "first element cleared"), ("ensures", "a[1] == 0", "second element cleared"))),
        ("first_two_ordered", "Given a non-null array with at least two elements, return true exactly when the first element is no greater than the second.", "boolean firstTwoOrdered(int[] a)",
         contract("public normal_behavior", "requires a != null;", "requires a.length >= 2;", "assignable \\nothing;", "ensures \\result <==> a[0] <= a[1];"), "return a[0] <= a[1];",
         clauses(("requires", "a != null", "array reference is non-null"), ("requires", "a.length >= 2", "array has two elements"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> a[0] <= a[1]", "result reports first-pair ordering"))),
    ]
    for item in extra_arrays:
        add("array_extra", *item)

    extra_strings_chars = [
        ("string_length", "Given a non-null String, return its length.", "int stringLength(String s)",
         contract("public normal_behavior", "requires s != null;", "assignable \\nothing;", "ensures \\result == s.length();"), "return s.length();",
         clauses(("requires", "s != null", "string reference is non-null"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == s.length()", "returns string length"))),
        ("string_is_empty", "Given a non-null String, return true exactly when its length is zero.", "boolean stringIsEmpty(String s)",
         contract("public normal_behavior", "requires s != null;", "assignable \\nothing;", "ensures \\result <==> s.length() == 0;"), "return s.length() == 0;",
         clauses(("requires", "s != null", "string reference is non-null"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> s.length() == 0", "result reports empty string"))),
        ("first_char", "Given a non-null nonempty String, return its first character.", "char firstChar(String s)",
         contract("public normal_behavior", "requires s != null;", "requires s.length() > 0;", "assignable \\nothing;", "ensures \\result == s.charAt(0);"), "return s.charAt(0);",
         clauses(("requires", "s != null", "string reference is non-null"), ("requires", "s.length() > 0", "string is nonempty"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == s.charAt(0)", "returns first character"))),
        ("last_char", "Given a non-null nonempty String, return its last character.", "char lastChar(String s)",
         contract("public normal_behavior", "requires s != null;", "requires s.length() > 0;", "assignable \\nothing;", "ensures \\result == s.charAt(s.length() - 1);"), "return s.charAt(s.length() - 1);",
         clauses(("requires", "s != null", "string reference is non-null"), ("requires", "s.length() > 0", "string is nonempty"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == s.charAt(s.length() - 1)", "returns last character"))),
        ("is_lowercase_ascii", "Given a character, return true exactly when it is a lowercase ASCII letter.", "boolean isLowerAscii(char ch)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> ('a' <= ch && ch <= 'z');"), "return 'a' <= ch && ch <= 'z';",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> ('a' <= ch && ch <= 'z')", "result reports lowercase ASCII"))),
        ("is_uppercase_ascii", "Given a character, return true exactly when it is an uppercase ASCII letter.", "boolean isUpperAscii(char ch)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> ('A' <= ch && ch <= 'Z');"), "return 'A' <= ch && ch <= 'Z';",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> ('A' <= ch && ch <= 'Z')", "result reports uppercase ASCII"))),
        ("ascii_to_lower", "Given an uppercase ASCII letter, return the corresponding lowercase letter.", "char toLowerAscii(char ch)",
         contract("public normal_behavior", "requires 'A' <= ch && ch <= 'Z';", "assignable \\nothing;", "ensures \\result == ch + ('a' - 'A');"), "return (char)(ch + ('a' - 'A'));",
         clauses(("requires", "'A' <= ch && ch <= 'Z'", "input is uppercase ASCII"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == ch + ('a' - 'A')", "returns lowercase counterpart"))),
        ("ascii_digit_check", "Given a character, return true exactly when it is an ASCII digit.", "boolean isAsciiDigit(char ch)",
         contract("public normal_behavior", "assignable \\nothing;", "ensures \\result <==> ('0' <= ch && ch <= '9');"), "return '0' <= ch && ch <= '9';",
         clauses(("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result <==> ('0' <= ch && ch <= '9')", "result reports ASCII digit"))),
    ]
    for item in extra_strings_chars:
        add("strings_chars", *item)

    extra_exceptions = [
        ("require_positive", "Given an integer x, return x when it is positive and throw IllegalArgumentException otherwise.", "int requirePositive(int x)",
         contract("public normal_behavior", "requires x > 0;", "assignable \\nothing;", "ensures \\result == x;", "also", "public exceptional_behavior", "requires x <= 0;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (x <= 0) throw new IllegalArgumentException();\nreturn x;",
         clauses(("requires", "x > 0", "normal case requires positive input"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x", "normal case returns input"), ("signals", "x <= 0 ==> IllegalArgumentException", "nonpositive input throws IllegalArgumentException"))),
        ("require_nonnegative", "Given an integer x, return x when it is nonnegative and throw IllegalArgumentException otherwise.", "int requireNonnegative(int x)",
         contract("public normal_behavior", "requires x >= 0;", "assignable \\nothing;", "ensures \\result == x;", "also", "public exceptional_behavior", "requires x < 0;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (x < 0) throw new IllegalArgumentException();\nreturn x;",
         clauses(("requires", "x >= 0", "normal case requires nonnegative input"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x", "normal case returns input"), ("signals", "x < 0 ==> IllegalArgumentException", "negative input throws IllegalArgumentException"))),
        ("checked_char_at", "Given a String and index, return the character at the index for valid inputs and throw IllegalArgumentException otherwise.", "char checkedCharAt(String s, int i)",
         contract("public normal_behavior", "requires s != null && 0 <= i && i < s.length();", "assignable \\nothing;", "ensures \\result == s.charAt(i);", "also", "public exceptional_behavior", "requires s == null || i < 0 || (s != null && i >= s.length());", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (s == null || i < 0 || i >= s.length()) throw new IllegalArgumentException();\nreturn s.charAt(i);",
         clauses(("requires", "s != null && 0 <= i && i < s.length()", "normal case has non-null string and valid index"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == s.charAt(i)", "normal case returns indexed character"), ("signals", "s == null || i < 0 || i >= s.length() ==> IllegalArgumentException", "bad input throws IllegalArgumentException"))),
        ("checked_first", "Given an array, return its first element when non-null and nonempty, otherwise throw IllegalArgumentException.", "int checkedFirst(int[] a)",
         contract("public normal_behavior", "requires a != null && a.length > 0;", "assignable \\nothing;", "ensures \\result == a[0];", "also", "public exceptional_behavior", "requires a == null || (a != null && a.length == 0);", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (a == null || a.length == 0) throw new IllegalArgumentException();\nreturn a[0];",
         clauses(("requires", "a != null && a.length > 0", "normal case has nonempty array"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[0]", "normal case returns first element"), ("signals", "a == null || a.length == 0 ==> IllegalArgumentException", "null or empty array throws IllegalArgumentException"))),
        ("checked_last", "Given an array, return its last element when non-null and nonempty, otherwise throw IllegalArgumentException.", "int checkedLast(int[] a)",
         contract("public normal_behavior", "requires a != null && a.length > 0;", "assignable \\nothing;", "ensures \\result == a[a.length - 1];", "also", "public exceptional_behavior", "requires a == null || (a != null && a.length == 0);", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (a == null || a.length == 0) throw new IllegalArgumentException();\nreturn a[a.length - 1];",
         clauses(("requires", "a != null && a.length > 0", "normal case has nonempty array"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == a[a.length - 1]", "normal case returns last element"), ("signals", "a == null || a.length == 0 ==> IllegalArgumentException", "null or empty array throws IllegalArgumentException"))),
        ("require_uppercase_ascii", "Given a character, return it when it is uppercase ASCII and throw IllegalArgumentException otherwise.", "char requireUpperAscii(char ch)",
         contract("public normal_behavior", "requires 'A' <= ch && ch <= 'Z';", "assignable \\nothing;", "ensures \\result == ch;", "also", "public exceptional_behavior", "requires ch < 'A' || ch > 'Z';", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (ch < 'A' || ch > 'Z') throw new IllegalArgumentException();\nreturn ch;",
         clauses(("requires", "'A' <= ch && ch <= 'Z'", "normal case has uppercase ASCII"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == ch", "normal case returns character"), ("signals", "ch < 'A' || ch > 'Z' ==> IllegalArgumentException", "non-uppercase input throws IllegalArgumentException"))),
        ("require_sorted_pair", "Given two integers x and y, return x when x <= y and throw IllegalArgumentException otherwise.", "int requireSortedPair(int x, int y)",
         contract("public normal_behavior", "requires x <= y;", "assignable \\nothing;", "ensures \\result == x;", "also", "public exceptional_behavior", "requires x > y;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (x > y) throw new IllegalArgumentException();\nreturn x;",
         clauses(("requires", "x <= y", "normal case has ordered pair"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x", "normal case returns first value"), ("signals", "x > y ==> IllegalArgumentException", "descending pair throws IllegalArgumentException"))),
        ("checked_successor", "Given an integer below Integer.MAX_VALUE, return its successor and throw IllegalArgumentException at Integer.MAX_VALUE.", "int checkedSuccessor(int x)",
         contract("public normal_behavior", "requires x < Integer.MAX_VALUE;", "assignable \\nothing;", "ensures \\result == x + 1;", "also", "public exceptional_behavior", "requires x == Integer.MAX_VALUE;", "assignable \\nothing;", "signals_only IllegalArgumentException;", "signals (IllegalArgumentException e) true;"), "if (x == Integer.MAX_VALUE) throw new IllegalArgumentException();\nreturn x + 1;",
         clauses(("requires", "x < Integer.MAX_VALUE", "normal case avoids overflow"), ("assignable", "\\nothing", "does not mutate state"), ("ensures", "\\result == x + 1", "normal case returns successor"), ("signals", "x == Integer.MAX_VALUE ==> IllegalArgumentException", "maximum input throws IllegalArgumentException"))),
    ]
    for item in extra_exceptions:
        add("exceptions", *item)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "requirements").mkdir(parents=True)
    (OUT / "ground-truth").mkdir(parents=True)

    requirements = []
    gt_specs = []
    for p in problems:
        path = OUT / "ground-truth" / p["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(p.pop("source"), encoding="utf-8")
        requirement_entry = {
            "id": p["id"],
            "path": p["path"],
            "category": p["category"],
            "requirement_en": p["requirement_en"],
        }
        if p["type_context"]:
            requirement_entry["type_context"] = p["type_context"]
        requirements.append(requirement_entry)
        ground_truth_entry = {
            "id": p["id"],
            "path": p["path"],
            "category": p["category"],
            "requirement_en": p["requirement_en"],
            "ground_truth_file": str(Path("benchmarks/java-problems/ground-truth") / p["path"]),
            "ground_truth_source": "manual",
            "function_signature": p["function_signature"],
            "ground_truth_clauses": p["ground_truth_clauses"],
            "ground_truth_contract": p["jml_contract"],
        }
        if p["type_context"]:
            ground_truth_entry["type_context"] = p["type_context"]
        gt_specs.append(ground_truth_entry)

    problem_count = len(problems)
    category_counts = Counter(p["category"] for p in requirements)
    category_summary = "\n".join(
        f"- `{category}`: {count}" for category, count in sorted(category_counts.items())
    )
    requirements_name = f"requirements_{problem_count}.json"
    ground_truth_name = f"requirements_{problem_count}_ground_truth_specs.json"

    (OUT / "requirements" / requirements_name).write_text(
        json.dumps(requirements, indent=2) + "\n", encoding="utf-8")
    (OUT / "requirements" / ground_truth_name).write_text(
        json.dumps(gt_specs, indent=2) + "\n", encoding="utf-8")
    if problem_count >= 44:
        (OUT / "requirements" / "requirements_44.json").write_text(
            json.dumps(requirements[:44], indent=2) + "\n", encoding="utf-8"
        )
        (OUT / "requirements" / "requirements_44_ground_truth_specs.json").write_text(
            json.dumps(gt_specs[:44], indent=2) + "\n", encoding="utf-8"
        )

    readme = f"""# java-problems

Java/OpenJML requirement-to-code benchmark dataset.

This is the first Java-specific extension of the C/ACSL benchmark. It follows:

```text
Requirement -> JML Spec -> Java Code -> OpenJML -> Spec Coverage
```

The set intentionally is not a one-to-one port of the C pointer-heavy problems.
It prioritizes arrays, loops, search, maximum/minimum, sortedness, mutation
frames, nullability, object invariants, and exception behavior.

## Problem Set

This dataset contains {problem_count} problems. Every reference implementation
in `ground-truth/` is expected to pass OpenJML ESC in the Java/OpenJML container.

Category distribution:

{category_summary}

## Layout

- `requirements/{requirements_name}`: natural-language requirements.
- `requirements/{ground_truth_name}`: curated JML ground-truth targets.
- `requirements/requirements_44*.json`: legacy 44-problem subset retained for reproducibility.
- `ground-truth/**/*.java`: reference Java implementations annotated with JML.

## Verify Reference Implementations

Use the local OpenJML installation:

```bash
./scripts/run_openjml_java_problems.sh
```

On arm64, OpenJML ESC needs an explicit solver:

```bash
OPENJML_SOLVER=/usr/bin/z3 ./scripts/run_openjml_java_problems.sh
```

Current reference status in this container with `OPENJML_SOLVER=/usr/bin/z3`:

```text
{problem_count} pass / {problem_count} total
```
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Generated {len(problems)} Java/OpenJML problems in {OUT}")


if __name__ == "__main__":
    main()
