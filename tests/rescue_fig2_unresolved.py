#!/usr/bin/env python3
"""Rescue near-threshold Figure 2(a) cells by retrying unresolved rows at larger M."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from test_az_grid import (
    SUMMARY_FIELDS,
    build_benchmark,
    repo_root,
    run_probe,
    summary_from_final,
    works,
    write_jsonl,
    write_summary_csv,
    write_summary_md,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_int_list(value: str) -> list[int]:
    result = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not result:
        raise ValueError("expected at least one integer")
    return result


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def trial_index(path: Path) -> int:
    match = re.search(r"trial(\d+)\.sets$", path.name)
    return int(match.group(1)) if match else 0


def dataset_paths_for(row: dict[str, Any], trials: int) -> list[Path] | None:
    if row.get("dataset_mode") != "shared_file":
        return None
    dataset_dir = Path(str(row.get("dataset_dir", "")))
    if not dataset_dir.exists():
        raise FileNotFoundError(f"dataset_dir does not exist for {row.get('search_id')}: {dataset_dir}")
    paths = sorted(dataset_dir.glob("trial*.sets"), key=trial_index)
    if len(paths) < trials:
        raise FileNotFoundError(
            f"dataset_dir has {len(paths)} trials, needs {trials} for {row.get('search_id')}: {dataset_dir}"
        )
    return paths


def config_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "search_id": str(row["search_id"]),
        "d": int(row["d"]),
        "l": int(row["l"]),
        "k": int(row["k"]),
        "mode": "circular",
        "circular_a": float(row["circular_a"]),
        "z": int(row["z"]),
        "seed": int(row["seed"]),
        "ca": int(row["ca"]),
        "cb": int(row["cb"]),
        "dedup_hashes": parse_bool(row.get("dedup_hashes", False)),
    }


def args_for_row(row: dict[str, Any], cli_args: argparse.Namespace) -> SimpleNamespace:
    final_trials = cli_args.final_trials or int(row.get("final_trials") or row.get("trials") or 100)
    target_success_rate = cli_args.target_success_rate or float(row.get("target_success_rate") or 0.9)
    return SimpleNamespace(
        target_success_rate=target_success_rate,
        final_trials=final_trials,
        probe_trials=int(row.get("probe_trials") or 0),
        min_range_length=cli_args.min_range_length,
        ci_confidence=float(row.get("ci_confidence") or cli_args.ci_confidence),
        ci_method=str(row.get("ci_method") or cli_args.ci_method),
        threshold_policy=str(row.get("threshold_policy") or cli_args.threshold_policy),
        shared_datasets=(row.get("dataset_mode") == "shared_file"),
    )


def try_rescue_row(
    binary: Path,
    row: dict[str, Any],
    offsets: list[int],
    cli_args: argparse.Namespace,
    errors_path: Path,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if row.get("best_M") in (None, ""):
        return None, [], []

    config = config_from_row(row)
    local_args = args_for_row(row, cli_args)
    dataset_paths = dataset_paths_for(row, int(local_args.final_trials))
    original_m = int(row["best_M"])
    probes: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []

    for offset in offsets:
        candidate_m = original_m + offset
        print(f"  try {config['search_id']} M={candidate_m} (+{offset})", flush=True)
        probe = run_probe(
            binary,
            config,
            candidate_m,
            int(local_args.final_trials),
            f"rescue_plus_{offset}",
            local_args,
            errors_path,
            dataset_paths,
        )
        if probe is not None:
            probe["rescue_source_M"] = original_m
            probe["rescue_M_offset"] = offset
            probes.append(probe)
            attempts.append(
                {
                    "M": candidate_m,
                    "offset": offset,
                    "status": probe.get("status"),
                    "success_rate": probe.get("success_rate"),
                    "successes": probe.get("successes"),
                    "trials": probe.get("trials"),
                    "ci_low": probe.get("ci_low"),
                    "ci_high": probe.get("ci_high"),
                }
            )
        else:
            attempts.append({"M": candidate_m, "offset": offset, "status": "benchmark_error"})
        if works(probe, local_args):
            summary = summary_from_final(config, probe, candidate_m, local_args, "ok")
            summary["rescue_source_status"] = row.get("status")
            summary["rescue_source_M"] = original_m
            summary["rescue_M_offset"] = offset
            summary["rescue_source_final_success_rate"] = row.get("final_success_rate")
            summary["rescue_attempts"] = attempts
            return summary, probes, attempts
    return None, probes, attempts


def write_report(
    path: Path,
    *,
    input_path: Path,
    output_dir: Path,
    offsets: list[int],
    ok_count: int,
    unresolved_count: int,
    rescued_rows: list[dict[str, Any]],
    unrescued: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2(a) Unresolved Rescue Report\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- Output directory: `{output_dir}`\n")
        handle.write(f"- M offsets tried: {', '.join('+' + str(value) for value in offsets)}\n")
        handle.write(f"- Original ok rows kept: {ok_count}\n")
        handle.write(f"- Original unresolved rows tested: {unresolved_count}\n")
        handle.write(f"- Rescued rows: {len(rescued_rows)}\n")
        handle.write(f"- Still unresolved or skipped: {len(unrescued)}\n\n")
        handle.write("## Rescued Rows\n\n")
        handle.write("| search_id | source M | new M | offset | success | R_w30 |\n")
        handle.write("| --- | ---: | ---: | ---: | ---: | ---: |\n")
        for row in rescued_rows:
            handle.write(
                f"| {row.get('search_id', '')} | {row.get('rescue_source_M', '')} | "
                f"{row.get('best_M', '')} | {row.get('rescue_M_offset', '')} | "
                f"{row.get('final_success_rate', '')} | {row.get('best_R_w30', '')} |\n"
            )
        handle.write("\n## Unrescued Rows\n\n")
        handle.write("| search_id | source M | final success | last tried |\n")
        handle.write("| --- | ---: | ---: | --- |\n")
        for row in unrescued:
            attempts = row.get("attempts", [])
            last = attempts[-1] if attempts else {}
            handle.write(
                f"| {row.get('search_id', '')} | {row.get('best_M', '')} | "
                f"{row.get('final_success_rate', '')} | {last} |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry unresolved Figure 2(a) cells at M plus small offsets.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig2_az_grid" / "summary.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_fig2_az_grid_rescued")
    parser.add_argument("--offsets", default="2,4,6,8")
    parser.add_argument("--final-trials", type=int, default=None, help="Override final trials. Defaults to each source row's final_trials.")
    parser.add_argument("--target-success-rate", type=float, default=None, help="Override target. Defaults to each source row's target.")
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--min-range-length", type=int, default=2)
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Limit unresolved rows for smoke tests.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    offsets = parse_int_list(args.offsets)
    if any(offset <= 0 for offset in offsets):
        raise SystemExit("--offsets must be positive integers")

    rows = read_jsonl(args.input)
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    unresolved_rows = [row for row in rows if row.get("status") == "unresolved"]
    if args.limit is not None:
        unresolved_rows = unresolved_rows[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dirs = {
        "summary_jsonl": args.output_dir / "summary.jsonl",
        "summary_csv": args.output_dir / "summary.csv",
        "summary_md": args.output_dir / "summary.md",
        "probes": args.output_dir / "rescue_probes.jsonl",
        "report": args.output_dir / "rescue_report.md",
        "run_config": args.output_dir / "run_config.json",
        "errors": args.output_dir / "errors.log",
    }

    if args.dry_run:
        print(f"would keep ok rows: {len(ok_rows)}")
        print(f"would retry unresolved rows: {len(unresolved_rows)}")
        print(f"offsets: {offsets}")
        print(f"output: {args.output_dir}")
        return

    root = repo_root()
    build_dir = root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    binary = build_benchmark(root, build_dir, args.skip_build)
    if dirs["errors"].exists():
        dirs["errors"].unlink()

    rescued_rows: list[dict[str, Any]] = []
    rescue_probes: list[dict[str, Any]] = []
    unrescued: list[dict[str, Any]] = []

    for index, row in enumerate(unresolved_rows, start=1):
        print(f"[{index}/{len(unresolved_rows)}] {row.get('search_id')}", flush=True)
        rescued, probes, attempts = try_rescue_row(binary, row, offsets, args, dirs["errors"])
        rescue_probes.extend(probes)
        if rescued is None:
            failed = dict(row)
            failed["attempts"] = attempts
            unrescued.append(failed)
            print("  not rescued", flush=True)
        else:
            rescued_rows.append(rescued)
            print(
                f"  rescued M={rescued.get('best_M')} success={rescued.get('final_success_rate')} "
                f"R={rescued.get('best_R_w30')}",
                flush=True,
            )

    combined = sorted(
        ok_rows + rescued_rows,
        key=lambda item: (int(item["d"]), int(item["k"]), int(item["l"]), float(item["circular_a"]), int(item["z"])),
    )
    write_jsonl(dirs["summary_jsonl"], combined)
    write_summary_csv(dirs["summary_csv"], combined)
    write_summary_md(dirs["summary_md"], combined)
    write_jsonl(dirs["probes"], rescue_probes)
    write_report(
        dirs["report"],
        input_path=args.input,
        output_dir=args.output_dir,
        offsets=offsets,
        ok_count=len(ok_rows),
        unresolved_count=len(unresolved_rows),
        rescued_rows=rescued_rows,
        unrescued=unrescued,
    )
    with dirs["run_config"].open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                "input_rows": len(rows),
                "ok_rows_kept": len(ok_rows),
                "unresolved_rows_tested": len(unresolved_rows),
                "rescued_rows": len(rescued_rows),
                "unrescued_rows": len(unrescued),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    for key in ("summary_jsonl", "summary_csv", "summary_md", "probes", "report", "run_config"):
        print(f"wrote {dirs[key]}")


if __name__ == "__main__":
    main()
