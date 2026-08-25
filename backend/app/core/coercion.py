from __future__ import annotations


def positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(value if value not in (None, "") else default))
    except (TypeError, ValueError):
        return default


def non_negative_float(value: object, default: float) -> float:
    try:
        return max(0.0, float(value if value not in (None, "") else default))
    except (TypeError, ValueError):
        return default
