from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_get_default(d: Dict[int, int], key: int, default: int) -> int:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(Implies(Old(key in d), Result() == Old(d[key])))
    Ensures(Implies(key not in d, Result() == default))
    if key in d:
        return d[key]
    return default
