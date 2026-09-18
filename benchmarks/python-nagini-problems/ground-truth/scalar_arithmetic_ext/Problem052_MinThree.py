from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def min_three(x: int, y: int, z: int) -> int:
    Ensures(Result() == x or Result() == y or Result() == z)
    Ensures(Result() <= x and Result() <= y and Result() <= z)
    if x <= y and x <= z:
        return x
    if y <= z:
        return y
    return z
