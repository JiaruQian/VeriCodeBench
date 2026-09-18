from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def second_element(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 2)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == Old(a[1]))
    return a[1]
