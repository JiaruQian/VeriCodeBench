from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def increment_first(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 1)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)))
    Ensures(a[0] == Old(a[0]) + 1)
    a[0] = a[0] + 1
