from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_get_or_default(a: List[int], i: int, default: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(i >= 0)
    Ensures(Acc(list_pred(a)))
    Ensures(Implies(i < Old(len(a)), Result() == Old(a[i])))
    Ensures(Implies(i >= Old(len(a)), Result() == default))
    if i < len(a):
        return a[i]
    return default
