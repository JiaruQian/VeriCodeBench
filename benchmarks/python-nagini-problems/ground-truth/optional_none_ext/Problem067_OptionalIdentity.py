from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def optional_identity(x: Optional[int]) -> Optional[int]:
    Ensures(Result() is x)
    return x
