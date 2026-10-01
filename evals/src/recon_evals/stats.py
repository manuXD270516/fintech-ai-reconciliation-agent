"""Small, dependency-free statistics with explicit denominators."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable


def wilson(successes: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson interval; None when the denominator is zero (reported as N/A)."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def f1(tp: int, fp: int, fn: int) -> float | None:
    if tp + fp + fn == 0:
        return None
    return round(2 * tp / (2 * tp + fp + fn), 4)


def macro(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 4) if present else None


SPLITS = (("dev", 60), ("calibration", 80), ("holdout", 100))


def split_of(family: str) -> str:
    """Deterministic 60/20/20 split by family: rows of one family never cross splits."""
    bucket = int(hashlib.sha256(family.encode()).hexdigest(), 16) % 100
    return next(name for name, bound in SPLITS if bucket < bound)
