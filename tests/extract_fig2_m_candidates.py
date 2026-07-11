#!/usr/bin/env python3
"""Extract fixed-M candidates from the old Figure 2(a) threshold grid."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
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


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def as_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fmt_float(value: float) -> str:
    return f"{value:.12g}"


def joined(values: list[Any]) -> str:
    return ",".join(str(value) for value in values)


def split_csv_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    return [part for part in str(value).split(",") if part != ""]


def merge_candidate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: int(row["M"]))
    chosen = ordered[len(ordered) // 2]
    d_value = int(chosen["d"])
    k_value = int(chosen["k"])
    l_value = int(chosen["l"])
    m_value = int(chosen["M"])

    a_values = sorted({value for row in rows for value in split_csv_values(row.get("source_a_values"))}, key=float)
    z_values = sorted({int(value) for row in rows for value in split_csv_values(row.get("source_z_values"))})
    search_ids = sorted({value for row in rows for value in split_csv_values(row.get("source_search_ids"))})
    m_values = sorted({int(row["M"]) for row in rows})
    r_values = [
        float(value)
        for row in rows
        for key in ("min_source_R_w30", "max_source_R_w30")
        if (value := row.get(key)) not in (None, "")
    ]
    success_values = [
        float(value)
        for row in rows
        for key in ("min_source_success_rate", "max_source_success_rate")
        if (value := row.get(key)) not in (None, "")
    ]
    return {
        "candidate_id": f"d{d_value}_k{k_value}_l{l_value}_M{m_value}",
        "d": d_value,
        "k": k_value,
        "l": l_value,
        "M": m_value,
        "field_C_over_d": m_value * l_value / float(d_value),
        "merged_candidate_count": len(rows),
        "merged_M_values": joined(m_values),
        "source_count": sum(int(row.get("source_count") or 0) for row in rows),
        "source_ok_count": sum(int(row.get("source_ok_count") or 0) for row in rows),
        "source_unresolved_count": sum(int(row.get("source_unresolved_count") or 0) for row in rows),
        "source_a_values": joined(a_values),
        "source_z_values": joined(z_values),
        "source_search_ids": joined(search_ids),
        "min_source_R_w30": min(r_values) if r_values else "",
        "max_source_R_w30": max(r_values) if r_values else "",
        "min_source_success_rate": min(success_values) if success_values else "",
        "max_source_success_rate": max(success_values) if success_values else "",
    }


def build_candidates(rows: list[dict[str, Any]], *, include_unresolved_with_m: bool) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        d_value = as_int(row, "d")
        k_value = as_int(row, "k")
        l_value = as_int(row, "l")
        m_value = as_int(row, "best_M") or as_int(row, "M")
        if d_value is None or k_value is None or l_value is None or m_value is None:
            continue
        status = str(row.get("status", ""))
        if status != "ok" and not include_unresolved_with_m:
            continue
        grouped[(d_value, k_value, l_value, m_value)].append(row)

    candidates: list[dict[str, Any]] = []
    for d_value, k_value, l_value, m_value in sorted(grouped):
        source_rows = grouped[(d_value, k_value, l_value, m_value)]
        a_values = sorted({fmt_float(value) for row in source_rows if (value := as_float(row, "circular_a")) is not None})
        z_values = sorted({int(value) for row in source_rows if (value := as_int(row, "z")) is not None})
        search_ids = sorted(str(row.get("search_id", "")) for row in source_rows if row.get("search_id") not in (None, ""))
        r_values = [value for row in source_rows if (value := as_float(row, "best_R_w30")) is not None]
        success_values = [value for row in source_rows if (value := as_float(row, "final_success_rate")) is not None]
        statuses = [str(row.get("status", "")) for row in source_rows]
        candidates.append(
            {
                "candidate_id": f"d{d_value}_k{k_value}_l{l_value}_M{m_value}",
                "d": d_value,
                "k": k_value,
                "l": l_value,
                "M": m_value,
                "field_C_over_d": m_value * l_value / float(d_value),
                "merged_candidate_count": 1,
                "merged_M_values": str(m_value),
                "source_count": len(source_rows),
                "source_ok_count": statuses.count("ok"),
                "source_unresolved_count": statuses.count("unresolved"),
                "source_a_values": joined(a_values),
                "source_z_values": joined(z_values),
                "source_search_ids": joined(search_ids),
                "min_source_R_w30": min(r_values) if r_values else "",
                "max_source_R_w30": max(r_values) if r_values else "",
                "min_source_success_rate": min(success_values) if success_values else "",
                "max_source_success_rate": max(success_values) if success_values else "",
            }
        )
    return candidates


def thin_close_candidates(candidates: list[dict[str, Any]], bin_width: float) -> list[dict[str, Any]]:
    if bin_width <= 0:
        return candidates
    grouped: dict[tuple[int, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        d_value = int(row["d"])
        k_value = int(row["k"])
        l_value = int(row["l"])
        c_value = float(row["field_C_over_d"])
        bin_index = math.floor((c_value + 1e-12) / bin_width)
        grouped[(d_value, k_value, l_value, bin_index)].append(row)
    return [merge_candidate_rows(rows) for _, rows in sorted(grouped.items())]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_md(path: Path, rows: list[dict[str, Any]], input_path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2 Fixed-M Candidates\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- Candidates: {len(rows)}\n\n")
        handle.write("| d | k | l | M | M*l/d | merged M | sources | ok | unresolved | source a | source z |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |\n")
        for row in rows:
            handle.write(
                f"| {row['d']} | {row['k']} | {row['l']} | {row['M']} | "
                f"{float(row['field_C_over_d']):.6g} | {row.get('merged_M_values', row['M'])} | {row['source_count']} | "
                f"{row['source_ok_count']} | {row['source_unresolved_count']} | "
                f"{row['source_a_values']} | {row['source_z_values']} |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract fixed-M candidates from old Figure 2(a) results.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig2_az_grid" / "summary.jsonl")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_fig2_m_candidates")
    parser.add_argument(
        "--c-over-d-bin-width",
        type=float,
        default=0.1,
        help="Merge close M candidates by M*l/d bins and keep the median M in each bin. Use 0 to disable.",
    )
    parser.add_argument(
        "--include-unresolved-with-m",
        action="store_true",
        help="Keep unresolved source rows when they still contain a best_M value.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.c_over_d_bin_width < 0:
        raise SystemExit("--c-over-d-bin-width must be non-negative")
    rows = read_rows(args.input)
    full_candidates = build_candidates(rows, include_unresolved_with_m=args.include_unresolved_with_m)
    candidates = thin_close_candidates(full_candidates, args.c_over_d_bin_width)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "m_candidates.jsonl", candidates)
    write_csv(args.output_dir / "m_candidates.csv", candidates)
    write_md(args.output_dir / "m_candidates.md", candidates, args.input)
    with (args.output_dir / "run_config.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "args": {
                    "input": str(args.input),
                    "output_dir": str(args.output_dir),
                    "include_unresolved_with_m": args.include_unresolved_with_m,
                    "c_over_d_bin_width": args.c_over_d_bin_width,
                },
                "input_rows": len(rows),
                "full_candidate_rows": len(full_candidates),
                "candidate_rows": len(candidates),
            },
            handle,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")
    print(f"wrote {args.output_dir / 'm_candidates.jsonl'}")
    print(f"wrote {args.output_dir / 'm_candidates.csv'}")
    print(f"wrote {args.output_dir / 'm_candidates.md'}")


if __name__ == "__main__":
    main()
