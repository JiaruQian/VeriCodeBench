from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def clamp_non_negative(x: int) -> int:
    Ensures(Result() >= 0)
    Ensures(Implies(x >= 0, Result() == x))
    Ensures(Implies(x < 0, Result() == 0))
    if x < 0:
        return 0
    return x
