from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def optional_negate(x: Optional[int]) -> Optional[int]:
    Ensures(Implies(x is None, Result() is None))
    Ensures(Implies(x is not None, Result() is not None))
    Ensures(Implies(x is not None, Result() == -x))
    if x is None:
        return None
    return -x
