from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def subtract_zero(x: int) -> int:
    Ensures(Result() == x)
    return x - 0
