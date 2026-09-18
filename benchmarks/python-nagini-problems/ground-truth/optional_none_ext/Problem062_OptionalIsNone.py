from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def optional_is_none(x: Optional[int]) -> bool:
    Ensures(Result() == (x is None))
    return x is None
