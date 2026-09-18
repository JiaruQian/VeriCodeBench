from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def require_some(x: Optional[int]) -> int:
    Requires(x is not None)
    Ensures(Result() == x)
    return x
