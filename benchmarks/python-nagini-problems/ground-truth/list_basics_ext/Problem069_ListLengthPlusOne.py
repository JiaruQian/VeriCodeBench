from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_length_plus_one(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == len(a) + 1)
    return len(a) + 1
