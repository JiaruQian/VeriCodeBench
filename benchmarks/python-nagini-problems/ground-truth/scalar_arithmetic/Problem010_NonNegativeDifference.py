from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def nonnegative_difference(x: int, y: int) -> int:
    Requires(x >= y)
    Ensures(Result() == x - y)
    Ensures(Result() >= 0)
    return x - y
