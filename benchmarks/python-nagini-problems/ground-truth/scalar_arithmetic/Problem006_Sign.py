from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def sign(x: int) -> int:
    Ensures(Result() == -1 or Result() == 0 or Result() == 1)
    Ensures(Implies(x < 0, Result() == -1))
    Ensures(Implies(x == 0, Result() == 0))
    Ensures(Implies(x > 0, Result() == 1))
    if x < 0:
        return -1
    if x > 0:
        return 1
    return 0
