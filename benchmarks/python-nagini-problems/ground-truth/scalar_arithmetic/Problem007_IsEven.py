from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def is_even(x: int) -> bool:
    Ensures(Result() == (x % 2 == 0))
    return x % 2 == 0
