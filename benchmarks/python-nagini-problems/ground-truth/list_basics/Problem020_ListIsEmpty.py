from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def list_is_empty(a: List[int]) -> bool:
    Requires(Acc(list_pred(a)))
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == (len(a) == 0))
    return len(a) == 0
