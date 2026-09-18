from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def zero_if_singleton(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(Implies(Old(len(a)) == 1, a[0] == 0))
    if len(a) == 1:
        a[0] = 0
