from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_index_is_zero(a: List[int], i: int) -> bool:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == (Old(a[i]) == 0))
    return a[i] == 0
