from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def min_int(x: int, y: int) -> int:
    Ensures(Result() == x or Result() == y)
    Ensures(Result() <= x and Result() <= y)
    if x <= y:
        return x
    return y
