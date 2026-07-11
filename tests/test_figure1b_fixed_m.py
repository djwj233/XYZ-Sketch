#!/usr/bin/env python3
"""Run the fixed-M peeling-simulation communication frontier for Figure 1(b)."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from json_schema import normalize_benchmark_row
from plot_figure2_fixed_m import (
    DEFAULT_MARKER_C,
    DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    DEFAULT_MARKER_D,
    DEFAULT_MARKER_DELTA,
    heuristic_a,
    heuristic_z_for_m,
)
from statistics import add_binomial_ci, normal_z
from test_fig2_fixed_m_sim import build_simulator, command_for, parse_simulator_row


DEFAULT_CONFIG = Path("tests/figure1b_fixed_m_config.csv")
DEFAULT_OUTPUT = Path("tests/results/paper_fig1b_fixed_m")

SUMMARY_FIELDS = [
    "schema_version",
    "record_type",
    "experiment",
    "algorithm",
    "variant",
    "implementation",
    "search_id",
    "d",
    "k",
    "l",
    "M",
    "circular_a",
    "z",
    "z_continuous",
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
    "target_success_rate",
    "required_successes",
    "target_met",
    "point_estimate_reaches_target",
    "status",
    "invalid_reason",
    "cell_bits",
    "bits",
    "bits_per_difference",
    "field_C_over_d",
    "R_w30",
    "seed",
    "dedup_hashes",
    "dataset_mode",
    "simulation_model",
    "M_source_file",
    "M_source_description",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean: {value}")


def parse_int_set(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    result = {int(part.strip()) for part in value.split(",") if part.strip()}
    if not result:
        raise argparse.ArgumentTypeError("--d-values must contain at least one integer")
    return result


def nearest_integer(value: float) -> int:
    return int(math.floor(value + 0.5))


def read_configs(path: Path, d_filter: set[int] | None) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"d", "k", "l", "M", "expected_z", "M_source_file", "M_source_description"}
    if not rows:
        raise SystemExit(f"configuration is empty: {path}")
    missing_fields = required - set(rows[0])
    if missing_fields:
        raise SystemExit(f"configuration is missing fields: {sorted(missing_fields)}")

    configs: list[dict[str, Any]] = []
    seen_d: set[int] = set()
    for row in rows:
        config = {
            "d": int(row["d"]),
            "k": int(row["k"]),
            "l": int(row["l"]),
            "M": int(row["M"]),
            "expected_z": int(row["expected_z"]),
            "M_source_file": row["M_source_file"],
            "M_source_description": row["M_source_description"],
        }
        if d_filter is not None and config["d"] not in d_filter:
            continue
        if min(config["d"], config["k"], config["l"], config["M"]) <= 0:
            raise SystemExit(f"configuration values must be positive: {config}")
        if config["d"] in seen_d:
            raise SystemExit(f"duplicate d in configuration: {config['d']}")
        seen_d.add(config["d"])
        configs.append(config)
    if not configs:
        raise SystemExit("no configurations remain after filtering")
    return sorted(configs, key=lambda item: int(item["d"]))


def prepare_configs(args: argparse.Namespace, configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    a_value = heuristic_a(
        c_constant=args.marker_c,
        c_orient_over_c_peel=args.marker_c_orient_over_c_peel,
    )
    prepared: list[dict[str, Any]] = []
    for index, original in enumerate(configs):
        config = dict(original)
        z_continuous = heuristic_z_for_m(
            int(config["M"]),
            a_value,
            d_constant=args.marker_d,
            delta=args.marker_delta,
        )
        z_value = nearest_integer(z_continuous)
        if z_value != int(config["expected_z"]):
            raise SystemExit(
                f"heuristic z mismatch for d={config['d']}: computed {z_value}, "
                f"configuration expects {config['expected_z']}"
            )
        config.update(
            {
                "search_id": f"d{config['d']}_k{config['k']}_l{config['l']}_M{config['M']}",
                "candidate_id": f"figure1b_d{config['d']}_M{config['M']}",
                "circular_a": a_value,
                "z": z_value,
                "z_continuous": z_continuous,
                "seed": args.base_seed + index * 1_000_000,
                "dedup_hashes": args.dedup_hashes,
            }
        )
        prepared.append(config)
    return prepared


def validate_source_files(root: Path, configs: list[dict[str, Any]]) -> None:
    for config in configs:
        source = Path(str(config["M_source_file"]))
        source_path = source if source.is_absolute() else root / source
        if not source_path.exists():
            raise SystemExit(f"M provenance file does not exist: {source_path}")


def ensure_dirs(root: Path, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    build = root / "build"
    build.mkdir(parents=True, exist_ok=True)
    return {
        "base": output_dir,
        "build": build,
        "raw": output_dir / "raw.jsonl",
        "summary_jsonl": output_dir / "summary.jsonl",
        "summary_csv": output_dir / "summary.csv",
        "summary_md": output_dir / "summary.md",
        "run_config": output_dir / "run_config.json",
        "errors": output_dir / "errors.log",
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSON in {path}:{line_number}: {exc}") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 1(b) Fixed-M Peeling Frontier\n\n")
        handle.write("| d | M | a | z | success | 95% CI | target | R_w30 | status |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |\n")
        for row in rows:
            handle.write(
                f"| {row['d']} | {row['M']} | {float(row['circular_a']):.6g} | {row['z']} | "
                f"{float(row['success_rate']):.3f} | "
                f"[{float(row['ci_low']):.3f}, {float(row['ci_high']):.3f}] | "
                f"{'met' if row['target_met'] else 'failed'} | {float(row['R_w30']):.6f} | "
                f"{row['status']} |\n"
            )


def persist(dirs: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    ordered = sorted(rows, key=lambda item: int(item["d"]))
    write_jsonl(dirs["raw"], ordered)
    write_jsonl(dirs["summary_jsonl"], ordered)
    write_csv(dirs["summary_csv"], ordered)
    write_markdown(dirs["summary_md"], ordered)


def validate_resume_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    for row in rows:
        if int(row.get("trials", -1)) != args.trials:
            raise SystemExit("cannot resume: existing row uses a different trial count")
        if abs(float(row.get("target_success_rate", -1.0)) - args.target_success_rate) > 1e-12:
            raise SystemExit("cannot resume: existing row uses a different target success rate")


def run_one(
    binary: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    errors_path: Path,
) -> dict[str, Any] | None:
    command = command_for(binary, config, args.trials)
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        with errors_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{config['search_id']}: {exc}\n")
        return None
    row = parse_simulator_row(command, config, completed, errors_path)
    if row is None:
        return None

    d_value = int(config["d"])
    l_value = int(config["l"])
    m_value = int(config["M"])
    cell_bits = (math.floor(math.log2(2 * l_value + 1)) + 1) + 32 * l_value
    bits = m_value * cell_bits
    success_rate = float(row.get("success_rate", 0.0))
    row.update(
        {
            "search_id": config["search_id"],
            "candidate_id": config["candidate_id"],
            "z_continuous": config["z_continuous"],
            "target_success_rate": args.target_success_rate,
            "required_successes": math.ceil(args.target_success_rate * args.trials),
            "target_met": success_rate >= args.target_success_rate,
            "point_estimate_reaches_target": success_rate >= args.target_success_rate,
            "cell_bits": cell_bits,
            "bits": bits,
            "bits_per_difference": bits / d_value,
            "R_w30": bits / (30.0 * d_value),
            "simulation_model": "circular_hypergraph_peeling",
            "M_source_file": config["M_source_file"],
            "M_source_description": config["M_source_description"],
        }
    )
    row = add_binomial_ci(row, confidence=args.ci_confidence, method="wilson")
    return normalize_benchmark_row(
        row,
        experiment="paper_fig1b_fixed_m",
        record_type="aggregate",
        algorithm="peeling_sim",
        variant=f"circular,a={float(config['circular_a']):.6g},z={int(config['z'])}",
        implementation="local/peeling-sim",
        status=str(row.get("status", "ok")),
        dataset_mode="simulated_hypergraph",
    )


def write_run_config(
    path: Path,
    args: argparse.Namespace,
    config_path: Path,
    configs: list[dict[str, Any]],
) -> None:
    payload = {
        "args": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "config_file": str(config_path),
        "configs": configs,
        "M_search_performed": False,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run fixed-M Figure 1(b) peeling simulations without M search.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--d-values", default=None, help="Optional comma-separated d filter.")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.9)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--dedup-hashes", type=parse_bool, default=False)
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--marker-c", type=float, default=DEFAULT_MARKER_C)
    parser.add_argument(
        "--marker-c-orient-over-c-peel",
        type=float,
        default=DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    )
    parser.add_argument("--marker-d", type=float, default=DEFAULT_MARKER_D)
    parser.add_argument("--marker-delta", type=float, default=DEFAULT_MARKER_DELTA)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.trials <= 0:
        raise SystemExit("--trials must be positive")
    if not (0.0 < args.target_success_rate <= 1.0):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")
    if args.base_seed < 0:
        raise SystemExit("--base-seed must be non-negative")
    normal_z(args.ci_confidence)

    root = repo_root()
    config_path = args.config if args.config.is_absolute() else root / args.config
    output_dir = args.output_dir if args.output_dir.is_absolute() else root / args.output_dir
    if not config_path.exists():
        raise SystemExit(f"configuration does not exist: {config_path}")
    configs = prepare_configs(args, read_configs(config_path, parse_int_set(args.d_values)))
    validate_source_files(root, configs)

    if args.dry_run:
        for config in configs:
            print(
                f"{config['search_id']}: d={config['d']} M={config['M']} "
                f"a={config['circular_a']:.12g} z={config['z']} "
                f"z_continuous={config['z_continuous']:.6f} trials={args.trials}"
            )
        return

    dirs = ensure_dirs(root, output_dir)
    binary = build_simulator(root, dirs["build"], args.skip_build)
    if args.resume:
        rows = read_jsonl(dirs["summary_jsonl"])
        validate_resume_rows(rows, args)
    else:
        for key in ("raw", "summary_jsonl", "summary_csv", "summary_md", "run_config", "errors"):
            if dirs[key].exists():
                dirs[key].unlink()
        rows = []

    completed_ids = {str(row.get("search_id")) for row in rows}
    pending = [config for config in configs if config["search_id"] not in completed_ids]
    write_run_config(dirs["run_config"], args, config_path, configs)
    print(f"configs={len(configs)} completed={len(completed_ids)} pending={len(pending)}", flush=True)

    def record(config: dict[str, Any], row: dict[str, Any] | None) -> None:
        if row is None:
            print(f"failed {config['search_id']}; see {dirs['errors']}", flush=True)
            return
        rows.append(row)
        persist(dirs, rows)
        print(
            f"completed {config['search_id']} success={row['successes']}/{row['trials']} "
            f"target_met={row['target_met']} R_w30={row['R_w30']:.6f}",
            flush=True,
        )

    if args.jobs == 1:
        for config in pending:
            record(config, run_one(binary, config, args, dirs["errors"]))
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = {
                executor.submit(run_one, binary, config, args, dirs["errors"]): config
                for config in pending
            }
            for future in as_completed(futures):
                config = futures[future]
                try:
                    row = future.result()
                except Exception as exc:  # Preserve other completed rows before surfacing a worker error.
                    with dirs["errors"].open("a", encoding="utf-8") as handle:
                        handle.write(f"{config['search_id']}: worker exception: {exc}\n")
                    row = None
                record(config, row)

    missing = [config["search_id"] for config in configs if config["search_id"] not in {str(row.get("search_id")) for row in rows}]
    if missing:
        raise SystemExit(f"incomplete run; missing {len(missing)} configurations")
    print(f"wrote {dirs['summary_csv']}")


if __name__ == "__main__":
    main()
