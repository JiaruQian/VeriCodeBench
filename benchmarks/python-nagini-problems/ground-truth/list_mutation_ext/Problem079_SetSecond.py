from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def set_second(a: List[int], value: int) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 2)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[1] == value)
    a[1] = value
