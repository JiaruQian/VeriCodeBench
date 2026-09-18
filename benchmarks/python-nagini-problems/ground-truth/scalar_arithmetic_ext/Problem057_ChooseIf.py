from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def choose_if(flag: bool, x: int, y: int) -> int:
    Ensures(Implies(flag, Result() == x))
    Ensures(Implies(not flag, Result() == y))
    if flag:
        return x
    return y
