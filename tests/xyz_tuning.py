#!/usr/bin/env python3
"""Shared XYZ-v2 tuning formulas for circular a and coupling z."""

from __future__ import annotations

import math
from typing import Mapping

# Fill these tables with theory/empirical constants when available.
# Missing tuples default to 1.0 so the ratio is neutral.
C_ORIENT: dict[tuple[int, int], float] = {}
C_PEEL: dict[tuple[int, int], float] = {}

DEFAULT_A_CONSTANT = 0.0
DEFAULT_Z_CONSTANT = 1.0
DEFAULT_DELTA = math.exp(-27.0)


def c_orient(k_value: int, l_value: int, overrides: Mapping[tuple[int, int], float] | None = None) -> float:
    table = overrides if overrides is not None else C_ORIENT
    return float(table.get((int(k_value), int(l_value)), 1.0))


def c_peel(k_value: int, l_value: int, overrides: Mapping[tuple[int, int], float] | None = None) -> float:
    table = overrides if overrides is not None else C_PEEL
    value = float(table.get((int(k_value), int(l_value)), 1.0))
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
