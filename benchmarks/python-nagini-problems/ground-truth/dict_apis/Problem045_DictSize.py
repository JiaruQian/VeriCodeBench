from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_size(d: Dict[int, int]) -> int:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == len(d))
    return len(d)
