from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_second_or_first(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(Implies(Old(len(a)) == 1, Result() == Old(a[0])))
    Ensures(Implies(Old(len(a)) >= 2, Result() == Old(a[1])))
    if len(a) >= 2:
        return a[1]
    return a[0]
