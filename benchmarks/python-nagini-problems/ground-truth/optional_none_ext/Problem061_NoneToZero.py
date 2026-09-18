from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def none_to_zero(x: Optional[int]) -> int:
    Ensures(Implies(x is None, Result() == 0))
    Ensures(Implies(x is not None, Result() == x))
    if x is None:
        return 0
    return x
