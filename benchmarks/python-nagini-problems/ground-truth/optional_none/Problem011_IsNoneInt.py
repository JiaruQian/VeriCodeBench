from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def is_none_int(x: Optional[int]) -> bool:
    Ensures(Result() == (x is None))
    return x is None
