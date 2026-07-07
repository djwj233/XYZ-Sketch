#!/usr/bin/env python3
"""Shared helpers for benchmark JSON records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "benchmark.v1"

DEFAULT_TIMING_FIELDS = (
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
)

IMPLEMENTATION_BY_ALGORITHM = {
    "xyz_v1": "local/XYZ-v1",
    "xyz_v2": "local/XYZ-v2",
    "iblt": "local/IBLT",
    "iblt_cpp": "external/IBLT_Cplusplus",
    "cpisync": "external/cpisync",
    "minisketch": "external/minisketch",
    "negentropy": "external/negentropy",
    "riblt": "external/riblt",
}


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _float_or_none(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if _is_blank(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_benchmark_row(
    row: dict[str, Any],
    *,
    experiment: str,
    record_type: str,
    algorithm: str | None = None,
    variant: str | None = None,
    implementation: str | None = None,
    status: str | None = None,
    dataset_mode: str | None = None,
) -> dict[str, Any]:
    """Return a benchmark.v1 row while preserving algorithm-specific fields."""
    normalized = dict(row)

    algo = algorithm or normalized.get("algorithm") or "unknown"
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["record_type"] = record_type
    normalized["experiment"] = experiment
    normalized["algorithm"] = str(algo)
    normalized["variant"] = str(
        variant
        or normalized.get("variant")
        or normalized.get("mode")
        or normalized.get("phase")
        or "default"
    )
    normalized["implementation"] = str(
        implementation
        or normalized.get("implementation")
        or IMPLEMENTATION_BY_ALGORITHM.get(str(algo), "unknown")
    )
    normalized["status"] = str(status or normalized.get("status") or "ok")
    normalized["dataset_mode"] = str(dataset_mode or normalized.get("dataset_mode") or "internal_generator")

    if "M" not in normalized and not _is_blank(normalized.get("m")):
        normalized["M"] = normalized["m"]
    if "m" not in normalized and not _is_blank(normalized.get("M")):
        normalized["m"] = normalized["M"]

    for key in ("d", "ca", "cb", "seed", "trials", "successes"):
        if _is_blank(normalized.get(key)):
            normalized[key] = 0
    for key in DEFAULT_TIMING_FIELDS:
        if _is_blank(normalized.get(key)):
            normalized[key] = 0.0

    trials = _int_or_none(normalized.get("trials")) or 0
    successes = _int_or_none(normalized.get("successes")) or 0
    if _is_blank(normalized.get("success_rate")):
        normalized["success_rate"] = successes / float(trials) if trials > 0 else 0.0

    if _is_blank(normalized.get("bits")):
        normalized["bits"] = 0.0

    d_value = _float_or_none(normalized.get("d")) or 0.0
    bits = _float_or_none(normalized.get("bits"))
    if bits is None:
        bits = 0.0

    if _is_blank(normalized.get("bits_per_difference")):
        normalized["bits_per_difference"] = bits / d_value if d_value > 0 else 0.0

    if _is_blank(normalized.get("bit_C_over_d")):
        c_over_d = _float_or_none(normalized.get("C_over_d"))
        normalized["bit_C_over_d"] = c_over_d if c_over_d is not None else (bits / (32.0 * d_value) if d_value > 0 else 0.0)

    if _is_blank(normalized.get("field_C_over_d")):
        m_value = _float_or_none(normalized.get("M"))
        l_value = _float_or_none(normalized.get("l"))
        if m_value is not None and l_value is not None and d_value > 0:
            normalized["field_C_over_d"] = m_value * l_value / d_value

    return normalized


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
