#!/usr/bin/env python3
"""Small statistical helpers for benchmark scripts."""

from __future__ import annotations

import math
from typing import Any


SUPPORTED_Z = {
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def normal_z(confidence: float) -> float:
    for supported, z_value in SUPPORTED_Z.items():
        if abs(float(confidence) - supported) < 1e-12:
            return z_value
    supported_values = ", ".join(str(value) for value in sorted(SUPPORTED_Z))
    raise ValueError(f"unsupported confidence level {confidence}; supported values: {supported_values}")


def wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("successes/trials must satisfy 0 <= successes <= trials")
    if trials == 0:
        return 0.0, 1.0

    z_value = normal_z(confidence)
    p_hat = successes / float(trials)
    z2 = z_value * z_value
    denom = 1.0 + z2 / trials
    center = (p_hat + z2 / (2.0 * trials)) / denom
    half = z_value * math.sqrt((p_hat * (1.0 - p_hat) / trials) + z2 / (4.0 * trials * trials)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def add_binomial_ci(row: dict[str, Any], confidence: float = 0.95, method: str = "wilson") -> dict[str, Any]:
    if method != "wilson":
        raise ValueError(f"unsupported CI method: {method}")
    updated = dict(row)
    successes = int(updated.get("successes", 0))
    trials = int(updated.get("trials", 0))
    ci_low, ci_high = wilson_interval(successes, trials, confidence)
    updated["ci_method"] = method
    updated["ci_confidence"] = confidence
    updated["ci_low"] = ci_low
    updated["ci_high"] = ci_high
    return updated
