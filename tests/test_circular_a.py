#!/usr/bin/env python3
"""Scan the circular spatial-coupling parameter a for XYZ-v2."""

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
    "M",
    "z",
    "circular_a",
    "best_M",
    "best_C_over_d",
    "target_success_rate",
    "trials",
    "probe_trials",
    "final_trials",
    "successes",
    "success_rate",
    "ci_low",
    "ci_high",
    "final_successes",
    "final_success_rate",
    "final_ci_low",
    "final_ci_high",
    "bits",
    "bit_C_over_d",
    "range_length",
    "circular_base_range",
    "threshold_policy",
    "ci_method",
    "ci_confidence",
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
    base = output_dir or root / "tests" / "results" / "circular_a"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "circular_a"
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "tmp": tmp,
        "raw_jsonl": base / "raw.jsonl",
        "raw_csv": base / "raw.csv",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "errors": base / "errors.log",
        "run_config": base / "run_config.json",
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
    out: list[float] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            num, den = part.split("/", 1)
            out.append(float(num) / float(den))
        else:
            out.append(float(part))
    return out


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
    variant = f"circular_a={float(config['circular_a']):.6g}"
    if config.get("dedup_variant_suffix"):
        variant += f",dedup={str(bool(config.get('dedup_hashes', False))).lower()}"
    return variant


def choose_m(d_value: int, l_value: int, k_value: int) -> int:
    if k_value == 3:
        target = 1.668
    elif k_value >= 4:
        target = 1.782
    elif d_value <= 100:
        target = 1.60
    elif d_value <= 1000:
        target = 1.30
    elif d_value <= 10000:
        target = 1.20
    else:
        target = 1.10
    return max(1, math.ceil(target * d_value / l_value))


def choose_z(m_value: int) -> int:
    return max(0, round((m_value ** (1.0 / 3.0)) / 3.0))


def make_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    d_values = parse_int_list(args.d_values)
    l_values = parse_int_list(args.l_values)
    k_values = parse_int_list(args.k_values)
    a_values = parse_float_list(args.a_values)
    m_values = parse_int_list(args.m_values) if args.m_values else []
    dedup_values = parse_bool_list(args.dedup_hashes)
    include_dedup_suffix = len(dedup_values) > 1 or any(dedup_values)
    configs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
                for a_index, circular_a in enumerate(a_values):
                    for dedup_hashes in dedup_values:
                        seed = (
                            args.base_seed
                            + 1_000_000 * d_index
                            + 10_000 * l_index
                            + 100 * k_index
                            + (0 if args.shared_datasets else a_index)
                        )
                        exact_m = m_values[0] if len(m_values) == 1 else None
                        if len(m_values) > 1:
                            exact_m = m_values[min(a_index, len(m_values) - 1)]
                        if exact_m is None:
                            exact_m = choose_m(d_value, l_value, k_value)
                        configs.append(
                            {
                                "search_id": f"d{d_value}_l{l_value}_k{k_value}_a{circular_a:.6g}{dedup_suffix(dedup_hashes, include_dedup_suffix)}",
                                "d": d_value,
                                "l": l_value,
                                "k": k_value,
                                "mode": "circular",
                                "M": exact_m,
                                "z": choose_z(exact_m),
                                "circular_a": circular_a,
                                "dedup_hashes": dedup_hashes,
                                "dedup_variant_suffix": include_dedup_suffix,
                                "seed": seed,
                                "ca": ca,
                                "cb": cb,
                            }
                        )
    return configs


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def lower_bound_m(config: dict[str, Any]) -> int:
    return max(int(config["k"]), math.ceil(int(config["d"]) / int(config["l"])), 1)


def initial_upper_m(config: dict[str, Any]) -> int:
    return max(lower_bound_m(config), math.ceil(1.5 * int(config["d"]) / int(config["l"])))


def max_m(config: dict[str, Any], max_c_over_d: float) -> int:
    return max(lower_bound_m(config), math.ceil(max_c_over_d * int(config["d"]) / int(config["l"])))


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
        str(choose_z(m_value)),
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
    if args.shared_datasets:
        if dataset_paths is None:
            raise ValueError("dataset_paths are required when --shared-datasets is enabled")
        trial_rows: list[dict[str, Any]] = []
        for dataset in dataset_paths[:trials]:
            command = command_for(binary, config, m_value, 1, seed, dataset=dataset)
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
        command = command_for(binary, config, m_value, trials, seed)
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
        }
    )
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        row,
        experiment="circular_a",
        record_type="probe" if phase != "fixed_m" else "aggregate",
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


def summary_from_fixed(row: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    summary = dict(row)
    summary.update(
        {
            "record_type": "aggregate",
            "search_id": config["search_id"],
            "best_M": "",
            "best_C_over_d": "",
            "final_successes": "",
            "final_success_rate": "",
            "final_ci_low": "",
            "final_ci_high": "",
        }
    )
    return normalize_benchmark_row(
        summary,
        experiment="circular_a",
        record_type="aggregate",
        algorithm="xyz_v2",
        variant=variant_name(config),
        implementation="local/XYZ-v2",
        dataset_mode=str(row.get("dataset_mode", "internal_generator")),
    )


def summary_from_threshold(
    config: dict[str, Any],
    final_row: dict[str, Any] | None,
    best_m: int | None,
    args: argparse.Namespace,
    status: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "search_id": config["search_id"],
        "d": config["d"],
        "l": config["l"],
        "k": config["k"],
        "mode": "circular",
        "circular_a": config["circular_a"],
        "target_success_rate": args.target_success_rate,
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "threshold_policy": args.threshold_policy,
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
        "status": status,
        "seed": config["seed"],
        "ca": config["ca"],
        "cb": config["cb"],
        "dedup_hashes": bool(config.get("dedup_hashes", False)),
        "dataset_mode": "shared_file" if args.shared_datasets else "internal_generator",
    }
    if final_row is None or best_m is None:
        base.update({"best_M": "", "best_C_over_d": "", "final_successes": "", "final_success_rate": "", "final_ci_low": "", "final_ci_high": "", "bits": 0})
    else:
        base.update(
            {
                "M": best_m,
                "z": choose_z(best_m),
                "best_M": best_m,
                "best_C_over_d": best_m * int(config["l"]) / int(config["d"]),
                "final_successes": final_row["successes"],
                "final_success_rate": final_row["success_rate"],
                "final_ci_low": final_row.get("ci_low", ""),
                "final_ci_high": final_row.get("ci_high", ""),
                "trials": final_row.get("trials", args.final_trials),
                "successes": final_row.get("successes", 0),
                "success_rate": final_row.get("success_rate", 0.0),
                "ci_low": final_row.get("ci_low", ""),
                "ci_high": final_row.get("ci_high", ""),
                "bits": final_row.get("bits", 0),
                "bit_C_over_d": final_row.get("bit_C_over_d", ""),
                "range_length": final_row.get("range_length", ""),
                "circular_base_range": final_row.get("circular_base_range", ""),
                "encode_avg_s": final_row.get("encode_avg_s", 0.0),
                "decode_avg_s": final_row.get("decode_avg_s", 0.0),
                "encode_median_s": final_row.get("encode_median_s", 0.0),
                "decode_median_s": final_row.get("decode_median_s", 0.0),
                "dataset_dir": final_row.get("dataset_dir", ""),
            }
        )
    return normalize_benchmark_row(
        base,
        experiment="circular_a",
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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(SUMMARY_FIELDS)
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Circular a Summary\n\n")
        handle.write("| d | l | k | a | M | success | CI | C/d | status |\n")
        handle.write("|---:|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for row in rows:
            m_value = row.get("best_M") or row.get("M") or ""
            c_over_d = row.get("best_C_over_d") or row.get("bit_C_over_d") or ""
            success = row.get("final_success_rate") or row.get("success_rate") or ""
            ci = ""
            lo = row.get("final_ci_low") or row.get("ci_low")
            hi = row.get("final_ci_high") or row.get("ci_high")
            if lo != "" and hi != "":
                ci = f"[{float(lo):.3f}, {float(hi):.3f}]"
            handle.write(
                f"| {row.get('d', '')} | {row.get('l', '')} | {row.get('k', '')} | "
                f"{float(row.get('circular_a', 0.0)):.6g} | {m_value} | {success} | {ci} | {c_over_d} | {row.get('status', '')} |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan XYZ-v2 circular spatial-coupling parameter a.")
    parser.add_argument("--mode", choices=["fixed-m", "threshold"], default="fixed-m")
    parser.add_argument("--d-values", default="1000")
    parser.add_argument("--l-values", default="6")
    parser.add_argument("--k-values", default="2")
    parser.add_argument("--a-values", default="0,0.1,0.2,1/3,0.4,0.5,0.6,0.75,0.9")
    parser.add_argument("--m-values", default=None)
    parser.add_argument("--trials", type=int, default=50)
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
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials <= 0 or args.probe_trials <= 0 or args.final_trials <= 0:
        raise SystemExit("trial counts must be positive")
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    for circular_a in parse_float_list(args.a_values):
        if not (0.0 <= circular_a < 1.0):
            raise SystemExit("--a-values must all be in [0, 1)")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    configs = make_grid(args)
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            if args.mode == "fixed-m":
                print(f"{config['search_id']}: M={config['M']} z={config['z']} seed={config['seed']}")
            else:
                print(f"{config['search_id']}: lo={lower_bound_m(config)} hi0={initial_upper_m(config)} max={max_m(config, args.max_c_over_d)}")
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    for key in ("raw_jsonl", "raw_csv", "summary_jsonl", "summary_csv", "summary_md", "errors"):
        if dirs[key].exists():
            dirs[key].unlink()

    raw_rows: list[dict[str, Any]] = []
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
                    max(args.trials, args.probe_trials, args.final_trials),
                    dataset_dir,
                )
            dataset_paths = dataset_cache[cache_key]

        if args.mode == "fixed-m":
            row = run_probe(binary, config, int(config["M"]), args.trials, int(config["seed"]), "fixed_m", args, dirs["errors"], dataset_paths)
            if row is None:
                continue
            raw_rows.append(row)
            summaries.append(summary_from_fixed(row, config))
            print(f"  M={config['M']} success_rate={row['success_rate']:.3f}", flush=True)
        else:
            best_m, probes = find_best_m(binary, config, args, dirs["errors"], dataset_paths)
            raw_rows.extend(probes)
            if best_m is None:
                summaries.append(summary_from_threshold(config, None, None, args, "unresolved"))
                print("  unresolved", flush=True)
            else:
                final_row = run_probe(binary, config, best_m, args.final_trials, int(config["seed"]), "final_validate", args, dirs["errors"], dataset_paths)
                if final_row is not None:
                    raw_rows.append(final_row)
                status = "ok" if works(final_row, args) else "unresolved"
                summary = summary_from_threshold(config, final_row, best_m, args, status)
                summaries.append(summary)
                print(f"  best_M={summary.get('best_M')} C/d={summary.get('best_C_over_d')} status={status}", flush=True)

        write_jsonl(dirs["raw_jsonl"], raw_rows)
        write_csv(dirs["raw_csv"], raw_rows)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_csv(dirs["summary_csv"], summaries)
        write_summary_md(dirs["summary_md"], summaries)

    with dirs["run_config"].open("w", encoding="utf-8") as handle:
        json.dump(vars(args), handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")

    print(f"wrote {dirs['raw_jsonl']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_md']}")
    if args.shared_datasets and not args.keep_datasets:
        # Keep files by default in tests/tmp for auditability during development.
        # This flag is reserved for a later cleanup pass.
        pass


if __name__ == "__main__":
    main()
