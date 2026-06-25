#!/usr/bin/env python3
"""Run XYZ-v2 z sensitivity experiments with fixed M."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONFIGS = [
    {"d": 1000, "l": 6, "k": 2, "M": 217},
    {"d": 3000, "l": 6, "k": 2, "M": 600},
    {"d": 10000, "l": 6, "k": 2, "M": 2000},
    {"d": 1000, "l": 6, "k": 3, "M": 278},
    {"d": 3000, "l": 6, "k": 3, "M": 834},
    {"d": 10000, "l": 6, "k": 3, "M": 2780},
]

DEFAULT_Z_VALUES = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32]

CSV_FIELDS = [
    "algorithm",
    "d",
    "l",
    "k",
    "M",
    "z",
    "RangeLength",
    "mode",
    "trials",
    "successes",
    "success_rate",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
    "bits",
    "bit_C_over_d",
    "field_C_over_d",
    "seed",
    "ca",
    "cb",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "z_sensitivity"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "jsonl": base / "raw.jsonl",
        "csv": base / "raw.csv",
        "summary": base / "summary.md",
        "errors": base / "errors.log",
    }


def exe_suffix() -> str:
    return ".exe" if sys.platform.startswith("win") else ""


def build_benchmark(root: Path, build_dir: Path, skip_build: bool) -> Path:
    binary = build_dir / f"xyz_v2_bench{exe_suffix()}"
    if skip_build:
        if not binary.exists():
            raise FileNotFoundError(f"benchmark binary not found: {binary}")
        return binary

    source = root / "XYZ-v2" / "xyz_v2_bench.cpp"
    command = ["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)]
    subprocess.run(command, cwd=root, check=True)
    return binary


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def choose_set_sizes(d_value: int, max_set_size: int, scale: int) -> tuple[int, int]:
    base = max(1000, d_value * scale)
    base = min(base, max_set_size)
    if base <= d_value:
        base = d_value + 2
    ca = base
    cb = base - (d_value % 2)
    if cb <= 0:
        cb = ca
    return ca, cb


def configs_from_args(args: argparse.Namespace) -> list[dict[str, int]]:
    if args.d_values or args.l_values or args.k_values or args.m_values:
        if not (args.d_values and args.l_values and args.k_values and args.m_values):
            raise SystemExit("--d-values, --l-values, --k-values, and --m-values must be provided together")
        d_values = parse_int_list(args.d_values)
        l_values = parse_int_list(args.l_values)
        k_values = parse_int_list(args.k_values)
        m_values = parse_int_list(args.m_values)
        if not (len(d_values) == len(l_values) == len(k_values) == len(m_values)):
            raise SystemExit("d/l/k/M value lists must have the same length")
        return [
            {"d": d_value, "l": l_value, "k": k_value, "M": m_value}
            for d_value, l_value, k_value, m_value in zip(d_values, l_values, k_values, m_values)
        ]
    return list(DEFAULT_CONFIGS)


def range_length(m_value: int, z_value: int) -> int:
    return m_value // (z_value + 1)


def valid_z(config: dict[str, int], z_value: int, min_range_length: int | None) -> bool:
    threshold = min_range_length if min_range_length is not None else max(2, int(config["k"]))
    return range_length(int(config["M"]), z_value) >= threshold


def z_values(args: argparse.Namespace) -> list[int]:
    return parse_int_list(args.z_values) if args.z_values else list(DEFAULT_Z_VALUES)


def command_for(binary: Path, config: dict[str, Any], z_value: int, seed: int, args: argparse.Namespace) -> list[str]:
    return [
        str(binary),
        "--d",
        str(config["d"]),
        "--l",
        str(config["l"]),
        "--k",
        str(config["k"]),
        "--m",
        str(config["M"]),
        "--z",
        str(z_value),
        "--mode",
        args.mode,
        "--trials",
        str(args.trials),
        "--seed",
        str(seed),
        "--ca",
        str(config["ca"]),
        "--cb",
        str(config["cb"]),
        "--format",
        "jsonl",
    ]


def append_error(path: Path, config: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("CONFIG " + json.dumps(config, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def run_one(
    binary: Path,
    config: dict[str, Any],
    z_value: int,
    seed: int,
    args: argparse.Namespace,
    errors_path: Path,
) -> dict[str, Any] | None:
    command = command_for(binary, config, z_value, seed, args)
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

    row["RangeLength"] = range_length(int(config["M"]), z_value)
    row["field_C_over_d"] = int(config["M"]) * int(config["l"]) / int(config["d"])
    row["bit_C_over_d"] = int(row["bits"]) / (32.0 * int(config["d"]))
    return row


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, Any]], planned: int) -> None:
    groups: dict[tuple[int, int, int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (int(row["d"]), int(row["l"]), int(row["k"]), int(row["M"]))
        groups.setdefault(key, []).append(row)

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# z Sensitivity Summary\n\n")
        handle.write(f"- Planned runs: {planned}\n")
        handle.write(f"- Completed runs: {len(rows)}\n\n")
        for key, group in sorted(groups.items()):
            best = max(group, key=lambda item: (float(item["success_rate"]), -int(item["z"])))
            heuristic_z = max(0, round((key[3] ** (1.0 / 3.0)) / 3.0))
            handle.write(
                f"- d={key[0]} l={key[1]} k={key[2]} M={key[3]}: "
                f"best_z={best['z']} success={best['success_rate']:.3f}, "
                f"heuristic_z={heuristic_z}\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XYZ-v2 z sensitivity experiments.")
    parser.add_argument("--d-values", default=None, help="Comma-separated d values.")
    parser.add_argument("--l-values", default=None, help="Comma-separated l values.")
    parser.add_argument("--k-values", default=None, help="Comma-separated k values.")
    parser.add_argument("--m-values", default=None, help="Comma-separated exact M values.")
    parser.add_argument("--z-values", default=None, help="Comma-separated z values.")
    parser.add_argument("--mode", default="spatial", choices=["spatial", "random", "circular", "naive"])
    parser.add_argument("--trials", type=int, default=30)
    parser.add_argument("--min-range-length", type=int, default=None)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials <= 0:
        raise SystemExit("--trials must be positive")

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    base_configs = configs_from_args(args)
    z_list = z_values(args)

    configs: list[dict[str, Any]] = []
    for index, config in enumerate(base_configs):
        ca, cb = choose_set_sizes(int(config["d"]), args.max_set_size, args.set_size_scale)
        enriched = dict(config)
        enriched["ca"] = ca
        enriched["cb"] = cb
        enriched["seed"] = args.base_seed + 1_000_000 * index
        configs.append(enriched)

    planned: list[tuple[dict[str, Any], int]] = []
    for config in configs:
        for z_value in z_list:
            if valid_z(config, z_value, args.min_range_length):
                planned.append((config, z_value))
    if args.limit is not None:
        planned = planned[: args.limit]

    if args.dry_run:
        for config, z_value in planned:
            print(
                f"d={config['d']} l={config['l']} k={config['k']} M={config['M']} "
                f"z={z_value} RangeLength={range_length(int(config['M']), z_value)} "
                f"seed={config['seed']}"
            )
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    for path in (dirs["jsonl"], dirs["csv"], dirs["summary"], dirs["errors"]):
        if path.exists():
            path.unlink()

    rows: list[dict[str, Any]] = []
    for index, (config, z_value) in enumerate(planned, start=1):
        print(
            f"[{index}/{len(planned)}] d={config['d']} l={config['l']} k={config['k']} "
            f"M={config['M']} z={z_value} RangeLength={range_length(int(config['M']), z_value)}",
            flush=True,
        )
        row = run_one(binary, config, z_value, int(config["seed"]), args, dirs["errors"])
        if row is None:
            print("  failed; see errors.log", flush=True)
            continue
        rows.append(row)
        print(
            f"  success_rate={row['success_rate']:.3f} "
            f"decode={row['decode_avg_s']:.3f}s",
            flush=True,
        )
        write_jsonl(dirs["jsonl"], rows)
        write_csv(dirs["csv"], rows)

    write_summary(dirs["summary"], rows, planned=len(planned))
    print(f"wrote {dirs['jsonl']}")
    print(f"wrote {dirs['csv']}")
    print(f"wrote {dirs['summary']}")


if __name__ == "__main__":
    main()
