from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_get_existing_plus_one(d: Dict[int, int], key: int) -> int:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == Old(d[key]) + 1)
    return d[key] + 1
