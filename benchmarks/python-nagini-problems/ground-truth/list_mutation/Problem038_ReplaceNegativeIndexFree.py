from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def replace_negative_index_free(a: List[int], i: int, value: int) -> None:
    Requires(Acc(list_pred(a)))
    Requires(0 <= i and i < len(a))
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[i] == value)
    a[i] = value
