#!/usr/bin/env python3
"""Find the smallest empirical working M for XYZ-v2 configurations."""

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


SUMMARY_FIELDS = [
    "search_id",
    "d",
    "l",
    "k",
    "best_M",
    "best_C_over_d",
    "z_policy",
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
    "ci_low_best_M",
    "ci_low_best_C_over_d",
    "uncertain_M_min",
    "uncertain_M_max",
    "uncertain_C_over_d_min",
    "uncertain_C_over_d_max",
    "encode_avg_s",
    "decode_avg_s",
    "status",
    "seed",
    "ca",
    "cb",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "best_m"
    base.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
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


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def make_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    d_values = parse_int_list(args.d_values)
    l_values = parse_int_list(args.l_values)
    k_values = parse_int_list(args.k_values)

    configs: list[dict[str, Any]] = []
    search_index = 0
    for d_index, d_value in enumerate(d_values):
        for l_index, l_value in enumerate(l_values):
            if l_value > d_value:
                continue
            for k_index, k_value in enumerate(k_values):
                ca, cb = choose_set_sizes(
                    d_value,
                    max_set_size=args.max_set_size,
                    scale=args.set_size_scale,
                )
                seed = args.base_seed + 1_000_000 * d_index + 10_000 * l_index + 100 * k_index
                configs.append(
                    {
                        "search_id": f"d{d_value}_l{l_value}_k{k_value}",
                        "d": d_value,
                        "l": l_value,
                        "k": k_value,
                        "seed": seed,
                        "ca": ca,
                        "cb": cb,
                        "mode": "spatial",
                        "index": search_index,
                    }
                )
                search_index += 1
    return configs


def choose_z(m_value: int, policy: str, fixed_z: int | None) -> int:
    if policy == "adaptive":
        return max(0, round((m_value ** (1.0 / 3.0)) / 3.0))
    if policy == "fixed":
        if fixed_z is None:
            raise ValueError("--fixed-z is required when --z-policy fixed")
        return fixed_z
    raise ValueError(f"unknown z policy: {policy}")


def initial_factor(k_value: int) -> float:
    if k_value <= 2:
        return 1.5
    if k_value == 3:
        return 2.5
    return 3.5


def lower_bound_m(config: dict[str, Any]) -> int:
    return max(int(config["k"]), math.ceil(int(config["d"]) / int(config["l"])), 1)


def initial_upper_m(config: dict[str, Any]) -> int:
    return max(
        lower_bound_m(config),
        math.ceil(initial_factor(int(config["k"])) * int(config["d"]) / int(config["l"])),
    )


def max_m(config: dict[str, Any], max_c_over_d: float) -> int:
    return max(lower_bound_m(config), math.ceil(max_c_over_d * int(config["d"]) / int(config["l"])))


def required_successes(target: float, trials: int) -> int:
    return math.ceil(target * trials)


def c_over_d_for_m(config: dict[str, Any], m_value: int | str | None) -> float | str:
    if m_value is None or m_value == "":
        return ""
    return int(m_value) * int(config["l"]) / int(config["d"])


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
        "ci_low_best_M": ci_low_best_m,
        "ci_low_best_C_over_d": c_over_d_for_m(config, ci_low_best_m),
        "uncertain_M_min": uncertain_min,
        "uncertain_M_max": uncertain_max,
        "uncertain_C_over_d_min": c_over_d_for_m(config, uncertain_min),
        "uncertain_C_over_d_max": c_over_d_for_m(config, uncertain_max),
    }


def command_for(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    z_value: int,
    trials: int,
    seed: int,
) -> list[str]:
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
        str(seed),
        "--mode",
        str(config["mode"]),
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


def run_probe(
    binary: Path,
    config: dict[str, Any],
    m_value: int,
    z_value: int,
    trials: int,
    seed: int,
    phase: str,
    args: argparse.Namespace,
    errors_path: Path,
) -> dict[str, Any] | None:
    command = command_for(binary, config, m_value, z_value, trials, seed)
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
        experiment="find_best_m",
        record_type="probe",
        algorithm="xyz_v2",
        variant=str(config["mode"]),
        implementation="local/XYZ-v2",
        dataset_mode="internal_generator",
    )


def works(row: dict[str, Any] | None, args: argparse.Namespace) -> bool:
    if row is None:
        return False
    if args.threshold_policy == "point":
        return int(row["successes"]) >= required_successes(args.target_success_rate, int(row["trials"]))
    if args.threshold_policy == "ci-low":
        return float(row.get("ci_low", 0.0)) >= args.target_success_rate
    raise ValueError(f"unknown threshold policy: {args.threshold_policy}")


def find_upper_bound(
    binary: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    errors_path: Path,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    hi = initial_upper_m(config)
    limit = max_m(config, args.max_c_over_d)

    while hi <= limit:
        z_value = choose_z(hi, args.z_policy, args.fixed_z)
        row = run_probe(
            binary,
            config,
            hi,
            z_value,
            args.probe_trials,
            int(config["seed"]),
            "upper_bound",
            args,
            errors_path,
        )
        if row is not None:
            probes.append(row)
        if works(row, args):
            return hi, probes
        hi *= 2

    return None, probes


def binary_search_m(
    binary: Path,
    config: dict[str, Any],
    hi: int,
    args: argparse.Namespace,
    errors_path: Path,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    lo = lower_bound_m(config)
    best: int | None = hi

    while lo <= hi:
        mid = (lo + hi) // 2
        z_value = choose_z(mid, args.z_policy, args.fixed_z)
        row = run_probe(
            binary,
            config,
            mid,
            z_value,
            args.probe_trials,
            int(config["seed"]),
            "binary_search",
            args,
            errors_path,
        )
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
) -> dict[str, Any] | None:
    z_value = choose_z(best_m, args.z_policy, args.fixed_z)
    return run_probe(
        binary,
        config,
        best_m,
        z_value,
        args.final_trials,
        int(config["seed"]),
        "final_validate",
        args,
        errors_path,
    )


def summary_from_final(
    config: dict[str, Any],
    final_row: dict[str, Any] | None,
    best_m: int | None,
    args: argparse.Namespace,
    status: str,
    probes: list[dict[str, Any]],
) -> dict[str, Any]:
    rollup = threshold_rollup(config, probes, args.target_success_rate)
    if final_row is None or best_m is None:
        return normalize_benchmark_row(
            {
                "search_id": config["search_id"],
                "d": config["d"],
                "l": config["l"],
                "k": config["k"],
                "mode": config["mode"],
                "best_M": "",
                "best_C_over_d": "",
                "z_policy": args.z_policy,
                "target_success_rate": args.target_success_rate,
                "required_probe_successes": required_successes(args.target_success_rate, args.probe_trials),
                "required_final_successes": required_successes(args.target_success_rate, args.final_trials),
                "probe_trials": args.probe_trials,
                "final_trials": args.final_trials,
                "final_successes": "",
                "final_success_rate": "",
                "final_ci_low": "",
                "final_ci_high": "",
                "ci_method": args.ci_method,
                "ci_confidence": args.ci_confidence,
                "threshold_policy": args.threshold_policy,
                "point_estimate_reaches_target": False,
                "ci_low_reaches_target": False,
                "ci_high_reaches_target": False,
                "encode_avg_s": "",
                "decode_avg_s": "",
                "status": status,
                "seed": config["seed"],
                "ca": config["ca"],
                "cb": config["cb"],
                **rollup,
            },
            experiment="find_best_m",
            record_type="threshold",
            algorithm="xyz_v2",
            variant=str(config["mode"]),
            implementation="local/XYZ-v2",
            dataset_mode="internal_generator",
        )

    return normalize_benchmark_row(
        {
            "search_id": config["search_id"],
            "d": config["d"],
            "l": config["l"],
            "k": config["k"],
            "mode": config["mode"],
            "M": best_m,
            "best_M": best_m,
            "best_C_over_d": best_m * int(config["l"]) / int(config["d"]),
            "z_policy": args.z_policy,
            "target_success_rate": args.target_success_rate,
            "required_probe_successes": required_successes(args.target_success_rate, args.probe_trials),
            "required_final_successes": required_successes(args.target_success_rate, args.final_trials),
            "probe_trials": args.probe_trials,
            "final_trials": args.final_trials,
            "final_successes": final_row["successes"],
            "final_success_rate": final_row["success_rate"],
            "final_ci_low": final_row.get("ci_low", ""),
            "final_ci_high": final_row.get("ci_high", ""),
            "ci_method": args.ci_method,
            "ci_confidence": args.ci_confidence,
            "threshold_policy": args.threshold_policy,
            **reaches_target(final_row, args.target_success_rate),
            **rollup,
            "encode_avg_s": final_row["encode_avg_s"],
            "decode_avg_s": final_row["decode_avg_s"],
            "status": status,
            "seed": config["seed"],
            "ca": config["ca"],
            "cb": config["cb"],
            "trials": final_row.get("trials", args.final_trials),
            "successes": final_row.get("successes", 0),
            "success_rate": final_row.get("success_rate", 0.0),
            "ci_low": final_row.get("ci_low", ""),
            "ci_high": final_row.get("ci_high", ""),
            "bits": final_row.get("bits", 0),
            "bit_C_over_d": final_row.get("bit_C_over_d", ""),
            "encode_median_s": final_row.get("encode_median_s", 0.0),
            "decode_median_s": final_row.get("decode_median_s", 0.0),
        },
        experiment="find_best_m",
        record_type="threshold",
        algorithm="xyz_v2",
        variant=str(config["mode"]),
        implementation="local/XYZ-v2",
        dataset_mode="internal_generator",
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
    parser = argparse.ArgumentParser(description="Find empirical best M for XYZ-v2.")
    parser.add_argument("--d-values", default="1000,3000,10000", help="Comma-separated d values.")
    parser.add_argument("--l-values", default="4,6,8", help="Comma-separated l values.")
    parser.add_argument("--k-values", default="2,3", help="Comma-separated k values.")
    parser.add_argument("--probe-trials", type=int, default=20, help="Trials per search probe.")
    parser.add_argument("--final-trials", type=int, default=100, help="Trials for final validation.")
    parser.add_argument("--target-success-rate", type=float, default=0.95, help="Target success rate.")
    parser.add_argument("--max-C-over-d", type=float, default=8.0, dest="max_c_over_d")
    parser.add_argument("--z-policy", choices=["adaptive", "fixed"], default="adaptive")
    parser.add_argument("--fixed-z", type=int, default=None)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--skip-build", action="store_true", help="Reuse existing benchmark binary.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned configurations only.")
    parser.add_argument("--limit", type=int, default=None, help="Run only first N configurations.")
    parser.add_argument("--output-dir", type=Path, default=None)
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
    if args.z_policy == "fixed" and args.fixed_z is None:
        raise SystemExit("--fixed-z is required with --z-policy fixed")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    configs = make_grid(args)
    if args.limit is not None:
        configs = configs[: args.limit]

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: lo={lower_bound_m(config)} "
                f"hi0={initial_upper_m(config)} max={max_m(config, args.max_c_over_d)} "
                f"seed={config['seed']} ca={config['ca']} cb={config['cb']}"
            )
        return

    binary = build_benchmark(root, dirs["build"], args.skip_build)
    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["errors"]):
        if path.exists():
            path.unlink()

    all_probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for index, config in enumerate(configs, start=1):
        print(
            f"[{index}/{len(configs)}] {config['search_id']} "
            f"target={args.target_success_rate} probe_trials={args.probe_trials}",
            flush=True,
        )
        hi, upper_probes = find_upper_bound(binary, config, args, dirs["errors"])
        all_probes.extend(upper_probes)

        if hi is None:
            print("  unresolved: no working upper bound", flush=True)
            summaries.append(summary_from_final(config, None, None, args, "unresolved", upper_probes))
            write_jsonl(dirs["probes"], all_probes)
            write_jsonl(dirs["summary_jsonl"], summaries)
            write_summary_csv(dirs["summary_csv"], summaries)
            continue

        best_m, search_probes = binary_search_m(binary, config, hi, args, dirs["errors"])
        all_probes.extend(search_probes)

        if best_m is None:
            print("  unresolved: binary search failed", flush=True)
            current_probes = upper_probes + search_probes
            summaries.append(summary_from_final(config, None, None, args, "unresolved", current_probes))
            write_jsonl(dirs["probes"], all_probes)
            write_jsonl(dirs["summary_jsonl"], summaries)
            write_summary_csv(dirs["summary_csv"], summaries)
            continue

        final_row = final_validate(binary, config, best_m, args, dirs["errors"])
        current_probes = upper_probes + search_probes
        if final_row is not None:
            all_probes.append(final_row)
            current_probes.append(final_row)
        status = "ok" if works(final_row, args) else "unresolved"
        summary = summary_from_final(config, final_row, best_m, args, status, current_probes)
        summaries.append(summary)
        print(
            f"  best_M={best_m} C/d={summary['best_C_over_d']:.3f} "
            f"final_success={summary['final_success_rate']} status={status}",
            flush=True,
        )

        write_jsonl(dirs["probes"], all_probes)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_summary_csv(dirs["summary_csv"], summaries)

    print(f"wrote {dirs['probes']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")


if __name__ == "__main__":
    main()
