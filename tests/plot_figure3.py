#!/usr/bin/env python3
"""Dependency-free SVG plots for paper Figure 3."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


COLORS = [
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#17becf",
    "#8c564b",
]


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def numeric(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def label_for(row: dict[str, Any]) -> str:
    algorithm = str(row.get("algorithm", "unknown"))
    variant = str(row.get("variant", ""))
    if algorithm == "xyz_v2":
        return "XYZ"
    if algorithm == "iblt":
        return "IBLT"
    if algorithm == "minisketch":
        return "minisketch"
    return f"{algorithm} {variant}".strip()


def collect_series(rows: list[dict[str, Any]], y_field: str) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if row.get("status") != "ok":
            continue
        d_value = numeric(row, "d")
        y_value = numeric(row, y_field)
        if d_value is None or y_value is None or d_value <= 0:
            continue
        series[label_for(row)].append((d_value, y_value))
    return {key: sorted(points) for key, points in series.items() if points}


def nice_range(values: list[float], *, log_scale: bool = False) -> tuple[float, float]:
    if not values:
        return (0.0, 1.0)
    lo = min(values)
    hi = max(values)
    if log_scale:
        lo = max(lo, 1e-12)
        hi = max(hi, lo * 1.01)
        return (lo, hi)
    if abs(hi - lo) < 1e-15:
        pad = abs(hi) * 0.1 + 1e-12
        return (lo - pad, hi + pad)
    pad = (hi - lo) * 0.08
    return (lo - pad, hi + pad)


def scale(value: float, lo: float, hi: float, out_lo: float, out_hi: float, *, log_scale: bool = False) -> float:
    if log_scale:
        value = math.log10(max(value, 1e-12))
        lo = math.log10(max(lo, 1e-12))
        hi = math.log10(max(hi, 1e-12))
    if abs(hi - lo) < 1e-15:
        return (out_lo + out_hi) / 2.0
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_svg(path: Path, series: dict[str, list[tuple[float, float]]], title: str, y_label: str) -> None:
    width = 920
    height = 560
    left = 82
    right = 230
    top = 46
    bottom = 74
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_x = [point[0] for points in series.values() for point in points]
    all_y = [point[1] for points in series.values() for point in points]
    x_lo, x_hi = nice_range(all_x, log_scale=True)
    y_lo, y_hi = nice_range(all_y, log_scale=False)

    def x_pos(value: float) -> float:
        return scale(value, x_lo, x_hi, left, left + plot_w, log_scale=True)

    def y_pos(value: float) -> float:
        return scale(value, y_lo, y_hi, top + plot_h, top, log_scale=False)

    x_ticks = sorted(set(all_x))
    if len(x_ticks) > 7:
        step = max(1, math.ceil(len(x_ticks) / 7))
        x_ticks = x_ticks[::step]
    y_ticks = [y_lo + (y_hi - y_lo) * i / 5.0 for i in range(6)]

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="28" font-family="Arial" font-size="20" font-weight="700">{svg_escape(title)}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
    ]
    for tick in x_ticks:
        x = x_pos(tick)
        lines.append(f'<line x1="{x:.2f}" y1="{top + plot_h}" x2="{x:.2f}" y2="{top + plot_h + 5}" stroke="#222"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_h + 24}" text-anchor="middle" font-family="Arial" font-size="12">{tick:g}</text>')
    for tick in y_ticks:
        y = y_pos(tick)
        lines.append(f'<line x1="{left - 5}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#222"/>')
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#eee"/>')
        lines.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12">{tick:.3g}</text>')
    lines.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="14">d</text>')
    lines.append(
        f'<text transform="translate(22 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="14">{svg_escape(y_label)}</text>'
    )

    for index, (name, points) in enumerate(sorted(series.items())):
        color = COLORS[index % len(COLORS)]
        path_data = " ".join(f"{'M' if i == 0 else 'L'} {x_pos(x):.2f} {y_pos(y):.2f}" for i, (x, y) in enumerate(points))
        lines.append(f'<path d="{path_data}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        for x, y in points:
            lines.append(f'<circle cx="{x_pos(x):.2f}" cy="{y_pos(y):.2f}" r="4" fill="{color}"/>')
        legend_y = top + 24 * index
        legend_x = left + plot_w + 28
        lines.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 24}" y2="{legend_y}" stroke="{color}" stroke-width="2.4"/>')
        lines.append(f'<text x="{legend_x + 32}" y="{legend_y + 4}" font-family="Arial" font-size="13">{svg_escape(name)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_source_summary(path: Path, input_path: Path, rows: list[dict[str, Any]], skipped: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 3 Plot Source Summary\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- Rows read: {len(rows)}\n")
        handle.write(f"- Rows skipped because status != ok: {skipped}\n")
        handle.write("- Output format: dependency-free SVG\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Figure 3 from compare-frontier summary.csv.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig3_compare_frontier" / "summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_figures")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    plots = [
        ("best_R_w30", "figure3a_communication.svg", "Figure 3(a): Communication", "R_w30"),
        ("update_avg_s_per_element", "figure3b_update_cost.svg", "Figure 3(b): Update Cost", "update seconds per element"),
        ("decode_avg_s_per_difference", "figure3c_decode_cost.svg", "Figure 3(c): Decode Cost", "decode seconds per difference"),
    ]
    for field, filename, title, ylabel in plots:
        write_svg(args.output_dir / filename, collect_series(rows, field), title, ylabel)
        print(f"wrote {args.output_dir / filename}")
    skipped = sum(1 for row in rows if row.get("status") != "ok")
    write_source_summary(args.output_dir / "figure3_source_summary.md", args.input, rows, skipped)
    print(f"wrote {args.output_dir / 'figure3_source_summary.md'}")


if __name__ == "__main__":
    main()
