"""Float comparison for generated JSON across platforms (docs/deviations.md, D32)."""

from __future__ import annotations

import math


def same_within_float_tolerance(a, b, rel: float = 1e-9, abs_: float = 1e-12) -> bool:
    """Structural equality; floats compared with a relative tolerance, everything else exactly."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_within_float_tolerance(a[k], b[k], rel, abs_) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_within_float_tolerance(x, y, rel, abs_) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return (isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool)
                and math.isclose(a, b, rel_tol=rel, abs_tol=abs_))
    return a == b
