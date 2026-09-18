from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def coalesce3(a: Optional[int], b: Optional[int], fallback: int) -> int:
    Ensures(Implies(a is not None, Result() == a))
    Ensures(Implies(a is None and b is not None, Result() == b))
    Ensures(Implies(a is None and b is None, Result() == fallback))
    if a is not None:
        return a
    if b is not None:
        return b
    return fallback
