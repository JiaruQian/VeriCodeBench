from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def require_existing_key(d: Dict[int, int], key: int) -> int:
    Requires(Acc(dict_pred(d)))
    Requires(key in d)
    Ensures(Acc(dict_pred(d)))
    Ensures(Result() == Old(d[key]))
    return d[key]
