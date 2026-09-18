#!/usr/bin/env python3
"""Generate the Python/Nagini benchmark problem set."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "python-nagini-problems"


def contract(clause_exprs: list[str]) -> str:
    return "\n".join(clause_exprs)


def nagini_expr(expr: str) -> str:
    if "==>" in expr:
        left, right = expr.split("==>", 1)
        return f"Implies({left.strip()}, {right.strip()})"
    return expr


def contract_call(typ: str, expr: str) -> str:
    fn = "Requires" if typ == "requires" else "Ensures"
    return f"{fn}({nagini_expr(expr)})"


def clause(idx: int, typ: str, expr: str, text: str) -> dict[str, str]:
    return {
        "id": f"gt{idx}",
        "type": typ,
        "expr": expr,
        "text": text,
        "source": "manual_nagini_ground_truth",
    }


def source(function_code: str) -> str:
    return (
        "from typing import Dict, List, Optional\n"
        "from nagini_contracts.contracts import *\n\n\n"
        f"{function_code.strip()}\n"
    )


PROBLEMS: list[dict[str, object]] = []


def add(
    category: str,
    name: str,
    func: str,
    requirement: str,
    signature: str,
    clause_data: list[tuple[str, str, str]],
    function_code: str,
) -> None:
    pid = len(PROBLEMS) + 1
    filename = f"Problem{pid:03d}_{name}.py"
    path = f"{category}/{filename}"
    clauses = [clause(i + 1, *c) for i, c in enumerate(clause_data)]
    PROBLEMS.append(
        {
            "id": pid,
            "path": path,
            "category": category,
            "requirement_en": requirement,
            "ground_truth_file": f"benchmarks/python-nagini-problems/ground-truth/{path}",
            "ground_truth_source": "manual",
            "verifier": "nagini",
            "spec_language": "nagini_contracts",
            "function_signature": signature,
            "ground_truth_clauses": clauses,
            "ground_truth_contract": contract(
                [contract_call(typ, expr) for typ, expr, _ in clause_data]
            ),
            "function_code": function_code,
        }
    )


# Scalar arithmetic and boolean APIs.
add(
    "scalar_arithmetic",
    "MaxInt",
    "max_int",
    "Given two Python integers, return the greater value.",
    "def max_int(x: int, y: int) -> int:",
    [
        ("ensures", "Result() == x or Result() == y", "result is one input"),
        ("ensures", "Result() >= x and Result() >= y", "result is at least both inputs"),
    ],
    """
def max_int(x: int, y: int) -> int:
    Ensures(Result() == x or Result() == y)
    Ensures(Result() >= x and Result() >= y)
    if x >= y:
        return x
    return y
""",
)

add(
    "scalar_arithmetic",
    "MinInt",
    "min_int",
    "Given two Python integers, return the smaller value.",
    "def min_int(x: int, y: int) -> int:",
    [
        ("ensures", "Result() == x or Result() == y", "result is one input"),
        ("ensures", "Result() <= x and Result() <= y", "result is at most both inputs"),
    ],
    """
def min_int(x: int, y: int) -> int:
    Ensures(Result() == x or Result() == y)
    Ensures(Result() <= x and Result() <= y)
    if x <= y:
        return x
    return y
""",
)

add(
    "scalar_arithmetic",
    "AbsInt",
    "abs_int",
    "Given a Python integer, return its absolute value.",
    "def abs_int(x: int) -> int:",
    [
        ("ensures", "Result() >= 0", "absolute value is nonnegative"),
        ("ensures", "x >= 0 ==> Result() == x", "nonnegative inputs are unchanged"),
        ("ensures", "x < 0 ==> Result() == -x", "negative inputs are negated"),
    ],
    """
def abs_int(x: int) -> int:
    Ensures(Result() >= 0)
    Ensures(Implies(x >= 0, Result() == x))
    Ensures(Implies(x < 0, Result() == -x))
    if x >= 0:
        return x
    return -x
""",
)

add(
    "scalar_arithmetic",
    "ClampInt",
    "clamp_int",
    "Given x and an ordered inclusive range [lo, hi], clamp x into that range.",
    "def clamp_int(x: int, lo: int, hi: int) -> int:",
    [
        ("requires", "lo <= hi", "bounds are ordered"),
        ("ensures", "lo <= Result() and Result() <= hi", "result lies in range"),
        ("ensures", "x < lo ==> Result() == lo", "low values clamp to lo"),
        ("ensures", "lo <= x and x <= hi ==> Result() == x", "in-range values are unchanged"),
        ("ensures", "x > hi ==> Result() == hi", "high values clamp to hi"),
    ],
    """
def clamp_int(x: int, lo: int, hi: int) -> int:
    Requires(lo <= hi)
    Ensures(lo <= Result() and Result() <= hi)
    Ensures(Implies(x < lo, Result() == lo))
    Ensures(Implies(lo <= x and x <= hi, Result() == x))
    Ensures(Implies(x > hi, Result() == hi))
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
""",
)

add(
    "scalar_arithmetic",
    "SafeDiv",
    "safe_div",
    "Given integers x and y with y nonzero, return integer division x // y without raising ZeroDivisionError.",
    "def safe_div(x: int, y: int) -> int:",
    [
        ("requires", "y != 0", "divisor is nonzero"),
        ("ensures", "Result() == x // y", "result is Python floor division"),
    ],
    """
def safe_div(x: int, y: int) -> int:
    Requires(y != 0)
    Ensures(Result() == x // y)
    return x // y
""",
)

add(
    "scalar_arithmetic",
    "Sign",
    "sign",
    "Return -1 for negative input, 0 for zero, and 1 for positive input.",
    "def sign(x: int) -> int:",
    [
        ("ensures", "Result() == -1 or Result() == 0 or Result() == 1", "result is a sign code"),
        ("ensures", "x < 0 ==> Result() == -1", "negative maps to -1"),
        ("ensures", "x == 0 ==> Result() == 0", "zero maps to 0"),
        ("ensures", "x > 0 ==> Result() == 1", "positive maps to 1"),
    ],
    """
def sign(x: int) -> int:
    Ensures(Result() == -1 or Result() == 0 or Result() == 1)
    Ensures(Implies(x < 0, Result() == -1))
    Ensures(Implies(x == 0, Result() == 0))
    Ensures(Implies(x > 0, Result() == 1))
    if x < 0:
        return -1
    if x > 0:
        return 1
    return 0
""",
)

add(
    "scalar_arithmetic",
    "IsEven",
    "is_even",
    "Return true exactly when the integer is even.",
    "def is_even(x: int) -> bool:",
    [("ensures", "Result() == (x % 2 == 0)", "boolean result matches parity")],
    """
def is_even(x: int) -> bool:
    Ensures(Result() == (x % 2 == 0))
    return x % 2 == 0
""",
)

add(
    "scalar_arithmetic",
    "BetweenInclusive",
    "between_inclusive",
    "Return true exactly when x lies in the inclusive interval [lo, hi].",
    "def between_inclusive(x: int, lo: int, hi: int) -> bool:",
    [("ensures", "Result() == (lo <= x and x <= hi)", "result captures inclusive membership")],
    """
def between_inclusive(x: int, lo: int, hi: int) -> bool:
    Ensures(Result() == (lo <= x and x <= hi))
    return lo <= x and x <= hi
""",
)

add(
    "scalar_arithmetic",
    "AddThree",
    "add_three",
    "Return the mathematical sum of three Python integers.",
    "def add_three(x: int, y: int, z: int) -> int:",
    [("ensures", "Result() == x + y + z", "result is the sum of all inputs")],
    """
def add_three(x: int, y: int, z: int) -> int:
    Ensures(Result() == x + y + z)
    return x + y + z
""",
)

add(
    "scalar_arithmetic",
    "NonNegativeDifference",
    "nonnegative_difference",
    "Given x >= y, return x - y and preserve nonnegativity.",
    "def nonnegative_difference(x: int, y: int) -> int:",
    [
        ("requires", "x >= y", "difference is nonnegative"),
        ("ensures", "Result() == x - y", "result is the difference"),
        ("ensures", "Result() >= 0", "result is nonnegative"),
    ],
    """
def nonnegative_difference(x: int, y: int) -> int:
    Requires(x >= y)
    Ensures(Result() == x - y)
    Ensures(Result() >= 0)
    return x - y
""",
)


# Optional/None compatibility APIs.
add(
    "optional_none",
    "IsNoneInt",
    "is_none_int",
    "Given an optional integer, return true exactly when it is None.",
    "def is_none_int(x: Optional[int]) -> bool:",
    [("ensures", "Result() == (x is None)", "result captures None status")],
    """
def is_none_int(x: Optional[int]) -> bool:
    Ensures(Result() == (x is None))
    return x is None
""",
)

add(
    "optional_none",
    "IsSomeInt",
    "is_some_int",
    "Given an optional integer, return true exactly when it contains an integer.",
    "def is_some_int(x: Optional[int]) -> bool:",
    [("ensures", "Result() == (x is not None)", "result captures non-None status")],
    """
def is_some_int(x: Optional[int]) -> bool:
    Ensures(Result() == (x is not None))
    return x is not None
""",
)

add(
    "optional_none",
    "UnwrapOr",
    "unwrap_or",
    "Return the contained optional integer, or the provided default when it is None.",
    "def unwrap_or(x: Optional[int], default: int) -> int:",
    [
        ("ensures", "x is not None ==> Result() == x", "non-None value is returned"),
        ("ensures", "x is None ==> Result() == default", "default is returned for None"),
    ],
    """
def unwrap_or(x: Optional[int], default: int) -> int:
    Ensures(Implies(x is not None, Result() == x))
    Ensures(Implies(x is None, Result() == default))
    if x is None:
        return default
    return x
""",
)

add(
    "optional_none",
    "RequireSome",
    "require_some",
    "Given a non-None optional integer, return the contained value without raising an exception.",
    "def require_some(x: Optional[int]) -> int:",
    [
        ("requires", "x is not None", "input contains a value"),
        ("ensures", "Result() == x", "contained value is returned"),
    ],
    """
def require_some(x: Optional[int]) -> int:
    Requires(x is not None)
    Ensures(Result() == x)
    return x
""",
)

add(
    "optional_none",
    "IncrementOptional",
    "increment_optional",
    "Increment a present optional integer and keep None unchanged.",
    "def increment_optional(x: Optional[int]) -> Optional[int]:",
    [
        ("ensures", "x is None ==> Result() is None", "None remains None"),
        ("ensures", "x is not None ==> Result() is not None", "present value produces a non-None result"),
        ("ensures", "x is not None ==> Result() == x + 1", "present value is incremented"),
    ],
    """
def increment_optional(x: Optional[int]) -> Optional[int]:
    Ensures(Implies(x is None, Result() is None))
    Ensures(Implies(x is not None, Result() is not None))
    Ensures(Implies(x is not None, Result() == x + 1))
    if x is None:
        return None
    return x + 1
""",
)

add(
    "optional_none",
    "PositiveOrNone",
    "positive_or_none",
    "Return x when x is positive, otherwise return None.",
    "def positive_or_none(x: int) -> Optional[int]:",
    [
        ("ensures", "x > 0 ==> Result() is not None", "positive value produces a non-None result"),
        ("ensures", "x > 0 ==> Result() == x", "positive value is returned"),
        ("ensures", "x <= 0 ==> Result() is None", "nonpositive values map to None"),
    ],
    """
def positive_or_none(x: int) -> Optional[int]:
    Ensures(Implies(x > 0, Result() is not None))
    Ensures(Implies(x > 0, Result() == x))
    Ensures(Implies(x <= 0, Result() is None))
    if x > 0:
        return x
    return None
""",
)

add(
    "optional_none",
    "DefaultIfZero",
    "default_if_zero",
    "Return the fallback exactly when x is zero, otherwise return x.",
    "def default_if_zero(x: int, fallback: int) -> int:",
    [
        ("ensures", "x == 0 ==> Result() == fallback", "zero maps to fallback"),
        ("ensures", "x != 0 ==> Result() == x", "nonzero maps to itself"),
    ],
    """
def default_if_zero(x: int, fallback: int) -> int:
    Ensures(Implies(x == 0, Result() == fallback))
    Ensures(Implies(x != 0, Result() == x))
    if x == 0:
        return fallback
    return x
""",
)

add(
    "optional_none",
    "Coalesce3",
    "coalesce3",
    "Return the first non-None value among a, b, and fallback, where fallback is always an integer.",
    "def coalesce3(a: Optional[int], b: Optional[int], fallback: int) -> int:",
    [
        ("ensures", "a is not None ==> Result() == a", "first value has priority"),
        ("ensures", "a is None and b is not None ==> Result() == b", "second value used when first is None"),
        ("ensures", "a is None and b is None ==> Result() == fallback", "fallback used when both are None"),
    ],
    """
def coalesce3(a: Optional[int], b: Optional[int], fallback: int) -> int:
    Ensures(Implies(a is not None, Result() == a))
    Ensures(Implies(a is None and b is not None, Result() == b))
    Ensures(Implies(a is None and b is None, Result() == fallback))
    if a is not None:
        return a
    if b is not None:
        return b
    return fallback
""",
)


# List basics. These emphasize typed contracts and list permissions.
for name, func, req, sig, clauses, body in [
    (
        "ListLength",
        "list_length",
        "Given a list of integers, return its length without mutating it.",
        "def list_length(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == len(a)", "result is list length"),
        ],
        "return len(a)",
    ),
    (
        "ListIsEmpty",
        "list_is_empty",
        "Return true exactly when the integer list is empty.",
        "def list_is_empty(a: List[int]) -> bool:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == (len(a) == 0)", "result captures empty status"),
        ],
        "return len(a) == 0",
    ),
    (
        "ListFirst",
        "list_first",
        "Given a nonempty integer list, return the first element.",
        "def list_first(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) > 0", "list is nonempty"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == Old(a[0])", "first element is returned"),
        ],
        "return a[0]",
    ),
    (
        "ListLast",
        "list_last",
        "Given a nonempty integer list, return the last element.",
        "def list_last(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) > 0", "list is nonempty"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == Old(a[len(a) - 1])", "last element is returned"),
        ],
        "return a[len(a) - 1]",
    ),
    (
        "ListGetAt",
        "list_get_at",
        "Given an integer list and a valid index, return the indexed element.",
        "def list_get_at(a: List[int], i: int) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "index is valid"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == Old(a[i])", "indexed element is returned"),
        ],
        "return a[i]",
    ),
    (
        "HeadOrDefault",
        "head_or_default",
        "Return the first list element when the list is nonempty, otherwise return the default.",
        "def head_or_default(a: List[int], default: int) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "len(a) == 0 ==> Result() == default", "empty list returns default"),
            ("ensures", "Old(len(a)) > 0 ==> Result() == Old(a[0])", "nonempty list returns first element"),
        ],
        "if len(a) == 0:\n        return default\n    return a[0]",
    ),
    (
        "SecondElement",
        "second_element",
        "Given a list with at least two elements, return the second element.",
        "def second_element(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) >= 2", "list has a second element"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == Old(a[1])", "second element is returned"),
        ],
        "return a[1]",
    ),
    (
        "ListSumTwo",
        "list_sum_two",
        "Given a list with at least two integers, return the sum of the first two.",
        "def list_sum_two(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) >= 2", "two elements are available"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == Old(a[0]) + Old(a[1])", "result sums first two elements"),
        ],
        "return a[0] + a[1]",
    ),
    (
        "ListContainsAtIndex",
        "list_contains_at_index",
        "Return true when the given valid index stores the target value.",
        "def list_contains_at_index(a: List[int], i: int, target: int) -> bool:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "index is valid"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == (Old(a[i]) == target)", "result compares indexed value"),
        ],
        "return a[i] == target",
    ),
    (
        "ListPrefixPairSorted",
        "list_prefix_pair_sorted",
        "Given a list with at least two elements, return true exactly when the first pair is nondecreasing.",
        "def list_prefix_pair_sorted(a: List[int]) -> bool:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) >= 2", "first pair exists"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "Result() == (Old(a[0]) <= Old(a[1]))", "result checks pair ordering"),
        ],
        "return a[0] <= a[1]",
    ),
]:
    contract_lines = []
    for typ, expr, _ in clauses:
        contract_lines.append(f"    {contract_call(typ, expr)}")
    add(
        "list_basics",
        name,
        func,
        req,
        sig,
        clauses,
        f"def {func}{sig[sig.index('('):]}\n" + "\n".join(contract_lines) + "\n    " + body,
    )


# List mutation APIs.
for name, func, req, sig, clauses, body in [
    (
        "SetAtIndex",
        "set_at_index",
        "Given a list, valid index, and value, store the value at that index.",
        "def set_at_index(a: List[int], i: int, value: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "index is valid"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[i] == value", "indexed element is updated"),
        ],
        "a[i] = value",
    ),
    (
        "SetFirst",
        "set_first",
        "Given a nonempty list, replace its first element with value.",
        "def set_first(a: List[int], value: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) > 0", "list is nonempty"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[0] == value", "first element is updated"),
        ],
        "a[0] = value",
    ),
    (
        "SetLast",
        "set_last",
        "Given a nonempty list, replace its last element with value.",
        "def set_last(a: List[int], value: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) > 0", "list is nonempty"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[len(a) - 1] == value", "last element is updated"),
        ],
        "a[len(a) - 1] = value",
    ),
    (
        "SwapFirstTwo",
        "swap_first_two",
        "Given a list with at least two elements, swap the first two elements.",
        "def swap_first_two(a: List[int]) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) >= 2", "two elements exist"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[0] == Old(a[1])", "old second element moves to first"),
            ("ensures", "a[1] == Old(a[0])", "old first element moves to second"),
        ],
        "tmp = a[0]\n    a[0] = a[1]\n    a[1] = tmp",
    ),
    (
        "IncrementAtIndex",
        "increment_at_index",
        "Given a list and valid index, increment that element by one.",
        "def increment_at_index(a: List[int], i: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "index is valid"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[i] == Old(a[i]) + 1", "indexed element is incremented"),
        ],
        "a[i] = a[i] + 1",
    ),
    (
        "DecrementAtIndex",
        "decrement_at_index",
        "Given a list and valid index, decrement that element by one.",
        "def decrement_at_index(a: List[int], i: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "index is valid"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[i] == Old(a[i]) - 1", "indexed element is decremented"),
        ],
        "a[i] = a[i] - 1",
    ),
    (
        "AppendValue",
        "append_value",
        "Append a value to the end of the list.",
        "def append_value(a: List[int], value: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a)) + 1", "list length increases by one"),
            ("ensures", "a[len(a) - 1] == value", "new last element is appended value"),
        ],
        "a.append(value)",
    ),
    (
        "ReadAndZeroLast",
        "read_and_zero_last",
        "Given a nonempty list, return its last element and replace that last element with zero.",
        "def read_and_zero_last(a: List[int]) -> int:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "len(a) > 0", "list is nonempty"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "Result() == Old(a[len(a) - 1])", "old last element is returned"),
            ("ensures", "a[len(a) - 1] == 0", "last element is replaced with zero"),
        ],
        "result = a[len(a) - 1]\n    a[len(a) - 1] = 0\n    return result",
    ),
    (
        "ZeroIfSingleton",
        "zero_if_singleton",
        "If the list has exactly one element, replace it with zero; otherwise only preserve the length.",
        "def zero_if_singleton(a: List[int]) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "Old(len(a)) == 1 ==> a[0] == 0", "singleton element is zeroed"),
        ],
        "if len(a) == 1:\n        a[0] = 0",
    ),
    (
        "ReplaceNegativeIndexFree",
        "replace_negative_index_free",
        "Given a valid nonnegative index, replace that element; the precondition rules out Python negative indexing.",
        "def replace_negative_index_free(a: List[int], i: int, value: int) -> None:",
        [
            ("requires", "Acc(list_pred(a))", "caller provides list permission"),
            ("requires", "0 <= i and i < len(a)", "negative indexing and out-of-bounds access are forbidden"),
            ("ensures", "Acc(list_pred(a))", "list permission is returned"),
            ("ensures", "len(a) == Old(len(a))", "list length is unchanged"),
            ("ensures", "a[i] == value", "valid indexed element is updated"),
        ],
        "a[i] = value",
    ),
]:
    contract_lines = []
    for typ, expr, _ in clauses:
        contract_lines.append(f"    {contract_call(typ, expr)}")
    add(
        "list_mutation",
        name,
        func,
        req,
        sig,
        clauses,
        f"def {func}{sig[sig.index('('):]}\n" + "\n".join(contract_lines) + "\n    " + body,
    )


# Dictionary APIs.
for name, func, req, sig, clauses, body in [
    (
        "DictContainsKey",
        "dict_contains_key",
        "Return true exactly when the dictionary contains the key.",
        "def dict_contains_key(d: Dict[int, int], key: int) -> bool:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "Result() == (key in d)", "result captures key membership"),
        ],
        "return key in d",
    ),
    (
        "DictGetExisting",
        "dict_get_existing",
        "Given a dictionary and an existing key, return the associated value.",
        "def dict_get_existing(d: Dict[int, int], key: int) -> int:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("requires", "key in d", "key exists"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "Result() == Old(d[key])", "associated value is returned"),
        ],
        "return d[key]",
    ),
    (
        "DictGetDefault",
        "dict_get_default",
        "Return the stored dictionary value when the key exists, otherwise return the default.",
        "def dict_get_default(d: Dict[int, int], key: int, default: int) -> int:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "Old(key in d) ==> Result() == Old(d[key])", "existing key returns stored value"),
            ("ensures", "key not in d ==> Result() == default", "missing key returns default"),
        ],
        "if key in d:\n        return d[key]\n    return default",
    ),
    (
        "DictSetKey",
        "dict_set_key",
        "Set a dictionary key to a value.",
        "def dict_set_key(d: Dict[int, int], key: int, value: int) -> None:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "key in d", "key exists after update"),
            ("ensures", "d[key] == value", "key maps to updated value"),
        ],
        "d[key] = value",
    ),
    (
        "DictIncrementExisting",
        "dict_increment_existing",
        "Given an existing key, increment its dictionary value by one.",
        "def dict_increment_existing(d: Dict[int, int], key: int) -> None:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("requires", "key in d", "key exists"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "key in d", "key still exists"),
            ("ensures", "d[key] == Old(d[key]) + 1", "stored value is incremented"),
        ],
        "d[key] = d[key] + 1",
    ),
    (
        "DictZeroExisting",
        "dict_zero_existing",
        "Given an existing key, replace its dictionary value with zero.",
        "def dict_zero_existing(d: Dict[int, int], key: int) -> None:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("requires", "key in d", "key exists before update"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "key in d", "key still exists"),
            ("ensures", "d[key] == 0", "stored value is zero after update"),
        ],
        "d[key] = 0",
    ),
    (
        "DictSize",
        "dict_size",
        "Return the number of key-value pairs in the dictionary.",
        "def dict_size(d: Dict[int, int]) -> int:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "Result() == len(d)", "result is dictionary size"),
        ],
        "return len(d)",
    ),
    (
        "DictEnsureKey",
        "dict_ensure_key",
        "Ensure a key is present with fallback value when missing; leave existing value unchanged when present.",
        "def dict_ensure_key(d: Dict[int, int], key: int, fallback: int) -> None:",
        [
            ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
            ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
            ("ensures", "key in d", "key exists after call"),
            ("ensures", "Old(key in d) ==> d[key] == Old(d[key])", "existing value is preserved"),
            ("ensures", "not Old(key in d) ==> d[key] == fallback", "missing key gets fallback"),
        ],
        "if key not in d:\n        d[key] = fallback",
    ),
]:
    contract_lines = []
    for typ, expr, _ in clauses:
        contract_lines.append(f"    {contract_call(typ, expr)}")
    add(
        "dict_apis",
        name,
        func,
        req,
        sig,
        clauses,
        f"def {func}{sig[sig.index('('):]}\n" + "\n".join(contract_lines) + "\n    " + body,
    )


# Exception-freedom oriented simple APIs.
add(
    "exception_freedom",
    "RequireValidIndex",
    "require_valid_index",
    "Given a list and valid nonnegative index, return the element without raising IndexError.",
    "def require_valid_index(a: List[int], i: int) -> int:",
    [
        ("requires", "Acc(list_pred(a))", "caller provides list permission"),
        ("requires", "0 <= i and i < len(a)", "index is valid and nonnegative"),
        ("ensures", "Acc(list_pred(a))", "list permission is returned"),
        ("ensures", "Result() == Old(a[i])", "indexed value is returned"),
    ],
    """
def require_valid_index(a: List[int], i: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[i]))
    return a[i]
""",
)

add(
    "exception_freedom",
    "RequireExistingKey",
    "require_existing_key",
    "Given a dictionary and existing key, return the value without raising KeyError.",
    "def require_existing_key(d: Dict[int, int], key: int) -> int:",
    [
        ("requires", "Acc(dict_pred(d))", "caller provides dictionary permission"),
        ("requires", "key in d", "key exists"),
        ("ensures", "Acc(dict_pred(d))", "dictionary permission is returned"),
        ("ensures", "Result() == Old(d[key])", "existing value is returned"),
    ],
    """
def require_existing_key(d: Dict[int, int], key: int) -> int:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == Old(d[key]))
    return d[key]
""",
)

add(
    "exception_freedom",
    "SafeReciprocalFlag",
    "safe_reciprocal_flag",
    "Return true exactly when division by x would be safe.",
    "def safe_reciprocal_flag(x: int) -> bool:",
    [("ensures", "Result() == (x != 0)", "true exactly for nonzero divisor")],
    """
def safe_reciprocal_flag(x: int) -> bool:
    Ensures(Result() == (x != 0))
    return x != 0
""",
)

add(
    "exception_freedom",
    "SafeSliceUpper",
    "safe_slice_upper",
    "Given a list and valid upper bound, return that upper bound; the precondition makes a[:n] safe.",
    "def safe_slice_upper(a: List[int], n: int) -> int:",
    [
        ("requires", "Acc(list_pred(a))", "caller provides list permission"),
        ("requires", "0 <= n and n <= len(a)", "slice upper bound is valid"),
        ("ensures", "Acc(list_pred(a))", "list permission is returned"),
        ("ensures", "Result() == n", "validated upper bound is returned"),
    ],
    """
def safe_slice_upper(a: List[int], n: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= n and n <= len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == n)
    return n
""",
)


def write_readme() -> None:
    counts: dict[str, int] = {}
    for p in PROBLEMS:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    lines = [
        "# python-nagini-problems",
        "",
        "Python/Nagini requirement-to-code benchmark dataset.",
        "",
        "This is the Python-specific extension of the C/ACSL, Java/JML, and",
        "Rust/Verus benchmark tracks. It follows:",
        "",
        "```text",
        "Requirement -> Nagini Contract -> Python Code -> Nagini -> Spec Coverage",
        "```",
        "",
        "The set is intentionally Python-oriented rather than a direct port of the",
        "C pointer-heavy problems. It prioritizes typed function contracts,",
        "`Optional`/`None` compatibility, list and dictionary mutation, simple",
        "symbolic-execution-friendly pure functions, and preconditions that rule",
        "out common Python runtime exceptions.",
        "",
        "## Problem Set",
        "",
        f"This dataset contains {len(PROBLEMS)} problems.",
        "",
        "Category distribution:",
        "",
    ]
    for category in sorted(counts):
        lines.append(f"- `{category}`: {counts[category]}")
    lines.extend(
        [
            "",
            "## Layout",
            "",
            f"- `requirements/requirements_{len(PROBLEMS)}.json`: natural-language requirements.",
            f"- `requirements/requirements_{len(PROBLEMS)}_ground_truth_specs.json`: curated Nagini ground-truth targets.",
            "- `ground-truth/**/*.py`: reference Python implementations annotated with Nagini contracts.",
            "",
            "## Verify Reference Implementations",
            "",
            "Use the local Nagini installation:",
            "",
            "```bash",
            "./scripts/run_nagini_python_problems.sh",
            "```",
            "",
            "The reference contracts include permissions such as `Acc(list_pred(a))`",
            "and `Acc(dict_pred(d))`, because Nagini models Python containers through",
            "explicit predicate permissions. Read-only container element postconditions",
            "use `Old(...)` to state facts about the pre-state element values.",
            "",
            "Current reference status in this container:",
            "",
            "```text",
            f"{len(PROBLEMS)} pass / {len(PROBLEMS)} total",
            "```",
            "",
        ]
    )
    (BENCH / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if BENCH.exists():
        shutil.rmtree(BENCH)
    for sub in ["requirements", "ground-truth"]:
        (BENCH / sub).mkdir(parents=True, exist_ok=True)

    reqs = []
    specs = []
    for p in PROBLEMS:
        reqs.append(
            {
                "id": p["id"],
                "path": p["path"],
                "category": p["category"],
                "requirement_en": p["requirement_en"],
            }
        )
        spec = {k: v for k, v in p.items() if k != "function_code"}
        specs.append(spec)
        gt_path = BENCH / "ground-truth" / str(p["path"])
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        gt_path.write_text(source(str(p["function_code"])), encoding="utf-8")

    n = len(PROBLEMS)
    (BENCH / "requirements" / f"requirements_{n}.json").write_text(
        json.dumps(reqs, indent=2) + "\n", encoding="utf-8"
    )
    (BENCH / "requirements" / f"requirements_{n}_ground_truth_specs.json").write_text(
        json.dumps(specs, indent=2) + "\n", encoding="utf-8"
    )
    write_readme()


if __name__ == "__main__":
    main()
