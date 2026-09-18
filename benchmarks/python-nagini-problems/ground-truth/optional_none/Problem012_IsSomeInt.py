from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def is_some_int(x: Optional[int]) -> bool:
    Ensures(Result() == (x is not None))
    return x is not None
