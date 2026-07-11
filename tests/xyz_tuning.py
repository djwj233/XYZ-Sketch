#!/usr/bin/env python3
"""Shared XYZ-Sketch tuning formulas for circular a and coupling z."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Mapping

# Implementation convention: choose_a uses a = C * c_orient / c_peel.
# The supplied July 2026 paper draft prints the reciprocal ratio; resolve that
# manuscript/implementation mismatch before treating a new full run as final.
#
# Threshold constants for random k-uniform hypergraphs with edge density m/n.
# The values below are precomputed from the formulas implemented in this file.
# Missing tuples are computed lazily, so the table is a cache of common paper tuples
# rather than a closed list of supported parameters.
C_ORIENT: dict[tuple[int, int], float] = {
    (2, 3): 2.877462805773105,
    (2, 6): 5.964436239513138,
    (3, 4): 3.997012625648743,
}
C_PEEL: dict[tuple[int, int], float] = {
    (2, 3): 2.5747013734932263,
    (2, 6): 4.937645362421951,
    (3, 4): 2.7467258763600393,
}

DEFAULT_A_CONSTANT = 0.27591534917087435
DEFAULT_Z_CONSTANT = 0.5
DEFAULT_DELTA = 0.1


def _validate_kl(k_value: int, l_value: int) -> tuple[int, int]:
    k_int = int(k_value)
    l_int = int(l_value)
    if k_int < 2:
        raise ValueError(f"k must be at least 2: {k_value}")
    if l_int < 1:
        raise ValueError(f"l must be positive: {l_value}")
    return k_int, l_int


def _poisson_lower_cdf(x_value: float, max_count: int) -> float:
    if max_count < 0:
        return 0.0
    term = 1.0
    total = 1.0
    for index in range(1, max_count + 1):
        term *= x_value / float(index)
        total += term
    return math.exp(-x_value) * total


def _poisson_tail(x_value: float, threshold: int) -> float:
    if threshold <= 0:
        return 1.0
    if x_value <= 0.0:
        return 0.0
    tail = 1.0 - _poisson_lower_cdf(x_value, threshold - 1)
    return min(1.0, max(0.0, tail))


def _density_from_x(k_value: int, l_value: int, x_value: float) -> float:
    q_value = _poisson_tail(x_value, l_value)
    if q_value <= 0.0:
        return float("inf")
    return x_value / (float(k_value) * (q_value ** (k_value - 1)))


def _orient_balance(k_value: int, l_value: int, x_value: float) -> float:
    q_l = _poisson_tail(x_value, l_value)
    q_l_plus = _poisson_tail(x_value, l_value + 1)
    if q_l_plus <= 0.0:
        return -float(l_value)
    return x_value * q_l / (float(k_value) * q_l_plus) - float(l_value)


@lru_cache(maxsize=None)
def computed_c_peel(k_value: int, l_value: int) -> float:
    k_int, l_int = _validate_kl(k_value, l_value)
    # l-peelability fails when the (l+1)-core appears. The threshold is
    # min_x x / (k * Pr[Poisson(x) >= l]^(k-1)).
    lo = 1e-10
    hi = max(10.0, 4.0 * float(l_int + 1))
    for _ in range(240):
        left = lo + (hi - lo) / 3.0
        right = hi - (hi - lo) / 3.0
        if _density_from_x(k_int, l_int, left) < _density_from_x(k_int, l_int, right):
            hi = right
        else:
            lo = left
    return _density_from_x(k_int, l_int, (lo + hi) / 2.0)


@lru_cache(maxsize=None)
def computed_c_orient(k_value: int, l_value: int) -> float:
    k_int, l_int = _validate_kl(k_value, l_value)
    # l-orientability fails when the (l+1)-core has edge/vertex ratio l.
    # With x as the core branching parameter, solve
    # x Pr[Poisson(x)>=l] / (k Pr[Poisson(x)>=l+1]) = l.
    lo = 1e-10
    hi = max(1.0, float(k_int * l_int + 1))
    while _orient_balance(k_int, l_int, hi) <= 0.0:
        hi *= 2.0
        if hi > 1e6:
            raise ValueError(f"failed to bracket c_orient for k={k_int}, l={l_int}")
    for _ in range(240):
        mid = (lo + hi) / 2.0
        if _orient_balance(k_int, l_int, mid) > 0.0:
            hi = mid
        else:
            lo = mid
    return _density_from_x(k_int, l_int, (lo + hi) / 2.0)


def c_orient(k_value: int, l_value: int, overrides: Mapping[tuple[int, int], float] | None = None) -> float:
    k_int, l_int = _validate_kl(k_value, l_value)
    table = overrides if overrides is not None else C_ORIENT
    value = table.get((k_int, l_int))
    if value is None:
        value = computed_c_orient(k_int, l_int)
    return float(value)


def c_peel(k_value: int, l_value: int, overrides: Mapping[tuple[int, int], float] | None = None) -> float:
    k_int, l_int = _validate_kl(k_value, l_value)
    table = overrides if overrides is not None else C_PEEL
    value = table.get((k_int, l_int))
    if value is None:
        value = computed_c_peel(k_int, l_int)
    value = float(value)
    if value <= 0.0:
        raise ValueError(f"c_peel must be positive for k={k_value}, l={l_value}")
    return value


def choose_a(
    k_value: int,
    l_value: int,
    *,
    a_constant: float = DEFAULT_A_CONSTANT,
    c_orient_value: float | None = None,
    c_peel_value: float | None = None,
) -> float:
    orient = c_orient_value if c_orient_value is not None else c_orient(k_value, l_value)
    peel = c_peel_value if c_peel_value is not None else c_peel(k_value, l_value)
    if peel <= 0.0:
        raise ValueError("c_peel must be positive")
    a_value = float(a_constant) * float(orient) / float(peel)
    if not (0.0 <= a_value < 1.0):
        raise ValueError(
            f"computed circular a must be in [0, 1): a={a_value} "
            f"for k={k_value}, l={l_value}, C={a_constant}, c_orient={orient}, c_peel={peel}"
        )
    return a_value


def choose_z(
    k_value: int,
    l_value: int,
    m_value: int,
    *,
    a_value: float,
    z_constant: float = DEFAULT_Z_CONSTANT,
    delta: float = DEFAULT_DELTA,
) -> int:
    if not (0.0 <= float(a_value) < 1.0):
        raise ValueError(f"a_value must be in [0, 1): {a_value}")
    if not (0.0 < float(delta) < 1.0):
        raise ValueError(f"delta must be in (0, 1): {delta}")
    if float(z_constant) < 0.0:
        raise ValueError(f"z_constant must be non-negative: {z_constant}")
    denominator = math.log(1.0 / float(delta))
    z_float = float(z_constant) * ((1.0 - float(a_value)) ** (2.0 / 3.0)) * ((int(m_value) / denominator) ** (1.0 / 3.0))
    return max(0, round(z_float))


def add_tuning_arguments(parser) -> None:
    parser.add_argument("--a-constant", type=float, default=DEFAULT_A_CONSTANT, help="C in a_{k,l}=C*c_orient/c_peel.")
    parser.add_argument("--z-constant", type=float, default=DEFAULT_Z_CONSTANT, help="D in the z_{k,l} formula.")
    parser.add_argument("--delta", type=float, default=DEFAULT_DELTA, help="delta in z_{k,l}=D(1-a)^(2/3)(M/log(1/delta))^(1/3).")
    parser.add_argument("--c-orient", type=float, default=None, help="Override c_orient for every scanned (k,l).")
    parser.add_argument("--c-peel", type=float, default=None, help="Override c_peel for every scanned (k,l).")


def a_from_args(k_value: int, l_value: int, args) -> float:
    return choose_a(
        k_value,
        l_value,
        a_constant=args.a_constant,
        c_orient_value=args.c_orient,
        c_peel_value=args.c_peel,
    )


def z_from_args(k_value: int, l_value: int, m_value: int, a_value: float, args) -> int:
    return choose_z(
        k_value,
        l_value,
        m_value,
        a_value=a_value,
        z_constant=args.z_constant,
        delta=args.delta,
    )
