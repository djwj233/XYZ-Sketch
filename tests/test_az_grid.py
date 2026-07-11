#!/usr/bin/env python3
"""Scan a circular-a/z threshold grid for paper Figure 2."""

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
    "search_id",
    "d",
    "l",
    "k",
    "mode",
    "circular_a",
    "z",
    "range_length_at_best_M",
    "best_M",
    "best_C_over_d",
    "best_R_w30",
    "target_success_rate",
    "probe_trials",
    "final_trials",
    "final_successes",
    "final_success_rate",
    "final_ci_low",
    "final_ci_high",
    "ci_method",
    "ci_confidence",
    "threshold_policy",
    "point_estimate_reaches_target",
    "ci_low_reaches_target",
    "ci_high_reaches_target",
    "encode_avg_s",
    "decode_avg_s",
    "status",
    "seed",
    "ca",
    "cb",
    "dedup_hashes",
    "dataset_mode",
    "dataset_dir",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def exe_suffix() -> str:
    return ".exe" if sys.platform.startswith("win") else ""


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "paper_fig2_az_grid"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "paper_fig2_az_grid"
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


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def range_length(m_value: int, z_value: int) -> int:
    return int(m_value) // (int(z_value) + 1)


def lower_bound_m(config: dict[str, Any]) -> int:
    return max(int(config["k"]), math.ceil(int(config["d"]) / int(config["l"])), 1)


def initial_upper_m(config: dict[str, Any]) -> int:
    return max(lower_bound_m(config), math.ceil(1.5 * int(config["d"]) / int(config["l"])))


def max_m(config: dict[str, Any], max_c_over_d: float) -> int:
    return max(lower_bound_m(config), math.ceil(max_c_over_d * int(config["d"]) / int(config["l"])))


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def c_over_d_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value in (None, ""):
        return ""
    return int(m_value) * int(config["l"]) / int(config["d"])


def r_w30_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value in (None, ""):
        return ""
    cell_bits = (math.floor(math.log2(2 * int(config["l"]) + 1)) + 1) + 32 * int(config["l"])
    return int(m_value) * cell_bits / (30.0 * int(config["d"]))


def r_w30_from_bits(bits: Any, d_value: Any) -> float | str:
    try:
        d_float = float(d_value)
        if d_float <= 0:
            return ""
        return float(bits) / (30.0 * d_float)
    except (TypeError, ValueError):
        return ""


def variant_name(config: dict[str, Any]) -> str:
    suffix = ",dedup=true" if bool(config.get("dedup_hashes", False)) else ""
    return f"circular,a={float(config['circular_a']):.6g},z={int(config['z'])}{suffix}"


def make_configs(args: argparse.Namespace) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    d_values = parse_int_list(args.d_values)
    l_values = parse_int_list(args.l_values)
    k_values = parse_int_list(args.k_values)
    a_values = parse_float_list(args.a_values)
    z_values = parse_int_list(args.z_values)
    dedup_hashes = parse_bool(args.dedup_hashes)
    for d_index, d_value in enumerate(d_values):
        ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                for a_index, a_value in enumerate(a_values):
                    if not (0.0 <= a_value < 1.0):
                        raise SystemExit(f"circular a must be in [0, 1): {a_value}")
                    for z_index, z_value in enumerate(z_values):
                        if z_value < 0:
                            raise SystemExit(f"z must be non-negative: {z_value}")
                        seed = args.base_seed + 1_000_000 * d_index + 10_000 * l_index + 100 * k_index
                        configs.append(
                            {
                                "search_id": f"d{d_value}_l{l_value}_k{k_value}_a{a_index}_z{z_value}",
                                "d": d_value,
                                "l": l_value,
                                "k": k_value,
                                "mode": "circular",
                                "circular_a": a_value,
                                "z": z_value,
                                "seed": seed,
                                "ca": ca,
                                "cb": cb,
                                "dedup_hashes": dedup_hashes,
                            }
                        )
    return configs


def command_for(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    trials: int,
    seed: int,
    dataset: Path | None = None,
) -> list[str]:
    command = [
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
        str(config["z"]),
        "--trials",
        str(trials),
        "--seed",
        str(seed),
        "--mode",
        "circular",
        "--circular-a",
        f"{float(config['circular_a']):.12g}",
        "--ca",
        str(config["ca"]),
        "--cb",
        str(config["cb"]),
        "--dedup-hashes",
        str(bool(config.get("dedup_hashes", False))).lower(),
        "--format",
        "jsonl",
    ]
    if dataset is not None:
        command.extend(["--dataset", str(dataset)])
    return command


def append_error(path: Path, config: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("CONFIG " + json.dumps(config, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def parse_benchmark_row(command: list[str], config: dict[str, Any], completed: subprocess.CompletedProcess[str], errors_path: Path) -> dict[str, Any] | None:
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
        return json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, config, command, f"JSONERROR {exc}\n{completed.stdout}")
        return None


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def aggregate_trial_rows(rows: list[dict[str, Any]], trials: int) -> dict[str, Any] | None:
    valid_rows = [row for row in rows if row.get("status", "ok") in {"ok", "failed_decode"}]
    if not valid_rows:
        return None
    first = dict(valid_rows[0])
    successes = sum(int(row.get("successes", 0)) for row in valid_rows)
    first["trials"] = len(valid_rows)
    first["attempted_trials"] = trials
    first["completed_trials"] = len(valid_rows)
    first["error_trials"] = max(0, trials - len(valid_rows))
    first["successes"] = successes
    first["success_rate"] = successes / float(len(valid_rows))
    first["status"] = "ok"
    first["encode_avg_s"] = sum(float(row.get("encode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    first["decode_avg_s"] = sum(float(row.get("decode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    first["encode_median_s"] = median([float(row.get("encode_median_s", 0.0)) for row in valid_rows])
    first["decode_median_s"] = median([float(row.get("decode_median_s", 0.0)) for row in valid_rows])
    return first


def run_probe(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    trials: int,
    phase: str,
    args: argparse.Namespace,
    errors_path: Path,
    dataset_paths: list[Path] | None,
) -> dict[str, Any] | None:
    if range_length(m_value, int(config["z"])) < args.min_range_length:
        return invalid_probe(config, m_value, trials, phase, args)

    if args.shared_datasets:
        if dataset_paths is None:
            raise ValueError("dataset_paths are required when --shared-datasets is enabled")
        trial_rows: list[dict[str, Any]] = []
        for dataset in dataset_paths[:trials]:
            command = command_for(binary, config, m_value, 1, int(config["seed"]), dataset=dataset)
            try:
                completed = subprocess.run(command, check=False, capture_output=True, text=True)
            except OSError as exc:
                append_error(errors_path, config, command, f"OSERROR {exc}")
                continue
            row = parse_benchmark_row(command, config, completed, errors_path)
            if row is not None:
                trial_rows.append(row)
        row = aggregate_trial_rows(trial_rows, trials)
        if row is None:
            return None
        row["dataset_mode"] = "shared_file"
        row["dataset_dir"] = str(dataset_paths[0].parent) if dataset_paths else ""
    else:
        command = command_for(binary, config, m_value, trials, int(config["seed"]))
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError as exc:
            append_error(errors_path, config, command, f"OSERROR {exc}")
            return None
        row = parse_benchmark_row(command, config, completed, errors_path)
        if row is None:
            return None

    row.update(
        {
            "search_id": config["search_id"],
            "phase": phase,
            "candidate_M": m_value,
            "target_success_rate": args.target_success_rate,
            "required_successes": required_successes(args.target_success_rate, trials),
            "circular_a": float(config["circular_a"]),
            "z": int(config["z"]),
            "range_length": range_length(m_value, int(config["z"])),
            "R_w30": r_w30_from_bits(row.get("bits", 0), config["d"]),
        }
    )
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        row,
        experiment="paper_fig2_az_grid",
        record_type="probe",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
    )


def invalid_probe(config: dict[str, Any], m_value: int, trials: int, phase: str, args: argparse.Namespace) -> dict[str, Any]:
    row = {
        "search_id": config["search_id"],
        "phase": phase,
        "candidate_M": m_value,
        "M": m_value,
        "m": m_value,
        "d": config["d"],
        "l": config["l"],
        "k": config["k"],
        "mode": "circular",
        "circular_a": float(config["circular_a"]),
        "z": int(config["z"]),
        "range_length": range_length(m_value, int(config["z"])),
        "target_success_rate": args.target_success_rate,
        "trials": trials,
        "successes": 0,
        "success_rate": 0.0,
        "bits": 0.0,
        "ci_low": 0.0,
        "ci_high": 0.0,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "ca": config["ca"],
        "cb": config["cb"],
        "seed": config["seed"],
        "status": "invalid",
        "invalid_reason": f"range_length < {args.min_range_length}",
    }
    return normalize_benchmark_row(
        row,
        experiment="paper_fig2_az_grid",
        record_type="probe",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        status="invalid",
        dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
    )


def works(row: dict[str, Any] | None, args: argparse.Namespace) -> bool:
    if row is None or row.get("status") != "ok":
        return False
    if args.threshold_policy == "point":
        return int(row["successes"]) >= required_successes(args.target_success_rate, int(row["trials"]))
    if args.threshold_policy == "ci-low":
        return float(row.get("ci_low", 0.0)) >= args.target_success_rate
    raise ValueError(f"unknown threshold policy: {args.threshold_policy}")


def find_best_m(
    binary: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    errors_path: Path,
    dataset_paths: list[Path] | None,
) -> tuple[int | None, list[dict[str, Any]], str]:
    probes: list[dict[str, Any]] = []
    limit = max_m(config, args.max_c_over_d)
    if range_length(limit, int(config["z"])) < args.min_range_length:
        return None, [invalid_probe(config, limit, args.probe_trials, "invalid_limit", args)], "invalid"

    hi = initial_upper_m(config)
    while hi <= limit:
        row = run_probe(binary, config, hi, args.probe_trials, "upper_bound", args, errors_path, dataset_paths)
        if row is not None:
            probes.append(row)
        if works(row, args):
            break
        hi *= 2
    else:
        return None, probes, "unresolved"

    lo = lower_bound_m(config)
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_probe(binary, config, mid, args.probe_trials, "binary_search", args, errors_path, dataset_paths)
        if row is not None:
            probes.append(row)
        if works(row, args):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best, probes, "ok"


def reaches_target(row: dict[str, Any], target: float) -> dict[str, bool]:
    return {
        "point_estimate_reaches_target": float(row.get("success_rate", 0.0)) >= target,
        "ci_low_reaches_target": float(row.get("ci_low", 0.0)) >= target,
        "ci_high_reaches_target": float(row.get("ci_high", 0.0)) >= target,
    }


def summary_from_final(
    config: dict[str, Any],
    final_row: dict[str, Any] | None,
    best_m: int | None,
    args: argparse.Namespace,
    status: str,
) -> dict[str, Any]:
    base = {
        "search_id": config["search_id"],
        "d": config["d"],
        "l": config["l"],
        "k": config["k"],
        "mode": "circular",
        "circular_a": float(config["circular_a"]),
        "z": int(config["z"]),
        "target_success_rate": args.target_success_rate,
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "threshold_policy": args.threshold_policy,
        "seed": config["seed"],
        "ca": config["ca"],
        "cb": config["cb"],
        "dedup_hashes": bool(config.get("dedup_hashes", False)),
        "dataset_mode": "shared_file" if args.shared_datasets else "internal_generator",
        "status": status,
    }
    if final_row is None or best_m is None:
        base.update(
            {
                "best_M": "",
                "best_C_over_d": "",
                "best_R_w30": "",
                "range_length_at_best_M": "",
                "final_successes": 0,
                "final_success_rate": 0.0,
                "final_ci_low": 0.0,
                "final_ci_high": 0.0,
                "trials": args.final_trials,
                "successes": 0,
                "success_rate": 0.0,
                "ci_low": 0.0,
                "ci_high": 0.0,
                "bits": 0.0,
                "encode_avg_s": 0.0,
                "decode_avg_s": 0.0,
                "encode_median_s": 0.0,
                "decode_median_s": 0.0,
                "dataset_dir": "",
                "point_estimate_reaches_target": False,
                "ci_low_reaches_target": False,
                "ci_high_reaches_target": False,
            }
        )
    else:
        base.update(
            {
                "M": best_m,
                "best_M": best_m,
                "best_C_over_d": c_over_d_for_m(config, best_m),
                "best_R_w30": r_w30_for_m(config, best_m),
                "range_length_at_best_M": range_length(best_m, int(config["z"])),
                "final_successes": final_row.get("successes", 0),
                "final_success_rate": final_row.get("success_rate", 0.0),
                "final_ci_low": final_row.get("ci_low", 0.0),
                "final_ci_high": final_row.get("ci_high", 0.0),
                **reaches_target(final_row, args.target_success_rate),
                "trials": final_row.get("trials", args.final_trials),
                "successes": final_row.get("successes", 0),
                "success_rate": final_row.get("success_rate", 0.0),
                "ci_low": final_row.get("ci_low", 0.0),
                "ci_high": final_row.get("ci_high", 0.0),
                "bits": final_row.get("bits", 0.0),
                "R_w30": final_row.get("R_w30", r_w30_for_m(config, best_m)),
                "bit_C_over_d": final_row.get("bit_C_over_d", ""),
                "encode_avg_s": final_row.get("encode_avg_s", 0.0),
                "decode_avg_s": final_row.get("decode_avg_s", 0.0),
                "encode_median_s": final_row.get("encode_median_s", 0.0),
                "decode_median_s": final_row.get("decode_median_s", 0.0),
                "dataset_dir": final_row.get("dataset_dir", ""),
            }
        )
    return normalize_benchmark_row(
        base,
        experiment="paper_fig2_az_grid",
        record_type="threshold",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        status=status,
        dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
    )


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
        handle.write("# Figure 2(a) a/z Grid Summary\n\n")
        handle.write("| d | k | l | a | z | M | R_w30 | success | CI low | status |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), int(item["k"]), int(item["l"]), float(item["circular_a"]), int(item["z"]))):
            handle.write(
                f"| {row.get('d', '')} | {row.get('k', '')} | {row.get('l', '')} | "
                f"{row.get('circular_a', '')} | {row.get('z', '')} | {row.get('best_M', '')} | "
                f"{row.get('best_R_w30', '')} | {row.get('final_success_rate', '')} | "
                f"{row.get('final_ci_low', '')} | {row.get('status', '')} |\n"
            )


def write_run_config(path: Path, args: argparse.Namespace, configs: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                "configs": configs,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


RESUME_ARG_KEYS = [
    "d_values",
    "l_values",
    "k_values",
    "a_values",
    "z_values",
    "probe_trials",
    "final_trials",
    "target_success_rate",
    "max_c_over_d",
    "min_range_length",
    "ci_confidence",
    "ci_method",
    "threshold_policy",
    "shared_datasets",
    "dataset_dir",
    "dedup_hashes",
    "base_seed",
    "max_set_size",
    "set_size_scale",
]


def comparable_arg_value(value: Any) -> Any:
    return str(value) if isinstance(value, Path) else value


def validate_resume_args(path: Path, args: argparse.Namespace) -> None:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        previous = json.load(handle).get("args", {})
    mismatches = []
    current = {key: comparable_arg_value(getattr(args, key)) for key in RESUME_ARG_KEYS}
    for key, value in current.items():
        if key in previous and previous[key] != value:
            mismatches.append((key, previous[key], value))
    if mismatches:
        detail = "; ".join(f"{key}: existing={old!r}, current={new!r}" for key, old, new in mismatches)
        raise SystemExit(
            "--resume refuses to mix different Figure 2 grid settings in one output directory. "
            f"Use a new --output-dir for the reduced run, or rerun with the original settings. Differences: {detail}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Figure 2(a) circular-a/z threshold grid.")
    parser.add_argument("--d-values", default="300")
    parser.add_argument("--l-values", default="6")
    parser.add_argument("--k-values", default="2")
    parser.add_argument("--a-values", default="0,0.3333333333,0.6")
    parser.add_argument("--z-values", default="0,1,2,3")
    parser.add_argument("--probe-trials", type=int, default=5)
    parser.add_argument("--final-trials", type=int, default=10)
    parser.add_argument("--target-success-rate", type=float, default=0.90)
    parser.add_argument("--max-C-over-d", type=float, default=8.0, dest="max_c_over_d")
    parser.add_argument("--min-range-length", type=int, default=2)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Skip cells already present in summary.jsonl and append remaining cells.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shared-datasets", action="store_true")
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--dedup-hashes", default="false")
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
    if args.max_c_over_d <= 0:
        raise SystemExit("--max-C-over-d must be positive")
    if args.min_range_length <= 0:
        raise SystemExit("--min-range-length must be positive")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    configs = make_configs(args)
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: a={config['circular_a']} z={config['z']} "
                f"lo={lower_bound_m(config)} hi0={initial_upper_m(config)} max={max_m(config, args.max_c_over_d)}"
            )
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    if args.resume:
        validate_resume_args(dirs["run_config"], args)
        summaries = read_jsonl(dirs["summary_jsonl"])
        completed_ids = {str(row.get("search_id")) for row in summaries if row.get("search_id") not in (None, "")}
        all_probes = [
            row
            for row in read_jsonl(dirs["probes"])
            if str(row.get("search_id")) in completed_ids
        ]
        print(f"[resume] completed={len(completed_ids)} remaining={len(configs) - len(completed_ids)}", flush=True)
    else:
        for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"], dirs["errors"]):
            if path.exists():
                path.unlink()
        all_probes: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
    write_run_config(dirs["run_config"], args, configs)

    for index, config in enumerate(configs, start=1):
        if args.resume and str(config["search_id"]) in completed_ids:
            print(f"[{index}/{len(configs)}] skip completed {config['search_id']}", flush=True)
            continue
        print(f"[{index}/{len(configs)}] {config['search_id']} a={config['circular_a']} z={config['z']}", flush=True)
        dataset_paths: list[Path] | None = None
        if args.shared_datasets:
            cache_key = (int(config["d"]), int(config["ca"]), int(config["cb"]), int(config["seed"]))
            if cache_key not in dataset_cache:
                dataset_config = DatasetConfig(
                    d=int(config["d"]),
                    ca=int(config["ca"]),
                    cb=int(config["cb"]),
                    seed=int(config["seed"]),
                )
                dataset_cache[cache_key] = prepare_datasets(
                    dataset_config,
                    max(args.probe_trials, args.final_trials),
                    dataset_dir,
                )
            dataset_paths = dataset_cache[cache_key]

        best_m, probes, search_status = find_best_m(binary, config, args, dirs["errors"], dataset_paths)
        all_probes.extend(probes)
        final_row = None
        status = search_status
        if best_m is not None:
            final_row = run_probe(binary, config, best_m, args.final_trials, "final_validate", args, dirs["errors"], dataset_paths)
            if final_row is not None:
                all_probes.append(final_row)
            status = "ok" if works(final_row, args) else "unresolved"
        summary = summary_from_final(config, final_row, best_m, args, status)
        summaries.append(summary)
        print(
            f"  status={summary['status']} M={summary.get('best_M', '')} "
            f"R={summary.get('best_R_w30', '')} success={summary.get('final_success_rate', '')}",
            flush=True,
        )
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
