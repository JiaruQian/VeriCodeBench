from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def increment_optional(x: Optional[int]) -> Optional[int]:
    Ensures(Implies(x is None, Result() is None))
    Ensures(Implies(x is not None, Result() is not None))
    Ensures(Implies(x is not None, Result() == x + 1))
    if x is None:
        return None
    return x + 1
