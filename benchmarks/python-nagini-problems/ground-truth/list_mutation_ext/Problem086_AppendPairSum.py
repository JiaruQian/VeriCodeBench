from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def append_pair_sum(a: List[int]) -> None:
    Requires(Acc(list_pred(a)))
    Requires(len(a) >= 2)
    Ensures(Acc(list_pred(a)))
    Ensures(len(a) == Old(len(a)) + 1)
    Ensures(a[len(a) - 1] == Old(a[0]) + Old(a[1]))
    a.append(a[0] + a[1])
