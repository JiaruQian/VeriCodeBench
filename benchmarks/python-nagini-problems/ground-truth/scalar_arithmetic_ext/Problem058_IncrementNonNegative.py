from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def increment_non_negative(x: int) -> int:
    Requires(x >= 0)
    Ensures(Result() == x + 1)
    Ensures(Result() > 0)
    return x + 1
