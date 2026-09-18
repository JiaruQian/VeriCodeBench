from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_length(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == len(a))
    return len(a)
