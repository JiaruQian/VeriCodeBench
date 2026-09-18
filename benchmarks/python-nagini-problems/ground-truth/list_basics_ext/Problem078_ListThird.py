from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_third(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 3)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[2]))
    return a[2]
