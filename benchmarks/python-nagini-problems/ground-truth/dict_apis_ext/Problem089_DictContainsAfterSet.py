from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_contains_after_set(d: Dict[int, int], key: int, value: int) -> None:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(key in d)
    Ensures(d[key] == value)
    d[key] = value
