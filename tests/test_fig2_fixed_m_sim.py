#!/usr/bin/env python3
"""Run fixed-M peeling grids for current Figure 1(b,c) and Appendix Figure 3."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from json_schema import normalize_benchmark_row
from statistics import add_binomial_ci, normal_z


SUMMARY_FIELDS = [
    "search_id",
    "candidate_id",
    "d",
    "k",
    "l",
    "M",
    "field_C_over_d",
    "mode",
    "circular_a",
    "z",
    "range_length",
    "circular_base_range",
    "trials",
    "successes",
    "success_rate",
    "peeling_success_rate",
    "ci_low",
    "ci_high",
    "ci_method",
    "ci_confidence",
    "status",
    "invalid_reason",
    "seed",
    "dedup_hashes",
    "source_count",
    "source_ok_count",
    "source_unresolved_count",
    "source_a_values",
    "source_z_values",
]

ERROR_LOCK = threading.Lock()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def exe_suffix() -> str:
    return ".exe" if sys.platform.startswith("win") else ""


def parse_float_list(value: str) -> list[float]:
    result = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not result:
        raise ValueError("expected at least one float")
    return result


def parse_int_list(value: str) -> list[int]:
    result = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not result:
        raise ValueError("expected at least one integer")
    return result


def parse_optional_int_set(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    return set(parse_int_list(value))


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def read_candidates(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_grid_specs(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    candidates = value.get("candidates") if isinstance(value, dict) else None
    if not isinstance(candidates, dict):
        raise ValueError("grid spec must contain a candidates object")
    return {str(key): dict(item) for key, item in candidates.items()}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


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
        handle.write("# Figure 2 Fixed-M Peeling Simulation\n\n")
        handle.write("| d | k | l | M | M*l/d | a | z | success | CI low | status |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(
            rows,
            key=lambda item: (
                int(item["d"]),
                int(item["k"]),
                int(item["l"]),
                int(item["M"]),
                float(item["circular_a"]),
                int(item["z"]),
            ),
        ):
            handle.write(
                f"| {row.get('d', '')} | {row.get('k', '')} | {row.get('l', '')} | "
                f"{row.get('M', '')} | {float(row.get('field_C_over_d', 0.0)):.6g} | "
                f"{float(row.get('circular_a', 0.0)):.6g} | {row.get('z', '')} | "
                f"{float(row.get('peeling_success_rate', row.get('success_rate', 0.0))):.6g} | "
                f"{float(row.get('ci_low', 0.0)):.6g} | {row.get('status', '')} |\n"
            )


def ensure_dirs(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "paper_fig2_fixed_m_sim"
    build = root / "build"
    base.mkdir(parents=True, exist_ok=True)
    build.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "build": build,
        "raw_jsonl": base / "raw.jsonl",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "run_config": base / "run_config.json",
        "errors": base / "errors.log",
    }


def build_simulator(root: Path, build_dir: Path, skip_build: bool) -> Path:
    binary = build_dir / f"fig2_peeling_sim{exe_suffix()}"
    if skip_build:
        if not binary.exists():
            raise FileNotFoundError(f"simulator binary not found: {binary}")
        return binary
    source = root / "tests" / "benchmarks" / "fig2_peeling_sim.cpp"
    subprocess.run(["g++", "-std=c++17", "-O2", str(source), "-o", str(binary)], cwd=root, check=True)
    return binary


def candidate_int(candidate: dict[str, Any], key: str) -> int:
    return int(float(candidate[key]))


def candidate_float(candidate: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = candidate.get(key)
    if value in (None, ""):
        return default
    return float(value)


def make_configs(args: argparse.Namespace, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    default_a_values = parse_float_list(args.a_values)
    default_z_values = parse_int_list(args.z_values)
    grid_specs = read_grid_specs(args.grid_spec)
    d_filter = parse_optional_int_set(args.d_values)
    m_filter = parse_optional_int_set(args.m_values)
    dedup_hashes = parse_bool(args.dedup_hashes)
    configs: list[dict[str, Any]] = []
    config_index = 0

    for candidate in candidates:
        d_value = candidate_int(candidate, "d")
        k_value = candidate_int(candidate, "k")
        l_value = candidate_int(candidate, "l")
        m_value = candidate_int(candidate, "M")
        if d_filter is not None and d_value not in d_filter:
            continue
        if m_filter is not None and m_value not in m_filter:
            continue
        candidate_id = str(candidate["candidate_id"])
        grid_spec = grid_specs.get(candidate_id)
        if grid_spec is None:
            a_values = default_a_values
            z_values = default_z_values
        else:
            a_values = [float(value) for value in grid_spec.get("a_values", [])]
            z_values = [int(value) for value in grid_spec.get("z_values", [])]
            if not a_values or not z_values:
                raise SystemExit(f"grid spec for {candidate_id} must define non-empty a_values and z_values")
        for a_index, a_value in enumerate(a_values):
            if not (0.0 <= a_value < 1.0):
                raise SystemExit(f"circular a must be in [0, 1): {a_value}")
            for z_value in z_values:
                if z_value < 0:
                    raise SystemExit(f"z must be non-negative: {z_value}")
                configs.append(
                    {
                        "search_id": f"{candidate['candidate_id']}_a{a_index}_z{z_value}",
                        "candidate_id": candidate_id,
                        "d": d_value,
                        "k": k_value,
                        "l": l_value,
                        "M": m_value,
                        "circular_a": a_value,
                        "z": z_value,
                        "seed": args.base_seed if args.shared_trial_seeds else args.base_seed + config_index * 1009,
                        "dedup_hashes": dedup_hashes,
                        "source_count": candidate.get("source_count", ""),
                        "source_ok_count": candidate.get("source_ok_count", ""),
                        "source_unresolved_count": candidate.get("source_unresolved_count", ""),
                        "source_a_values": candidate.get("source_a_values", ""),
                        "source_z_values": candidate.get("source_z_values", ""),
                        "source_search_ids": candidate.get("source_search_ids", ""),
                        "source_field_C_over_d": candidate_float(candidate, "field_C_over_d"),
                    }
                )
                config_index += 1
    if args.limit is not None:
        configs = configs[: args.limit]
    return configs


def command_for(binary: Path, config: dict[str, Any], trials: int) -> list[str]:
    return [
        str(binary),
        "--d",
        str(config["d"]),
        "--l",
        str(config["l"]),
        "--k",
        str(config["k"]),
        "--M",
        str(config["M"]),
        "--a",
        f"{float(config['circular_a']):.12g}",
        "--z",
        str(config["z"]),
        "--trials",
        str(trials),
        "--seed",
        str(config["seed"]),
        "--dedup-hashes",
        str(bool(config["dedup_hashes"])).lower(),
        "--format",
        "jsonl",
    ]


def append_error(path: Path, config: dict[str, Any], command: list[str], message: str) -> None:
    with ERROR_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("CONFIG " + json.dumps(config, sort_keys=True) + "\n")
            handle.write("COMMAND " + json.dumps(command) + "\n")
            handle.write(message.rstrip() + "\n\n")


def parse_simulator_row(
    command: list[str],
    config: dict[str, Any],
    completed: subprocess.CompletedProcess[str],
    errors_path: Path,
) -> dict[str, Any] | None:
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


def run_config(binary: Path, config: dict[str, Any], args: argparse.Namespace, errors_path: Path) -> dict[str, Any] | None:
    command = command_for(binary, config, args.trials)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        append_error(errors_path, config, command, f"OSERROR {exc}")
        return None
    row = parse_simulator_row(command, config, completed, errors_path)
    if row is None:
        return None
    row.update(
        {
            "search_id": config["search_id"],
            "candidate_id": config["candidate_id"],
            "source_count": config["source_count"],
            "source_ok_count": config["source_ok_count"],
            "source_unresolved_count": config["source_unresolved_count"],
            "source_a_values": config["source_a_values"],
            "source_z_values": config["source_z_values"],
            "source_search_ids": config["source_search_ids"],
        }
    )
    row = add_binomial_ci(row, confidence=args.ci_confidence, method=args.ci_method)
    row["peeling_success_rate"] = row.get("success_rate", 0.0)
    return normalize_benchmark_row(
        row,
        experiment="paper_fig2_fixed_m_sim",
        record_type="aggregate",
        algorithm="peeling_sim",
        variant=f"circular,a={float(config['circular_a']):.6g},z={int(config['z'])}",
        implementation="local/peeling-sim",
        status=str(row.get("status", "ok")),
        dataset_mode="simulated_hypergraph",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed-M circular a/z peeling simulations for Figure 1 and Appendix Figure 3.")
    parser.add_argument("--m-candidates", type=Path, default=Path("tests") / "results" / "paper_fig2_m_candidates" / "m_candidates.csv")
    parser.add_argument("--a-values", default="0,0.1,0.2,0.3333333333,0.4,0.5,0.6,0.75,0.9")
    parser.add_argument("--z-values", default="0,1,2,3,4,5,6,8,10,12,16")
    parser.add_argument("--grid-spec", type=Path, default=None, help="Optional candidate-specific a/z grid JSON.")
    parser.add_argument("--d-values", default=None, help="Optional comma-separated d filter.")
    parser.add_argument("--m-values", default=None, help="Optional comma-separated M filter.")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--dedup-hashes", default="false")
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--jobs", type=int, default=1, help="Number of simulator subprocesses to run concurrently.")
    parser.add_argument(
        "--shared-trial-seeds", dest="shared_trial_seeds", action="store_true",
        help="Use the same trial seeds for every fixed-M and (a,z) configuration (default).",
    )
    parser.add_argument(
        "--independent-trial-seeds", dest="shared_trial_seeds", action="store_false",
        help="Use different trial seeds for each grid cell.",
    )
    parser.set_defaults(shared_trial_seeds=True)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials <= 0:
        raise SystemExit("--trials must be positive")
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")
    normal_z(args.ci_confidence)

    root = repo_root()
    dirs = ensure_dirs(root, args.output_dir)
    candidates = read_candidates(args.m_candidates)
    configs = make_configs(args, candidates)

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: d={config['d']} k={config['k']} l={config['l']} "
                f"M={config['M']} a={config['circular_a']} z={config['z']}"
            )
        return

    binary = build_simulator(root, dirs["build"], args.skip_build)
    if args.resume:
        summaries = read_jsonl(dirs["summary_jsonl"])
        completed_ids = {str(row.get("search_id")) for row in summaries if row.get("search_id") not in (None, "")}
        raw_rows = [row for row in read_jsonl(dirs["raw_jsonl"]) if str(row.get("search_id")) in completed_ids]
        print(f"[resume] completed={len(completed_ids)} remaining={len(configs) - len(completed_ids)}", flush=True)
    else:
        for path in (dirs["raw_jsonl"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"], dirs["errors"]):
            if path.exists():
                path.unlink()
        summaries: list[dict[str, Any]] = []
        raw_rows: list[dict[str, Any]] = []
        completed_ids: set[str] = set()

    write_run_config(dirs["run_config"], args, configs)
    pending: list[tuple[int, dict[str, Any]]] = []
    for index, config in enumerate(configs, start=1):
        if args.resume and str(config["search_id"]) in completed_ids:
            print(f"[{index}/{len(configs)}] skip completed {config['search_id']}", flush=True)
            continue
        pending.append((index, config))

    def record_result(index: int, config: dict[str, Any], row: dict[str, Any] | None) -> None:
        if row is None:
            print(f"[{index}/{len(configs)}] failed {config['search_id']}", flush=True)
            return
        raw_rows.append(row)
        summaries.append(row)
        raw_rows.sort(key=lambda item: str(item.get("search_id", "")))
        summaries.sort(key=lambda item: str(item.get("search_id", "")))
        print(
            f"[{index}/{len(configs)}] {config['search_id']} status={row.get('status')} "
            f"success={row.get('peeling_success_rate')} ci=[{row.get('ci_low')}, {row.get('ci_high')}]",
            flush=True,
        )
        write_jsonl(dirs["raw_jsonl"], raw_rows)
        write_jsonl(dirs["summary_jsonl"], summaries)
        write_summary_csv(dirs["summary_csv"], summaries)
        write_summary_md(dirs["summary_md"], summaries)

    if args.jobs == 1:
        for index, config in pending:
            record_result(index, config, run_config(binary, config, args, dirs["errors"]))
    else:
        print(f"[parallel] jobs={args.jobs} pending={len(pending)}", flush=True)
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_config, binary, config, args, dirs["errors"]): (index, config)
                for index, config in pending
            }
            for future in as_completed(futures):
                index, config = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    append_error(dirs["errors"], config, [], f"WORKER ERROR {exc}")
                    row = None
                record_result(index, config, row)

    print(f"wrote {dirs['raw_jsonl']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")


if __name__ == "__main__":
    main()
