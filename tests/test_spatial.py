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


SUMMARY_FIELDS = [
    "search_id",
    "d",
    "l",
    "k",
    "mode",
    "best_M",
    "best_C_over_d",
    "z_at_best_M",
    "target_success_rate",
    "required_probe_successes",
    "required_final_successes",
    "probe_trials",
    "final_trials",
    "final_successes",
    "final_success_rate",
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
    base = output_dir or root / "tests" / "results" / "spatial"
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

    source = root / "XYZ-v2" / "xyz_v2_bench.cpp"
    command = ["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)]
    subprocess.run(command, cwd=root, check=True)
    return binary


def parse_int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_str_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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
                    seed = (
                        args.base_seed
                        + 1_000_000 * d_index
                        + 10_000 * l_index
                        + 100 * k_index
                        + mode_index
                    )
                    configs.append(
                        {
                            "search_id": f"d{d_value}_l{l_value}_k{k_value}_{mode}",
                            "d": d_value,
                            "l": l_value,
                            "k": k_value,
                            "mode": mode,
                            "seed": seed,
                            "ca": ca,
                            "cb": cb,
                        }
                    )
    return configs


def choose_z(mode: str, m_value: int) -> int:
    if mode == "random":
        return 0
    return max(0, round((m_value ** (1.0 / 3.0)) / 3.0))


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


def command_for(binary: Path, config: dict[str, Any], m_value: int, z_value: int, trials: int, seed: int) -> list[str]:
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
    trials: int,
    seed: int,
    phase: str,
    target: float,
    errors_path: Path,
) -> dict[str, Any] | None:
    z_value = choose_z(str(config["mode"]), m_value)
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
        append_error(errors_path, config, command, f"PARSE got {len(lines)} lines\n{completed.stdout}")
        return None

    try:
        row = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        append_error(errors_path, config, command, f"JSONERROR {exc}\n{completed.stdout}")
        return None

    row.update(
        {
            "search_id": config["search_id"],
            "phase": phase,
            "candidate_M": m_value,
            "target_success_rate": target,
            "required_successes": required_successes(target, trials),
            "z_at_candidate_M": z_value,
        }
    )
    return row


def works(row: dict[str, Any] | None, target: float) -> bool:
    if row is None:
        return False
    return int(row["successes"]) >= required_successes(target, int(row["trials"]))


def find_best_m(
    binary: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    errors_path: Path,
) -> tuple[int | None, list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    hi = initial_upper_m(config)
    limit = max_m(config, args.max_c_over_d)

    while hi <= limit:
        row = run_probe(binary, config, hi, args.probe_trials, int(config["seed"]), "upper_bound", args.target_success_rate, errors_path)
        if row is not None:
            probes.append(row)
        if works(row, args.target_success_rate):
            break
        hi *= 2
    else:
        return None, probes

    lo = lower_bound_m(config)
    best = hi
    while lo <= hi:
        mid = (lo + hi) // 2
        row = run_probe(binary, config, mid, args.probe_trials, int(config["seed"]), "binary_search", args.target_success_rate, errors_path)
        if row is not None:
            probes.append(row)
        if works(row, args.target_success_rate):
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
    return run_probe(binary, config, best_m, args.final_trials, int(config["seed"]), "final_validate", args.target_success_rate, errors_path)


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
        "mode": config["mode"],
        "target_success_rate": args.target_success_rate,
        "required_probe_successes": required_successes(args.target_success_rate, args.probe_trials),
        "required_final_successes": required_successes(args.target_success_rate, args.final_trials),
        "probe_trials": args.probe_trials,
        "final_trials": args.final_trials,
        "status": status,
        "seed": config["seed"],
        "ca": config["ca"],
        "cb": config["cb"],
    }
    if final_row is None or best_m is None:
        base.update(
            {
                "best_M": "",
                "best_C_over_d": "",
                "z_at_best_M": "",
                "final_successes": "",
                "final_success_rate": "",
                "encode_avg_s": "",
                "decode_avg_s": "",
            }
        )
        return base

    base.update(
        {
            "best_M": best_m,
            "best_C_over_d": best_m * int(config["l"]) / int(config["d"]),
            "z_at_best_M": choose_z(str(config["mode"]), best_m),
            "final_successes": final_row["successes"],
            "final_success_rate": final_row["success_rate"],
            "encode_avg_s": final_row["encode_avg_s"],
            "decode_avg_s": final_row["decode_avg_s"],
        }
    )
    return base


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
    if args.probe_trials <= 0 or args.final_trials <= 0:
        raise SystemExit("--probe-trials and --final-trials must be positive")
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.max_c_over_d <= 0:
        raise SystemExit("--max-C-over-d must be positive")

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
    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["errors"]):
        if path.exists():
            path.unlink()

    all_probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    for index, config in enumerate(configs, start=1):
        print(f"[{index}/{len(configs)}] {config['search_id']}", flush=True)
        best_m, probes = find_best_m(binary, config, args, dirs["errors"])
        all_probes.extend(probes)
        if best_m is None:
            print("  unresolved", flush=True)
            summaries.append(summary_from_final(config, None, None, args, "unresolved"))
        else:
            final_row = final_validate(binary, config, best_m, args, dirs["errors"])
            if final_row is not None:
                all_probes.append(final_row)
            status = "ok" if works(final_row, args.target_success_rate) else "unresolved"
            summary = summary_from_final(config, final_row, best_m, args, status)
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


if __name__ == "__main__":
    main()
