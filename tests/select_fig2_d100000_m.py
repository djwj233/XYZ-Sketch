#!/usr/bin/env python3
"""Select fixed-M candidates for a large-d Figure 2 peeling grid."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
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


PROBE_FIELDS = [
    "d",
    "k",
    "l",
    "M",
    "circular_a",
    "z",
    "heuristic_z",
    "trials",
    "successes",
    "success_rate",
    "target_success_rate",
    "target_met",
    "seed",
    "dedup_hashes",
    "status",
]

CANDIDATE_FIELDS = [
    "candidate_id",
    "d",
    "k",
    "l",
    "M",
    "field_C_over_d",
    "merged_candidate_count",
    "merged_M_values",
    "source_count",
    "source_ok_count",
    "source_unresolved_count",
    "source_a_values",
    "source_z_values",
    "source_search_ids",
    "min_source_R_w30",
    "max_source_R_w30",
    "min_source_success_rate",
    "max_source_success_rate",
]


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean: {value}")


def parse_offsets(value: str) -> list[int]:
    offsets = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not offsets or any(offset <= 0 for offset in offsets):
        raise argparse.ArgumentTypeError("candidate offsets must be positive integers")
    return offsets


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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def probe_matches(row: dict[str, Any], args: argparse.Namespace, a_value: float, m_value: int, z_value: int) -> bool:
    return (
        int(row.get("d", -1)) == args.d
        and int(row.get("k", -1)) == args.k
        and int(row.get("l", -1)) == args.l
        and int(row.get("M", -1)) == m_value
        and math.isclose(float(row.get("circular_a", -1.0)), a_value, abs_tol=1e-10)
        and int(row.get("z", -1)) == z_value
        and int(row.get("trials", -1)) == args.trials
        and int(row.get("seed", -1)) == args.base_seed
        and bool(row.get("dedup_hashes", False)) == args.dedup_hashes
        and math.isclose(float(row.get("target_success_rate", -1.0)), args.target_success_rate, abs_tol=1e-12)
        and str(row.get("status", "")) == "ok"
    )


def simulator_command(
    binary: Path,
    args: argparse.Namespace,
    *,
    m_value: int,
    a_value: float,
    z_value: int,
    trials: int,
    seed: int,
) -> list[str]:
    return [
        str(binary),
        "--d",
        str(args.d),
        "--k",
        str(args.k),
        "--l",
        str(args.l),
        "--M",
        str(m_value),
        "--a",
        f"{a_value:.12g}",
        "--z",
        str(z_value),
        "--trials",
        str(trials),
        "--seed",
        str(seed),
        "--dedup-hashes",
        str(args.dedup_hashes).lower(),
        "--format",
        "jsonl",
    ]


def make_probe_runner(
    binary: Path,
    args: argparse.Namespace,
    probes_path: Path,
    a_value: float,
) -> tuple[Any, list[dict[str, Any]]]:
    probes = read_jsonl(probes_path) if args.resume else []

    def probe(m_value: int) -> dict[str, Any]:
        z_float = heuristic_z_for_m(
            m_value,
            a_value,
            d_constant=args.marker_d,
            delta=args.marker_delta,
        )
        z_value = max(0, int(math.floor(z_float + 0.5)))
        for row in reversed(probes):
            if probe_matches(row, args, a_value, m_value, z_value):
                print(
                    f"[cached] M={m_value} a={a_value:.6g} z={z_value} "
                    f"success={float(row['success_rate']):.3f}",
                    flush=True,
                )
                return row

        worker_count = min(args.jobs, args.trials)
        chunk_base = args.trials // worker_count
        chunk_remainder = args.trials % worker_count
        chunks: list[tuple[int, int]] = []
        trial_offset = 0
        for worker_index in range(worker_count):
            chunk_trials = chunk_base + (1 if worker_index < chunk_remainder else 0)
            chunks.append((chunk_trials, args.base_seed + trial_offset))
            trial_offset += chunk_trials

        def run_chunk(chunk: tuple[int, int]) -> dict[str, Any]:
            chunk_trials, chunk_seed = chunk
            command = simulator_command(
                binary,
                args,
                m_value=m_value,
                a_value=a_value,
                z_value=z_value,
                trials=chunk_trials,
                seed=chunk_seed,
            )
            completed = subprocess.run(command, check=False, capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"simulator failed for M={m_value}: returncode={completed.returncode}\n{completed.stderr}"
                )
            output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
            if len(output_lines) != 1:
                raise RuntimeError(f"expected one simulator row for M={m_value}, got {len(output_lines)}")
            return json.loads(output_lines[0])

        if worker_count == 1:
            chunk_rows = [run_chunk(chunks[0])]
        else:
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                chunk_rows = list(executor.map(run_chunk, chunks))
        row = dict(chunk_rows[0])
        row["trials"] = sum(int(chunk_row["trials"]) for chunk_row in chunk_rows)
        row["successes"] = sum(int(chunk_row["successes"]) for chunk_row in chunk_rows)
        row["success_rate"] = row["successes"] / row["trials"]
        row["peeling_success_rate"] = row["success_rate"]
        row["seed"] = args.base_seed
        row.update(
            {
                "heuristic_z": z_float,
                "target_success_rate": args.target_success_rate,
                "target_met": float(row["success_rate"]) >= args.target_success_rate,
            }
        )
        probes.append(row)
        write_jsonl(probes_path, probes)
        write_csv(probes_path.with_suffix(".csv"), probes, PROBE_FIELDS)
        print(
            f"[probe] M={m_value} a={a_value:.6g} z={z_value} "
            f"success={int(row['successes'])}/{args.trials}={float(row['success_rate']):.3f}",
            flush=True,
        )
        return row

    return probe, probes


def align_down(value: int, resolution: int) -> int:
    return max(resolution, (value // resolution) * resolution)


def align_up(value: int, resolution: int) -> int:
    return max(resolution, ((value + resolution - 1) // resolution) * resolution)


def find_threshold(args: argparse.Namespace, probe: Any) -> tuple[int, int, int]:
    resolution = args.m_resolution
    low = align_down(args.lower_m, resolution)
    high = align_up(args.upper_m, resolution)
    low_row = probe(low)

    while bool(low_row["target_met"]) and low > resolution:
        high = low
        low = align_down(max(resolution, low // 2), resolution)
        low_row = probe(low)
    if bool(low_row["target_met"]):
        return low, low, high

    high_row = probe(high)
    while not bool(high_row["target_met"]):
        low = high
        high = align_up(high * 2, resolution)
        if high > args.max_m:
            raise RuntimeError(f"no passing M found up to --max-m={args.max_m}")
        high_row = probe(high)

    initial_low = low
    initial_high = high
    while high - low > resolution:
        middle = ((low // resolution + high // resolution) // 2) * resolution
        if middle <= low:
            middle = low + resolution
        middle_row = probe(middle)
        if bool(middle_row["target_met"]):
            high = middle
        else:
            low = middle
    return high, initial_low, initial_high


def stabilize_threshold(args: argparse.Namespace, probe: Any, binary_threshold: int) -> int:
    resolution = args.m_resolution

    def passing_window(start_m: int) -> bool:
        for index in range(args.pass_streak):
            m_value = start_m + index * resolution
            if m_value > args.max_m or not bool(probe(m_value)["target_met"]):
                return False
        return True

    candidate = align_up(binary_threshold, resolution)
    for _ in range(args.max_stabilization_steps + 1):
        if passing_window(candidate):
            backward_steps = 0
            while candidate > resolution and backward_steps < args.max_stabilization_steps:
                previous = candidate - resolution
                if not passing_window(previous):
                    break
                candidate = previous
                backward_steps += 1
            return candidate
        candidate += resolution
    raise RuntimeError(
        f"no run of {args.pass_streak} passing M values found within "
        f"{args.max_stabilization_steps} steps after M={binary_threshold}"
    )


def build_candidates(args: argparse.Namespace, threshold_m: int, a_value: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in args.candidate_offsets:
        m_value = threshold_m + offset
        rows.append(
            {
                "candidate_id": f"d{args.d}_k{args.k}_l{args.l}_M{m_value}",
                "d": args.d,
                "k": args.k,
                "l": args.l,
                "M": m_value,
                "field_C_over_d": m_value * args.l / float(args.d),
                "merged_candidate_count": 1,
                "merged_M_values": str(m_value),
                "source_count": 1,
                "source_ok_count": 1,
                "source_unresolved_count": 0,
                "source_a_values": f"{a_value:.12g}",
                "source_z_values": str(
                    max(
                        0,
                        int(
                            math.floor(
                                heuristic_z_for_m(
                                    m_value,
                                    a_value,
                                    d_constant=args.marker_d,
                                    delta=args.marker_delta,
                                )
                                + 0.5
                            )
                        ),
                    )
                ),
                "source_search_ids": f"d{args.d}_heuristic_threshold_M{threshold_m}_plus{offset}",
                "min_source_R_w30": "",
                "max_source_R_w30": "",
                "min_source_success_rate": "",
                "max_source_success_rate": "",
            }
        )
    return rows


def write_candidate_md(path: Path, rows: list[dict[str, Any]], threshold_m: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2 d=100000 M Candidates\n\n")
        handle.write(f"- Empirical threshold M: `{threshold_m}`\n")
        handle.write("- Candidate policy: `threshold M + offset`\n\n")
        handle.write("| d | k | l | M | M*l/d | source a | source z |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
        for row in rows:
            handle.write(
                f"| {row['d']} | {row['k']} | {row['l']} | {row['M']} | "
                f"{float(row['field_C_over_d']):.6g} | {row['source_a_values']} | "
                f"{row['source_z_values']} |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find large-d Figure 2 M values at the fitted heuristic point.")
    parser.add_argument("--d", type=int, default=100000)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--l", type=int, default=6)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.9)
    parser.add_argument("--lower-m", type=int, default=10000)
    parser.add_argument("--upper-m", type=int, default=40000)
    parser.add_argument("--max-m", type=int, default=1000000)
    parser.add_argument("--m-resolution", type=int, default=1)
    parser.add_argument("--pass-streak", type=int, default=1)
    parser.add_argument("--max-stabilization-steps", type=int, default=20)
    parser.add_argument("--candidate-offsets", type=parse_offsets, default=parse_offsets("100,200,300"))
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--jobs", type=int, default=1, help="Parallel trial chunks per threshold probe.")
    parser.add_argument("--dedup-hashes", type=parse_bool, default=False)
    parser.add_argument("--marker-c", type=float, default=DEFAULT_MARKER_C)
    parser.add_argument(
        "--marker-c-orient-over-c-peel",
        type=float,
        default=DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    )
    parser.add_argument("--marker-d", type=float, default=DEFAULT_MARKER_D)
    parser.add_argument("--marker-delta", type=float, default=DEFAULT_MARKER_DELTA)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests") / "results" / "paper_fig2_d100000_m_search",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if min(args.d, args.k, args.l, args.trials, args.lower_m, args.m_resolution, args.pass_streak) <= 0:
        raise SystemExit("d, k, l, trials, and lower M must be positive")
    if args.upper_m <= args.lower_m:
        raise SystemExit("--upper-m must be greater than --lower-m")
    if args.max_m < args.upper_m:
        raise SystemExit("--max-m must be at least --upper-m")
    if args.jobs <= 0:
        raise SystemExit("--jobs must be positive")
    if args.max_stabilization_steps < 0:
        raise SystemExit("--max-stabilization-steps must be non-negative")
    if not (0.0 < args.target_success_rate <= 1.0):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.marker_c < 0.0 or args.marker_c_orient_over_c_peel <= 0.0 or args.marker_d < 0.0:
        raise SystemExit("marker C, ratio, and D must be non-negative with a positive ratio")
    if not (0.0 < args.marker_delta < 1.0):
        raise SystemExit("--marker-delta must be in (0, 1)")


def main() -> None:
    args = parse_args()
    validate_args(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    root = repo_root()
    binary = build_simulator(root, root / "build", args.skip_build)
    a_value = heuristic_a(
        c_constant=args.marker_c,
        c_orient_over_c_peel=args.marker_c_orient_over_c_peel,
    )
    probes_path = args.output_dir / "threshold_probes.jsonl"
    probe, probes = make_probe_runner(binary, args, probes_path, a_value)
    binary_threshold_m, bracket_low, bracket_high = find_threshold(args, probe)
    threshold_m = stabilize_threshold(args, probe, binary_threshold_m)
    candidates = build_candidates(args, threshold_m, a_value)

    write_jsonl(args.output_dir / "m_candidates.jsonl", candidates)
    write_csv(args.output_dir / "m_candidates.csv", candidates, CANDIDATE_FIELDS)
    write_candidate_md(args.output_dir / "m_candidates.md", candidates, threshold_m)
    with (args.output_dir / "threshold_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "d": args.d,
                "k": args.k,
                "l": args.l,
                "trials": args.trials,
                "target_success_rate": args.target_success_rate,
                "required_successes": math.ceil(args.target_success_rate * args.trials - 1e-12),
                "base_seed": args.base_seed,
                "jobs": args.jobs,
                "dedup_hashes": args.dedup_hashes,
                "marker_c": args.marker_c,
                "marker_c_orient_over_c_peel": args.marker_c_orient_over_c_peel,
                "marker_a": a_value,
                "marker_d": args.marker_d,
                "marker_delta": args.marker_delta,
                "binary_bracket": [bracket_low, bracket_high],
                "binary_threshold_M": binary_threshold_m,
                "threshold_M": threshold_m,
                "m_resolution": args.m_resolution,
                "pass_streak": args.pass_streak,
                "max_stabilization_steps": args.max_stabilization_steps,
                "candidate_offsets": args.candidate_offsets,
                "candidate_M_values": [int(row["M"]) for row in candidates],
                "probe_count": len(probes),
                "caveat": "20-trial empirical binary search assumes an approximately monotone success predicate.",
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")

    print(f"threshold M={threshold_m}")
    print(f"candidate M values={','.join(str(row['M']) for row in candidates)}")
    print(f"wrote {args.output_dir / 'threshold_summary.json'}")
    print(f"wrote {args.output_dir / 'm_candidates.csv'}")


if __name__ == "__main__":
    main()
