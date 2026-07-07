#!/usr/bin/env python3
"""Verify benchmark JSONL files against the local benchmark.v1 schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from json_schema import SCHEMA_VERSION


COMMON_REQUIRED = [
    "schema_version",
    "record_type",
    "experiment",
    "algorithm",
    "variant",
    "implementation",
    "status",
]

BENCHMARK_REQUIRED = [
    "d",
    "ca",
    "cb",
    "seed",
    "dataset_mode",
    "trials",
    "successes",
    "success_rate",
    "bits",
    "bits_per_difference",
    "bit_C_over_d",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
]

KNOWN_RECORD_TYPES = {
    "trial",
    "aggregate",
    "probe",
    "threshold",
    "unavailable",
    "error",
}


def _float(value: Any) -> float | None:
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value == "" or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def collect_paths(paths: list[Path], recursive: bool) -> list[Path]:
    collected: list[Path] = []
    for path in paths:
        if path.is_dir():
            pattern = "**/*.jsonl" if recursive else "*.jsonl"
            collected.extend(sorted(path.glob(pattern)))
            if recursive:
                collected.extend(sorted(path.glob("**/summary.json")))
        else:
            collected.append(path)
    return collected


def verify_row(row: dict[str, Any], *, strict: bool, allow_legacy: bool) -> list[str]:
    errors: list[str] = []

    if allow_legacy and "schema_version" not in row:
        return errors

    for key in COMMON_REQUIRED:
        if key not in row or row[key] == "":
            errors.append(f"missing {key}")

    if row.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")

    if row.get("record_type") not in KNOWN_RECORD_TYPES:
        errors.append(f"unknown record_type {row.get('record_type')!r}")

    required = COMMON_REQUIRED + (BENCHMARK_REQUIRED if strict else [])
    for key in required:
        if key not in row or row[key] == "":
            errors.append(f"missing {key}")

    trials = _int(row.get("trials"))
    successes = _int(row.get("successes"))
    success_rate = _float(row.get("success_rate"))
    if trials is not None and trials < 0:
        errors.append("trials must be non-negative")
    if successes is not None and successes < 0:
        errors.append("successes must be non-negative")
    if trials is not None and successes is not None and successes > trials:
        errors.append("successes must not exceed trials")
    if success_rate is not None and not (0.0 <= success_rate <= 1.0):
        errors.append("success_rate must be in [0, 1]")

    d_value = _float(row.get("d"))
    bits = _float(row.get("bits"))
    bits_per_difference = _float(row.get("bits_per_difference"))
    bit_c_over_d = _float(row.get("bit_C_over_d"))
    if bits is not None and bits < 0:
        errors.append("bits must be non-negative")
    if d_value is not None and d_value > 0 and bits is not None:
        expected_bits_per_difference = bits / d_value
        if bits_per_difference is not None and abs(bits_per_difference - expected_bits_per_difference) > 1e-6:
            errors.append("bits_per_difference does not match bits/d")
        expected_bit_c_over_d = bits / (32.0 * d_value)
        if bit_c_over_d is not None and abs(bit_c_over_d - expected_bit_c_over_d) > 1e-6:
            errors.append("bit_C_over_d does not match bits/(32*d)")

    for key in ("encode_avg_s", "decode_avg_s", "encode_median_s", "decode_median_s"):
        value = _float(row.get(key))
        if value is not None and value < 0:
            errors.append(f"{key} must be non-negative")

    ci_low = _float(row.get("ci_low"))
    ci_high = _float(row.get("ci_high"))
    ci_confidence = _float(row.get("ci_confidence"))
    if ci_confidence is not None and not (0.0 < ci_confidence < 1.0):
        errors.append("ci_confidence must be in (0, 1)")
    if ci_low is not None and not (0.0 <= ci_low <= 1.0):
        errors.append("ci_low must be in [0, 1]")
    if ci_high is not None and not (0.0 <= ci_high <= 1.0):
        errors.append("ci_high must be in [0, 1]")
    if ci_low is not None and ci_high is not None and ci_low > ci_high:
        errors.append("ci_low must not exceed ci_high")

    return errors


def verify_file(path: Path, *, strict: bool, allow_legacy: bool, max_errors: int) -> tuple[int, int]:
    checked = 0
    failures = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            checked += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                failures += 1
                print(f"{path}:{line_number}: invalid JSON: {exc}", file=sys.stderr)
                if failures >= max_errors:
                    return checked, failures
                continue
            errors = verify_row(row, strict=strict, allow_legacy=allow_legacy)
            if errors:
                failures += 1
                print(f"{path}:{line_number}: " + "; ".join(errors), file=sys.stderr)
                if failures >= max_errors:
                    return checked, failures
    return checked, failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify benchmark JSONL files.")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--strict", action="store_true", help="Require all benchmark metric fields.")
    parser.add_argument("--allow-legacy", action="store_true", help="Accept rows without schema_version.")
    parser.add_argument("--recursive", action="store_true", help="Search directories recursively.")
    parser.add_argument("--max-errors", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = collect_paths(args.paths, args.recursive)
    if not paths:
        raise SystemExit("no JSONL files found")

    total_checked = 0
    total_failures = 0
    for path in paths:
        checked, failures = verify_file(
            path,
            strict=args.strict,
            allow_legacy=args.allow_legacy,
            max_errors=max(1, args.max_errors - total_failures),
        )
        total_checked += checked
        total_failures += failures
        if total_failures >= args.max_errors:
            break

    print(f"checked={total_checked} failures={total_failures}")
    if total_failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
