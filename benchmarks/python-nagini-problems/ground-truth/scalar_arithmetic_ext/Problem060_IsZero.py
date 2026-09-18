from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def is_zero(x: int) -> bool:
    Ensures(Result() == (x == 0))
    return x == 0
