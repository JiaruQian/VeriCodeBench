from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def optional_or_default(x: Optional[int], default: int) -> int:
    Ensures(Implies(x is None, Result() == default))
    Ensures(Implies(x is not None, Result() == x))
    if x is None:
        return default
    return x
