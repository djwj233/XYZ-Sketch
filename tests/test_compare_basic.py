#!/usr/bin/env python3
"""Run a basic comparison between XYZ-v2 and local IBLT."""

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


CSV_FIELDS = [
    "algorithm",
    "variant",
    "implementation",
    "d",
    "ca",
    "cb",
    "trials",
    "successes",
    "success_rate",
    "encode_avg_s",
    "decode_avg_s",
    "encode_median_s",
    "decode_median_s",
    "bits",
    "bits_per_difference",
    "bit_C_over_d",
    "seed",
    "dataset_mode",
    "dataset_dir",
    "status",
    "l",
    "k",
    "M",
    "z",
    "mode",
    "field_C_over_d",
    "cells",
    "hash_count",
    "cell_bits",
    "capacity_factor",
    "mbar",
    "mbar_factor",
    "bits_param",
    "epsilon",
    "redundant",
    "hashes",
    "bytes",
    "reconcile_avg_s",
    "reconcile_median_s",
    "unavailable_reason",
    "expected_entries",
    "value_size",
    "field_bits",
    "capacity",
    "symbol_factor",
    "symbols_sent",
    "max_symbols",
    "symbol_bits",
    "frame_size_limit",
    "timestamp_mode",
    "rounds",
    "client_bytes",
    "server_bytes",
]

DEFAULT_D_VALUES = [100, 300, 1000, 3000, 10000]
SUPPORTED_ALGORITHMS = {
    "xyz_v1",
    "xyz_v2",
    "iblt",
    "iblt_cpp",
    "minisketch",
    "cpisync",
    "riblt",
    "negentropy",
}
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def exe_suffix() -> str:
    return ".exe" if sys.platform.startswith("win") else ""


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "compare_basic"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    tmp = root / "tests" / "tmp" / "compare_basic"
    tmp.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "tmp": tmp,
        "raw_jsonl": base / "raw.jsonl",
        "raw_csv": base / "raw.csv",
        "summary": base / "summary.md",
        "errors": base / "errors.log",
        "run_config": base / "run_config.json",
    }


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_float_list(value: str) -> list[float]:
    return [float(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def choose_xyz_c_over_d_target(d_value: int, k_value: int) -> float:
    if k_value == 3:
        return 1.668
    if k_value >= 4:
        return 1.782
    if d_value <= 100:
        return 1.60
    if d_value <= 1000:
        return 1.30
    if d_value <= 10000:
        return 1.20
    if d_value <= 100000:
        return 1.12
    return 1.10


def choose_xyz_m(d_value: int, l_value: int, k_value: int) -> int:
    return max(1, math.ceil(choose_xyz_c_over_d_target(d_value, k_value) * d_value / l_value))


def choose_z(m_value: int) -> int:
    return max(0, round((m_value ** (1.0 / 3.0)) / 3.0))


def build_binaries(root: Path, build_dir: Path, algorithms: set[str], skip_build: bool) -> dict[str, Path]:
    binaries = {
        "xyz_v1": build_dir / f"xyz_v1_bench{exe_suffix()}",
        "xyz_v2": build_dir / f"xyz_v2_bench{exe_suffix()}",
        "iblt": build_dir / f"iblt_bench{exe_suffix()}",
        "iblt_cpp": build_dir / f"iblt_cpp_bench{exe_suffix()}",
        "minisketch": build_dir / f"minisketch_bench{exe_suffix()}",
        "cpisync": build_dir / f"cpisync_bench{exe_suffix()}",
        "riblt": root / "tests" / "benchmarks" / "riblt_bench.go",
        "negentropy": build_dir / f"negentropy_bench{exe_suffix()}",
    }
    if skip_build:
        for algorithm in algorithms:
            if not binaries[algorithm].exists():
                raise FileNotFoundError(f"benchmark binary not found: {binaries[algorithm]}")
        return binaries

    commands: list[list[str]] = []
    if "xyz_v1" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "xyz_v1_bench.cpp"),
            "-o",
            str(binaries["xyz_v1"]),
        ])
    if "xyz_v2" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "xyz_v2_bench.cpp"),
            "-o",
            str(binaries["xyz_v2"]),
        ])
    if "iblt" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "iblt_bench.cpp"),
            "-o",
            str(binaries["iblt"]),
        ])
    if "iblt_cpp" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "iblt_cpp_bench.cpp"),
            str(root / "external" / "IBLT_Cplusplus" / "iblt.cpp"),
            str(root / "external" / "IBLT_Cplusplus" / "murmurhash3.cpp"),
            str(root / "external" / "IBLT_Cplusplus" / "utilstrencodings.cpp"),
            "-o",
            str(binaries["iblt_cpp"]),
        ])
    if "minisketch" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            "-DENABLE_REAL_MINISKETCH",
            "-I",
            str(root / "external" / "minisketch" / "include"),
            "-I",
            str(root / "external" / "minisketch" / "src"),
            str(root / "tests" / "benchmarks" / "minisketch_bench.cpp"),
            str(root / "external" / "minisketch" / "src" / "minisketch.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_1byte.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_2bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_3bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_4bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_5bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_6bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_7bytes.cpp"),
            str(root / "external" / "minisketch" / "src" / "fields" / "generic_8bytes.cpp"),
            "-o",
            str(binaries["minisketch"]),
        ])
    if "cpisync" in algorithms:
        commands.append([
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "cpisync_bench.cpp"),
            "-o",
            str(binaries["cpisync"]),
        ])
    if "negentropy" in algorithms:
        real_command = [
            "g++",
            "-std=c++20",
            "-O2",
            "-DENABLE_REAL_NEGENTROPY",
            "-I",
            str(root / "external" / "negentropy" / "cpp"),
            str(root / "tests" / "benchmarks" / "negentropy_bench.cpp"),
            "-lcrypto",
            "-o",
            str(binaries["negentropy"]),
        ]
        stub_command = [
            "g++",
            "-std=c++17",
            "-O2",
            str(root / "tests" / "benchmarks" / "negentropy_bench.cpp"),
            "-o",
            str(binaries["negentropy"]),
        ]
        try:
            subprocess.run(real_command, cwd=root, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError):
            subprocess.run(stub_command, cwd=root, check=True)
    for command in commands:
        subprocess.run(command, cwd=root, check=True)
    if "cpisync" in algorithms and not sys.platform.startswith("win"):
        try:
            subprocess.run(cpisync_real_build_command(root, binaries["cpisync"]), cwd=root, check=True)
        except (OSError, subprocess.CalledProcessError):
            # Keep the stub binary. It reports status=unavailable without breaking the run.
            pass
    return binaries


def cpisync_real_build_command(root: Path, output: Path) -> list[str]:
    sources = [
        "CommSocket.cpp",
        "CommString.cpp",
        "Communicant.cpp",
        "CPISync.cpp",
        "DataObject.cpp",
        "GenSync.cpp",
        "InterCPISync.cpp",
        "Logger.cpp",
        "probCPISync.cpp",
        "SyncMethod.cpp",
        "UID.cpp",
        "HashSync.cpp",
        "CommDummy.cpp",
        "IBLT.cpp",
        "IBLTSync.cpp",
        "FullSync.cpp",
        "kshingling.cpp",
        "kshinglingSync.cpp",
        "UniqueDecode.cpp",
        "AdjMtx.cpp",
        "PerformanceData.cpp",
        "IBLTSync_SetDiff.cpp",
        "StrataEst.cpp",
        "StrataEst_CPI.cpp",
        "CPI.cpp",
        "SetsOfContent.cpp",
        "RCDS.cpp",
    ]
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        "-DENABLE_REAL_CPISYNC",
        "-I",
        str(root / "external" / "cpisync" / "include"),
        str(root / "tests" / "benchmarks" / "cpisync_bench.cpp"),
    ]
    command.extend(str(root / "external" / "cpisync" / "src" / source) for source in sources)
    command.extend(["-lntl", "-lgmp", "-lpthread", "-o", str(output)])
    return command


def make_jobs(args: argparse.Namespace) -> list[dict[str, Any]]:
    d_values = parse_int_list(args.d_values) if args.d_values else list(DEFAULT_D_VALUES)
    algorithms = parse_str_list(args.algorithms)
    unknown = set(algorithms) - SUPPORTED_ALGORITHMS
    if unknown:
        raise SystemExit(f"unsupported algorithms for first version: {', '.join(sorted(unknown))}")
    capacity_factors = parse_float_list(args.capacity_factors)
    mbar_factors = parse_float_list(args.mbar_factors)
    symbol_factors = parse_float_list(args.symbol_factors)
    frame_size_limits = parse_int_list(args.frame_size_limits)
    timestamp_modes = parse_str_list(args.timestamp_modes)

    jobs: list[dict[str, Any]] = []
    for d_index, d_value in enumerate(d_values):
        ca, cb = choose_set_sizes(d_value, args.max_set_size, args.set_size_scale)
        base_seed = args.base_seed + 1_000_000 * d_index
        if "xyz_v1" in algorithms:
            jobs.append(
                {
                    "algorithm": "xyz_v1",
                    "variant": "basic",
                    "d": d_value,
                    "ca": ca,
                    "cb": cb,
                    "trials": args.trials,
                    "seed": base_seed,
                }
            )
        if "xyz_v2" in algorithms:
            m_value = choose_xyz_m(d_value, args.xyz_l, args.xyz_k)
            jobs.append(
                {
                    "algorithm": "xyz_v2",
                    "variant": args.xyz_mode,
                    "d": d_value,
                    "ca": ca,
                    "cb": cb,
                    "trials": args.trials,
                    "seed": base_seed,
                    "l": args.xyz_l,
                    "k": args.xyz_k,
                    "M": m_value,
                    "z": choose_z(m_value),
                    "mode": args.xyz_mode,
                }
            )
        if "iblt" in algorithms:
            for factor in capacity_factors:
                jobs.append(
                    {
                        "algorithm": "iblt",
                        "variant": f"capacity_factor={factor:g}",
                        "d": d_value,
                        "ca": ca,
                        "cb": cb,
                        "trials": args.trials,
                        "seed": base_seed,
                        "capacity_factor": factor,
                    }
                )
        if "iblt_cpp" in algorithms:
            for factor in capacity_factors:
                jobs.append(
                    {
                        "algorithm": "iblt_cpp",
                        "variant": f"capacity_factor={factor:g}",
                        "d": d_value,
                        "ca": ca,
                        "cb": cb,
                        "trials": args.trials,
                        "seed": base_seed,
                        "capacity_factor": factor,
                        "value_size": args.iblt_cpp_value_size,
                    }
                )
        if "minisketch" in algorithms:
            for factor in capacity_factors:
                jobs.append(
                    {
                        "algorithm": "minisketch",
                        "variant": f"capacity_factor={factor:g}",
                        "d": d_value,
                        "ca": ca,
                        "cb": cb,
                        "trials": args.trials,
                        "seed": base_seed,
                        "capacity_factor": factor,
                        "field_bits": args.minisketch_field_bits,
                    }
                )
        if "cpisync" in algorithms:
            for factor in mbar_factors:
                jobs.append(
                    {
                        "algorithm": "cpisync",
                        "variant": f"mbar_factor={factor:g}",
                        "d": d_value,
                        "ca": ca,
                        "cb": cb,
                        "trials": args.trials,
                        "seed": base_seed,
                        "mbar_factor": factor,
                        "mbar": max(1, math.ceil(factor * d_value)),
                        "bits_param": args.cpisync_bits,
                        "epsilon": args.cpisync_epsilon,
                        "redundant": args.cpisync_redundant,
                        "hashes": args.cpisync_hashes,
                    }
                )
        if "riblt" in algorithms:
            for factor in symbol_factors:
                jobs.append(
                    {
                        "algorithm": "riblt",
                        "variant": f"symbol_factor={factor:g}",
                        "d": d_value,
                        "ca": ca,
                        "cb": cb,
                        "trials": args.trials,
                        "seed": base_seed,
                        "symbol_factor": factor,
                        "symbol_bits": args.riblt_symbol_bits,
                        "field_bits": args.riblt_field_bits,
                    }
                )
        if "negentropy" in algorithms:
            for frame_size_limit in frame_size_limits:
                for timestamp_mode in timestamp_modes:
                    jobs.append(
                        {
                            "algorithm": "negentropy",
                            "variant": f"frame_size={frame_size_limit},timestamp={timestamp_mode}",
                            "d": d_value,
                            "ca": ca,
                            "cb": cb,
                            "trials": args.trials,
                            "seed": base_seed,
                            "frame_size_limit": frame_size_limit,
                            "timestamp_mode": timestamp_mode,
                        }
                    )
    if args.limit is not None:
        jobs = jobs[: args.limit]
    return jobs


def command_for(binary: Path, job: dict[str, Any], dataset: Path | None = None) -> list[str]:
    if job["algorithm"] == "xyz_v1":
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] == "xyz_v2":
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--l",
            str(job["l"]),
            "--k",
            str(job["k"]),
            "--m",
            str(job["M"]),
            "--z",
            str(job["z"]),
            "--mode",
            str(job["mode"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] == "iblt":
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--capacity-factor",
            str(job["capacity_factor"]),
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] in {"iblt_cpp", "minisketch"}:
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--capacity-factor",
            str(job["capacity_factor"]),
            "--format",
            "jsonl",
        ]
        if job["algorithm"] == "iblt_cpp":
            command.extend(["--value-size", str(job["value_size"])])
        if job["algorithm"] == "minisketch":
            command.extend(["--field-bits", str(job["field_bits"])])
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] == "cpisync":
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--mbar-factor",
            str(job["mbar_factor"]),
            "--bits",
            str(job["bits_param"]),
            "--epsilon",
            str(job["epsilon"]),
            "--redundant",
            str(job["redundant"]),
            "--hashes",
            "true" if job["hashes"] else "false",
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] == "riblt":
        command = [
            "go",
            "run",
            binary.name,
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--symbol-factor",
            str(job["symbol_factor"]),
            "--symbol-bits",
            str(job["symbol_bits"]),
            "--field-bits",
            str(job["field_bits"]),
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    if job["algorithm"] == "negentropy":
        command = [
            str(binary),
            "--d",
            str(job["d"]),
            "--trials",
            str(job["trials"]),
            "--seed",
            str(job["seed"]),
            "--ca",
            str(job["ca"]),
            "--cb",
            str(job["cb"]),
            "--frame-size-limit",
            str(job["frame_size_limit"]),
            "--timestamp-mode",
            str(job["timestamp_mode"]),
            "--format",
            "jsonl",
        ]
        if dataset is not None:
            command.extend(["--dataset", str(dataset)])
            trial_index = command.index("--trials")
            command[trial_index + 1] = "1"
        return command
    raise ValueError(f"unknown algorithm: {job['algorithm']}")


def append_error(path: Path, job: dict[str, Any], command: list[str], message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("JOB " + json.dumps(job, sort_keys=True) + "\n")
        handle.write("COMMAND " + json.dumps(command) + "\n")
        handle.write(message.rstrip() + "\n\n")


def normalize_row(row: dict[str, Any], job: dict[str, Any], record_type: str = "trial") -> dict[str, Any]:
    d_value = int(job["d"])
    row.setdefault("algorithm", job["algorithm"])
    row["variant"] = job.get("variant", row.get("variant", "default"))
    row.setdefault("status", "ok")
    row.setdefault("dataset_mode", job.get("dataset_mode", "internal_generator"))
    row.setdefault("dataset_dir", job.get("dataset_dir", ""))
    row.setdefault("bits", 0)
    row["bits_per_difference"] = float(row["bits"]) / float(d_value)
    row["bit_C_over_d"] = float(row.get("bit_C_over_d", row.get("C_over_d"))) if "C_over_d" in row or "bit_C_over_d" in row else float(row["bits"]) / (32.0 * d_value)

    if row["algorithm"] == "xyz_v2":
        row["variant"] = job["variant"]
        row["field_C_over_d"] = int(row["M"]) * int(row["l"]) / float(d_value)
    if row["algorithm"] == "xyz_v1":
        row["implementation"] = "local/XYZ-v1"
    if row["algorithm"] == "iblt":
        row["implementation"] = "local/IBLT"
    if row["algorithm"] == "iblt_cpp":
        row.setdefault("implementation", "external/IBLT_Cplusplus")
        row.setdefault("capacity_factor", job.get("capacity_factor"))
        row.setdefault("value_size", job.get("value_size"))
    if row["algorithm"] == "minisketch":
        row.setdefault("implementation", "external/minisketch")
        row.setdefault("capacity_factor", job.get("capacity_factor"))
        row.setdefault("field_bits", job.get("field_bits"))
        row.setdefault("capacity", max(1, math.ceil(float(job.get("capacity_factor", 1.0)) * d_value)))
    if row["algorithm"] == "cpisync":
        row.setdefault("implementation", "external/cpisync")
        row.setdefault("mbar", job.get("mbar"))
        row.setdefault("mbar_factor", job.get("mbar_factor"))
        row.setdefault("bits_param", job.get("bits_param"))
        row.setdefault("epsilon", job.get("epsilon"))
        row.setdefault("redundant", job.get("redundant"))
        row.setdefault("hashes", job.get("hashes"))
        row.setdefault("bytes", float(row.get("bits", 0)) / 8.0)
        row.setdefault("reconcile_avg_s", row.get("decode_avg_s", 0.0))
        row.setdefault("reconcile_median_s", row.get("decode_median_s", 0.0))
    if row["algorithm"] == "riblt":
        row.setdefault("implementation", "external/riblt")
        row.setdefault("symbol_factor", job.get("symbol_factor"))
        row.setdefault("symbol_bits", job.get("symbol_bits"))
        row.setdefault("field_bits", job.get("field_bits"))
        row.setdefault("max_symbols", max(1, math.ceil(float(job.get("symbol_factor", 1.0)) * d_value)))
    if row["algorithm"] == "negentropy":
        row.setdefault("implementation", "external/negentropy")
        row.setdefault("frame_size_limit", job.get("frame_size_limit"))
        row.setdefault("timestamp_mode", job.get("timestamp_mode"))
    return normalize_benchmark_row(
        row,
        experiment="compare_basic",
        record_type=record_type,
        algorithm=str(job["algorithm"]),
        variant=str(row.get("variant", job.get("variant", "default"))),
    )


def run_one_dataset(
    binaries: dict[str, Path],
    job: dict[str, Any],
    dataset: Path,
    errors_path: Path,
) -> dict[str, Any]:
    binary = binaries[job["algorithm"]]
    command = command_for(binary, job, dataset=dataset)
    cwd = binary.parent if job["algorithm"] == "riblt" else None
    try:
        completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    except OSError as exc:
        append_error(errors_path, job, command, f"OSERROR {exc}")
        row = dict(job)
        status = "unavailable" if job["algorithm"] == "riblt" else "benchmark_error"
        row.update({
            "successes": 0,
            "success_rate": 0.0,
            "bits": 0,
            "status": status,
            "unavailable_reason": str(exc),
        })
        return normalize_failure(row, record_type="error")

    if completed.returncode != 0:
        append_error(
            errors_path,
            job,
            command,
            f"RETURNCODE {completed.returncode}\nSTDOUT\n{completed.stdout}\nSTDERR\n{completed.stderr}",
        )
        row = dict(job)
        row.update({"successes": 0, "success_rate": 0.0, "bits": 0, "status": "benchmark_error"})
        return normalize_failure(row, record_type="error")

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        append_error(errors_path, job, command, f"PARSE got {len(lines)} lines\n{completed.stdout}")
        row = dict(job)
        row.update({"successes": 0, "success_rate": 0.0, "bits": 0, "status": "parse_error"})
        return normalize_failure(row, record_type="error")

    try:
        row = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, job, command, f"JSONERROR {exc}\n{completed.stdout}")
        row = dict(job)
        row.update({"successes": 0, "success_rate": 0.0, "bits": 0, "status": "parse_error"})
        return normalize_failure(row)
    return normalize_row(row, job)


def aggregate_trials(job: dict[str, Any], trial_rows: list[dict[str, Any]], dataset_dir: Path) -> dict[str, Any]:
    valid_statuses = {"ok", "failed_decode"}
    valid_rows = [row for row in trial_rows if row.get("status") in valid_statuses]
    if not valid_rows:
        unavailable_rows = [row for row in trial_rows if row.get("status") == "unavailable"]
        if unavailable_rows:
            row = dict(unavailable_rows[0])
            row["trials"] = int(job["trials"])
            row["successes"] = 0
            row["success_rate"] = 0.0
            row["seed"] = job["seed"]
            row["dataset_mode"] = "shared_file"
            row["dataset_dir"] = str(dataset_dir)
            row["variant"] = job.get("variant", row.get("variant", "default"))
            return normalize_row(row, job, record_type="unavailable")
        row = dict(job)
        row.update({"successes": 0, "success_rate": 0.0, "bits": 0, "status": "benchmark_error"})
        return normalize_failure(row, record_type="error")

    successes = sum(int(row.get("successes", 0)) for row in valid_rows)
    trials = len(valid_rows)
    first = dict(valid_rows[0])
    first["trials"] = trials
    first["attempted_trials"] = int(job["trials"])
    first["completed_trials"] = trials
    first["error_trials"] = max(0, len(trial_rows) - trials)
    first["successes"] = successes
    first["success_rate"] = successes / float(trials)
    first["status"] = "ok"
    first["encode_avg_s"] = sum(float(row.get("encode_avg_s", 0.0)) for row in valid_rows) / trials
    first["decode_avg_s"] = sum(float(row.get("decode_avg_s", 0.0)) for row in valid_rows) / trials
    encode_values = sorted(float(row.get("encode_median_s", 0.0)) for row in valid_rows)
    decode_values = sorted(float(row.get("decode_median_s", 0.0)) for row in valid_rows)
    mid = trials // 2
    if trials % 2:
        first["encode_median_s"] = encode_values[mid]
        first["decode_median_s"] = decode_values[mid]
    else:
        first["encode_median_s"] = (encode_values[mid - 1] + encode_values[mid]) / 2.0
        first["decode_median_s"] = (decode_values[mid - 1] + decode_values[mid]) / 2.0
    first["seed"] = job["seed"]
    first["dataset_mode"] = "shared_file"
    first["dataset_dir"] = str(dataset_dir)
    first["variant"] = job.get("variant", first.get("variant", "default"))
    if first["algorithm"] == "iblt":
        first["implementation"] = "local/IBLT"
    if first["algorithm"] == "iblt_cpp":
        first.setdefault("implementation", "external/IBLT_Cplusplus")
    if first["algorithm"] == "minisketch":
        first.setdefault("implementation", "external/minisketch")
    if first["algorithm"] == "cpisync":
        first.setdefault("implementation", "external/cpisync")
        first["reconcile_avg_s"] = (
            sum(float(row.get("reconcile_avg_s", row.get("decode_avg_s", 0.0))) for row in valid_rows) / trials
        )
        reconcile_values = sorted(float(row.get("reconcile_median_s", row.get("decode_median_s", 0.0))) for row in valid_rows)
        if trials % 2:
            first["reconcile_median_s"] = reconcile_values[mid]
        else:
            first["reconcile_median_s"] = (reconcile_values[mid - 1] + reconcile_values[mid]) / 2.0
        first["bytes"] = sum(float(row.get("bytes", 0.0)) for row in valid_rows) / trials
        first["bits"] = first["bytes"] * 8.0
    if first["algorithm"] == "riblt":
        first.setdefault("implementation", "external/riblt")
    if first["algorithm"] == "negentropy":
        first.setdefault("implementation", "external/negentropy")
    return normalize_row(first, job, record_type="aggregate")


def normalize_failure(row: dict[str, Any], record_type: str = "error") -> dict[str, Any]:
    row.setdefault("trials", 0)
    row.setdefault("ca", 0)
    row.setdefault("cb", 0)
    row.setdefault("variant", row.get("mode", "default"))
    row.setdefault("encode_avg_s", 0.0)
    row.setdefault("decode_avg_s", 0.0)
    row.setdefault("encode_median_s", 0.0)
    row.setdefault("decode_median_s", 0.0)
    row.setdefault("bits_per_difference", 0.0)
    row.setdefault("bit_C_over_d", 0.0)
    row.setdefault("seed", 0)
    row.setdefault("bits", 0.0)
    row.setdefault("successes", 0)
    row.setdefault("success_rate", 0.0)
    return normalize_benchmark_row(
        row,
        experiment="compare_basic",
        record_type=record_type,
        algorithm=str(row.get("algorithm", "unknown")),
        variant=str(row.get("variant", row.get("mode", "default"))),
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def clear_output_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except PermissionError:
        with path.open("w", encoding="utf-8"):
            pass


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for row in rows:
        key = (int(row["d"]), int(row["ca"]), int(row["cb"]))
        groups.setdefault(key, []).append(row)

    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Basic Algorithm Comparison Summary\n\n")
        handle.write(f"- Rows: {len(rows)}\n\n")
        for key, group in sorted(groups.items()):
            handle.write(f"## d={key[0]} ca={key[1]} cb={key[2]}\n\n")
            handle.write("| algorithm | variant | success | bits/diff | bit C/d | encode avg s | decode avg s | status |\n")
            handle.write("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n")
            for row in sorted(group, key=lambda item: (str(item["algorithm"]), str(item.get("variant", "")))):
                handle.write(
                    f"| {row['algorithm']} | {row.get('variant', '')} | "
                    f"{float(row.get('success_rate', 0.0)):.3f} | "
                    f"{float(row.get('bits_per_difference', 0.0)):.3f} | "
                    f"{float(row.get('bit_C_over_d', 0.0)):.3f} | "
                    f"{float(row.get('encode_avg_s', 0.0)):.6f} | "
                    f"{float(row.get('decode_avg_s', 0.0)):.6f} | "
                    f"{row.get('status', 'ok')} |\n"
                )
            handle.write("\n")


def write_run_config(path: Path, args: argparse.Namespace, jobs: list[dict[str, Any]]) -> None:
    serialized_args = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in vars(args).items()
    }
    payload = {
        "args": serialized_args,
        "jobs": jobs,
        "supported_algorithms": sorted(SUPPORTED_ALGORITHMS),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a basic algorithm comparison.")
    parser.add_argument("--algorithms", default="xyz_v2,iblt")
    parser.add_argument("--d-values", default=None)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--capacity-factors", default="1.5,2.0,2.5,3.0")
    parser.add_argument("--mbar-factors", default="1.0,1.2,1.5")
    parser.add_argument("--symbol-factors", default="1.35,1.5,1.8")
    parser.add_argument("--frame-size-limits", default="0")
    parser.add_argument("--timestamp-modes", default="value")
    parser.add_argument("--xyz-l", type=int, default=6)
    parser.add_argument("--xyz-k", type=int, default=2)
    parser.add_argument("--xyz-mode", default="spatial", choices=["spatial", "random", "circular", "naive"])
    parser.add_argument("--iblt-cpp-value-size", type=int, default=4)
    parser.add_argument("--minisketch-field-bits", type=int, default=30)
    parser.add_argument("--cpisync-bits", type=int, default=30)
    parser.add_argument("--cpisync-epsilon", type=int, default=64)
    parser.add_argument("--cpisync-redundant", type=int, default=0)
    parser.add_argument("--cpisync-hashes", action="store_true")
    parser.add_argument("--riblt-symbol-bits", type=int, default=64)
    parser.add_argument("--riblt-field-bits", type=int, default=30)
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
    if args.trials <= 0:
        raise SystemExit("--trials must be positive")
    if args.xyz_l <= 0 or args.xyz_k <= 0:
        raise SystemExit("--xyz-l and --xyz-k must be positive")

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    dataset_dir = args.dataset_dir or dirs["tmp"]
    jobs = make_jobs(args)

    if args.dry_run:
        for job in jobs:
            preview = dict(job)
            preview["dataset_dir"] = str(dataset_dir)
            print(json.dumps(preview, sort_keys=True))
        return

    algorithms = {str(job["algorithm"]) for job in jobs}
    binaries = build_binaries(root, dirs["build"], algorithms, args.skip_build)

    for path in (dirs["raw_jsonl"], dirs["raw_csv"], dirs["summary"], dirs["errors"], dirs["run_config"]):
        clear_output_file(path)

    write_run_config(dirs["run_config"], args, jobs)

    rows: list[dict[str, Any]] = []
    for index, job in enumerate(jobs, start=1):
        dataset_config = DatasetConfig(
            d=int(job["d"]),
            ca=int(job["ca"]),
            cb=int(job["cb"]),
            seed=int(job["seed"]),
        )
        dataset_paths = prepare_datasets(dataset_config, int(job["trials"]), dataset_dir)
        print(
            f"[{index}/{len(jobs)}] {job['algorithm']} {job.get('variant', '')} "
            f"d={job['d']} trials={job['trials']}",
            flush=True,
        )
        trial_rows = [
            run_one_dataset(binaries, job, dataset_path, dirs["errors"])
            for dataset_path in dataset_paths
        ]
        row = aggregate_trials(job, trial_rows, dataset_paths[0].parent)
        rows.append(row)
        print(
            f"  success_rate={float(row.get('success_rate', 0.0)):.3f} "
            f"bit_C_over_d={float(row.get('bit_C_over_d', 0.0)):.3f}",
            flush=True,
        )
        write_jsonl(dirs["raw_jsonl"], rows)
        write_csv(dirs["raw_csv"], rows)

    write_summary(dirs["summary"], rows)
    print(f"wrote {dirs['raw_jsonl']}")
    print(f"wrote {dirs['raw_csv']}")
    print(f"wrote {dirs['summary']}")
    print(f"wrote {dirs['run_config']}")
    if not args.keep_datasets and args.dataset_dir is None and dataset_dir.exists():
        shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
