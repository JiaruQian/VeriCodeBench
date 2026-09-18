from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_first_or_zero(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(Implies(Old(len(a)) == 0, Result() == 0))
    Ensures(Implies(Old(len(a)) > 0, Result() == Old(a[0])))
    if len(a) == 0:
        return 0
    return a[0]
