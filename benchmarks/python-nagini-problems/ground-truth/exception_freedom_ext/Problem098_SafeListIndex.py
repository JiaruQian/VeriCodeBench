from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_list_index(a: List[int], i: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == i)
    return i
