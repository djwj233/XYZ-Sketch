#!/usr/bin/env python3
"""Compare IBLT uniform placement with a spatially coupled placement."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from dataset_generator import DatasetConfig, choose_set_sizes, prepare_datasets
from json_schema import normalize_benchmark_row
from statistics import add_binomial_ci, normal_z


SUMMARY_FIELDS = [
    "schema_version",
    "record_type",
    "experiment",
    "algorithm",
    "variant",
    "implementation",
    "status",
    "search_id",
    "d",
    "mode",
    "hash_count",
    "best_cells",
    "best_capacity_factor",
    "best_bit_C_over_d",
    "target_success_rate",
    "threshold_policy",
    "probe_trials",
    "final_trials",
    "final_successes",
    "final_success_rate",
    "final_ci_low",
    "final_ci_high",
    "ci_method",
    "ci_confidence",
    "uniform_cells",
    "spatial_cells",
    "uniform_bit_C_over_d",
    "spatial_bit_C_over_d",
    "relative_improvement",
    "cells",
    "capacity_factor",
    "cell_bits",
    "z",
    "window_size",
    "ca",
    "cb",
    "seed",
    "dataset_mode",
    "trials",
    "successes",
    "success_rate",
    "ci_low",
    "ci_high",
    "bits",
    "bits_per_difference",
    "bit_C_over_d",
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
    base = output_dir or root / "tests" / "results" / "iblt_spatial"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "iblt_spatial"
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "tmp": tmp,
        "probes": base / "probes.jsonl",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "run_config": base / "run_config.json",
        "errors": base / "errors.log",
    }


def build_benchmark(root: Path, build_dir: Path, skip_build: bool) -> Path:
    binary = build_dir / f"iblt_sc_bench{exe_suffix()}"
    if skip_build:
        if not binary.exists():
            raise FileNotFoundError(f"benchmark binary not found: {binary}")
        return binary
    source = root / "tests" / "benchmarks" / "iblt_sc_bench.cpp"
    subprocess.run(["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)], cwd=root, check=True)
    return binary


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def hash_count_value(policy: str, d_value: int) -> str:
    if policy == "auto":
        return "4" if d_value < 200 else "3"
    return policy


def choose_z(mode: str, cells: int, fixed_z: int | None) -> int:
    if mode == "uniform":
        return 0
    if fixed_z is not None:
        return fixed_z
    return max(0, round((cells ** (1.0 / 3.0)) / 3.0))


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def works(row: dict[str, Any] | None, args: argparse.Namespace) -> bool:
    if row is None:
        return False
    if args.threshold_policy == "point":
        return int(row["successes"]) >= required_successes(args.target_success_rate, int(row["trials"]))
    if args.threshold_policy == "ci-low":
        return float(row.get("ci_low", 0.0)) >= args.target_success_rate
    raise ValueError(f"unknown threshold policy: {args.threshold_policy}")


def make_configs(args: argparse.Namespace) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    modes = parse_str_list(args.modes)
    hash_counts = parse_str_list(args.hash_counts)
    for d_index, d_value in enumerate(parse_int_list(args.d_values)):
        ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
        seed = args.base_seed + 1_000_000 * d_index
        for hash_count in hash_counts:
            if hash_count != "auto":
                parsed = int(hash_count)
                if parsed <= 0:
                    raise SystemExit("--hash-counts values must be positive or auto")
            for mode in modes:
                if mode not in {"uniform", "spatial"}:
                    raise SystemExit(f"unknown mode: {mode}")
                configs.append(
                    {
                        "search_id": f"d{d_value}_h{hash_count}_{mode}",
                        "d": d_value,
                        "mode": mode,
                        "hash_count": hash_count,
                        "seed": seed,
                        "ca": ca,
                        "cb": cb,
                    }
                )
    return configs


def command_for(
    binary: Path,
    config: dict[str, Any],
    cells: int,
    trials: int,
    dataset: Path,
    args: argparse.Namespace,
) -> list[str]:
    return [
        str(binary),
        "--d",
        str(config["d"]),
        "--trials",
        str(trials),
        "--seed",
        str(config["seed"]),
        "--ca",
        str(config["ca"]),
        "--cb",
        str(config["cb"]),
        "--cells",
        str(cells),
        "--mode",
        str(config["mode"]),
        "--hash-count",
        hash_count_value(str(config["hash_count"]), int(config["d"])),
        "--z",
        str(choose_z(str(config["mode"]), cells, args.fixed_z)),
        "--dataset",
        str(dataset),
        "--format",
        "jsonl",
    ]


def append_error(path: Path, config: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("CONFIG " + json.dumps(config, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def run_one_dataset(
    binary: Path,
    config: dict[str, Any],
    cells: int,
    dataset: Path,
    args: argparse.Namespace,
    errors_path: Path,
) -> dict[str, Any] | None:
    command = command_for(binary, config, cells, 1, dataset, args)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        append_error(errors_path, config, command, f"OSERROR {exc}")
        return None
    if completed.returncode != 0:
        append_error(errors_path, config, command, f"RETURNCODE {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}")
        return None
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        append_error(errors_path, config, command, f"PARSE got {len(lines)} lines\n{completed.stdout}")
        return None
    try:
        return json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, config, command, f"JSONERROR {exc}\n{completed.stdout}")
        return None


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def aggregate_trial_rows(config: dict[str, Any], cells: int, rows: list[dict[str, Any]], args: argparse.Namespace, phase: str) -> dict[str, Any] | None:
    ok_rows = [row for row in rows if row is not None]
    if not ok_rows:
        return None
    trials = len(ok_rows)
    successes = sum(int(row.get("successes", 0)) for row in ok_rows)
    first = dict(ok_rows[0])
    first["trials"] = trials
    first["successes"] = successes
    first["success_rate"] = successes / float(trials)
    first["encode_avg_s"] = sum(float(row.get("encode_avg_s", 0.0)) for row in ok_rows) / trials
    first["decode_avg_s"] = sum(float(row.get("decode_avg_s", 0.0)) for row in ok_rows) / trials
    first["encode_median_s"] = median([float(row.get("encode_median_s", 0.0)) for row in ok_rows])
    first["decode_median_s"] = median([float(row.get("decode_median_s", 0.0)) for row in ok_rows])
    first["cells"] = cells
    first["capacity_factor"] = cells / float(config["d"])
    first["search_id"] = config["search_id"]
    first["phase"] = phase
    first["target_success_rate"] = args.target_success_rate
    first["required_successes"] = required_successes(args.target_success_rate, trials)
    first["dataset_mode"] = "shared_file"
    first["status"] = "ok"
    first = add_binomial_ci(first, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        first,
        experiment="iblt_spatial_threshold",
        record_type="probe",
        algorithm="iblt",
        variant=str(config["mode"]),
        implementation="tests/benchmarks/iblt_sc_bench",
        dataset_mode="shared_file",
    )


def run_probe(
    binary: Path,
    config: dict[str, Any],
    cells: int,
    dataset_paths: list[Path],
    trials: int,
    args: argparse.Namespace,
    errors_path: Path,
    phase: str,
) -> dict[str, Any] | None:
    trial_rows: list[dict[str, Any]] = []
    for dataset in dataset_paths[:trials]:
        row = run_one_dataset(binary, config, cells, dataset, args, errors_path)
        if row is not None:
            trial_rows.append(row)
    return aggregate_trial_rows(config, cells, trial_rows, args, phase)


def lower_cells(config: dict[str, Any], args: argparse.Namespace) -> int:
    return max(1, math.ceil(args.min_capacity_factor * int(config["d"])))


def upper_cells(config: dict[str, Any], args: argparse.Namespace) -> int:
    return max(lower_cells(config, args), math.ceil(args.max_capacity_factor * int(config["d"])))


def initial_cells(config: dict[str, Any], args: argparse.Namespace) -> int:
    return max(lower_cells(config, args), math.ceil(args.initial_capacity_factor * int(config["d"])))


def find_best_cells(
    binary: Path,
    config: dict[str, Any],
    dataset_paths: list[Path],
    args: argparse.Namespace,
    errors_path: Path,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    hi = initial_cells(config, args)
    limit = upper_cells(config, args)
    while hi <= limit:
        row = run_probe(binary, config, hi, dataset_paths, args.probe_trials, args, errors_path, "upper_bound")
        if row is not None:
            probes.append(row)
        if works(row, args):
            break
        hi *= 2
    else:
        return None, probes

    lo = lower_cells(config, args)
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_probe(binary, config, mid, dataset_paths, args.probe_trials, args, errors_path, "binary_search")
        if row is not None:
            probes.append(row)
        if works(row, args):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best, probes


def summary_from_final(
    config: dict[str, Any],
    best_cells: int | None,
    final_row: dict[str, Any] | None,
    args: argparse.Namespace,
    status: str,
) -> dict[str, Any]:
    base = {
        "search_id": config["search_id"],
        "d": config["d"],
        "mode": config["mode"],
        "hash_count": hash_count_value(str(config["hash_count"]), int(config["d"])),
        "target_success_rate": args.target_success_rate,
        "threshold_policy": args.threshold_policy,
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "ca": config["ca"],
        "cb": config["cb"],
        "seed": config["seed"],
        "dataset_mode": "shared_file",
        "status": status,
    }
    if best_cells is None or final_row is None:
        base.update(
            {
                "best_cells": "",
                "best_capacity_factor": "",
                "best_bit_C_over_d": "",
                "final_successes": "",
                "final_success_rate": "",
                "final_ci_low": "",
                "final_ci_high": "",
            }
        )
    else:
        base.update(
            {
                "best_cells": best_cells,
                "best_capacity_factor": best_cells / float(config["d"]),
                "best_bit_C_over_d": final_row.get("bit_C_over_d", 0.0),
                "final_successes": final_row.get("successes", 0),
                "final_success_rate": final_row.get("success_rate", 0.0),
                "final_ci_low": final_row.get("ci_low", ""),
                "final_ci_high": final_row.get("ci_high", ""),
                **final_row,
            }
        )
    return normalize_benchmark_row(
        base,
        experiment="iblt_spatial_threshold",
        record_type="threshold",
        algorithm="iblt",
        variant=str(config["mode"]),
        implementation="tests/benchmarks/iblt_sc_bench",
        dataset_mode="shared_file",
        status=status,
    )


def add_pairwise_improvements(summaries: list[dict[str, Any]]) -> None:
    groups: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
    for row in summaries:
        key = (int(row["d"]), str(row.get("hash_count", "")))
        groups.setdefault(key, {})[str(row["mode"])] = row
    for group in groups.values():
        uniform = group.get("uniform")
        spatial = group.get("spatial")
        if not uniform or not spatial:
            continue
        uniform_bits = float(uniform.get("best_bit_C_over_d", 0.0) or 0.0)
        spatial_bits = float(spatial.get("best_bit_C_over_d", 0.0) or 0.0)
        improvement = ""
        if uniform_bits > 0 and spatial_bits > 0:
            improvement = (uniform_bits - spatial_bits) / uniform_bits
        for row in (uniform, spatial):
            row["uniform_cells"] = uniform.get("best_cells", "")
            row["spatial_cells"] = spatial.get("best_cells", "")
            row["uniform_bit_C_over_d"] = uniform.get("best_bit_C_over_d", "")
            row["spatial_bit_C_over_d"] = spatial.get("best_bit_C_over_d", "")
            row["relative_improvement"] = improvement


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# IBLT Uniform vs Spatial Summary\n\n")
        handle.write("| d | hash_count | mode | cells | bit C/d | success | ci low | improvement |\n")
        handle.write("| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), str(item.get("hash_count", "")), str(item["mode"]))):
            improvement = row.get("relative_improvement", "")
            improvement_text = "" if improvement == "" else f"{float(improvement):.3f}"
            handle.write(
                f"| {row['d']} | {row.get('hash_count', '')} | {row['mode']} | {row.get('best_cells', '')} | "
                f"{float(row.get('best_bit_C_over_d', 0.0) or 0.0):.3f} | "
                f"{float(row.get('final_success_rate', 0.0) or 0.0):.3f} | "
                f"{float(row.get('final_ci_low', 0.0) or 0.0):.3f} | {improvement_text} |\n"
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
    parser = argparse.ArgumentParser(description="Compare IBLT uniform and spatial placements.")
    parser.add_argument("--d-values", default="100,300,1000")
    parser.add_argument("--modes", default="uniform,spatial")
    parser.add_argument("--hash-counts", default="auto")
    parser.add_argument("--probe-trials", type=int, default=20)
    parser.add_argument("--final-trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.95)
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--min-capacity-factor", type=float, default=0.5)
    parser.add_argument("--initial-capacity-factor", type=float, default=1.5)
    parser.add_argument("--max-capacity-factor", type=float, default=5.0)
    parser.add_argument("--fixed-z", type=int, default=None)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.probe_trials <= 0 or args.final_trials <= 0:
        raise SystemExit("--probe-trials and --final-trials must be positive")
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.min_capacity_factor <= 0 or args.initial_capacity_factor <= 0 or args.max_capacity_factor <= 0:
        raise SystemExit("capacity factors must be positive")
    if args.min_capacity_factor > args.max_capacity_factor:
        raise SystemExit("--min-capacity-factor must not exceed --max-capacity-factor")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    configs = make_configs(args)
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: lo={lower_cells(config, args)} "
                f"hi0={initial_cells(config, args)} max={upper_cells(config, args)} "
                f"seed={config['seed']} ca={config['ca']} cb={config['cb']}"
            )
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"], dirs["errors"]):
        if path.exists():
            path.unlink()
    write_run_config(dirs["run_config"], args, configs)

    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    all_probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for index, config in enumerate(configs, start=1):
        cache_key = (int(config["d"]), int(config["ca"]), int(config["cb"]), int(config["seed"]))
        if cache_key not in dataset_cache:
            dataset_config = DatasetConfig(d=int(config["d"]), ca=int(config["ca"]), cb=int(config["cb"]), seed=int(config["seed"]))
            dataset_cache[cache_key] = prepare_datasets(dataset_config, args.final_trials, dataset_dir)
        dataset_paths = dataset_cache[cache_key]

        print(f"[{index}/{len(configs)}] {config['search_id']}", flush=True)
        best_cells, probes = find_best_cells(binary, config, dataset_paths, args, dirs["errors"])
        all_probes.extend(probes)
        if best_cells is None:
            print("  unresolved", flush=True)
            summaries.append(summary_from_final(config, None, None, args, "unresolved"))
        else:
            final_row = run_probe(binary, config, best_cells, dataset_paths, args.final_trials, args, dirs["errors"], "final_validate")
            if final_row is not None:
                all_probes.append(final_row)
            status = "ok" if works(final_row, args) else "unresolved"
            summary = summary_from_final(config, best_cells, final_row, args, status)
            summaries.append(summary)
            print(
                f"  cells={best_cells} bit_C/d={float(summary.get('best_bit_C_over_d', 0.0) or 0.0):.3f} "
                f"success={summary.get('final_success_rate', '')} status={status}",
                flush=True,
            )

        add_pairwise_improvements(summaries)
        write_jsonl(dirs["probes"], all_probes)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_summary_csv(dirs["summary_csv"], summaries)
        write_summary_md(dirs["summary_md"], summaries)

    print(f"wrote {dirs['probes']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")


if __name__ == "__main__":
    main()
