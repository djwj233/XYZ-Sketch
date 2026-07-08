#!/usr/bin/env python3
"""Compare XYZ-v2 spatial-coupling modes by searching best M."""

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
from xyz_tuning import add_tuning_arguments, a_from_args, z_from_args


SUMMARY_FIELDS = [
    "search_id",
    "d",
    "l",
    "k",
    "mode",
    "best_M",
    "best_C_over_d",
    "best_R_w30",
    "z_at_best_M",
    "target_success_rate",
    "required_probe_successes",
    "required_final_successes",
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
    "point_best_M",
    "point_best_C_over_d",
    "point_best_R_w30",
    "ci_low_best_M",
    "ci_low_best_C_over_d",
    "ci_low_best_R_w30",
    "uncertain_M_min",
    "uncertain_M_max",
    "uncertain_C_over_d_min",
    "uncertain_C_over_d_max",
    "uncertain_R_w30_min",
    "uncertain_R_w30_max",
    "encode_avg_s",
    "decode_avg_s",
    "status",
    "seed",
    "ca",
    "cb",
    "dedup_hashes",
    "circular_a",
    "dataset_mode",
    "dataset_dir",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "spatial"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "spatial"
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "tmp": tmp,
        "probes": base / "probes.jsonl",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
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

    source = root / "tests" / "benchmarks" / "xyz_v2_bench.cpp"
    command = ["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)]
    subprocess.run(command, cwd=root, check=True)
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


def dedup_suffix(dedup_hashes: bool, include: bool) -> str:
    return f"_dedup{1 if dedup_hashes else 0}" if include else ""


def variant_name(config: dict[str, Any]) -> str:
    variant = str(config["mode"])
    if config.get("dedup_variant_suffix"):
        variant += f",dedup={str(bool(config.get('dedup_hashes', False))).lower()}"
    return variant


def modes_for_k(k_value: int, requested_modes: list[str] | None, include_diagnostic_circular: bool) -> list[str]:
    if requested_modes:
        return requested_modes
    if k_value <= 2:
        return ["random", "circular", "naive"]
    modes = ["random", "naive"]
    if include_diagnostic_circular:
        modes.append("circular")
    return modes


def make_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    d_values = parse_int_list(args.d_values)
    l_values = parse_int_list(args.l_values)
    k_values = parse_int_list(args.k_values)
    requested_modes = parse_str_list(args.modes) if args.modes else None
    valid_modes = {"random", "circular", "naive", "spatial"}
    dedup_values = parse_bool_list(args.dedup_hashes)
    include_dedup_suffix = len(dedup_values) > 1 or any(dedup_values)

    configs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
                for mode_index, mode in enumerate(modes_for_k(k_value, requested_modes, args.include_diagnostic_circular)):
                    if mode not in valid_modes:
                        raise SystemExit(f"unknown mode: {mode}")
                    for dedup_hashes in dedup_values:
                        seed = (
                            args.base_seed
                            + 1_000_000 * d_index
                            + 10_000 * l_index
                            + 100 * k_index
                            + (0 if args.shared_datasets else mode_index)
                        )
                        configs.append(
                            {
                                "search_id": f"d{d_value}_l{l_value}_k{k_value}_{mode}{dedup_suffix(dedup_hashes, include_dedup_suffix)}",
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


def choose_z(mode: str, m_value: int, config: dict[str, Any], args: argparse.Namespace) -> int:
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


def initial_upper_m(config: dict[str, Any]) -> int:
    return max(
        lower_bound_m(config),
        math.ceil(initial_factor(str(config["mode"]), int(config["k"])) * int(config["d"]) / int(config["l"])),
    )


def max_m(config: dict[str, Any], max_c_over_d: float) -> int:
    return max(lower_bound_m(config), math.ceil(max_c_over_d * int(config["d"]) / int(config["l"])))


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def c_over_d_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value is None or m_value == "":
        return ""
    return int(m_value) * int(config["l"]) / int(config["d"])


def r_w30_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value is None or m_value == "":
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


def reaches_target(row: dict[str, Any], target: float) -> dict[str, bool]:
    return {
        "point_estimate_reaches_target": float(row.get("success_rate", 0.0)) >= target,
        "ci_low_reaches_target": float(row.get("ci_low", 0.0)) >= target,
        "ci_high_reaches_target": float(row.get("ci_high", 0.0)) >= target,
    }


def threshold_rollup(config: dict[str, Any], probes: list[dict[str, Any]], target: float) -> dict[str, Any]:
    candidates = [
        row
        for row in probes
        if row is not None and row.get("status") == "ok" and row.get("candidate_M") not in (None, "")
    ]
    point_ms = [int(row["candidate_M"]) for row in candidates if float(row.get("success_rate", 0.0)) >= target]
    ci_low_ms = [int(row["candidate_M"]) for row in candidates if float(row.get("ci_low", 0.0)) >= target]
    uncertain_ms = [
        int(row["candidate_M"])
        for row in candidates
        if float(row.get("ci_low", 0.0)) < target <= float(row.get("ci_high", 0.0))
    ]
    point_best_m = min(point_ms) if point_ms else ""
    ci_low_best_m = min(ci_low_ms) if ci_low_ms else ""
    uncertain_min = min(uncertain_ms) if uncertain_ms else ""
    uncertain_max = max(uncertain_ms) if uncertain_ms else ""
    return {
        "point_best_M": point_best_m,
        "point_best_C_over_d": c_over_d_for_m(config, point_best_m),
        "point_best_R_w30": r_w30_for_m(config, point_best_m),
        "ci_low_best_M": ci_low_best_m,
        "ci_low_best_C_over_d": c_over_d_for_m(config, ci_low_best_m),
        "ci_low_best_R_w30": r_w30_for_m(config, ci_low_best_m),
        "uncertain_M_min": uncertain_min,
        "uncertain_M_max": uncertain_max,
        "uncertain_C_over_d_min": c_over_d_for_m(config, uncertain_min),
        "uncertain_C_over_d_max": c_over_d_for_m(config, uncertain_max),
        "uncertain_R_w30_min": r_w30_for_m(config, uncertain_min),
        "uncertain_R_w30_max": r_w30_for_m(config, uncertain_max),
    }


def command_for(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    z_value: int,
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
        str(z_value),
        "--trials",
        str(trials),
        "--seed",
        str(seed),
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
    seed: int,
    phase: str,
    args: argparse.Namespace,
    errors_path: Path,
    dataset_paths: list[Path] | None = None,
) -> dict[str, Any] | None:
    z_value = choose_z(str(config["mode"]), m_value, config, args)
    if args.shared_datasets:
        if dataset_paths is None:
            raise ValueError("dataset_paths are required when --shared-datasets is enabled")
        trial_rows: list[dict[str, Any]] = []
        for dataset in dataset_paths[:trials]:
            command = command_for(binary, config, m_value, z_value, 1, seed, dataset=dataset)
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
        command = command_for(binary, config, m_value, z_value, trials, seed)
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
            "z_at_candidate_M": z_value,
            "R_w30": r_w30_from_bits(row.get("bits", 0), config["d"]),
            "circular_a": float(config.get("circular_a", 1.0 / 3.0)),
        }
    )
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        row,
        experiment="spatial_threshold",
        record_type="probe",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
    )


def works(row: dict[str, Any] | None, args: argparse.Namespace) -> bool:
    if row is None:
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
    dataset_paths: list[Path] | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    hi = initial_upper_m(config)
    limit = max_m(config, args.max_c_over_d)

    while hi <= limit:
        row = run_probe(binary, config, hi, args.probe_trials, int(config["seed"]), "upper_bound", args, errors_path, dataset_paths)
        if row is not None:
            probes.append(row)
        if works(row, args):
            break
        hi *= 2
    else:
        return None, probes

    lo = lower_bound_m(config)
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_probe(binary, config, mid, args.probe_trials, int(config["seed"]), "binary_search", args, errors_path, dataset_paths)
        if row is not None:
            probes.append(row)
        if works(row, args):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return best, probes


def final_validate(
    binary: Path,
    config: dict[str, Any],
    best_m: int,
    args: argparse.Namespace,
    errors_path: Path,
    dataset_paths: list[Path] | None = None,
) -> dict[str, Any] | None:
    return run_probe(binary, config, best_m, args.final_trials, int(config["seed"]), "final_validate", args, errors_path, dataset_paths)


def summary_from_final(
    config: dict[str, Any],
    final_row: dict[str, Any] | None,
    best_m: int | None,
    args: argparse.Namespace,
    status: str,
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    rollup = threshold_rollup(config, probes, args.target_success_rate)
    base = {
        "search_id": config["search_id"],
        "d": config["d"],
        "l": config["l"],
        "k": config["k"],
        "mode": config["mode"],
        "target_success_rate": args.target_success_rate,
        "required_probe_successes": required_successes(args.target_success_rate, args.probe_trials),
        "required_final_successes": required_successes(args.target_success_rate, args.final_trials),
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "threshold_policy": args.threshold_policy,
        "status": status,
        "seed": config["seed"],
        "ca": config["ca"],
        "cb": config["cb"],
        "dedup_hashes": bool(config.get("dedup_hashes", False)),
        "circular_a": float(config.get("circular_a", 1.0 / 3.0)),
        "dataset_mode": "shared_file" if args.shared_datasets else "internal_generator",
        **rollup,
    }
    if final_row is None or best_m is None:
        base.update(
            {
                "best_M": "",
                "best_C_over_d": "",
                "best_R_w30": "",
                "z_at_best_M": "",
                "final_successes": "",
                "final_success_rate": "",
                "final_ci_low": "",
                "final_ci_high": "",
                "point_estimate_reaches_target": False,
                "ci_low_reaches_target": False,
                "ci_high_reaches_target": False,
                "encode_avg_s": "",
                "decode_avg_s": "",
                "dataset_dir": "",
            }
        )
        return normalize_benchmark_row(
            base,
            experiment="spatial_threshold",
            record_type="threshold",
            algorithm="xyz_v2",
            variant=variant_name(config),
            implementation="local/XYZ-v2",
            dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
        )

    base.update(
        {
            "M": best_m,
            "best_M": best_m,
            "best_C_over_d": best_m * int(config["l"]) / int(config["d"]),
            "best_R_w30": r_w30_for_m(config, best_m),
            "z_at_best_M": choose_z(str(config["mode"]), best_m, config, args),
            "final_successes": final_row["successes"],
            "final_success_rate": final_row["success_rate"],
            "final_ci_low": final_row.get("ci_low", ""),
            "final_ci_high": final_row.get("ci_high", ""),
            **reaches_target(final_row, args.target_success_rate),
            "trials": final_row.get("trials", args.final_trials),
            "successes": final_row.get("successes", 0),
            "success_rate": final_row.get("success_rate", 0.0),
            "ci_low": final_row.get("ci_low", ""),
            "ci_high": final_row.get("ci_high", ""),
            "bits": final_row.get("bits", 0),
            "bit_C_over_d": final_row.get("bit_C_over_d", ""),
            "encode_avg_s": final_row["encode_avg_s"],
            "decode_avg_s": final_row["decode_avg_s"],
            "encode_median_s": final_row.get("encode_median_s", 0.0),
            "decode_median_s": final_row.get("decode_median_s", 0.0),
            "dataset_dir": final_row.get("dataset_dir", ""),
        }
    )
    return normalize_benchmark_row(
        base,
        experiment="spatial_threshold",
        record_type="threshold",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode="shared_file" if args.shared_datasets else "internal_generator",
        status=status,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare XYZ-v2 spatial-coupling modes.")
    parser.add_argument("--d-values", default="1000,3000,10000")
    parser.add_argument("--l-values", default="4,6,8")
    parser.add_argument("--k-values", default="2,3")
    parser.add_argument("--modes", default=None, help="Comma-separated modes. Defaults depend on k.")
    parser.add_argument("--include-diagnostic-circular", action="store_true")
    parser.add_argument("--probe-trials", type=int, default=30)
    parser.add_argument("--final-trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.95)
    parser.add_argument("--max-C-over-d", type=float, default=8.0, dest="max_c_over_d")
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--shared-datasets", action="store_true")
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-datasets", action="store_true")
    parser.add_argument("--dedup-hashes", default="false")
    parser.add_argument("--circular-a", type=float, default=None, help="Override circular a. By default use a_{k,l}=C*c_orient/c_peel.")
    add_tuning_arguments(parser)
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
    if args.circular_a is not None and not (0.0 <= args.circular_a < 1.0):
        raise SystemExit("--circular-a must be in [0, 1)")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    configs = make_grid(args)
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: mode={config['mode']} lo={lower_bound_m(config)} "
                f"hi0={initial_upper_m(config)} max={max_m(config, args.max_c_over_d)}"
            )
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["errors"]):
        if path.exists():
            path.unlink()

    all_probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for index, config in enumerate(configs, start=1):
        print(f"[{index}/{len(configs)}] {config['search_id']}", flush=True)
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

        best_m, probes = find_best_m(binary, config, args, dirs["errors"], dataset_paths)
        all_probes.extend(probes)
        if best_m is None:
            print("  unresolved", flush=True)
            summaries.append(summary_from_final(config, None, None, args, "unresolved", probes))
        else:
            final_row = final_validate(binary, config, best_m, args, dirs["errors"], dataset_paths)
            current_probes = list(probes)
            if final_row is not None:
                all_probes.append(final_row)
                current_probes.append(final_row)
            status = "ok" if works(final_row, args) else "unresolved"
            summary = summary_from_final(config, final_row, best_m, args, status, current_probes)
            summaries.append(summary)
            print(
                f"  best_M={summary['best_M']} C/d={summary['best_C_over_d']:.3f} "
                f"success={summary['final_success_rate']} status={status}",
                flush=True,
            )

        write_jsonl(dirs["probes"], all_probes)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_summary_csv(dirs["summary_csv"], summaries)

    print(f"wrote {dirs['probes']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    if args.shared_datasets and not args.keep_datasets:
        # Keep files by default in tests/tmp for auditability during development.
        # This flag is reserved for a later cleanup pass.
        pass


if __name__ == "__main__":
    main()
