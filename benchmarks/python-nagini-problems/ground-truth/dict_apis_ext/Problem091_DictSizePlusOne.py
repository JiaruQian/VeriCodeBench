from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_size_plus_one(d: Dict[int, int]) -> int:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == len(d) + 1)
    return len(d) + 1
