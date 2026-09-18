from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_contains_key(d: Dict[int, int], key: int) -> bool:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == (key in d))
    return key in d
