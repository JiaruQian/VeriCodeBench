from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_first(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) > 0)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[0]))
    return a[0]
