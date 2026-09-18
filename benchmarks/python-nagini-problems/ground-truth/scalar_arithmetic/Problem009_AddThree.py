from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def add_three(x: int, y: int, z: int) -> int:
    Ensures(Result() == x + y + z)
    return x + y + z
