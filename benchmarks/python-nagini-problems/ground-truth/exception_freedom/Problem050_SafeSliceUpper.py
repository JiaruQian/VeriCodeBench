from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_slice_upper(a: List[int], n: int) -> int:
    Requires(Acc(list_pred(a)))
    Requires(0 <= n and n <= len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == n)
    return n
