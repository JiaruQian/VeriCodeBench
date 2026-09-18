from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def set_last_to_length(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[len(a) - 1] == len(a))
    a[len(a) - 1] = len(a)
