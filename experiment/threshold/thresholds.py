#!/usr/bin/env python3
"""Compute l-peelability and l-orientability thresholds from Appendix A.2."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class ThresholdResult:
    k: int
    ell: int
    peel_xi: float
    c_peel: float
    peel_residual: float
    orient_xi: float
    c_orient: float
    orient_residual: float


def _validate(k: int, ell: int) -> None:
    if k < 2:
        raise ValueError("k must be at least 2")
    if ell < 1:
        raise ValueError("ell must be positive")


def poisson_pmf(xi: float, value: int) -> float:
    """Return Pr[Poisson(xi) = value]."""
    if xi < 0.0:
        raise ValueError("xi must be non-negative")
    if value < 0:
        return 0.0
    if xi == 0.0:
        return 1.0 if value == 0 else 0.0
    return math.exp(-xi + value * math.log(xi) - math.lgamma(value + 1.0))


def poisson_tail(xi: float, threshold: int) -> float:
    """Return Q(xi, threshold) = Pr[Poisson(xi) >= threshold]."""
    if xi < 0.0:
        raise ValueError("xi must be non-negative")
    if threshold <= 0:
        return 1.0
    if xi == 0.0:
        return 0.0

    if xi >= threshold:
        term = math.exp(-xi)
        lower = term
        for value in range(1, threshold):
            term *= xi / value
            lower += term
        return min(1.0, max(0.0, 1.0 - lower))

    term = poisson_pmf(xi, threshold)
    upper = term
    value = threshold
    for _ in range(100000):
        value += 1
        term *= xi / value
        upper += term
        if term <= max(1e-300, upper * 1e-16):
            break
    else:
        raise RuntimeError("Poisson upper-tail summation did not converge")
    return min(1.0, max(0.0, upper))


def density(k: int, ell: int, xi: float) -> float:
    q_value = poisson_tail(xi, ell)
    if q_value <= 0.0:
        return math.inf
    return xi / (k * q_value ** (k - 1))


def peel_equation(k: int, ell: int, xi: float) -> float:
    """Stationary equation for the peelability threshold."""
    return poisson_tail(xi, ell) - (
        (k - 1) * xi * poisson_pmf(xi, ell - 1)
    )


def orient_equation(k: int, ell: int, xi: float) -> float:
    """Root equation xi Q(xi,l)/Q(xi,l+1) - k*l."""
    q_value = poisson_tail(xi, ell)
    q_next = poisson_tail(xi, ell + 1)
    if q_next <= 0.0:
        return -float(k * ell)
    return xi * q_value / q_next - k * ell


def _positive_root(function: Callable[[float], float], initial_hi: float) -> float:
    lo = 1e-8
    hi = max(1.0, initial_hi)
    f_lo = function(lo)
    if not math.isfinite(f_lo) or f_lo >= 0.0:
        raise RuntimeError(f"invalid lower bracket: f({lo})={f_lo}")

    f_hi = function(hi)
    while not math.isfinite(f_hi) or f_hi <= 0.0:
        hi *= 2.0
        if hi > 1e7:
            raise RuntimeError("could not bracket positive root")
        f_hi = function(hi)

    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = function(mid)
        if f_mid > 0.0:
            hi = mid
        else:
            lo = mid
        if hi - lo <= 1e-14 * max(1.0, mid):
            break
    return (lo + hi) / 2.0


def compute_threshold(k: int, ell: int) -> ThresholdResult:
    _validate(k, ell)
    if (k, ell) == (2, 1):
        return ThresholdResult(
            k=k,
            ell=ell,
            peel_xi=0.0,
            c_peel=0.0,
            peel_residual=0.0,
            orient_xi=0.0,
            c_orient=0.5,
            orient_residual=0.0,
        )

    peel_xi = _positive_root(
        lambda xi: peel_equation(k, ell, xi),
        initial_hi=float(ell + 1),
    )
    orient_xi = _positive_root(
        lambda xi: orient_equation(k, ell, xi),
        initial_hi=float(k * ell + 1),
    )
    return ThresholdResult(
        k=k,
        ell=ell,
        peel_xi=peel_xi,
        c_peel=density(k, ell, peel_xi),
        peel_residual=peel_equation(k, ell, peel_xi),
        orient_xi=orient_xi,
        c_orient=density(k, ell, orient_xi),
        orient_residual=orient_equation(k, ell, orient_xi),
    )


def parse_pairs(value: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"pair must use k:ell syntax: {item}")
        k_text, ell_text = item.split(":", 1)
        pair = (int(k_text), int(ell_text))
        _validate(*pair)
        pairs.append(pair)
    if not pairs:
        raise ValueError("at least one k:ell pair is required")
    return pairs


def appendix_grid() -> list[tuple[int, int]]:
    return [(k, ell) for ell in range(1, 9) for k in range(2, 8)]


def render_table(results: Iterable[ThresholdResult]) -> str:
    lines = [
        " k ell       peel_xi          c_peel      orient_xi        c_orient",
    ]
    for result in results:
        lines.append(
            f"{result.k:2d} {result.ell:3d}  {result.peel_xi:14.10f}  "
            f"{result.c_peel:14.10f}  {result.orient_xi:14.10f}  "
            f"{result.c_orient:14.10f}"
        )
    return "\n".join(lines) + "\n"


def render_json(results: Iterable[ThresholdResult]) -> str:
    return json.dumps(
        [asdict(result) for result in results],
        indent=2,
        sort_keys=True,
    ) + "\n"


def render_csv(results: Iterable[ThresholdResult]) -> str:
    output = io.StringIO()
    fields = list(ThresholdResult.__dataclass_fields__)
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for result in results:
        writer.writerow(asdict(result))
    return output.getvalue()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="2:3,2:6,3:4")
    parser.add_argument(
        "--appendix-grid",
        action="store_true",
        help="Compute all k=2..7, ell=1..8 entries in Appendix Table 3.",
    )
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs = appendix_grid() if args.appendix_grid else parse_pairs(args.pairs)
    results = [compute_threshold(k, ell) for k, ell in pairs]
    renderers = {"table": render_table, "json": render_json, "csv": render_csv}
    text = renderers[args.format](results)
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
