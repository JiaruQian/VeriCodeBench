from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_ensure_key(d: Dict[int, int], key: int, fallback: int) -> None:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(key in d)
    Ensures(Implies(Old(key in d), d[key] == Old(d[key])))
    Ensures(Implies(not Old(key in d), d[key] == fallback))
    if key not in d:
        d[key] = fallback
