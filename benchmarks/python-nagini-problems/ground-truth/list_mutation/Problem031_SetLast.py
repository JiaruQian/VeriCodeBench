from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def set_last(a: List[int], value: int) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) > 0)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[len(a) - 1] == value)
    a[len(a) - 1] = value
