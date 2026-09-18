from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def require_valid_index(a: List[int], i: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[i]))
    return a[i]
