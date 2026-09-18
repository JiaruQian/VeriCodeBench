from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_update_existing(d: Dict[int, int], key: int, value: int) -> None:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(key in d)
    Ensures(d[key] == value)
    Ensures(len(d) == Old(len(d)))
    d[key] = value
