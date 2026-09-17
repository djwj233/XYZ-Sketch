import math
from typing import Tuple


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    if not 0 <= successes <= trials or trials <= 0:
        raise ValueError("invalid binomial counts")
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    low = max(0.0, center - radius)
    high = min(1.0, center + radius)
    if successes == 0:
        low = 0.0
    if successes == trials:
        high = 1.0
    return low, high
