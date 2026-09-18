from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_dict_key(d: Dict[int, int], key: int) -> int:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == key)
    return key
