from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_increment_key(d: Dict[int, int], key: int) -> None:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(key in d)
    Ensures(d[key] == Old(d[key]) + 1)
    d[key] = d[key] + 1
