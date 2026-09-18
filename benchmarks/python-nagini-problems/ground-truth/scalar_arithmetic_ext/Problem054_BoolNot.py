from typing import Dict, List, Optional
from nagini_contracts.contracts import *


def bool_not(b: bool) -> bool:
    Ensures(Result() == (not b))
    return not b
