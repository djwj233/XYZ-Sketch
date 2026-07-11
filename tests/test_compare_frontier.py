#!/usr/bin/env python3
"""Paper Figure 2 frontier comparison across practical baselines."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dataset_generator import DatasetConfig, choose_set_sizes, prepare_datasets
from json_schema import normalize_benchmark_row
from statistics import add_binomial_ci, normal_z
from test_compare_basic import build_binaries
from xyz_tuning import add_tuning_arguments, a_from_args, z_from_args


SUPPORTED_ALGORITHMS = {"xyz_sketch", "iblt", "minisketch", "cpisync", "riblt", "negentropy"}
CURRENT_ARGS: argparse.Namespace

SUMMARY_FIELDS = [
    "algorithm",
    "variant",
    "implementation",
    "d",
    "ca",
    "cb",
    "best_parameter_name",
    "best_parameter",
    "search_parameter",
    "final_parameter_offset",
    "final_retry_count",
    "final_parameter_multiplier",
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
    "mbar",
    "mbar_factor",
    "bits_param",
    "epsilon",
    "frame_size_limit",
    "timestamp_mode",
    "symbol_factor",
    "symbols_sent",
    "symbols_sent_avg",
    "symbols_sent_median",
    "symbols_sent_p90",
    "max_symbols",
    "symbol_bits",
    "coded_symbol_bits",
    "field_bits",
    "rounds",
    "rounds_avg",
    "rounds_median",
    "rounds_p90",
    "client_bytes",
    "client_bytes_avg",
    "client_bytes_median",
    "client_bytes_p90",
    "server_bytes",
    "server_bytes_avg",
    "server_bytes_median",
    "server_bytes_p90",
    "communication_model",
    "job_timeout_s",
    "job_elapsed_s",
    "unavailable_reason",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "paper_fig2_end_to_end"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "paper_fig2_end_to_end"
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


def parse_algorithm_set(value: str) -> set[str]:
    algorithms = set(parse_str_list(value))
    unknown = algorithms - SUPPORTED_ALGORITHMS
    if unknown:
        raise SystemExit(f"unsupported algorithms in fixed list: {', '.join(sorted(unknown))}")
    return algorithms


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    ordered = sorted(values)
    index = math.ceil(q * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def r_w30(bits: Any, d_value: Any) -> float:
    d_float = float(d_value)
    return float(bits) / (30.0 * d_float) if d_float > 0 else 0.0


def choose_job_set_sizes(d_value: int, args: argparse.Namespace) -> tuple[int, int]:
    if args.set_size_policy == "legacy":
        return choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
    base = max(1, math.ceil(float(args.set_size_ratio) * float(d_value)))
    ca = base
    cb = base - (d_value % 2)
    if cb <= 0:
        cb = ca
    return ca, cb


def choose_z(job: dict[str, Any], m_value: int, args: argparse.Namespace) -> int:
    return z_from_args(int(job["k"]), int(job["l"]), int(m_value), float(job.get("circular_a", 0.0)), args)


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
        ca, cb = choose_job_set_sizes(d_value, args)
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
            if algorithm == "xyz_sketch":
                tuning = tuning_for_d(tuning_rows, d_value)
                circular_a = float(tuning["a_star"]) if tuning is not None else (args.xyz_circular_a if args.xyz_circular_a is not None else a_from_args(args.xyz_k, args.xyz_l, args))
                fixed_z = int(tuning["z_star"]) if tuning is not None else None
                base.update(
                    {
                        "variant": "circular,tuned" if tuning is not None else "circular,heuristic-a-z",
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
            elif algorithm == "cpisync":
                base.update(
                    {
                        "variant": f"mbar_search,bits={args.cpisync_bits},epsilon={args.cpisync_epsilon}",
                        "parameter_name": "mbar",
                        "bits_param": args.cpisync_bits,
                        "epsilon": args.cpisync_epsilon,
                        "redundant": args.cpisync_redundant,
                        "hashes": args.cpisync_hashes,
                    }
                )
            elif algorithm == "riblt":
                base.update(
                    {
                        "variant": f"symbol_search,symbol_bits={args.riblt_symbol_bits}",
                        "parameter_name": "max_symbols",
                        "symbol_bits": args.riblt_symbol_bits,
                        "field_bits": args.riblt_field_bits,
                    }
                )
            elif algorithm == "negentropy":
                base.update(
                    {
                        "variant": f"frame_search,timestamp={args.negentropy_timestamp_mode}",
                        "parameter_name": "frame_size_limit",
                        "timestamp_mode": args.negentropy_timestamp_mode,
                    }
                )
            jobs.append(base)
    if args.limit is not None:
        jobs = jobs[: args.limit]
    return jobs


def lower_bound(job: dict[str, Any]) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_sketch":
        return max(1, math.ceil(d_value / int(job["l"])), int(job["k"]))
    if job["algorithm"] == "negentropy":
        return 4096
    return 1


def initial_upper(job: dict[str, Any]) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_sketch":
        return max(lower_bound(job), math.ceil(1.5 * d_value / int(job["l"])))
    if job["algorithm"] == "iblt":
        return max(1, math.ceil(1.5 * d_value))
    if job["algorithm"] == "minisketch":
        return max(1, d_value)
    if job["algorithm"] == "cpisync":
        return max(1, math.ceil(1.2 * d_value))
    if job["algorithm"] == "riblt":
        return max(1, math.ceil(1.5 * d_value))
    if job["algorithm"] == "negentropy":
        return max(4096, 512 * d_value)
    raise ValueError(f"unknown algorithm: {job['algorithm']}")


def fixed_parameter(job: dict[str, Any]) -> int:
    d_value = int(job["d"])
    if job["algorithm"] in {"minisketch", "cpisync"}:
        return d_value
    raise ValueError(f"no fixed parameter policy for algorithm: {job['algorithm']}")


def max_parameter(job: dict[str, Any], max_factor: float) -> int:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_sketch":
        return max(lower_bound(job), math.ceil(max_factor * d_value / int(job["l"])))
    if job["algorithm"] == "negentropy":
        return max(lower_bound(job), math.ceil(max_factor * 512.0 * d_value))
    return max(1, math.ceil(max_factor * d_value))


def parameter_to_command_fields(job: dict[str, Any], parameter: int) -> dict[str, Any]:
    d_value = int(job["d"])
    if job["algorithm"] == "xyz_sketch":
        z_value = int(job["fixed_z"]) if job.get("fixed_z") not in (None, "") else choose_z(job, parameter, CURRENT_ARGS)
        return {"M": parameter, "z": z_value}
    if job["algorithm"] in {"iblt", "minisketch"}:
        return {"capacity_factor": float(parameter) / float(d_value), "capacity": parameter}
    if job["algorithm"] == "cpisync":
        return {"mbar": parameter, "mbar_factor": float(parameter) / float(d_value)}
    if job["algorithm"] == "riblt":
        return {"max_symbols": parameter, "symbol_factor": float(parameter) / float(d_value)}
    if job["algorithm"] == "negentropy":
        return {"frame_size_limit": parameter}
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
    if job["algorithm"] == "xyz_sketch":
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
    elif job["algorithm"] == "cpisync":
        command = common + [
            "--mbar",
            str(fields["mbar"]),
            "--bits",
            str(job["bits_param"]),
            "--epsilon",
            str(job["epsilon"]),
            "--redundant",
            str(job["redundant"]),
            "--hashes",
            "true" if job["hashes"] else "false",
        ]
    elif job["algorithm"] == "riblt":
        command = [
            "go",
            "run",
            binary.name,
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
            "--symbol-factor",
            f"{float(fields['symbol_factor']):.12g}",
            "--symbol-bits",
            str(job["symbol_bits"]),
            "--field-bits",
            str(job["field_bits"]),
        ]
    elif job["algorithm"] == "negentropy":
        command = common + [
            "--frame-size-limit",
            str(fields["frame_size_limit"]),
            "--timestamp-mode",
            str(job["timestamp_mode"]),
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


def aggregate_distribution_fields(aggregate: dict[str, Any], valid_rows: list[dict[str, Any]]) -> None:
    for field in ("bits", "symbols_sent", "rounds", "client_bytes", "server_bytes"):
        values = [float(row[field]) for row in valid_rows if row.get(field) not in (None, "")]
        if not values:
            continue
        aggregate[f"{field}_avg"] = sum(values) / float(len(values))
        aggregate[f"{field}_median"] = median(values)
        aggregate[f"{field}_p90"] = percentile(values, 0.90)
        if field == "bits":
            aggregate[field] = values[0] if len(set(values)) == 1 else aggregate[f"{field}_p90"]
        elif field in {"symbols_sent", "rounds", "client_bytes", "server_bytes"}:
            aggregate[field] = aggregate[f"{field}_p90"] if len(set(values)) != 1 else values[0]


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
    if job["algorithm"] == "xyz_sketch":
        row["xyz_circular_a"] = float(job["circular_a"])
        row["xyz_z"] = int(parameter_to_command_fields(job, parameter)["z"])
        row["xyz_tuning_source"] = job.get("xyz_tuning_source", "")
        row["xyz_tuning_d"] = job.get("xyz_tuning_d", "")
    elif job["algorithm"] == "cpisync":
        fields = parameter_to_command_fields(job, parameter)
        row["mbar"] = int(fields["mbar"])
        row["mbar_factor"] = float(fields["mbar_factor"])
        row["bits_param"] = job["bits_param"]
        row["epsilon"] = job["epsilon"]
    elif job["algorithm"] == "negentropy":
        row["frame_size_limit"] = int(parameter_to_command_fields(job, parameter)["frame_size_limit"])
        row["timestamp_mode"] = job["timestamp_mode"]
    elif job["algorithm"] == "riblt":
        fields = parameter_to_command_fields(job, parameter)
        row["symbol_factor"] = float(fields["symbol_factor"])
        row["max_symbols"] = int(fields["max_symbols"])
        row["symbol_bits"] = job["symbol_bits"]
        row.setdefault("coded_symbol_bits", int(job["symbol_bits"]) + 128)
        row["field_bits"] = job["field_bits"]
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    return normalize_benchmark_row(
        row,
        experiment="paper_fig2_end_to_end",
        record_type="probe",
        algorithm=str(job["algorithm"]),
        variant=str(job["variant"]),
        dataset_mode="shared_file",
    )


def timeout_probe_row(
    job: dict[str, Any],
    parameter: int,
    args: argparse.Namespace,
    dataset_dir: Path,
    completed_trials: int,
    attempted_trials: int,
    reason: str,
) -> dict[str, Any]:
    row = {
        "algorithm": job["algorithm"],
        "variant": job["variant"],
        "d": job["d"],
        "ca": job["ca"],
        "cb": job["cb"],
        "seed": job["seed"],
        "trials": completed_trials,
        "attempted_trials": attempted_trials,
        "completed_trials": completed_trials,
        "error_trials": max(0, attempted_trials - completed_trials),
        "successes": 0,
        "success_rate": 0.0,
        "bits": 0.0,
        "status": "job_timeout",
        "encode_avg_s": 0.0,
        "decode_avg_s": 0.0,
        "encode_median_s": 0.0,
        "decode_median_s": 0.0,
        "unavailable_reason": reason,
    }
    return normalize_probe_row(row, job, parameter, args, dataset_dir)


def remaining_timeout_s(deadline: float | None) -> float | None:
    if deadline is None:
        return None
    return max(0.0, deadline - time.monotonic())


def deadline_expired(deadline: float | None) -> bool:
    return deadline is not None and remaining_timeout_s(deadline) <= 0.0


def run_candidate(
    binaries: dict[str, Path],
    job: dict[str, Any],
    parameter: int,
    dataset_paths: list[Path],
    trials: int,
    args: argparse.Namespace,
    errors_path: Path,
    deadline: float | None = None,
) -> dict[str, Any]:
    binary = binaries[job["algorithm"]]
    trial_rows: list[dict[str, Any]] = []
    for dataset in dataset_paths[:trials]:
        if deadline_expired(deadline):
            return timeout_probe_row(job, parameter, args, dataset_paths[0].parent, len(trial_rows), trials, "job timeout before candidate trial")
        command = command_for(binary, job, parameter, dataset)
        cwd = binary.parent if job["algorithm"] == "riblt" else None
        env = None
        if job["algorithm"] == "riblt":
            env = os.environ.copy()
            env["PATH"] = "/usr/local/go1.21/bin:" + env.get("PATH", "")
            env.setdefault("GOPROXY", "https://goproxy.cn,direct")
            env.setdefault("GOSUMDB", "off")
        try:
            timeout_s = remaining_timeout_s(deadline)
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                timeout=timeout_s if timeout_s is None or timeout_s > 0.0 else 0.001,
                check=False,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            append_error(errors_path, job, command, f"TIMEOUT after {exc.timeout}s")
            return timeout_probe_row(job, parameter, args, dataset_paths[0].parent, len(trial_rows), trials, "job timeout during candidate trial")
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
    aggregate["status"] = "ok" if len(valid_rows) == trials else "incomplete"
    aggregate["encode_avg_s"] = sum(float(row.get("encode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    aggregate["decode_avg_s"] = sum(float(row.get("decode_avg_s", 0.0)) for row in valid_rows) / len(valid_rows)
    aggregate["encode_median_s"] = median([float(row.get("encode_median_s", 0.0)) for row in valid_rows])
    aggregate["decode_median_s"] = median([float(row.get("decode_median_s", 0.0)) for row in valid_rows])
    aggregate_distribution_fields(aggregate, valid_rows)
    aggregate["C_over_d"] = float(aggregate.get("bits", 0.0)) / (32.0 * float(job["d"]))
    aggregate["bit_C_over_d"] = aggregate["C_over_d"]
    return normalize_probe_row(aggregate, job, parameter, args, dataset_paths[0].parent)


def works(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if row.get("status") != "ok":
        return False
    if args.threshold_policy == "point":
        return int(row.get("successes", 0)) >= required_successes(args.target_success_rate, int(row.get("trials", 0)))
    if args.threshold_policy == "ci-low":
        return float(row.get("ci_low", 0.0)) >= args.target_success_rate
    raise ValueError(f"unknown threshold policy: {args.threshold_policy}")


def format_progress_row(row: dict[str, Any], args: argparse.Namespace) -> str:
    success_rate = float(row.get("success_rate", 0.0))
    successes = int(row.get("successes", 0))
    trials = int(row.get("trials", 0))
    bits = float(row.get("bits", 0.0))
    r_value = row.get("R_w30", "")
    r_text = f"{float(r_value):.4g}" if r_value not in (None, "") else ""
    status = row.get("status", "")
    verdict = "pass" if works(row, args) else "fail"
    return (
        f"success={success_rate:.3g} ({successes}/{trials}) "
        f"R={r_text} bits={bits:.0f} status={status} {verdict}"
    )


def format_job_details(job: dict[str, Any], args: argparse.Namespace) -> str:
    parts = [f"parameter={job['parameter_name']}"]
    if job["algorithm"] == "xyz_sketch":
        parts.extend([
            f"k={job['k']}",
            f"l={job['l']}",
            f"a={float(job['circular_a']):.6g}",
        ])
        if job.get("fixed_z") not in (None, ""):
            parts.append(f"z={job['fixed_z']} tuned")
        else:
            parts.append(f"z=formula(D={float(args.z_constant):.6g})")
    elif job["algorithm"] == "riblt":
        parts.append(f"symbol_bits={job['symbol_bits']}")
    elif job["algorithm"] == "cpisync":
        parts.extend([f"bits={job['bits_param']}", f"epsilon={job['epsilon']}"])
    elif job["algorithm"] == "negentropy":
        parts.append(f"timestamp={job['timestamp_mode']}")
    return ", ".join(parts)


def should_retry_final(row: dict[str, Any] | None, job: dict[str, Any], args: argparse.Namespace) -> bool:
    if row is None or works(row, args):
        return False
    if row.get("status") == "job_timeout":
        return False
    retry_algorithms = parse_algorithm_set(args.final_retry_algorithms)
    if job["algorithm"] not in retry_algorithms:
        return False
    return float(row.get("success_rate", 0.0)) >= args.final_retry_min_success_rate


def retry_parameter(search_parameter: int, current_parameter: int, retry_index: int, args: argparse.Namespace) -> int:
    grown = math.ceil(float(search_parameter) * (args.final_retry_growth ** retry_index))
    return max(current_parameter + 1, grown)


def search_best_parameter(
    binaries: dict[str, Path],
    job: dict[str, Any],
    dataset_paths: list[Path],
    args: argparse.Namespace,
    errors_path: Path,
    deadline: float | None = None,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    fixed_algorithms = parse_algorithm_set(args.fixed_parameter_algorithms)
    if job["algorithm"] in fixed_algorithms:
        parameter = fixed_parameter(job)
        print(f"    fixed probe {job['parameter_name']}={parameter} trials={args.probe_trials} ...", flush=True)
        row = run_candidate(binaries, job, parameter, dataset_paths, args.probe_trials, args, errors_path, deadline)
        row["phase"] = "fixed_probe"
        probes.append(row)
        print(f"      fixed {job['parameter_name']}={parameter} {format_progress_row(row, args)}", flush=True)
        return parameter, probes

    limit = max_parameter(job, args.max_parameter_factor)
    hi = initial_upper(job)
    print(f"    search bounds: lower={lower_bound(job)} initial_upper={hi} max={limit}", flush=True)
    while hi <= limit:
        if deadline_expired(deadline):
            print("    job timeout before next upper-bound probe", flush=True)
            probes.append(timeout_probe_row(job, hi, args, dataset_paths[0].parent, 0, args.probe_trials, "job timeout before upper-bound probe"))
            return None, probes
        print(f"    upper-bound probe {job['parameter_name']}={hi} trials={args.probe_trials} ...", flush=True)
        row = run_candidate(binaries, job, hi, dataset_paths, args.probe_trials, args, errors_path, deadline)
        row["phase"] = "upper_bound"
        probes.append(row)
        print(f"      upper {job['parameter_name']}={hi} {format_progress_row(row, args)}", flush=True)
        if row.get("status") == "job_timeout":
            return None, probes
        if works(row, args):
            break
        hi *= 2
    else:
        print(f"    unresolved: no passing upper bound up to {limit}", flush=True)
        return None, probes

    lo = lower_bound(job)
    best = hi
    while lo <= hi:
        if deadline_expired(deadline):
            print("    job timeout before next binary probe", flush=True)
            probes.append(timeout_probe_row(job, best, args, dataset_paths[0].parent, 0, args.probe_trials, "job timeout before binary probe"))
            return best, probes
        mid = (lo + hi) // 2
        print(f"    binary probe {job['parameter_name']}={mid} range=[{lo},{hi}] trials={args.probe_trials} ...", flush=True)
        row = run_candidate(binaries, job, mid, dataset_paths, args.probe_trials, args, errors_path, deadline)
        row["phase"] = "binary_search"
        probes.append(row)
        print(f"      binary {job['parameter_name']}={mid} {format_progress_row(row, args)}", flush=True)
        if row.get("status") == "job_timeout":
            return best, probes
        if works(row, args):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    print(f"    best candidate {job['parameter_name']}={best}", flush=True)
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
        "update_metric_policy": "build_both_sketches_s/(ca+cb)",
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
        "job_timeout_s": args.job_timeout_s,
        "final_retry_count": final_row.get("final_retry_count", 0) if final_row is not None else 0,
        "final_parameter_multiplier": final_row.get("final_parameter_multiplier", "") if final_row is not None else "",
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
                "unavailable_reason": "no passing parameter found or job timeout",
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
        if job["algorithm"] == "xyz_sketch":
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
        if job["algorithm"] == "cpisync":
            fields = parameter_to_command_fields(job, best_parameter)
            base["mbar"] = int(fields["mbar"])
            base["mbar_factor"] = float(fields["mbar_factor"])
            base["bits_param"] = job["bits_param"]
            base["epsilon"] = job["epsilon"]
        if job["algorithm"] == "riblt":
            fields = parameter_to_command_fields(job, best_parameter)
            base["symbol_factor"] = float(fields["symbol_factor"])
            base["max_symbols"] = int(fields["max_symbols"])
            base["symbols_sent"] = final_row.get("symbols_sent", 0)
            base["symbols_sent_avg"] = final_row.get("symbols_sent_avg", "")
            base["symbols_sent_median"] = final_row.get("symbols_sent_median", "")
            base["symbols_sent_p90"] = final_row.get("symbols_sent_p90", "")
            base["symbol_bits"] = job["symbol_bits"]
            base["coded_symbol_bits"] = final_row.get("coded_symbol_bits", int(job["symbol_bits"]) + 128)
            base["field_bits"] = job["field_bits"]
            base["communication_model"] = final_row.get("communication_model", "rateless")
        if job["algorithm"] == "negentropy":
            base["frame_size_limit"] = int(parameter_to_command_fields(job, best_parameter)["frame_size_limit"])
            base["timestamp_mode"] = job["timestamp_mode"]
            base["rounds"] = final_row.get("rounds", 0)
            base["rounds_avg"] = final_row.get("rounds_avg", "")
            base["rounds_median"] = final_row.get("rounds_median", "")
            base["rounds_p90"] = final_row.get("rounds_p90", "")
            base["client_bytes"] = final_row.get("client_bytes", 0)
            base["client_bytes_avg"] = final_row.get("client_bytes_avg", "")
            base["client_bytes_median"] = final_row.get("client_bytes_median", "")
            base["client_bytes_p90"] = final_row.get("client_bytes_p90", "")
            base["server_bytes"] = final_row.get("server_bytes", 0)
            base["server_bytes_avg"] = final_row.get("server_bytes_avg", "")
            base["server_bytes_median"] = final_row.get("server_bytes_median", "")
            base["server_bytes_p90"] = final_row.get("server_bytes_p90", "")
            base["communication_model"] = final_row.get("communication_model", "interactive")
    base.update(timing_metrics(base))
    return normalize_benchmark_row(
        base,
        experiment="paper_fig2_end_to_end",
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
        handle.write("# Figure 2 End-to-End Summary\n\n")
        handle.write("| d | algorithm | variant | parameter | R_w30 | success | update/elem s | decode/diff s | status |\n")
        handle.write("| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), str(item["algorithm"]), str(item["variant"]))):
            handle.write(
                f"| {row.get('d', '')} | {row.get('algorithm', '')} | {row.get('variant', '')} | "
                f"{row.get('best_parameter', '')} | {row.get('best_R_w30', '')} | "
                f"{row.get('final_success_rate', '')} | {row.get('update_avg_s_per_element', '')} | "
                f"{row.get('decode_avg_s_per_difference', '')} | {row.get('status', '')} |\n"
            )


def collect_environment(root: Path) -> dict[str, Any]:
    memory_kib = None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                memory_kib = int(line.split()[1])
                break
    def command_output(command: list[str]) -> str:
        try:
            return subprocess.run(command, cwd=root, check=True, capture_output=True, text=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""
    gxx_output = command_output(["g++", "--version"])
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "memory_kib": memory_kib,
        "git_commit": command_output(["git", "rev-parse", "HEAD"]),
        "gxx_version": gxx_output.splitlines()[0] if gxx_output else "",
    }


def write_run_config(path: Path, args: argparse.Namespace, jobs: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                "environment": collect_environment(repo_root()),
                "jobs": jobs,
                "supported_algorithms": sorted(SUPPORTED_ALGORITHMS),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Figure 2 per-algorithm communication frontier searches.")
    parser.add_argument("--d-values", default="100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000")
    parser.add_argument("--algorithms", default="xyz_sketch,iblt,minisketch,riblt,cpisync")
    parser.add_argument("--probe-trials", type=int, default=30)
    parser.add_argument("--final-trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.90)
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument(
        "--fixed-parameter-algorithms",
        default="minisketch,cpisync",
        help="Comma-separated algorithms to evaluate at their deterministic parameter d instead of binary searching. Currently intended for minisketch,cpisync.",
    )
    parser.add_argument("--max-parameter-factor", type=float, default=8.0)
    parser.add_argument("--final-retry-algorithms", default="", help="Comma-separated algorithms whose failed final validation may be retried at a larger parameter.")
    parser.add_argument("--final-retry-growth", type=float, default=1.05)
    parser.add_argument("--final-retry-limit", type=int, default=0)
    parser.add_argument("--final-retry-min-success-rate", type=float, default=0.75)
    parser.add_argument("--job-timeout-s", type=float, default=0.0, help="Per (algorithm,d) job timeout in seconds. Use 0 to disable.")
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--xyz-l", type=int, default=6)
    parser.add_argument("--xyz-k", type=int, default=2)
    parser.add_argument("--xyz-circular-a", type=float, default=None, help="Override XYZ circular a. By default use a_{k,l}=C*c_orient/c_peel.")
    parser.add_argument("--xyz-final-m-offset", type=int, default=0, help="Add this offset to the searched XYZ-Sketch M before final validation.")
    add_tuning_arguments(parser)
    parser.set_defaults(a_constant=0.27591534917087435, z_constant=0.5, delta=0.1)
    parser.add_argument("--xyz-tuning", type=Path, default=None, help="Optional Figure 2 tuning summary. If omitted, use heuristic a,z formulas.")
    parser.add_argument("--minisketch-field-bits", type=int, default=30)
    parser.add_argument("--cpisync-bits", type=int, default=30)
    parser.add_argument("--cpisync-epsilon", type=int, default=64)
    parser.add_argument("--cpisync-redundant", type=int, default=0)
    parser.add_argument("--cpisync-hashes", action="store_true")
    parser.add_argument("--negentropy-timestamp-mode", default="value", choices=["value", "constant", "random"])
    parser.add_argument("--riblt-symbol-bits", type=int, default=64)
    parser.add_argument("--riblt-field-bits", type=int, default=30)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-datasets", action="store_true")
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--set-size-policy", default="fixed-ratio", choices=["fixed-ratio", "legacy"])
    parser.add_argument("--set-size-ratio", type=float, default=2.0)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    global CURRENT_ARGS
    args = parse_args()
    CURRENT_ARGS = args
    if args.probe_trials <= 0 or args.final_trials <= 0:
        raise SystemExit("--probe-trials and --final-trials must be positive")
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.max_parameter_factor <= 0:
        raise SystemExit("--max-parameter-factor must be positive")
    if args.final_retry_growth <= 1.0:
        raise SystemExit("--final-retry-growth must be greater than 1")
    if args.final_retry_limit < 0:
        raise SystemExit("--final-retry-limit must be non-negative")
    if not (0.0 <= args.final_retry_min_success_rate <= 1.0):
        raise SystemExit("--final-retry-min-success-rate must be in [0, 1]")
    retry_algorithms = parse_algorithm_set(args.final_retry_algorithms)
    unsupported_retry = retry_algorithms - {"xyz_sketch", "iblt", "riblt"}
    if unsupported_retry:
        raise SystemExit("--final-retry-algorithms currently supports only xyz_sketch,iblt,riblt")
    fixed_algorithms = parse_algorithm_set(args.fixed_parameter_algorithms)
    unsupported_fixed = fixed_algorithms - {"minisketch", "cpisync"}
    if unsupported_fixed:
        raise SystemExit("--fixed-parameter-algorithms currently supports only minisketch,cpisync")
    if args.job_timeout_s < 0:
        raise SystemExit("--job-timeout-s must be non-negative")
    if args.xyz_l <= 0 or args.xyz_k <= 0:
        raise SystemExit("--xyz-l and --xyz-k must be positive")
    if args.xyz_final_m_offset < 0:
        raise SystemExit("--xyz-final-m-offset must be non-negative")
    if args.set_size_ratio <= 0:
        raise SystemExit("--set-size-ratio must be positive")
    if args.xyz_circular_a is not None and not (0.0 <= args.xyz_circular_a < 1.0):
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
    print(f"building/preparing benchmark binaries for {', '.join(sorted(algorithms))} ...", flush=True)
    binaries = build_binaries(root, dirs["build"], algorithms, args.skip_build)
    print("benchmark binaries ready", flush=True)

    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"], dirs["errors"]):
        if path.exists():
            path.unlink()
    write_run_config(dirs["run_config"], args, jobs)

    dataset_cache: dict[tuple[int, int, int, int], list[Path]] = {}
    probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for index, job in enumerate(jobs, start=1):
        job_start = time.monotonic()
        deadline = None if args.job_timeout_s == 0 else job_start + float(args.job_timeout_s)
        print(f"[{index}/{len(jobs)}] {job['algorithm']} d={job['d']} {job['variant']}", flush=True)
        print(f"  details: {format_job_details(job, args)}", flush=True)
        if deadline is not None:
            print(f"  job timeout: {args.job_timeout_s:.0f}s", flush=True)
        cache_key = (int(job["d"]), int(job["ca"]), int(job["cb"]), int(job["seed"]))
        if cache_key not in dataset_cache:
            dataset_count = args.probe_trials + args.final_trials
            print(
                f"  preparing {dataset_count} shared datasets in {dataset_dir} "
                f"({args.probe_trials} search + {args.final_trials} final)",
                flush=True,
            )
            dataset_config = DatasetConfig(d=int(job["d"]), ca=int(job["ca"]), cb=int(job["cb"]), seed=int(job["seed"]))
            dataset_cache[cache_key] = prepare_datasets(dataset_config, dataset_count, dataset_dir)
        else:
            print("  reusing shared datasets", flush=True)
        dataset_paths = dataset_cache[cache_key]
        search_dataset_paths = dataset_paths[: args.probe_trials]
        final_dataset_paths = dataset_paths[args.probe_trials : args.probe_trials + args.final_trials]

        best_parameter, job_probes = search_best_parameter(binaries, job, search_dataset_paths, args, dirs["errors"], deadline)
        probes.extend(job_probes)
        final_row = None
        final_parameter = best_parameter
        final_parameter_offset = 0
        final_retry_count = 0
        if best_parameter is not None:
            if job["algorithm"] == "xyz_sketch" and args.xyz_final_m_offset > 0:
                final_parameter_offset = args.xyz_final_m_offset
                final_parameter = best_parameter + args.xyz_final_m_offset
                print(
                    f"    final parameter offset: searched M={best_parameter}, "
                    f"final M={final_parameter} (+{args.xyz_final_m_offset})",
                    flush=True,
                )
            print(f"    final check {job['parameter_name']}={final_parameter} trials={args.final_trials} ...", flush=True)
            final_row = run_candidate(binaries, job, final_parameter, final_dataset_paths, args.final_trials, args, dirs["errors"], deadline)
            final_row["phase"] = "final_validate"
            final_row["final_retry_count"] = final_retry_count
            final_row["final_parameter_multiplier"] = float(final_parameter) / float(best_parameter) if best_parameter else ""
            probes.append(final_row)
            print(f"      final {job['parameter_name']}={final_parameter} {format_progress_row(final_row, args)}", flush=True)
            while final_retry_count < args.final_retry_limit and should_retry_final(final_row, job, args):
                final_retry_count += 1
                final_parameter = retry_parameter(best_parameter, final_parameter, final_retry_count, args)
                final_parameter_offset = final_parameter - best_parameter
                print(
                    f"    final retry {final_retry_count}/{args.final_retry_limit} "
                    f"{job['parameter_name']}={final_parameter} "
                    f"multiplier={float(final_parameter) / float(best_parameter):.6g} ...",
                    flush=True,
                )
                final_row = run_candidate(binaries, job, final_parameter, final_dataset_paths, args.final_trials, args, dirs["errors"], deadline)
                final_row["phase"] = "final_retry"
                final_row["final_retry_count"] = final_retry_count
                final_row["final_parameter_multiplier"] = float(final_parameter) / float(best_parameter)
                probes.append(final_row)
                print(f"      retry {job['parameter_name']}={final_parameter} {format_progress_row(final_row, args)}", flush=True)
        summary = summary_from_final(job, final_parameter, final_row, args)
        summary["search_parameter"] = best_parameter if best_parameter is not None else ""
        summary["final_parameter_offset"] = final_parameter_offset
        summary["final_retry_count"] = final_retry_count
        summary["final_parameter_multiplier"] = float(final_parameter) / float(best_parameter) if best_parameter and final_parameter else ""
        summary["job_elapsed_s"] = time.monotonic() - job_start
        if final_row is not None and final_row.get("status") == "job_timeout":
            summary["status"] = "job_timeout"
            summary["unavailable_reason"] = final_row.get("unavailable_reason", "job timeout")
        elif deadline_expired(deadline) and summary.get("status") != "ok":
            summary["status"] = "job_timeout"
            summary["unavailable_reason"] = "job timeout"
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
