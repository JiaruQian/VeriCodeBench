from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def positive_or_none(x: int) -> Optional[int]:
    Ensures(Implies(x > 0, Result() is not None))
    Ensures(Implies(x > 0, Result() == x))
    Ensures(Implies(x <= 0, Result() is None))
    if x > 0:
        return x
    return None
