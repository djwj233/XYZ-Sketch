#!/usr/bin/env python3
"""Scan XYZ-v2 sharp-threshold curves for uniform and spatial modes."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from dataset_generator import choose_set_sizes
from json_schema import normalize_benchmark_row
from statistics import add_binomial_ci, normal_z
from xyz_tuning import add_tuning_arguments, a_from_args, z_from_args


RAW_FIELDS = [
    "schema_version",
    "record_type",
    "experiment",
    "algorithm",
    "variant",
    "implementation",
    "status",
    "scan_id",
    "d",
    "l",
    "k",
    "mode",
    "M",
    "z",
    "M0",
    "M_offset",
    "C_over_d_offset",
    "grid_index",
    "grid_size",
    "threshold_source",
    "ca",
    "cb",
    "seed",
    "dedup_hashes",
    "circular_a",
    "dataset_mode",
    "trials",
    "successes",
    "success_rate",
    "ci_low",
    "ci_high",
    "ci_method",
    "ci_confidence",
    "bits",
    "bits_per_difference",
    "bit_C_over_d",
    "R_w30",
    "field_C_over_d",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
]

SUMMARY_FIELDS = [
    "schema_version",
    "record_type",
    "experiment",
    "algorithm",
    "variant",
    "implementation",
    "status",
    "scan_id",
    "d",
    "l",
    "k",
    "mode",
    "M0",
    "threshold_source",
    "grid_size",
    "M_min",
    "M_max",
    "point_M_50",
    "point_C_over_d_50",
    "point_M_95",
    "point_C_over_d_95",
    "point_M_90",
    "point_R_w30_90",
    "ci_low_M_95",
    "ci_low_C_over_d_95",
    "ci_low_M_90",
    "ci_low_R_w30_90",
    "transition_M_min",
    "transition_M_max",
    "transition_width_M",
    "transition_C_over_d_min",
    "transition_C_over_d_max",
    "transition_width_C_over_d",
    "max_slope",
    "ca",
    "cb",
    "seed",
    "dedup_hashes",
    "circular_a",
    "dataset_mode",
    "trials",
    "successes",
    "success_rate",
    "ci_low",
    "ci_high",
    "ci_method",
    "ci_confidence",
    "bits",
    "bits_per_difference",
    "bit_C_over_d",
    "R_w30",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def exe_suffix() -> str:
    return ".exe" if sys.platform.startswith("win") else ""


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "xyz_sharp_threshold"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "raw_jsonl": base / "raw.jsonl",
        "raw_csv": base / "raw.csv",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "run_config": base / "run_config.json",
        "errors": base / "errors.log",
    }


def build_benchmark(root: Path, build_dir: Path, skip_build: bool) -> Path:
    binary = build_dir / f"xyz_v2_bench{exe_suffix()}"
    if skip_build:
        if not binary.exists():
            raise FileNotFoundError(f"benchmark binary not found: {binary}")
        return binary
    source = root / "tests" / "benchmarks" / "xyz_v2_bench.cpp"
    subprocess.run(["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)], cwd=root, check=True)
    return binary


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def parse_bool_list(value: str) -> list[bool]:
    return [parse_bool(part) for part in value.split(",") if part.strip()]


def r_w30_from_bits(bits: Any, d_value: Any) -> float | str:
    try:
        d_float = float(d_value)
        if d_float <= 0:
            return ""
        return float(bits) / (30.0 * d_float)
    except (TypeError, ValueError):
        return ""


def dedup_suffix(dedup_hashes: bool, include: bool) -> str:
    return f"_dedup{1 if dedup_hashes else 0}" if include else ""


def variant_name(config: dict[str, Any]) -> str:
    variant = str(config["mode"])
    if config.get("dedup_variant_suffix"):
        variant += f",dedup={str(bool(config.get('dedup_hashes', False))).lower()}"
    return variant


def choose_z(mode: str, m_value: int, fixed_z: int | None, config: dict[str, Any], args: argparse.Namespace) -> int:
    if fixed_z is not None:
        return fixed_z
    if mode == "random":
        return 0
    return z_from_args(int(config["k"]), int(config["l"]), m_value, float(config.get("circular_a", 0.0)), args)


def initial_factor(mode: str, k_value: int) -> float:
    if mode == "circular":
        return 1.5
    if mode == "random":
        return 2.5
    if mode == "naive":
        return 2.5 if k_value <= 3 else 3.5
    return 2.0


def lower_bound_m(config: dict[str, Any]) -> int:
    return max(int(config["k"]), math.ceil(int(config["d"]) / int(config["l"])), 1)


def initial_m0(config: dict[str, Any]) -> int:
    return max(
        lower_bound_m(config),
        math.ceil(initial_factor(str(config["mode"]), int(config["k"])) * int(config["d"]) / int(config["l"])),
    )


def max_m(config: dict[str, Any], max_c_over_d: float) -> int:
    return max(lower_bound_m(config), math.ceil(max_c_over_d * int(config["d"]) / int(config["l"])))


def c_over_d(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value in (None, ""):
        return ""
    return int(m_value) * int(config["l"]) / int(config["d"])


def log_progress(args: argparse.Namespace, message: str) -> None:
    if not getattr(args, "quiet", False):
        print(message, flush=True)


def r_w30_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value in (None, ""):
        return ""
    cell_bits = (math.floor(math.log2(2 * int(config["l"]) + 1)) + 1) + 32 * int(config["l"])
    return int(m_value) * cell_bits / (30.0 * int(config["d"]))


def make_configs(args: argparse.Namespace) -> list[dict[str, Any]]:
    d_values = parse_int_list(args.d_values)
    l_values = parse_int_list(args.l_values)
    k_values = parse_int_list(args.k_values)
    modes = parse_str_list(args.modes)
    valid_modes = {"random", "spatial", "circular", "naive"}
    dedup_values = parse_bool_list(args.dedup_hashes)
    include_dedup_suffix = len(dedup_values) > 1 or any(dedup_values)
    configs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                for mode_index, mode in enumerate(modes):
                    if mode not in valid_modes:
                        raise SystemExit(f"unknown mode: {mode}")
                    for dedup_hashes in dedup_values:
                        seed = (
                            args.base_seed
                            + 1_000_000 * d_index
                            + 10_000 * l_index
                            + 100 * k_index
                            + mode_index
                        )
                        configs.append(
                            {
                                "scan_id": f"d{d_value}_l{l_value}_k{k_value}_{mode}{dedup_suffix(dedup_hashes, include_dedup_suffix)}",
                                "d": d_value,
                                "l": l_value,
                                "k": k_value,
                                "mode": mode,
                                "dedup_hashes": dedup_hashes,
                                "dedup_variant_suffix": include_dedup_suffix,
                                "circular_a": args.circular_a if args.circular_a is not None else a_from_args(k_value, l_value, args),
                                "seed": seed,
                                "ca": ca,
                                "cb": cb,
                            }
                        )
    return configs


def load_threshold_summary(path: Path | None) -> dict[tuple[int, int, int, str], int]:
    if path is None:
        return {}
    centers: dict[tuple[int, int, int, str], int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            mode = str(row.get("mode", row.get("variant", "")))
            if not mode:
                continue
            value = row.get("point_best_M") or row.get("best_M") or row.get("ci_low_best_M")
            if value in (None, ""):
                continue
            key = (int(row["d"]), int(row["l"]), int(row["k"]), mode)
            centers[key] = int(value)
    return centers


def m_grid(config: dict[str, Any], m0: int, args: argparse.Namespace) -> list[int]:
    radius = max(args.min_window, math.ceil(args.window_fraction * m0))
    lo = max(lower_bound_m(config), m0 - radius)
    hi = m0 + radius
    if args.step is not None:
        return list(range(lo, hi + 1, max(1, args.step)))
    if args.points <= 1 or hi <= lo:
        return [m0]
    values = {
        int(round(lo + (hi - lo) * index / float(args.points - 1)))
        for index in range(args.points)
    }
    values.add(m0)
    return sorted(value for value in values if value >= lower_bound_m(config))


def command_for(binary: Path, config: dict[str, Any], m_value: int, z_value: int, trials: int) -> list[str]:
    return [
        str(binary),
        "--d",
        str(config["d"]),
        "--l",
        str(config["l"]),
        "--k",
        str(config["k"]),
        "--m",
        str(m_value),
        "--z",
        str(z_value),
        "--trials",
        str(trials),
        "--seed",
        str(config["seed"]),
        "--mode",
        str(config["mode"]),
        "--circular-a",
        f"{float(config.get('circular_a', 1.0 / 3.0)):.12g}",
        "--ca",
        str(config["ca"]),
        "--cb",
        str(config["cb"]),
        "--dedup-hashes",
        str(bool(config.get("dedup_hashes", False))).lower(),
        "--format",
        "jsonl",
    ]


def append_error(path: Path, config: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("CONFIG " + json.dumps(config, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def run_point(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    trials: int,
    args: argparse.Namespace,
    errors_path: Path,
    *,
    scan_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    z_value = choose_z(str(config["mode"]), m_value, args.fixed_z, config, args)
    command = command_for(binary, config, m_value, z_value, trials)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        append_error(errors_path, config, command, f"OSERROR {exc}")
        return None
    if completed.returncode != 0:
        append_error(
            errors_path,
            config,
            command,
            f"RETURNCODE {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        )
        return None
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        append_error(errors_path, config, command, f"PARSE got {len(lines)} lines\n{completed.stdout}")
        return None
    try:
        row = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, config, command, f"JSONERROR {exc}\n{completed.stdout}")
        return None
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    row["R_w30"] = r_w30_from_bits(row.get("bits", 0), config["d"])
    row["circular_a"] = float(config.get("circular_a", 1.0 / 3.0))
    if scan_metadata:
        row.update(scan_metadata)
    row.setdefault("scan_id", config["scan_id"])
    row.setdefault("threshold_source", "internal")
    return normalize_benchmark_row(
        row,
        experiment="xyz_sharp_threshold",
        record_type="aggregate",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode="internal_generator",
    )


def estimate_m0(binary: Path, config: dict[str, Any], args: argparse.Namespace, errors_path: Path) -> tuple[int, str]:
    if args.dry_run:
        return initial_m0(config), "heuristic"
    lo = lower_bound_m(config)
    hi = initial_m0(config)
    limit = max_m(config, args.max_c_over_d)
    log_progress(
        args,
        f"  [center] {config['scan_id']} search start: lo={lo} initial_hi={hi} limit={limit} "
        f"target={args.center_target}",
    )
    while hi <= limit:
        row = run_point(binary, config, hi, args.center_trials, args, errors_path)
        if row is None:
            log_progress(args, f"  [center] upper_bound M={hi}: failed; see errors.log")
        else:
            log_progress(
                args,
                f"  [center] upper_bound M={hi}: success={float(row.get('success_rate', 0.0)):.3f} "
                f"({row.get('successes', 0)}/{row.get('trials', args.center_trials)})",
            )
        if row is not None and float(row.get("success_rate", 0.0)) >= args.center_target:
            break
        hi *= 2
    else:
        fallback = min(limit, max(lo, hi // 2))
        log_progress(args, f"  [center] unresolved before limit; using M={fallback}")
        return fallback, "internal_unresolved"
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_point(binary, config, mid, args.center_trials, args, errors_path)
        if row is None:
            log_progress(args, f"  [center] binary M={mid}: failed; see errors.log")
        else:
            log_progress(
                args,
                f"  [center] binary M={mid}: success={float(row.get('success_rate', 0.0)):.3f} "
                f"({row.get('successes', 0)}/{row.get('trials', args.center_trials)})",
            )
        if row is not None and float(row.get("success_rate", 0.0)) >= args.center_target:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    log_progress(args, f"  [center] selected M0={best}")
    return best, "internal_search"


def first_m(rows: list[dict[str, Any]], predicate: Any) -> int | str:
    matches = [int(row["M"]) for row in rows if predicate(row)]
    return min(matches) if matches else ""


def first_value(rows: list[dict[str, Any]], predicate: Any, field: str) -> Any:
    matches = [row for row in rows if predicate(row)]
    if not matches:
        return ""
    row = min(matches, key=lambda item: int(item["M"]))
    return row.get(field, "")


def summarize_group(config: dict[str, Any], rows: list[dict[str, Any]], m0: int, source: str, args: argparse.Namespace) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: int(row["M"]))
    point_m50 = first_m(ordered, lambda row: float(row.get("success_rate", 0.0)) >= 0.50)
    point_m95 = first_m(ordered, lambda row: float(row.get("success_rate", 0.0)) >= 0.95)
    ci_low_m95 = first_m(ordered, lambda row: float(row.get("ci_low", 0.0)) >= 0.95)
    target = float(args.target_success_rate)
    point_m90 = first_m(ordered, lambda row: float(row.get("success_rate", 0.0)) >= target)
    ci_low_m90 = first_m(ordered, lambda row: float(row.get("ci_low", 0.0)) >= target)
    transition_min = first_m(ordered, lambda row: float(row.get("ci_high", 0.0)) >= 0.10)
    transition_max = first_m(ordered, lambda row: float(row.get("ci_low", 0.0)) >= 0.90)

    max_slope = ""
    slopes: list[float] = []
    for left, right in zip(ordered, ordered[1:]):
        dx = float(right.get("field_C_over_d", 0.0)) - float(left.get("field_C_over_d", 0.0))
        if dx > 0:
            slopes.append((float(right.get("success_rate", 0.0)) - float(left.get("success_rate", 0.0))) / dx)
    if slopes:
        max_slope = max(slopes)

    transition_width_m: int | str = ""
    transition_width_c: float | str = ""
    if transition_min != "" and transition_max != "":
        transition_width_m = int(transition_max) - int(transition_min)
        transition_width_c = c_over_d(config, int(transition_max)) - c_over_d(config, int(transition_min))  # type: ignore[operator]

    status = "ok"
    if not ordered:
        status = "benchmark_error"
    elif all(float(row.get("success_rate", 0.0)) == 0.0 for row in ordered):
        status = "all_zero"
    elif all(float(row.get("success_rate", 0.0)) == 1.0 for row in ordered):
        status = "all_one"

    row = {
        "scan_id": config["scan_id"],
        "d": config["d"],
        "l": config["l"],
        "k": config["k"],
        "mode": config["mode"],
        "M0": m0,
        "threshold_source": source,
        "grid_size": len(ordered),
        "M_min": int(ordered[0]["M"]) if ordered else "",
        "M_max": int(ordered[-1]["M"]) if ordered else "",
        "point_M_50": point_m50,
        "point_C_over_d_50": c_over_d(config, point_m50),
        "point_M_95": point_m95,
        "point_C_over_d_95": c_over_d(config, point_m95),
        "ci_low_M_95": ci_low_m95,
        "ci_low_C_over_d_95": c_over_d(config, ci_low_m95),
        "point_M_90": point_m90,
        "point_R_w30_90": first_value(ordered, lambda row: float(row.get("success_rate", 0.0)) >= target, "R_w30"),
        "ci_low_M_90": ci_low_m90,
        "ci_low_R_w30_90": first_value(ordered, lambda row: float(row.get("ci_low", 0.0)) >= target, "R_w30"),
        "transition_M_min": transition_min,
        "transition_M_max": transition_max,
        "transition_width_M": transition_width_m,
        "transition_C_over_d_min": c_over_d(config, transition_min),
        "transition_C_over_d_max": c_over_d(config, transition_max),
        "transition_width_C_over_d": transition_width_c,
        "max_slope": max_slope,
        "ca": config["ca"],
        "cb": config["cb"],
        "seed": config["seed"],
        "dedup_hashes": bool(config.get("dedup_hashes", False)),
        "circular_a": float(config.get("circular_a", 1.0 / 3.0)),
        "dataset_mode": "internal_generator",
        "trials": args.trials,
        "successes": 0,
        "success_rate": 0.0,
        "ci_low": 0.0,
        "ci_high": 1.0,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "bits": 0.0,
        "bits_per_difference": 0.0,
        "bit_C_over_d": 0.0,
        "R_w30": 0.0,
        "encode_avg_s": 0.0,
        "decode_avg_s": 0.0,
        "encode_median_s": 0.0,
        "decode_median_s": 0.0,
        "status": status,
    }
    return normalize_benchmark_row(
        row,
        experiment="xyz_sharp_threshold",
        record_type="aggregate",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode="internal_generator",
        status=status,
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, summaries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# XYZ Sharp-Threshold Summary\n\n")
        handle.write("| d | l | k | mode | M0 | M@50 | M@90 | R@90 | CI-low M@90 | CI-low R@90 | M@95 | width M | status |\n")
        handle.write("| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(summaries, key=lambda item: (int(item["d"]), int(item["l"]), int(item["k"]), str(item["mode"]))):
            handle.write(
                f"| {row['d']} | {row['l']} | {row['k']} | {row['mode']} | {row.get('M0', '')} | "
                f"{row.get('point_M_50', '')} | {row.get('point_M_90', '')} | "
                f"{row.get('point_R_w30_90', '')} | {row.get('ci_low_M_90', '')} | "
                f"{row.get('ci_low_R_w30_90', '')} | {row.get('point_M_95', '')} | "
                f"{row.get('transition_width_M', '')} | {row.get('status', '')} |\n"
            )


def write_run_config(path: Path, args: argparse.Namespace, configs: list[dict[str, Any]]) -> None:
    payload = {
        "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "configs": configs,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XYZ-v2 uniform-vs-SC sharp-threshold scans.")
    parser.add_argument("--d-values", default="1000,3000,10000")
    parser.add_argument("--l-values", default="6")
    parser.add_argument("--k-values", default="2,3")
    parser.add_argument("--modes", default="random,spatial")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--center-trials", type=int, default=20)
    parser.add_argument("--center-target", type=float, default=0.50)
    parser.add_argument("--target-success-rate", type=float, default=0.90)
    parser.add_argument("--points", type=int, default=41)
    parser.add_argument("--step", type=int, default=None)
    parser.add_argument("--window-fraction", type=float, default=0.20)
    parser.add_argument("--min-window", type=int, default=8)
    parser.add_argument("--threshold-summary", type=Path, default=None)
    parser.add_argument("--max-C-over-d", type=float, default=8.0, dest="max_c_over_d")
    parser.add_argument("--fixed-z", type=int, default=None)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dedup-hashes", default="false")
    parser.add_argument("--circular-a", type=float, default=None, help="Override circular a. By default use a_{k,l}=C*c_orient/c_peel.")
    add_tuning_arguments(parser)
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials <= 0 or args.center_trials <= 0:
        raise SystemExit("--trials and --center-trials must be positive")
    if not (0 < args.center_target <= 1):
        raise SystemExit("--center-target must be in (0, 1]")
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.circular_a is not None and not (0.0 <= args.circular_a < 1.0):
        raise SystemExit("--circular-a must be in [0, 1)")
    if args.points <= 0:
        raise SystemExit("--points must be positive")
    if args.window_fraction < 0 or args.min_window < 0:
        raise SystemExit("--window-fraction and --min-window must be non-negative")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    configs = make_configs(args)
    if args.limit is not None:
        configs = configs[: args.limit]
    summary_centers = load_threshold_summary(args.threshold_summary)
    log_progress(
        args,
        f"[setup] configs={len(configs)} trials={args.trials} center_trials={args.center_trials} "
        f"points={args.points} output={dirs['base']}",
    )

    if not args.dry_run and not args.skip_build:
        log_progress(args, "[setup] building xyz_v2_bench")
    else:
        log_progress(args, "[setup] using existing/skipped benchmark build")
    binary = build_benchmark(root, dirs["build"], args.skip_build) if not args.dry_run else dirs["build"] / f"xyz_v2_bench{exe_suffix()}"
    if dirs["errors"].exists():
        dirs["errors"].unlink()

    planned: list[tuple[dict[str, Any], int, str, list[int]]] = []
    for config_index, config in enumerate(configs, start=1):
        log_progress(args, f"[plan {config_index}/{len(configs)}] {config['scan_id']}")
        key = (int(config["d"]), int(config["l"]), int(config["k"]), str(config["mode"]))
        if key in summary_centers:
            m0 = summary_centers[key]
            source = "threshold_summary"
            log_progress(args, f"  [center] using threshold-summary M0={m0}")
        else:
            m0, source = estimate_m0(binary, config, args, dirs["errors"])
        grid = m_grid(config, m0, args)
        log_progress(args, f"  [grid] source={source} range={grid[0]}..{grid[-1]} points={len(grid)}")
        planned.append((config, m0, source, grid))

    if args.dry_run:
        for config, m0, source, grid in planned:
            print(
                f"{config['scan_id']}: source={source} M0={m0} "
                f"grid={grid[0]}..{grid[-1]} points={len(grid)}"
            )
        return

    for path in (dirs["raw_jsonl"], dirs["raw_csv"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"]):
        if path.exists():
            path.unlink()
    write_run_config(dirs["run_config"], args, configs)

    raw_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for config_index, (config, m0, source, grid) in enumerate(planned, start=1):
        group_rows: list[dict[str, Any]] = []
        log_progress(args, f"[scan {config_index}/{len(planned)}] {config['scan_id']} M0={m0} points={len(grid)}")
        for grid_index, m_value in enumerate(grid):
            log_progress(args, f"  [point {grid_index + 1}/{len(grid)}] running M={m_value}")
            metadata = {
                "scan_id": config["scan_id"],
                "M0": m0,
                "M_offset": m_value - m0,
                "C_over_d_offset": c_over_d(config, m_value) - c_over_d(config, m0),  # type: ignore[operator]
                "grid_index": grid_index,
                "grid_size": len(grid),
                "threshold_source": source,
            }
            row = run_point(binary, config, m_value, args.trials, args, dirs["errors"], scan_metadata=metadata)
            if row is None:
                log_progress(args, f"  [point {grid_index + 1}/{len(grid)}] M={m_value}: failed; see errors.log")
                continue
            group_rows.append(row)
            raw_rows.append(row)
            log_progress(
                args,
                f"  [point {grid_index + 1}/{len(grid)}] M={m_value} "
                f"C/d={float(row.get('field_C_over_d', 0.0)):.3f} "
                f"success={float(row.get('success_rate', 0.0)):.3f} "
                f"({row.get('successes', 0)}/{row.get('trials', args.trials)})",
            )
            write_jsonl(dirs["raw_jsonl"], raw_rows)
            write_csv(dirs["raw_csv"], raw_rows, RAW_FIELDS)
        summary = summarize_group(config, group_rows, m0, source, args)
        summaries.append(summary)
        log_progress(args, f"[scan {config_index}/{len(planned)}] summary status={summary.get('status', '')}")
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_csv(dirs["summary_csv"], summaries, SUMMARY_FIELDS)
        write_summary_md(dirs["summary_md"], summaries)

    print(f"wrote {dirs['raw_jsonl']}")
    print(f"wrote {dirs['raw_csv']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")


if __name__ == "__main__":
    main()
