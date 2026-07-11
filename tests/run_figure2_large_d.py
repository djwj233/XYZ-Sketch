#!/usr/bin/env python3
"""Run the complete large-d fixed-M Figure 2 workflow."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from plot_figure2_fixed_m import (
    DEFAULT_MARKER_C,
    DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    DEFAULT_MARKER_D,
    DEFAULT_MARKER_DELTA,
    heuristic_a,
    heuristic_z_for_m,
)
from test_fig2_fixed_m_sim import build_simulator, repo_root


VALID_STAGES = {"search", "prepare", "grid", "plot"}


def parse_int_list(value: str) -> list[int]:
    values = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not values or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("expected positive comma-separated integers")
    return values


def parse_float_list(value: str) -> list[float]:
    values = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("expected comma-separated numbers")
    return values


def parse_stages(value: str) -> set[str]:
    stages = {part.strip() for part in value.split(",") if part.strip()}
    unknown = stages - VALID_STAGES
    if not stages or unknown:
        raise argparse.ArgumentTypeError(f"stages must come from {sorted(VALID_STAGES)}; unknown={sorted(unknown)}")
    return stages


def nice_integer(value: float) -> int:
    if value <= 1.0:
        return 1
    exponent = math.floor(math.log10(value))
    scale = 10**exponent
    normalized = value / scale
    choices = [1.0, 2.0, 5.0, 10.0]
    chosen = min(choices, key=lambda item: (abs(item - normalized), item))
    return max(1, int(round(chosen * scale)))


def run_command(command: list[str], *, root: Path, commands: list[list[str]]) -> None:
    commands.append(command)
    print(f"$ {shlex.join(command)}", flush=True)
    subprocess.run(command, cwd=root, check=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_candidates(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def derive_candidate_file(
    source_path: Path,
    output_path: Path,
    *,
    d_value: int,
    k_value: int,
    l_value: int,
    threshold_m: int,
    offsets: list[int],
    marker_a: float,
    marker_d: float,
    marker_delta: float,
) -> list[dict[str, Any]]:
    source_rows = read_candidates(source_path)
    if not source_rows:
        raise ValueError(f"candidate source is empty: {source_path}")
    fields = list(source_rows[0])
    rows: list[dict[str, Any]] = []
    for offset in offsets:
        m_value = threshold_m + offset
        row = {field: "" for field in fields}
        row.update(
            {
                "candidate_id": f"d{d_value}_k{k_value}_l{l_value}_M{m_value}",
                "d": d_value,
                "k": k_value,
                "l": l_value,
                "M": m_value,
                "field_C_over_d": m_value * l_value / float(d_value),
                "merged_candidate_count": 1,
                "merged_M_values": str(m_value),
                "source_count": 1,
                "source_ok_count": 1,
                "source_unresolved_count": 0,
                "source_a_values": f"{marker_a:.12g}",
                "source_z_values": str(
                    max(
                        0,
                        int(
                            math.floor(
                                heuristic_z_for_m(
                                    m_value,
                                    marker_a,
                                    d_constant=marker_d,
                                    delta=marker_delta,
                                )
                                + 0.5
                            )
                        ),
                    )
                ),
                "source_search_ids": f"d{d_value}_threshold_M{threshold_m}_plus{offset}",
            }
        )
        rows.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def centered_float_values(center: float, *, step: float, radius: int) -> list[float]:
    values = [center + offset * step for offset in range(-radius, radius + 1)]
    if any(not (0.0 <= value < 1.0) for value in values):
        raise ValueError(
            f"centered a grid leaves [0,1): center={center}, step={step}, radius={radius}"
        )
    return [float(f"{value:.12g}") for value in values]


def build_centered_grid_specs(
    candidates: list[dict[str, Any]],
    *,
    marker_a: float,
    marker_d: float,
    marker_delta: float,
    a_step: float,
    a_radius: int,
    z_step: int,
    z_step_fraction: float,
    z_radius: int,
) -> dict[str, Any]:
    a_values = centered_float_values(marker_a, step=a_step, radius=a_radius)
    specs: dict[str, Any] = {}
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        m_value = int(float(candidate["M"]))
        z_float = heuristic_z_for_m(
            m_value,
            marker_a,
            d_constant=marker_d,
            delta=marker_delta,
        )
        z_center = max(0, int(math.floor(z_float + 0.5)))
        current_z_step = z_step or nice_integer(max(1.0, z_center * z_step_fraction))
        if z_center - z_radius * current_z_step < 0:
            raise ValueError(
                f"centered z grid becomes negative for {candidate_id}: "
                f"center={z_center}, step={current_z_step}, radius={z_radius}"
            )
        z_values = [
            z_center + offset * current_z_step
            for offset in range(-z_radius, z_radius + 1)
        ]
        specs[candidate_id] = {
            "candidate_id": candidate_id,
            "M": m_value,
            "heuristic_a": marker_a,
            "heuristic_z": z_float,
            "a_center": marker_a,
            "z_center": z_center,
            "a_step": a_step,
            "z_step": current_z_step,
            "a_values": a_values,
            "z_values": z_values,
        }
    return {"policy": "formula_centered", "candidates": specs}


def nearest(values: list[float] | list[int], target: float) -> float | int:
    return min(values, key=lambda value: (abs(value - target), value))


def summarize_grid(
    summary_csv: Path,
    *,
    marker_a: float,
    marker_d: float,
    marker_delta: float,
    target: float,
) -> list[dict[str, Any]]:
    with summary_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "ok":
            grouped[int(float(row["M"]))].append(row)

    result: list[dict[str, Any]] = []
    for m_value, group in sorted(grouped.items()):
        z_float = heuristic_z_for_m(
            m_value,
            marker_a,
            d_constant=marker_d,
            delta=marker_delta,
        )
        a_values = sorted({float(row["circular_a"]) for row in group})
        z_values = sorted({int(float(row["z"])) for row in group})
        marked_a = float(nearest(a_values, marker_a))
        marked_z = int(nearest(z_values, z_float))
        marked = next(
            row
            for row in group
            if math.isclose(float(row["circular_a"]), marked_a, abs_tol=1e-10)
            and int(float(row["z"])) == marked_z
        )
        best_success = max(float(row["peeling_success_rate"]) for row in group)
        result.append(
            {
                "M": m_value,
                "field_C_over_d": float(marked["field_C_over_d"]),
                "heuristic_a": marker_a,
                "heuristic_z": z_float,
                "marked_a": marked_a,
                "marked_z": marked_z,
                "marked_success_rate": float(marked["peeling_success_rate"]),
                "panel_best_success_rate": best_success,
                "target_cells": sum(float(row["peeling_success_rate"]) >= target for row in group),
            }
        )
    return result


def write_summary_md(path: Path, d_value: int, state: dict[str, Any]) -> None:
    grid_summary = state.get("grid_summary", [])
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"# Figure 2 Large-d Workflow: d={d_value}\n\n")
        handle.write(f"- Status: `{state.get('status', '')}`\n")
        handle.write(f"- Stable empirical threshold M: `{state.get('threshold_M', '')}`\n")
        handle.write(f"- M resolution: `{state.get('m_resolution', '')}`\n")
        handle.write(f"- Threshold pass streak: `{state.get('threshold_pass_streak', '')}`\n")
        handle.write(f"- Candidate offsets: `{state.get('candidate_offsets', [])}`\n")
        handle.write(f"- Candidate M values: `{state.get('candidate_M_values', [])}`\n")
        handle.write(f"- Grid spec: `{state.get('grid_spec_path', '')}`\n")
        handle.write(f"- a grid: `{state.get('a_values', [])}`\n")
        handle.write(f"- z grids by M: `{state.get('z_values_by_M', {})}`\n\n")
        if grid_summary:
            handle.write("| M | M*l/d | heuristic z | marked cell | marked success | panel best | target cells |\n")
            handle.write("| ---: | ---: | ---: | --- | ---: | ---: | ---: |\n")
            for row in grid_summary:
                handle.write(
                    f"| {row['M']} | {row['field_C_over_d']:.6g} | {row['heuristic_z']:.4f} | "
                    f"({row['marked_a']:.6g},{row['marked_z']}) | {row['marked_success_rate']:.3f} | "
                    f"{row['panel_best_success_rate']:.3f} | {row['target_cells']} |\n"
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reliable large-d Figure 2 M selection, grids, and plots.")
    parser.add_argument("--d-values", type=parse_int_list, default=parse_int_list("1000000,10000000"))
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--l", type=int, default=6)
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--target-success-rate", type=float, default=0.9)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--m-lower-factor", type=float, default=0.1)
    parser.add_argument("--m-upper-factor", type=float, default=0.4)
    parser.add_argument("--m-max-factor", type=float, default=2.0)
    parser.add_argument("--m-resolution-fraction", type=float, default=0.0001)
    parser.add_argument("--pass-streak", type=int, default=2)
    parser.add_argument("--offset-fractions", type=parse_float_list, default=parse_float_list("0.005,0.01,0.02"))
    parser.add_argument("--a-step", type=float, default=0.1)
    parser.add_argument("--a-radius", type=int, default=3)
    parser.add_argument("--z-step", type=int, default=0, help="Fixed centered z step; 0 selects it from z center.")
    parser.add_argument("--z-step-fraction", type=float, default=0.125)
    parser.add_argument("--z-radius", type=int, default=4)
    parser.add_argument("--marker-c", type=float, default=DEFAULT_MARKER_C)
    parser.add_argument(
        "--marker-c-orient-over-c-peel",
        type=float,
        default=DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    )
    parser.add_argument("--marker-d", type=float, default=DEFAULT_MARKER_D)
    parser.add_argument("--marker-delta", type=float, default=DEFAULT_MARKER_DELTA)
    parser.add_argument("--stages", type=parse_stages, default=parse_stages("search,prepare,grid,plot"))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--search-source-template",
        default=None,
        help="Optional existing search directory template, for example tests/results/paper_fig2_d{d}_m_search.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("tests") / "results" / "paper_fig2_large_d",
    )
    parser.add_argument(
        "--figure-root",
        type=Path,
        default=Path("tests") / "results" / "paper_figures" / "figure2_large_d",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if min(args.k, args.l, args.trials, args.jobs, args.pass_streak) <= 0:
        raise SystemExit("k, l, trials, jobs, and pass streak must be positive")
    if not (0.0 < args.target_success_rate <= 1.0):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if not (0.0 < args.m_lower_factor < args.m_upper_factor <= args.m_max_factor):
        raise SystemExit("require 0 < lower factor < upper factor <= max factor")
    if args.m_resolution_fraction <= 0.0:
        raise SystemExit("--m-resolution-fraction must be positive")
    if any(value <= 0.0 for value in args.offset_fractions):
        raise SystemExit("--offset-fractions must be positive")
    if args.a_step <= 0.0 or args.a_radius < 0:
        raise SystemExit("a step must be positive and a radius non-negative")
    if args.z_step < 0 or args.z_step_fraction <= 0.0 or args.z_radius < 0:
        raise SystemExit("z step/radius must be non-negative and z step fraction positive")


def main() -> None:
    args = parse_args()
    validate_args(args)
    root = repo_root()
    if not args.output_root.is_absolute():
        args.output_root = root / args.output_root
    if not args.figure_root.is_absolute():
        args.figure_root = root / args.figure_root
    args.output_root.mkdir(parents=True, exist_ok=True)
    args.figure_root.mkdir(parents=True, exist_ok=True)
    if {"search", "grid"} & args.stages:
        build_simulator(root, root / "build", args.skip_build)

    marker_a = heuristic_a(
        c_constant=args.marker_c,
        c_orient_over_c_peel=args.marker_c_orient_over_c_peel,
    )
    master_rows: list[dict[str, Any]] = []
    python = sys.executable

    for d_value in args.d_values:
        print(f"\n=== d={d_value} ===", flush=True)
        d_root = args.output_root / f"d{d_value}"
        if args.search_source_template:
            search_dir = Path(args.search_source_template.format(d=d_value))
            if not search_dir.is_absolute():
                search_dir = root / search_dir
        else:
            search_dir = d_root / "m_search"
        grid_dir = d_root / "fixed_m_sim"
        figure_dir = args.figure_root / f"d{d_value}"
        d_root.mkdir(parents=True, exist_ok=True)
        commands: list[list[str]] = []
        state_path = d_root / "workflow_summary.json"
        state: dict[str, Any] = read_json(state_path) if args.resume and state_path.exists() else {}
        workflow_config = {
            "d": d_value,
            "k": args.k,
            "l": args.l,
            "trials": args.trials,
            "target_success_rate": args.target_success_rate,
            "base_seed": args.base_seed,
            "m_lower_factor": args.m_lower_factor,
            "m_upper_factor": args.m_upper_factor,
            "m_max_factor": args.m_max_factor,
            "m_resolution_fraction": args.m_resolution_fraction,
            "pass_streak": args.pass_streak,
            "offset_fractions": args.offset_fractions,
            "a_step": args.a_step,
            "a_radius": args.a_radius,
            "z_step": args.z_step,
            "z_step_fraction": args.z_step_fraction,
            "z_radius": args.z_radius,
            "search_source_template": args.search_source_template,
            "marker_c": args.marker_c,
            "marker_c_orient_over_c_peel": args.marker_c_orient_over_c_peel,
            "marker_d": args.marker_d,
            "marker_delta": args.marker_delta,
        }
        previous_config = state.get("workflow_config")
        if args.resume and previous_config is not None and previous_config != workflow_config:
            raise SystemExit(
                f"resume configuration mismatch for d={d_value}; use the original arguments "
                "or select a new --output-root"
            )
        state.update(
            {
                "d": d_value,
                "k": args.k,
                "l": args.l,
                "trials": args.trials,
                "target_success_rate": args.target_success_rate,
                "jobs": args.jobs,
                "base_seed": args.base_seed,
                "marker_c": args.marker_c,
                "marker_c_orient_over_c_peel": args.marker_c_orient_over_c_peel,
                "marker_a": marker_a,
                "marker_d": args.marker_d,
                "marker_delta": args.marker_delta,
                "workflow_config": workflow_config,
                "status": "running",
            }
        )

        resolution = nice_integer(d_value * args.m_resolution_fraction)
        offsets = sorted({nice_integer(d_value * fraction) for fraction in args.offset_fractions})
        lower_m = max(1, int(round(d_value * args.m_lower_factor)))
        upper_m = max(lower_m + 1, int(round(d_value * args.m_upper_factor)))
        max_m = max(upper_m, int(round(d_value * args.m_max_factor)))
        state.update({"m_resolution": resolution, "candidate_offsets": offsets})
        write_json(state_path, state)

        if "search" in args.stages:
            command = [
                python,
                str(root / "tests" / "select_fig2_d100000_m.py"),
                "--d",
                str(d_value),
                "--k",
                str(args.k),
                "--l",
                str(args.l),
                "--trials",
                str(args.trials),
                "--target-success-rate",
                str(args.target_success_rate),
                "--lower-m",
                str(lower_m),
                "--upper-m",
                str(upper_m),
                "--max-m",
                str(max_m),
                "--m-resolution",
                str(resolution),
                "--pass-streak",
                str(args.pass_streak),
                "--candidate-offsets",
                ",".join(str(value) for value in offsets),
                "--base-seed",
                str(args.base_seed),
                "--jobs",
                str(args.jobs),
                "--marker-c",
                str(args.marker_c),
                "--marker-c-orient-over-c-peel",
                str(args.marker_c_orient_over_c_peel),
                "--marker-d",
                str(args.marker_d),
                "--marker-delta",
                str(args.marker_delta),
                "--skip-build",
                "--output-dir",
                str(search_dir),
            ]
            if args.resume:
                command.append("--resume")
            run_command(command, root=root, commands=commands)

        threshold_summary_path = search_dir / "threshold_summary.json"
        source_candidates_path = search_dir / "m_candidates.csv"
        if not threshold_summary_path.exists() or not source_candidates_path.exists():
            raise SystemExit(f"missing search outputs for d={d_value}; include the search stage first")
        threshold_summary = read_json(threshold_summary_path)
        if args.search_source_template and "search" not in args.stages:
            candidates_path = d_root / "m_candidates.csv"
            candidates = derive_candidate_file(
                source_candidates_path,
                candidates_path,
                d_value=d_value,
                k_value=args.k,
                l_value=args.l,
                threshold_m=int(threshold_summary["threshold_M"]),
                offsets=offsets,
                marker_a=marker_a,
                marker_d=args.marker_d,
                marker_delta=args.marker_delta,
            )
        else:
            candidates_path = source_candidates_path
            candidates = read_candidates(candidates_path)
        candidate_m_values = [int(float(row["M"])) for row in candidates]
        state.update(
            {
                "binary_threshold_M": threshold_summary.get("binary_threshold_M"),
                "threshold_M": threshold_summary["threshold_M"],
                "m_resolution": threshold_summary.get("m_resolution", 1),
                "threshold_pass_streak": threshold_summary.get("pass_streak", 1),
                "candidate_M_values": candidate_m_values,
            }
        )

        grid_spec = build_centered_grid_specs(
            candidates,
            marker_a=marker_a,
            marker_d=args.marker_d,
            marker_delta=args.marker_delta,
            a_step=args.a_step,
            a_radius=args.a_radius,
            z_step=args.z_step,
            z_step_fraction=args.z_step_fraction,
            z_radius=args.z_radius,
        )
        grid_spec_path = d_root / "grid_spec.json"
        write_json(grid_spec_path, grid_spec)
        candidate_specs = grid_spec["candidates"]
        first_spec = next(iter(candidate_specs.values()))
        state.update(
            {
                "grid_spec_path": str(grid_spec_path),
                "a_values": first_spec["a_values"],
                "z_values_by_M": {
                    str(spec["M"]): spec["z_values"] for spec in candidate_specs.values()
                },
            }
        )
        write_json(state_path, state)

        if "grid" in args.stages:
            command = [
                python,
                str(root / "tests" / "test_fig2_fixed_m_sim.py"),
                "--m-candidates",
                str(candidates_path),
                "--grid-spec",
                str(grid_spec_path),
                "--trials",
                str(args.trials),
                "--ci-confidence",
                "0.95",
                "--jobs",
                str(args.jobs),
                "--base-seed",
                str(args.base_seed),
                "--shared-trial-seeds",
                "--skip-build",
                "--output-dir",
                str(grid_dir),
            ]
            if args.resume:
                command.append("--resume")
            run_command(command, root=root, commands=commands)
            run_command(
                [
                    python,
                    str(root / "tests" / "json_verifier.py"),
                    str(grid_dir / "summary.jsonl"),
                    "--strict",
                ],
                root=root,
                commands=commands,
            )

        summary_csv = grid_dir / "summary.csv"
        if ("plot" in args.stages or "grid" in args.stages) and not summary_csv.exists():
            raise SystemExit(f"missing fixed-M summary for d={d_value}; include the grid stage first")
        if summary_csv.exists():
            state["grid_summary"] = summarize_grid(
                summary_csv,
                marker_a=marker_a,
                marker_d=args.marker_d,
                marker_delta=args.marker_delta,
                target=args.target_success_rate,
            )

        if "plot" in args.stages:
            run_command(
                [
                    python,
                    str(root / "tests" / "plot_figure2_fixed_m.py"),
                    "--input",
                    str(summary_csv),
                    "--output-dir",
                    str(figure_dir),
                    "--only",
                    "all",
                    "--target-success-rate",
                    str(args.target_success_rate),
                    "--marker-c",
                    str(args.marker_c),
                    "--marker-c-orient-over-c-peel",
                    str(args.marker_c_orient_over_c_peel),
                    "--marker-d",
                    str(args.marker_d),
                    "--marker-delta",
                    str(args.marker_delta),
                ],
                root=root,
                commands=commands,
            )

        state.update(
            {
                "status": "complete",
                "commands": commands,
                "search_dir": str(search_dir),
                "grid_dir": str(grid_dir),
                "figure_dir": str(figure_dir),
            }
        )
        write_json(state_path, state)
        write_summary_md(d_root / "workflow_summary.md", d_value, state)
        master_rows.append(state)

    write_json(args.output_root / "workflow_summary.json", master_rows)
    print(f"wrote {args.output_root / 'workflow_summary.json'}", flush=True)


if __name__ == "__main__":
    main()
