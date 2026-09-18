from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def require_some_plus_one(x: Optional[int]) -> int:
    Requires(x is not None)
    Ensures(Result() == x + 1)
    return x + 1
