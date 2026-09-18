from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def head_or_default(a: List[int], default: int) -> int:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(Implies(len(a) == 0, Result() == default))
    Ensures(Implies(Old(len(a)) > 0, Result() == Old(a[0])))
    if len(a) == 0:
        return default
    return a[0]
