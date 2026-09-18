from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def between_inclusive(x: int, lo: int, hi: int) -> bool:
    Ensures(Result() == (lo <= x and x <= hi))
    return lo <= x and x <= hi
