import hashlib
import math
import random
import statistics
from typing import Iterable, Sequence, Tuple


def wilson(successes: int, trials: int) -> Tuple[float, float]:
    if trials <= 0 or not 0 <= successes <= trials:
        raise ValueError("invalid binomial counts")
    z = 1.959963984540054
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def percentile_bootstrap(
    values: Sequence[float],
    *,
    seed_material: str,
    repetitions: int = 10_000,
    estimator: str = "median",
) -> Tuple[float, float]:
    if not values:
        raise ValueError("bootstrap requires values")
    if estimator not in {"mean", "median"}:
        raise ValueError("unsupported bootstrap estimator")
    seed = int.from_bytes(hashlib.sha256(seed_material.encode("ascii")).digest()[:8], "big")
    generator = random.Random(seed)
    estimates = []
    for _ in range(repetitions):
        sample = [values[generator.randrange(len(values))] for _ in values]
        estimates.append(
            statistics.fmean(sample) if estimator == "mean" else statistics.median(sample)
        )
    estimates.sort()
    low = estimates[math.floor(0.025 * repetitions)]
    high = estimates[min(repetitions - 1, math.ceil(0.975 * repetitions) - 1)]
    return low, high
