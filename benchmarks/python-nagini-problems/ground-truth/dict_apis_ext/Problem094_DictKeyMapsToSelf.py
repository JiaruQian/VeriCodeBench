from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def dict_key_maps_to_self(d: Dict[int, int], key: int) -> None:
    Requires(Acc(dict_pred(d)))
    Ensures(Acc(dict_pred(d)))
    Ensures(key in d)
    Ensures(d[key] == key)
    d[key] = key
