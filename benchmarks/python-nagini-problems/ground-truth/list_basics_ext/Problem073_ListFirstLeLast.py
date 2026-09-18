from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_first_le_last(a: List[int]) -> bool:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == (Old(a[0]) <= Old(a[len(a) - 1])))
    return a[0] <= a[len(a) - 1]
