from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_contains_at_index(a: List[int], i: int, target: int) -> bool:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == (Old(a[i]) == target))
    return a[i] == target
