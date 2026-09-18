from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def default_if_zero(x: int, fallback: int) -> int:
    Ensures(Implies(x == 0, Result() == fallback))
    Ensures(Implies(x != 0, Result() == x))
    if x == 0:
        return fallback
    return x
