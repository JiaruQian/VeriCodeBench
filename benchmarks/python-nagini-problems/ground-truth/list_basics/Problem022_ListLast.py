from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_last(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) > 0)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[len(a) - 1]))
    return a[len(a) - 1]
