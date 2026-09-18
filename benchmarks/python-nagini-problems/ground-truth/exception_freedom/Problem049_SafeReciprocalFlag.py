from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def safe_reciprocal_flag(x: int) -> bool:
    Ensures(Result() == (x != 0))
    return x != 0
