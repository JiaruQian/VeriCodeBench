from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def append_zero(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)) + 1)
    Ensures(a[len(a) - 1] == 0)
    a.append(0)
