from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_get_at(a: List[int], i: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[i]))
    return a[i]
