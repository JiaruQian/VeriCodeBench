from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def clamp_int(x: int, lo: int, hi: int) -> int:
    Requires(lo <= hi)
    Ensures(lo <= Result() and Result() <= hi)
    Ensures(Implies(x < lo, Result() == lo))
    Ensures(Implies(lo <= x and x <= hi, Result() == x))
    Ensures(Implies(x > hi, Result() == hi))
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
