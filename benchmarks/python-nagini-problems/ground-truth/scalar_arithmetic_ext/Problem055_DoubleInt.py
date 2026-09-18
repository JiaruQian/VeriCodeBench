from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def double_int(x: int) -> int:
    Ensures(Result() == x + x)
    return x + x
