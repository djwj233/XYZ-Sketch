"""Pointwise confidence intervals reported with success probabilities."""

import math
from typing import Tuple


def wilson_interval(
    successes: int,
    trials: int,
    z_score: float = 1.959963984540054,
) -> Tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("Wilson interval requires 0 <= successes <= trials and trials > 0")
    p = successes / trials
    z2 = z_score * z_score
    denominator = 1.0 + z2 / trials
    center = (p + z2 / (2.0 * trials)) / denominator
    radius = (
        z_score
        * math.sqrt(p * (1.0 - p) / trials + z2 / (4.0 * trials * trials))
        / denominator
    )
    low = 0.0 if successes == 0 else max(0.0, center - radius)
    high = 1.0 if successes == trials else min(1.0, center + radius)
    return low, high

