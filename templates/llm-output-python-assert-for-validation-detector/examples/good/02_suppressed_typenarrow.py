"""Good: assert audited and explicitly suppressed (type-narrowing)."""
from typing import Optional


def consume(value: Optional[int]) -> int:
    if value is None:
        return 0
    assert value is not None  # assert-ok
    return value + 1
