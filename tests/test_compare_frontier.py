#!/usr/bin/env python3
"""Paper Figure 3 frontier comparison across practical baselines."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from dataset_generator import DatasetConfig, choose_set_sizes, prepare_datasets
from json_schema import normalize_benchmark_row
from statistics import add_binomial_ci, normal_z
from test_compare_basic import build_binaries


SUPPORTED_ALGORITHMS = {"xyz_v2", "iblt", "minisketch"}

SUMMARY_FIELDS = [
    "algorithm",
    "variant",
    "implementation",
    "d",
    "ca",
    "cb",
    "best_parameter_name",
    "best_parameter",
    "best_bits",
    "best_R_w30",
    "best_bit_C_over_d",
    "target_success_rate",
    "probe_trials",
    "final_trials",
    "final_successes",
    "final_success_rate",
    "final_ci_low",
    "final_ci_high",
    "threshold_policy",
    "update_avg_s_per_element",
    "update_denominator",
    "update_metric_policy",
    "decode_avg_s_per_difference",
    "decode_denominator",
    "decode_metric_policy",
    "encode_avg_s",
    "decode_avg_s",
    "status",
    "dataset_mode",
    "dataset_dir",
    "seed",
    "xyz_circular_a",
    "xyz_z",
    "xyz_tuning_source",
    "xyz_tuning_d",
    "unavailable_reason",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "paper_fig3_compare_frontier"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "paper_fig3_compare_frontier"
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


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def r_w30(bits: Any, d_value: Any) -> float:
    d_float = float(d_value)
    return float(bits) / (30.0 * d_float) if d_float > 0 else 0.0


def choose_z(m_value: int) -> int:
    return max(0, round((int(m_value) ** (1.0 / 3.0)) / 3.0))


def read_xyz_tuning(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") == "ok" and row.get("a_star") not in (None, "") and row.get("z_star") not in (None, ""):
                rows.append(row)
    return rows


def tuning_for_d(tuning_rows: list[dict[str, Any]], d_value: int) -> dict[str, Any] | None:
    if not tuning_rows:
        return None
    exact = [row for row in tuning_rows if int(row.get("d", -1)) == d_value]
    if exact:
        return exact[0]
    smaller = [row for row in tuning_rows if int(row.get("d", -1)) <= d_value]
    if smaller:
        return max(smaller, key=lambda row: int(row["d"]))
    return min(tuning_rows, key=lambda row: abs(int(row["d"]) - d_value))


def make_jobs(args: argparse.Namespace) -> list[dict[str, Any]]:
    algorithms = parse_str_list(args.algorithms)
    unknown = set(algorithms) - SUPPORTED_ALGORITHMS
    if unknown:
        raise SystemExit(f"unsupported algorithms for first frontier version: {', '.join(sorted(unknown))}")
    d_values = parse_int_list(args.d_values)
    tuning_rows = read_xyz_tuning(args.xyz_tuning)
    jobs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
        seed = args.base_seed + 1_000_000 * d_index
        for algorithm in algorithms:
            base = {
                "algorithm": algorithm,
                "d": d_value,
                "ca": ca,
                "cb": cb,
                "seed": seed,
                "probe_trials": args.probe_trials,
                "final_trials": args.final_trials,
            }
            if algorithm == "xyz_v2":
                tuning = tuning_for_d(tuning_rows, d_value)
                circular_a = float(tuning["a_star"]) if tuning is not None else args.xyz_circular_a
                fixed_z = int(tuning["z_star"]) if tuning is not None else None
                base.update(
                    {
                        "variant": "circular,tuned" if tuning is not None else "circular,heuristic-z",
                        "parameter_name": "M",
                        "l": args.xyz_l,
                        "k": args.xyz_k,
                        "mode": "circular",
                        "circular_a": circular_a,
                        "fixed_z": fixed_z,
                        "xyz_tuning_source": str(args.xyz_tuning) if tuning is not None else "",
                        "xyz_tuning_d": int(tuning["d"]) if tuning is not None else "",
                    }
                )
            elif algorithm == "iblt":
                base.update({"variant": "capacity_search", "parameter_name": "cells"})
            elif algorithm == "minisketch":
                base.update(
                    {
                        "variant": f"capacity_search,field_bits={args.minisketch_field_bits}",
                        "parameter_name": "capacity",
                        "field_bits": args.minisketch_field_bits,
                    }
                )
            jobs.append(base)
    if args.limit is not None:
        jobs = jobs[: args.limit]
    return jobs


def lower_bound(job: dict[str, Any]) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_v2":
        return max(1, math.ceil(d_value / int(job["l"])), int(job["k"]))
    return 1


def initial_upper(job: dict[str, Any]) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_v2":
        return max(lower_bound(job), math.ceil(1.5 * d_value / int(job["l"])))
    if job["algorithm"] == "iblt":
        return max(1, math.ceil(1.5 * d_value))
    if job["algorithm"] == "minisketch":
        return max(1, d_value)
    raise ValueError(f"unknown algorithm: {job['algorithm']}")


def max_parameter(job: dict[str, Any], max_factor: float) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_v2":
        return max(lower_bound(job), math.ceil(max_factor * d_value / int(job["l"])))
    return max(1, math.ceil(max_factor * d_value))


def parameter_to_command_fields(job: dict[str, Any], parameter: int) -> dict[str, Any]:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_v2":
        z_value = int(job["fixed_z"]) if job.get("fixed_z") not in (None, "") else choose_z(parameter)
        return {"M": parameter, "z": z_value}
    if job["algorithm"] in {"iblt", "minisketch"}:
        return {"capacity_factor": float(parameter) / float(d_value), "capacity": parameter}
    raise ValueError(f"unknown algorithm: {job['algorithm']}")


def command_for(binary: Path, job: dict[str, Any], parameter: int, dataset: Path) -> list[str]:
    fields = parameter_to_command_fields(job, parameter)
    common = [
        str(binary),
        "--d",
        str(job["d"]),
        "--trials",
        "1",
        "--seed",
        str(job["seed"]),
        "--ca",
        str(job["ca"]),
        "--cb",
        str(job["cb"]),
    ]
    if job["algorithm"] == "xyz_v2":
        command = common + [
            "--l",
            str(job["l"]),
            "--k",
            str(job["k"]),
            "--m",
            str(fields["M"]),
            "--z",
            str(fields["z"]),
            "--mode",
            str(job["mode"]),
            "--circular-a",
            f"{float(job['circular_a']):.12g}",
        ]
    elif job["algorithm"] == "iblt":
        command = common + ["--capacity-factor", f"{float(fields['capacity_factor']):.12g}"]
    elif job["algorithm"] == "minisketch":
        command = common + [
            "--capacity-factor",
            f"{float(fields['capacity_factor']):.12g}",
            "--field-bits",
            str(job["field_bits"]),
        ]
    else:
        raise ValueError(f"unknown algorithm: {job['algorithm']}")
    command.extend(["--dataset", str(dataset), "--format", "jsonl"])
    return command


def append_error(path: Path, job: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("JOB " + json.dumps(job, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def parse_benchmark_output(command: list[str], job: dict[str, Any], completed: subprocess.CompletedProcess[str], errors_path: Path) -> dict[str, Any] | None:
    if completed.returncode != 0:
        append_error(
            errors_path,
            job,
            command,
            f"RETURNCODE {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        )
        return None
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        append_error(errors_path, job, command, f"PARSE got {len(lines)} lines\n{completed.stdout}")
        return None
    try:
        return json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, job, command, f"JSONERROR {exc}\n{completed.stdout}")
        return None


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def normalize_probe_row(row: dict[str, Any], job: dict[str, Any], parameter: int, args: argparse.Namespace, dataset_dir: Path) -> dict[str, Any]:
    row = dict(row)
    row["algorithm"] = job["algorithm"]
    row["variant"] = job["variant"]
    row["candidate_parameter"] = parameter
    row["candidate_parameter_name"] = job["parameter_name"]
    row["target_success_rate"] = args.target_success_rate
    row["required_successes"] = required_successes(args.target_success_rate, int(row.get("trials", 1)))
    row["dataset_mode"] = "shared_file"
    row["dataset_dir"] = str(dataset_dir)
    row["seed"] = job["seed"]
    row.setdefault("ca", job["ca"])
    row.setdefault("cb", job["cb"])
    row["R_w30"] = r_w30(row.get("bits", 0.0), job["d"])
    if job["algorithm"] == "xyz_v2":
        row["xyz_circular_a"] = float(job["circular_a"])
        row["xyz_z"] = int(parameter_to_command_fields(job, parameter)["z"])
        row["xyz_tuning_source"] = job.get("xyz_tuning_source", "")
        row["xyz_tuning_d"] = job.get("xyz_tuning_d", "")
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        row,
        experiment="paper_fig3_compare_frontier",
        record_type="probe",
        algorithm=str(job["algorithm"]),
        variant=str(job["variant"]),
        dataset_mode="shared_file",
    )


def run_candidate(
    binaries: dict[str, Path],
    job: dict[str, Any],
    parameter: int,
    dataset_paths: list[Path],
    trials: int,
    args: argparse.Namespace,
    errors_path: Path,
) -> dict[str, Any]:
    binary = binaries[job["algorithm"]]
    trial_rows: list[dict[str, Any]] = []
    for dataset in dataset_paths[:trials]:
        command = command_for(binary, job, parameter, dataset)
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError as exc:
            append_error(errors_path, job, command, f"OSERROR {exc}")
            continue
        parsed = parse_benchmark_output(command, job, completed, errors_path)
        if parsed is not None:
            trial_rows.append(parsed)

    valid_rows = [row for row in trial_rows if row.get("status", "ok") in {"ok", "failed_decode"}]
    if not valid_rows:
        row = {
            "algorithm": job["algorithm"],
            "variant": job["variant"],
            "d": job["d"],
            "ca": job["ca"],
            "cb": job["cb"],
            "seed": job["seed"],
            "trials": trials,
            "successes": 0,
            "success_rate": 0.0,
            "bits": 0.0,
            "status": "benchmark_error",
            "encode_avg_s": 0.0,
            "decode_avg_s": 0.0,
            "encode_median_s": 0.0,
            "decode_median_s": 0.0,
        }
        return normalize_probe_row(row, job, parameter, args, dataset_paths[0].parent)

    successes = sum(int(row.get("successes", 0)) for row in valid_rows)
    aggregate = dict(valid_rows[0])
    aggregate["trials"] = len(valid_rows)
    aggregate["attempted_trials"] = trials
    aggregate["completed_trials"] = len(valid_rows)
    aggregate["error_trials"] = max(0, trials - len(valid_rows))
    aggregate["successes"] = successes
    aggregate["success_rate"] = successes / float(len(valid_rows))
    aggregate["status"] = "ok"
    aggregate["encode_avg_s"] = sum(float(row.get("encode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    aggregate["decode_avg_s"] = sum(float(row.get("decode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    aggregate["encode_median_s"] = median([float(row.get("encode_median_s", 0.0)) for row in valid_rows])
    aggregate["decode_median_s"] = median([float(row.get("decode_median_s", 0.0)) for row in valid_rows])
    return normalize_probe_row(aggregate, job, parameter, args, dataset_paths[0].parent)


def works(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if row.get("status") != "ok":
        return False
    if args.threshold_policy == "point":
        return int(row.get("successes", 0)) >= required_successes(args.target_success_rate, int(row.get("trials", 0)))
    if args.threshold_policy == "ci-low":
        return float(row.get("ci_low", 0.0)) >= args.target_success_rate
    raise ValueError(f"unknown threshold policy: {args.threshold_policy}")


def search_best_parameter(
    binaries: dict[str, Path],
    job: dict[str, Any],
    dataset_paths: list[Path],
    args: argparse.Namespace,
    errors_path: Path,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    limit = max_parameter(job, args.max_parameter_factor)
    hi = initial_upper(job)
    while hi <= limit:
        row = run_candidate(binaries, job, hi, dataset_paths, args.probe_trials, args, errors_path)
        row["phase"] = "upper_bound"
        probes.append(row)
        if works(row, args):
            break
        hi *= 2
    else:
        return None, probes

    lo = lower_bound(job)
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_candidate(binaries, job, mid, dataset_paths, args.probe_trials, args, errors_path)
        row["phase"] = "binary_search"
        probes.append(row)
        if works(row, args):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    return best, probes


def timing_metrics(row: dict[str, Any]) -> dict[str, Any]:
    ca = int(row.get("ca", 0))
    cb = int(row.get("cb", 0))
    d_value = int(row.get("d", 0))
    update_denominator = ca + cb
    decode_denominator = d_value
    encode_avg = float(row.get("encode_avg_s", 0.0))
    decode_avg = float(row.get("decode_avg_s", 0.0))
    return {
        "update_denominator": update_denominator,
        "update_avg_s_per_element": encode_avg / update_denominator if update_denominator > 0 else 0.0,
        "update_metric_policy": "encode_avg_s/(ca+cb)",
        "decode_denominator": decode_denominator,
        "decode_avg_s_per_difference": decode_avg / decode_denominator if decode_denominator > 0 else 0.0,
        "decode_metric_policy": "decode_or_reconcile_avg_s/d",
    }


def summary_from_final(job: dict[str, Any], best_parameter: int | None, final_row: dict[str, Any] | None, args: argparse.Namespace) -> dict[str, Any]:
    base = {
        "algorithm": job["algorithm"],
        "variant": job["variant"],
        "d": job["d"],
        "ca": job["ca"],
        "cb": job["cb"],
        "seed": job["seed"],
        "best_parameter_name": job["parameter_name"],
        "target_success_rate": args.target_success_rate,
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "threshold_policy": args.threshold_policy,
        "dataset_mode": "shared_file",
        "ci_method": args.ci_method,
        "ci_confidence": args.ci_confidence,
    }
    if final_row is None or best_parameter is None:
        base.update(
            {
                "best_parameter": "",
                "best_bits": 0.0,
                "best_R_w30": "",
                "best_bit_C_over_d": "",
                "trials": args.final_trials,
                "successes": 0,
                "success_rate": 0.0,
                "final_successes": 0,
                "final_success_rate": 0.0,
                "final_ci_low": 0.0,
                "final_ci_high": 0.0,
                "bits": 0.0,
                "encode_avg_s": 0.0,
                "decode_avg_s": 0.0,
                "encode_median_s": 0.0,
                "decode_median_s": 0.0,
                "dataset_dir": "",
                "status": "unresolved",
            }
        )
    else:
        status = "ok" if works(final_row, args) else "unresolved"
        bits = float(final_row.get("bits", 0.0))
        base.update(
            {
                "best_parameter": best_parameter,
                "best_bits": bits,
                "best_R_w30": r_w30(bits, job["d"]),
                "best_bit_C_over_d": float(final_row.get("bit_C_over_d", bits / (32.0 * float(job["d"])))),
                "trials": final_row.get("trials", args.final_trials),
                "successes": final_row.get("successes", 0),
                "success_rate": final_row.get("success_rate", 0.0),
                "final_successes": final_row.get("successes", 0),
                "final_success_rate": final_row.get("success_rate", 0.0),
                "final_ci_low": final_row.get("ci_low", 0.0),
                "final_ci_high": final_row.get("ci_high", 0.0),
                "ci_low": final_row.get("ci_low", 0.0),
                "ci_high": final_row.get("ci_high", 0.0),
                "bits": bits,
                "encode_avg_s": final_row.get("encode_avg_s", 0.0),
                "decode_avg_s": final_row.get("decode_avg_s", 0.0),
                "encode_median_s": final_row.get("encode_median_s", 0.0),
                "decode_median_s": final_row.get("decode_median_s", 0.0),
                "dataset_dir": final_row.get("dataset_dir", ""),
                "status": status,
            }
        )
        if job["algorithm"] == "xyz_v2":
            base.update(
                {
                    "xyz_circular_a": float(job["circular_a"]),
                    "xyz_z": int(parameter_to_command_fields(job, best_parameter)["z"]),
                    "xyz_tuning_source": job.get("xyz_tuning_source", ""),
                    "xyz_tuning_d": job.get("xyz_tuning_d", ""),
                    "l": job["l"],
                    "k": job["k"],
                    "M": best_parameter,
                    "mode": job["mode"],
                }
            )
        if job["algorithm"] in {"iblt", "minisketch"}:
            base["capacity"] = best_parameter
            base["capacity_factor"] = float(best_parameter) / float(job["d"])
        if job["algorithm"] == "minisketch":
            base["field_bits"] = job["field_bits"]
    base.update(timing_metrics(base))
    return normalize_benchmark_row(
        base,
        experiment="paper_fig3_compare_frontier",
        record_type="threshold",
        algorithm=str(job["algorithm"]),
        variant=str(job["variant"]),
        status=str(base["status"]),
        dataset_mode="shared_file",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 3 Frontier Summary\n\n")
        handle.write("| d | algorithm | variant | parameter | R_w30 | success | update/elem s | decode/diff s | status |\n")
        handle.write("| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), str(item["algorithm"]), str(item["variant"]))):
            handle.write(
                f"| {row.get('d', '')} | {row.get('algorithm', '')} | {row.get('variant', '')} | "
                f"{row.get('best_parameter', '')} | {row.get('best_R_w30', '')} | "
                f"{row.get('final_success_rate', '')} | {row.get('update_avg_s_per_element', '')} | "
                f"{row.get('decode_avg_s_per_difference', '')} | {row.get('status', '')} |\n"
            )


def write_run_config(path: Path, args: argparse.Namespace, jobs: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                "jobs": jobs,
                "supported_algorithms": sorted(SUPPORTED_ALGORITHMS),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Figure 3 per-algorithm communication frontier searches.")
    parser.add_argument("--d-values", default="100,300")
    parser.add_argument("--algorithms", default="xyz_v2,iblt,minisketch")
    parser.add_argument("--probe-trials", type=int, default=5)
    parser.add_argument("--final-trials", type=int, default=10)
    parser.add_argument("--target-success-rate", type=float, default=0.90)
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--max-parameter-factor", type=float, default=8.0)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--xyz-l", type=int, default=6)
    parser.add_argument("--xyz-k", type=int, default=2)
    parser.add_argument("--xyz-circular-a", type=float, default=0.0)
    parser.add_argument("--xyz-tuning", type=Path, default=None)
    parser.add_argument("--minisketch-field-bits", type=int, default=30)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-datasets", action="store_true")
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
    if args.max_parameter_factor <= 0:
        raise SystemExit("--max-parameter-factor must be positive")
    if args.xyz_l <= 0 or args.xyz_k <= 0:
        raise SystemExit("--xyz-l and --xyz-k must be positive")
    if not (0.0 <= args.xyz_circular_a < 1.0):
        raise SystemExit("--xyz-circular-a must be in [0, 1)")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    jobs = make_jobs(args)

    if args.dry_run:
        for job in jobs:
            print(json.dumps(job, sort_keys=True))
        return

    algorithms = {str(job["algorithm"]) for job in jobs}
    binaries = build_binaries(root, dirs["build"], algorithms, args.skip_build)

    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"], dirs["errors"]):
        if path.exists():
            path.unlink()
    write_run_config(dirs["run_config"], args, jobs)

    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for index, job in enumerate(jobs, start=1):
        print(f"[{index}/{len(jobs)}] {job['algorithm']} d={job['d']} {job['variant']}", flush=True)
        cache_key = (int(job["d"]), int(job["ca"]), int(job["cb"]), int(job["seed"]))
        if cache_key not in dataset_cache:
            dataset_config = DatasetConfig(d=int(job["d"]), ca=int(job["ca"]), cb=int(job["cb"]), seed=int(job["seed"]))
            dataset_cache[cache_key] = prepare_datasets(dataset_config, max(args.probe_trials, args.final_trials), dataset_dir)
        dataset_paths = dataset_cache[cache_key]

        best_parameter, job_probes = search_best_parameter(binaries, job, dataset_paths, args, dirs["errors"])
        probes.extend(job_probes)
        final_row = None
        if best_parameter is not None:
            final_row = run_candidate(binaries, job, best_parameter, dataset_paths, args.final_trials, args, dirs["errors"])
            final_row["phase"] = "final_validate"
            probes.append(final_row)
        summary = summary_from_final(job, best_parameter, final_row, args)
        summaries.append(summary)
        print(
            f"  status={summary['status']} parameter={summary.get('best_parameter', '')} "
            f"R={summary.get('best_R_w30', '')} success={summary.get('final_success_rate', '')}",
            flush=True,
        )
        write_jsonl(dirs["probes"], probes)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_csv(dirs["summary_csv"], summaries)
        write_summary_md(dirs["summary_md"], summaries)

    print(f"wrote {dirs['probes']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")
    if not args.keep_datasets and args.dataset_dir is None and dataset_dir.exists():
        shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
