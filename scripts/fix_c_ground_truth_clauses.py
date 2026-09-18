#!/usr/bin/env python3
"""Apply audited corrections to malformed C semantic target clauses."""
import json
from pathlib import Path

PATH = Path("benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json")

CORRECTIONS = {
    2: [("r1", "ensures", r"\old(*b) ==> *a == 0"), ("r2", "ensures", r"!\old(*b) ==> *a == \old(*a)"), ("r3", "ensures", r"*b == \old(*b)")],
    4: [("r1", "ensures", r"\result >= *a"), ("r2", "ensures", r"\result >= *b"), ("r3", "ensures", r"\result == *a || \result == *b")],
    7: [("r1", "ensures", r"\result == *a + *b + *r")],
    8: [("r1", "ensures", r"\result == *p + *q")],
    9: [("gt1", "requires", r"\valid(a+(0..n-1))"), ("gt2", "requires", "n > 0"), ("gt3", "ensures", r"\forall integer i,j; 0<=i<=j<=n-1 ==> a[i]<=a[j]")],
    10: [("r1", "ensures", r"\forall integer k; 0 <= k < n ==> a[k] == 2 * \old(a[k])")],
    12: [("r1", "ensures", r"\forall integer k; 0 <= k < n && k % 2 == 0 ==> a[k] == 0"), ("r2", "ensures", r"\forall integer k; 0 <= k < n && k % 2 != 0 ==> a[k] == \old(a[k])")],
    14: [("r1", "ensures", r"\result >= x"), ("r2", "ensures", r"\result >= y"), ("r3", "ensures", r"\result == x || \result == y")],
    16: [("r1", "ensures", r"arr[n1] == \old(arr[n2])"), ("r2", "ensures", r"arr[n2] == \old(arr[n1])")],
    11: [("r1", "requires", "n > 0"), ("r2", "requires", r"\valid(a+(0..n-1))"), ("r3", "assigns", r"a[0..n-1]"), ("r4", "ensures", r"\forall integer k; 0 <= k < n ==> a[k] == \at(a[n-1-k], Pre)")],
    15: [("r1", "requires", "n > 0"), ("r2", "requires", r"\valid_read(arr+(0..n-1))"), ("r3", "ensures", r"\forall integer k; 0 <= k < n ==> arr[k] == (\at(arr[k], Pre) + c)")],
    17: [("r1", "requires", "n > 0"), ("gt1", "requires", r"\valid_read(arr+(0..n-1))"), ("gt2", "assigns", r"\nothing"), ("gt3", "ensures", r"\forall integer k; 0 <= k < n ==> arr[k] <= \result"), ("gt4", "ensures", r"\exists integer k; 0 <= k < n && arr[k] == \result")],
    18: [("gt1", "requires", "n >= 0"), ("gt2", "requires", r"\valid_read(arr+(0..n-1))"), ("gt3", "assigns", r"\nothing"), ("gt4", "ensures", r"-1 <= \result < n"), ("gt5", "ensures", r"0 <= \result < n ==> arr[\result] == x"), ("gt6", "ensures", r"(\result == -1) ==> (\forall integer i; 0 <= i < n ==> arr[i] != x)"), ("gt7", "assigns", r"\nothing")],
    31: [("r1", "requires", "n > 0"), ("gt1", "requires", r"\valid_read(a + (0..n-1))"), ("gt2", "requires", "n > 0"), ("gt3", "ensures", r"\forall integer k; 0 <= k < n ==> \result >= a[k]"), ("gt4", "ensures", r"\exists integer k; 0 <= k < n && \result == a[k]"), ("gt5", "assigns", r"\nothing")],
    33: [("gt1", "requires", "n > 0"), ("gt2", "requires", r"\valid_read(a+(0..n-1))"), ("gt3", "requires", r"\forall integer k, l; 0 <= k <= l < n ==> a[k] <= a[l]"), ("gt4", "assigns", r"\nothing"), ("gt5", "ensures", r"\result >= -1 && \result < n"), ("gt6", "ensures", r"a[\result] == x"), ("gt7", "ensures", r"\result == -1")],
    36: [("r1", "ensures", r"\result == 1 <==> ((a + b > c) && (a + c > b) && (b + c > a))"), ("r2", "ensures", r"\result == 0 <==> !((a + b > c) && (a + c > b) && (b + c > a))")],
    37: [("r1", "ensures", r"\result == 1 <==> (a + b + c == 180)"), ("r2", "ensures", r"\result == 0 <==> (a + b + c != 180)")],
    42: [("r1", "requires", "a >= 0 && b >= 0"), ("r2", "ensures", r"a % \result == 0 && b % \result == 0"), ("gt2", "assigns", r"\nothing")],
    44: [("gt1", "requires", "n >= 4"), ("gt2", "ensures", r"\result == (n - 4) / 3 + 1"), ("gt3", "assigns", r"\nothing")],
    46: [("r1", "ensures", r"\result >= 0"), ("r2", "ensures", r"\result == val || \result == -val")],
    30: [("r1", "ensures", r"*sum >= 0"), ("gt1", "requires", "n > 0 && x > 0"), ("gt2", "requires", r"(integer)n * x <= INT_MAX"), ("gt3", "requires", r"\valid(sum)"), ("gt4", "requires", r"\valid_read(a + (0..n-1))"), ("gt5", "assigns", r"*sum"), ("gt6", "ensures", r"\result >= 0 && \result <= n"), ("gt7", "ensures", r"*sum == \result * x")],
    48: [("r1", "requires", "x >= 0"), ("r2", "ensures", r"\result == x")],
    44: [("gt1", "requires", "n >= 4"), ("gt2", "ensures", r"\result == (n - 4) / 3 + 1"), ("gt3", "assigns", r"\nothing")],
    50: [("r1", "requires", "n > 0"), ("gt1", "requires", r"\valid_read(a + (0..n-1))"), ("gt2", "requires", "n > 0"), ("gt3", "ensures", r"\forall integer k; 0 <= k < n ==> \result >= a[k]"), ("gt4", "ensures", r"\exists integer k; 0 <= k < n && \result == a[k]"), ("gt5", "assigns", r"\nothing")],
}

data = json.loads(PATH.read_text())
for row in data:
    if int(row["id"]) in CORRECTIONS:
        row["ground_truth_clauses"] = [
            {"id": ident, "type": kind, "expr": expr, "source": "audited_c_ground_truth_correction"}
            for ident, kind, expr in CORRECTIONS[int(row["id"])]
        ]
        row["ground_truth_source"] = "audited_manual"
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print(f"corrected {len(CORRECTIONS)} C ground-truth rows")
