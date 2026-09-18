from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def copy_first_to_last(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[len(a) - 1] == Old(a[0]))
    a[len(a) - 1] = a[0]
