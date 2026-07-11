#!/usr/bin/env python3
"""Run the first XYZ-Sketch d/l/k parameter sweep.

This script is an experiment driver. It builds or locates the C++ benchmark
binary, runs a moderate parameter grid, and writes structured raw results.
"""

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
from xyz_tuning import add_tuning_arguments, a_from_args, z_from_args


QUICK_D_VALUES = [100, 300, 1000, 3000, 10000]
QUICK_L_VALUES = [2, 3, 4, 6, 8, 10]
QUICK_K_VALUES = [2, 3, 4]

EXTENDED_D_VALUES = [
    10,
    30,
    100,
    300,
    1000,
    3000,
    10000,
    30000,
    100000,
    300000,
    1000000,
]
EXTENDED_L_VALUES = [2, 3, 4, 6, 8, 10, 16, 20]
EXTENDED_K_VALUES = [2, 3, 4]

CSV_FIELDS = [
    "algorithm",
    "mode",
    "d",
    "l",
    "k",
    "M",
    "z",
    "trials",
    "successes",
    "success_rate",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
    "bits",
    "C_over_d",
    "seed",
    "ca",
    "cb",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "dlk"
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
    binary = build_dir / f"xyz_sketch_bench{exe_suffix()}"
    if skip_build:
        if not binary.exists():
            raise FileNotFoundError(f"benchmark binary not found: {binary}")
        return binary

    source = root / "tests" / "benchmarks" / "xyz_sketch_bench.cpp"
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        str(source),
        "-o",
        str(binary),
    ]
    subprocess.run(command, cwd=root, check=True)
    return binary


def choose_trials(d: int, quick: bool) -> int:
    if quick:
        if d <= 1000:
            return 10
        if d <= 10000:
            return 5
        return 3
    if d <= 10000:
        return 100
    if d <= 100000:
        return 50
    return 30


def choose_c_over_d_target(d: int, k_value: int) -> float:
    if k_value == 3:
        return 1.668
    if k_value >= 4:
        return 1.782
    if d <= 100:
        return 1.60
    if d <= 1000:
        return 1.30
    if d <= 10000:
        return 1.20
    if d <= 100000:
        return 1.12
    return 1.10


def choose_m(d: int, l_value: int, k_value: int) -> int:
    return max(1, math.ceil(choose_c_over_d_target(d, k_value) * d / l_value))


def choose_z(m_value: int, k_value: int, l_value: int, a_value: float, args: argparse.Namespace) -> int:
    return z_from_args(k_value, l_value, m_value, a_value, args)


def default_grid(extended: bool, max_set_size: int, scale: int, base_seed: int) -> list[dict[str, Any]]:
    d_values = EXTENDED_D_VALUES if extended else QUICK_D_VALUES
    l_values = EXTENDED_L_VALUES if extended else QUICK_L_VALUES
    k_values = EXTENDED_K_VALUES if extended else QUICK_K_VALUES

    configs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                m_value = choose_m(d_value, l_value, k_value)
                if m_value < k_value:
                    continue
                ca, cb = choose_set_sizes(d_value, max_set_size=max_set_size, scale=scale)
                seed = base_seed + 1_000_000 * d_index + 10_000 * l_index + 100 * k_index
                configs.append(
                    {
                        "d": d_value,
                        "l": l_value,
                        "k": k_value,
                        "m": m_value,
                        "z": choose_z(m_value, k_value, l_value, a_from_args(k_value, l_value, args), args),
                        "circular_a": a_from_args(k_value, l_value, args),
                        "trials": choose_trials(d_value, quick=not extended),
                        "seed": seed,
                        "mode": "spatial",
                        "ca": ca,
                        "cb": cb,
                    }
                )
    return configs


def command_for(binary: Path, config: dict[str, Any]) -> list[str]:
    return [
        str(binary),
        "--d",
        str(config["d"]),
        "--l",
        str(config["l"]),
        "--k",
        str(config["k"]),
        "--m",
        str(config["m"]),
        "--z",
        str(config["z"]),
        "--trials",
        str(config["trials"]),
        "--seed",
        str(config["seed"]),
        "--mode",
        str(config["mode"]),
        "--circular-a",
        str(config.get("circular_a", 0.0)),
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


def run_one(binary: Path, config: dict[str, Any], errors_path: Path) -> dict[str, Any] | None:
    command = command_for(binary, config)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
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
        append_error(
            errors_path,
            config,
            command,
            f"PARSE expected one JSONL line, got {len(lines)}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        )
        return None

    try:
        row = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(
            errors_path,
            config,
            command,
            f"JSONERROR {exc}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        )
        return None
    return normalize_benchmark_row(
        row,
        experiment="dlk_sweep",
        record_type="aggregate",
        algorithm="xyz_sketch",
        variant=str(config["mode"]),
        implementation="local/XYZ-Sketch",
        dataset_mode="internal_generator",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, Any]], attempted: int) -> None:
    failures = attempted - len(rows)
    avg_success = 0.0
    if rows:
        avg_success = sum(float(row["success_rate"]) for row in rows) / len(rows)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# d/l/k Sweep Summary\n\n")
        handle.write(f"- Attempted configurations: {attempted}\n")
        handle.write(f"- Completed configurations: {len(rows)}\n")
        handle.write(f"- Failed configurations: {failures}\n")
        handle.write(f"- Average success rate: {avg_success:.4f}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run XYZ-Sketch d/l/k parameter sweep.")
    parser.add_argument("--extended", action="store_true", help="Use the extended parameter grid.")
    parser.add_argument("--skip-build", action="store_true", help="Reuse an existing benchmark binary.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N configurations.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Override output directory.")
    parser.add_argument("--base-seed", type=int, default=114514, help="Base seed for generated configs.")
    parser.add_argument(
        "--max-set-size",
        type=int,
        default=100000,
        help="Maximum generated Alice/Bob set size for this scripted sweep.",
    )
    parser.add_argument(
        "--set-size-scale",
        type=int,
        default=10,
        help="Use roughly scale*d elements per side, capped by --max-set-size.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    binary = build_benchmark(root, dirs["build"], args.skip_build)
    configs = default_grid(
        extended=args.extended,
        max_set_size=args.max_set_size,
        scale=args.set_size_scale,
        base_seed=args.base_seed,
    )
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            print(" ".join(command_for(binary, config)))
        return

    rows: list[dict[str, Any]] = []
    if dirs["errors"].exists():
        dirs["errors"].unlink()

    for index, config in enumerate(configs, start=1):
        print(
            f"[{index}/{len(configs)}] d={config['d']} l={config['l']} "
            f"k={config['k']} M={config['m']} z={config['z']} trials={config['trials']}",
            flush=True,
        )
        row = run_one(binary, config, dirs["errors"])
        if row is None:
            print("  failed; see errors.log", flush=True)
            continue
        rows.append(row)
        print(
            f"  success_rate={row['success_rate']:.3f} "
            f"C_over_d={row['C_over_d']:.3f} "
            f"encode={row['encode_avg_s']:.3f}s decode={row['decode_avg_s']:.3f}s",
            flush=True,
        )
        write_jsonl(dirs["jsonl"], rows)
        write_csv(dirs["csv"], rows)

    write_summary(dirs["summary"], rows, attempted=len(configs))
    print(f"wrote {dirs['jsonl']}")
    print(f"wrote {dirs['csv']}")
    print(f"wrote {dirs['summary']}")


if __name__ == "__main__":
    main()
