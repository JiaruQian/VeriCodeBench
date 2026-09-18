from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def unwrap_or(x: Optional[int], default: int) -> int:
    Ensures(Implies(x is not None, Result() == x))
    Ensures(Implies(x is None, Result() == default))
    if x is None:
        return default
    return x
