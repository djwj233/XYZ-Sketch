#!/usr/bin/env python3
"""Extract z_star(d) from Figure 2(a) a/z grid summaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from json_schema import normalize_benchmark_row
from xyz_tuning import add_tuning_arguments, z_from_args


ARGS: argparse.Namespace

SUMMARY_FIELDS = [
    "d",
    "l",
    "k",
    "a_star",
    "z_star",
    "R_w30_at_star",
    "best_M_at_star",
    "z_theory",
    "z_theory_policy",
    "delta_z",
    "source_summary",
    "status",
    "candidate_count",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2(b) z_star Summary\n\n")
        handle.write("| d | k | l | a_star | z_star | z_theory | delta_z | R_w30 | M | status |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), int(item["k"]), int(item["l"]))):
            handle.write(
                f"| {row.get('d', '')} | {row.get('k', '')} | {row.get('l', '')} | "
                f"{row.get('a_star', '')} | {row.get('z_star', '')} | {row.get('z_theory', '')} | "
                f"{row.get('delta_z', '')} | {row.get('R_w30_at_star', '')} | "
                f"{row.get('best_M_at_star', '')} | {row.get('status', '')} |\n"
            )


def ensure_dirs(output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or Path("tests") / "results" / "paper_fig2_z_star"
    base.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "run_config": base / "run_config.json",
    }


def z_theory_for_row(row: dict[str, Any], args: argparse.Namespace) -> int:
    return z_from_args(int(row.get("k", 0)), int(row.get("l", 0)), int(row["best_M"]), float(row.get("circular_a", 0.0)), args)


def best_key(row: dict[str, Any], preferred_a: float, tolerance: float) -> tuple[float, float, int, float]:
    r_value = float(row.get("best_R_w30", float("inf")))
    # Quantize by tolerance so tiny float noise does not dominate the tie-breakers.
    r_bucket = round(r_value / tolerance) * tolerance if tolerance > 0 else r_value
    ci_low = float(row.get("final_ci_low", 0.0))
    z_value = int(row.get("z", 0))
    a_distance = abs(float(row.get("circular_a", 0.0)) - preferred_a)
    return (r_bucket, -ci_low, z_value, a_distance)


def aggregate_group(
    rows: list[dict[str, Any]],
    *,
    source_summary: Path,
    preferred_a: float,
    tolerance: float,
    z_theory_policy: str,
) -> dict[str, Any]:
    first = rows[0]
    ok_rows = [
        row
        for row in rows
        if row.get("status") == "ok"
        and row.get("best_R_w30") not in (None, "")
        and row.get("best_M") not in (None, "")
    ]
    if not ok_rows:
        row = {
            "d": first.get("d", 0),
            "l": first.get("l", 0),
            "k": first.get("k", 0),
            "a_star": "",
            "z_star": "",
            "R_w30_at_star": "",
            "best_M_at_star": "",
            "z_theory": "",
            "z_theory_policy": z_theory_policy,
            "delta_z": "",
            "source_summary": str(source_summary),
            "candidate_count": 0,
            "status": "unresolved",
            "trials": 0,
            "successes": 0,
            "success_rate": 0.0,
            "bits": 0.0,
        }
        return normalize_benchmark_row(
            row,
            experiment="paper_fig2_z_star",
            record_type="aggregate",
            algorithm="xyz_v2",
            variant="z_star",
            implementation="local/XYZ-v2",
            status="unresolved",
            dataset_mode=first.get("dataset_mode", "unknown"),
        )

    best = min(ok_rows, key=lambda row: best_key(row, preferred_a, tolerance))
    best_m = int(best["best_M"])
    z_theory = z_theory_for_row(best, ARGS)
    z_star = int(best["z"])
    row = {
        "d": best.get("d", 0),
        "l": best.get("l", 0),
        "k": best.get("k", 0),
        "a_star": float(best["circular_a"]),
        "z_star": z_star,
        "R_w30_at_star": float(best["best_R_w30"]),
        "best_M_at_star": best_m,
        "z_theory": z_theory,
        "z_theory_policy": z_theory_policy,
        "delta_z": z_star - z_theory,
        "source_summary": str(source_summary),
        "candidate_count": len(ok_rows),
        "status": "ok",
        "trials": best.get("trials", best.get("final_trials", 0)),
        "successes": best.get("successes", best.get("final_successes", 0)),
        "success_rate": best.get("success_rate", best.get("final_success_rate", 0.0)),
        "ci_low": best.get("ci_low", best.get("final_ci_low", 0.0)),
        "ci_high": best.get("ci_high", best.get("final_ci_high", 1.0)),
        "ci_method": best.get("ci_method", "wilson"),
        "ci_confidence": best.get("ci_confidence", 0.95),
        "bits": best.get("bits", 0.0),
        "ca": best.get("ca", 0),
        "cb": best.get("cb", 0),
        "seed": best.get("seed", 0),
        "dataset_mode": best.get("dataset_mode", "unknown"),
    }
    return normalize_benchmark_row(
        row,
        experiment="paper_fig2_z_star",
        record_type="aggregate",
        algorithm="xyz_v2",
        variant=f"a={float(best['circular_a']):.6g},z={z_star}",
        implementation="local/XYZ-v2",
        status="ok",
        dataset_mode=best.get("dataset_mode", "unknown"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Figure 2(b) z_star rows from an a/z grid summary.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig2_az_grid" / "summary.jsonl")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--preferred-a", type=float, default=0.0)
    parser.add_argument("--tie-tolerance", type=float, default=1e-9)
    parser.add_argument("--z-theory-policy", default="D(1-a)^(2/3)(M/log(1/delta))^(1/3)")
    add_tuning_arguments(parser)
    return parser.parse_args()


def main() -> None:
    global ARGS
    args = parse_args()
    ARGS = args
    if args.tie_tolerance < 0:
        raise SystemExit("--tie-tolerance must be non-negative")
    rows = read_jsonl(args.input)
    groups: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("record_type") != "threshold":
            continue
        key = (int(row.get("d", 0)), int(row.get("k", 0)), int(row.get("l", 0)))
        groups[key].append(row)

    summaries = [
        aggregate_group(
            group_rows,
            source_summary=args.input,
            preferred_a=args.preferred_a,
            tolerance=args.tie_tolerance,
            z_theory_policy=args.z_theory_policy,
        )
        for _, group_rows in sorted(groups.items())
    ]
    dirs = ensure_dirs(args.output_dir)
    for path in (dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"]):
        if path.exists():
            path.unlink()
    write_jsonl(dirs["summary_jsonl"], summaries)
    write_csv(dirs["summary_csv"], summaries)
    write_summary_md(dirs["summary_md"], summaries)
    with dirs["run_config"].open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "input": str(args.input),
                "preferred_a": args.preferred_a,
                "tie_tolerance": args.tie_tolerance,
                "z_theory_policy": args.z_theory_policy,
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")


if __name__ == "__main__":
    main()
