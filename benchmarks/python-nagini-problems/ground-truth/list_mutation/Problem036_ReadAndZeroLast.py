from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def read_and_zero_last(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) > 0)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(Result() == Old(a[len(a) - 1]))
    Ensures(a[len(a) - 1] == 0)
    result = a[len(a) - 1]
    a[len(a) - 1] = 0
    return result
