from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def append_value(a: List[int], value: int) -> None:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)) + 1)
    Ensures(a[len(a) - 1] == value)
    a.append(value)
