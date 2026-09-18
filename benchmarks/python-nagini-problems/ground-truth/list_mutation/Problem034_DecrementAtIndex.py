from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def decrement_at_index(a: List[int], i: int) -> None:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[i] == Old(a[i]) - 1)
    a[i] = a[i] - 1
