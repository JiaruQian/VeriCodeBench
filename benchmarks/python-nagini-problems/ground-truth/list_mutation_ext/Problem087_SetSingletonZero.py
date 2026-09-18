from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def set_singleton_zero(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) == 1)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == 1)
    Ensures(a[0] == 0)
    a[0] = 0
