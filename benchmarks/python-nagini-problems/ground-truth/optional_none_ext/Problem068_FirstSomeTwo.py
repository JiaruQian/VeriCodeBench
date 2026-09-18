from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def first_some_two(x: Optional[int], y: Optional[int]) -> Optional[int]:
    Ensures(Implies(x is not None, Result() is x))
    Ensures(Implies(x is None, Result() is y))
    if x is None:
        return y
    return x
