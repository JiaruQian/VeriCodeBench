from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def optional_positive(x: Optional[int]) -> bool:
    Ensures(Implies(x is None, Result() == False))
    Ensures(Implies(x is not None, Result() == (x > 0)))
    if x is None:
        return False
    return x > 0
