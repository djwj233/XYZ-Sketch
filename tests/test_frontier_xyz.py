#!/usr/bin/env python3
"""Paper Figure 1(b) frontier wrapper for XYZ-Sketch."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from test_spatial import SUMMARY_FIELDS


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_tuple_values(value: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            k_text, l_text = item.split(":", 1)
        elif "-" in item:
            k_text, l_text = item.split("-", 1)
        else:
            raise ValueError(f"tuple must be k:l or k-l, got {item!r}")
        result.append((int(k_text), int(l_text)))
    if not result:
        raise ValueError("--tuple-values must contain at least one tuple")
    return result


def ensure_output_dir(root: Path, output_dir: Path | None) -> dict[str, Path]:
    base = output_dir or root / "tests" / "results" / "paper_fig1_frontier"
    shards = base / "shards"
    base.mkdir(parents=True, exist_ok=True)
    shards.mkdir(parents=True, exist_ok=True)
    return {
        "base": base,
        "shards": shards,
        "probes": base / "probes.jsonl",
        "summary_jsonl": base / "summary.jsonl",
        "summary_csv": base / "summary.csv",
        "summary_md": base / "summary.md",
        "run_config": base / "run_config.json",
    }


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
        handle.write("# Figure 1(b) XYZ Communication Frontier\n\n")
        handle.write("| d | k | l | mode | M | R_w30 | success | CI low | status |\n")
        handle.write("| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | --- |\n")
        for row in sorted(rows, key=lambda item: (int(item["d"]), int(item["k"]), int(item["l"]), str(item["mode"]))):
            handle.write(
                f"| {row.get('d', '')} | {row.get('k', '')} | {row.get('l', '')} | {row.get('mode', '')} | "
                f"{row.get('best_M', '')} | {row.get('best_R_w30', '')} | "
                f"{row.get('final_success_rate', '')} | {row.get('final_ci_low', '')} | {row.get('status', '')} |\n"
            )


def rewrite_experiment(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["experiment"] = "paper_fig1_frontier"
    return rows


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Run the XYZ Figure 1(b) communication frontier experiment.")
    parser.add_argument("--d-values", default="100,300,1000,3000,10000,30000,100000,300000,1000000,3000000,10000000")
    parser.add_argument("--tuple-values", default="2:3,2:6,3:4", help="Comma-separated k:l tuples.")
    parser.add_argument("--modes", default="random,naive,circular")
    parser.add_argument("--probe-trials", type=int, default=30)
    parser.add_argument("--final-trials", type=int, default=100)
    parser.add_argument("--target-success-rate", type=float, default=0.90)
    parser.add_argument("--threshold-policy", default="point", choices=["point", "ci-low"])
    parser.add_argument("--max-C-over-d", type=float, default=8.0, dest="max_c_over_d")
    parser.add_argument("--ci-confidence", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    parser.add_argument("--ci-method", default="wilson", choices=["wilson"])
    parser.add_argument("--circular-a", type=float, default=None, help="Override circular a. If omitted, downstream scripts compute a from --a-constant.")
    parser.add_argument("--dedup-hashes", default="false")
    parser.add_argument("--shared-datasets", dest="shared_datasets", action="store_true", default=True)
    parser.add_argument("--no-shared-datasets", dest="shared_datasets", action="store_false")
    parser.add_argument("--base-seed", type=int, default=114514)
    parser.add_argument("--max-set-size", type=int, default=100000)
    parser.add_argument("--set-size-scale", type=int, default=10)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_known_args()


def main() -> None:
    args, passthrough = parse_args()
    if not (0 < args.target_success_rate <= 1):
        raise SystemExit("--target-success-rate must be in (0, 1]")
    if args.circular_a is not None and not (0.0 <= args.circular_a < 1.0):
        raise SystemExit("--circular-a must be in [0, 1)")

    root = repo_root()
    dirs = ensure_output_dir(root, args.output_dir)
    tuples = parse_tuple_values(args.tuple_values)
    test_spatial = root / "tests" / "test_spatial.py"

    commands: list[tuple[tuple[int, int], Path, list[str]]] = []
    for tuple_index, (k_value, l_value) in enumerate(tuples):
        shard_dir = dirs["shards"] / f"k{k_value}_l{l_value}"
        command = [
            sys.executable,
            str(test_spatial),
            "--d-values",
            args.d_values,
            "--k-values",
            str(k_value),
            "--l-values",
            str(l_value),
            "--modes",
            args.modes,
            "--probe-trials",
            str(args.probe_trials),
            "--final-trials",
            str(args.final_trials),
            "--target-success-rate",
            str(args.target_success_rate),
            "--threshold-policy",
            args.threshold_policy,
            "--max-C-over-d",
            str(args.max_c_over_d),
            "--ci-confidence",
            str(args.ci_confidence),
            "--ci-method",
            args.ci_method,
            "--dedup-hashes",
            args.dedup_hashes,
            "--base-seed",
            str(args.base_seed + tuple_index * 100_000),
            "--max-set-size",
            str(args.max_set_size),
            "--set-size-scale",
            str(args.set_size_scale),
            "--output-dir",
            str(shard_dir),
        ]
        if args.circular_a is not None:
            command.extend(["--circular-a", str(args.circular_a)])
        if args.shared_datasets:
            command.append("--shared-datasets")
        if args.skip_build or tuple_index > 0:
            command.append("--skip-build")
        if args.dry_run:
            command.append("--dry-run")
        command.extend(passthrough)
        commands.append(((k_value, l_value), shard_dir, command))

    if args.dry_run:
        for _, _, command in commands:
            print(" ".join(command))
        return

    for path in (dirs["probes"], dirs["summary_jsonl"], dirs["summary_csv"], dirs["summary_md"], dirs["run_config"]):
        if path.exists():
            path.unlink()

    for (k_value, l_value), _, command in commands:
        print(f"[Figure1 frontier] k={k_value} l={l_value}", flush=True)
        subprocess.run(command, cwd=root, check=True)

    probes: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for _, shard_dir, _ in commands:
        probes.extend(rewrite_experiment(read_jsonl(shard_dir / "probes.jsonl")))
        summaries.extend(rewrite_experiment(read_jsonl(shard_dir / "summary.jsonl")))

    write_jsonl(dirs["probes"], probes)
    write_jsonl(dirs["summary_jsonl"], summaries)
    write_summary_csv(dirs["summary_csv"], summaries)
    write_summary_md(dirs["summary_md"], summaries)
    with dirs["run_config"].open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
                "passthrough": passthrough,
                "tuples": [{"k": k_value, "l": l_value} for k_value, l_value in tuples],
                "shards": [str(shard_dir) for _, shard_dir, _ in commands],
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")

    print(f"wrote {dirs['probes']}")
    print(f"wrote {dirs['summary_jsonl']}")
    print(f"wrote {dirs['summary_csv']}")
    print(f"wrote {dirs['summary_md']}")
    print(f"wrote {dirs['run_config']}")


if __name__ == "__main__":
    main()
