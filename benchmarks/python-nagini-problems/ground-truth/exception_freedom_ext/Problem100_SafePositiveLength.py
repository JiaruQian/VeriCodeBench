from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_positive_length(a: List[int]) -> int:
    Requires(Acc(list_pred(a)))
    Requires(len(a) > 0)
    Ensures(Acc(list_pred(a)))
    Ensures(Result() == len(a))
    Ensures(Result() > 0)
    return len(a)
