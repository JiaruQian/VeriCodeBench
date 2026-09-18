from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def zero_first_if_positive(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(Implies(Old(a[0]) > 0, a[0] == 0))
    Ensures(Implies(Old(a[0]) <= 0, a[0] == Old(a[0])))
    if a[0] > 0:
        a[0] = 0
