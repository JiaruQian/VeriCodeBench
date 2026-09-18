from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def abs_int(x: int) -> int:
    Ensures(Result() >= 0)
    Ensures(Implies(x >= 0, Result() == x))
    Ensures(Implies(x < 0, Result() == -x))
    if x >= 0:
        return x
    return -x
