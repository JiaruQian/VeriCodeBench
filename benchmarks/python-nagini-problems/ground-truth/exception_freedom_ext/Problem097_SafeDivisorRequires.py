from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_divisor_requires(x: int, y: int) -> int:
    Requires(y != 0)
    Ensures(Result() == x // y)
    return x // y
