#!/usr/bin/env python3
"""Dependency-free SVG plots for paper Figure 2."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PALETTE = [
    "#f7fbff",
    "#deebf7",
    "#c6dbef",
    "#9ecae1",
    "#6baed6",
    "#3182bd",
    "#08519c",
]


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, Any], key: str) -> float | None:
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


def as_int(row: dict[str, Any], key: str) -> int | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def svg_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, value)):02x}" for value in rgb)


def mix(left: str, right: str, t: float) -> str:
    lr, lg, lb = hex_to_rgb(left)
    rr, rg, rb = hex_to_rgb(right)
    return rgb_to_hex(
        (
            round(lr + (rr - lr) * t),
            round(lg + (rg - lg) * t),
            round(lb + (rb - lb) * t),
        )
    )


def color_for(value: float, vmin: float, vmax: float) -> str:
    if vmax <= vmin:
        return PALETTE[len(PALETTE) // 2]
    t = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
    scaled = t * (len(PALETTE) - 1)
    index = min(len(PALETTE) - 2, int(math.floor(scaled)))
    return mix(PALETTE[index], PALETTE[index + 1], scaled - index)


def fmt_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.3g}"


def scale(value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float, *, log_scale: bool = False) -> float:
    if log_scale:
        value = math.log10(max(value, 1e-12))
        in_lo = math.log10(max(in_lo, 1e-12))
        in_hi = math.log10(max(in_hi, 1e-12))
    if abs(in_hi - in_lo) < 1e-15:
        return (out_lo + out_hi) / 2
    return out_lo + (value - in_lo) * (out_hi - out_lo) / (in_hi - in_lo)


def z_theory_for(best_m: int, circular_a: float, *, delta: float = math.exp(-27.0), z_constant: float = 1.0) -> int:
    denominator = math.log(1.0 / delta)
    value = z_constant * ((1.0 - circular_a) ** (2.0 / 3.0)) * ((best_m / denominator) ** (1.0 / 3.0))
    return max(0, round(value))


def collect_grid(
    rows: list[dict[str, Any]],
    *,
    metric: str,
    d_filter: set[int] | None,
) -> tuple[dict[int, dict[tuple[float, int], dict[str, Any]]], list[float], list[int], list[float]]:
    by_d: dict[int, dict[tuple[float, int], dict[str, Any]]] = defaultdict(dict)
    a_values: set[float] = set()
    z_values: set[int] = set()
    metric_values: list[float] = []
    for row in rows:
        d_value = as_int(row, "d")
        a_value = as_float(row, "circular_a")
        z_value = as_int(row, "z")
        metric_value = as_float(row, metric)
        if d_value is None or a_value is None or z_value is None:
            continue
        if d_filter is not None and d_value not in d_filter:
            continue
        by_d[d_value][(a_value, z_value)] = row
        a_values.add(a_value)
        z_values.add(z_value)
        if row.get("status") == "ok" and metric_value is not None:
            metric_values.append(metric_value)
    return by_d, sorted(a_values), sorted(z_values), metric_values


def best_rows_by_d(rows: list[dict[str, Any]], *, metric: str, d_filter: set[int] | None) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        d_value = as_int(row, "d")
        metric_value = as_float(row, metric)
        best_m = as_int(row, "best_M")
        if d_value is None or metric_value is None or best_m is None:
            continue
        if d_filter is not None and d_value not in d_filter:
            continue
        grouped[d_value].append(row)

    selected: list[dict[str, Any]] = []
    for d_value in sorted(grouped):
        best = min(
            grouped[d_value],
            key=lambda row: (
                float(as_float(row, metric) or float("inf")),
                int(as_int(row, "z") or 0),
                float(as_float(row, "circular_a") or 0.0),
            ),
        )
        a_value = as_float(best, "circular_a") or 0.0
        best_m = as_int(best, "best_M") or 0
        selected.append(
            {
                **best,
                "a_star": a_value,
                "z_star": as_int(best, "z") or 0,
                "z_theory": z_theory_for(best_m, a_value),
                "R_w30_at_star": as_float(best, metric) or 0.0,
                "best_M_at_star": best_m,
            }
        )
    return selected


def write_heatmap_svg(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    metric: str,
    d_filter: set[int] | None,
    title: str,
) -> dict[str, Any]:
    by_d, a_values, z_values, metric_values = collect_grid(rows, metric=metric, d_filter=d_filter)
    if not by_d:
        raise SystemExit("no rows available for the requested d-values")
    if not metric_values:
        raise SystemExit(f"no ok rows with metric {metric!r}")

    d_values = sorted(by_d)
    vmin = min(metric_values)
    vmax = max(metric_values)
    cell_w = 50
    cell_h = 27
    left = 92
    top = 104
    panel_gap = 62
    panel_w = cell_w * len(a_values)
    panel_h = cell_h * len(z_values)
    right = 190
    bottom = 64
    width = left + panel_w + right
    height = top + len(d_values) * panel_h + (len(d_values) - 1) * panel_gap + bottom

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<pattern id="missing-hatch" width="8" height="8" patternUnits="userSpaceOnUse">',
        '<rect width="8" height="8" fill="#f2f2f2"/>',
        '<path d="M-2 8 L8 -2 M0 10 L10 0" stroke="#c9c9c9" stroke-width="1"/>',
        "</pattern>",
        "</defs>",
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="34" font-family="Arial" font-size="21" font-weight="700">{svg_escape(title)}</text>',
        f'<text x="{left}" y="58" font-family="Arial" font-size="13" fill="#555">color = {svg_escape(metric)} for status=ok; hatched cells did not validate at target success rate</text>',
    ]

    for panel_index, d_value in enumerate(d_values):
        x0 = left
        y0 = top + panel_index * (panel_h + panel_gap)
        lines.append(f'<text x="{x0}" y="{y0 - 18}" font-family="Arial" font-size="16" font-weight="700">d = {d_value:g}</text>')
        for col, a_value in enumerate(a_values):
            x = x0 + col * cell_w + cell_w / 2
            lines.append(f'<text x="{x:.2f}" y="{y0 - 5}" text-anchor="middle" font-family="Arial" font-size="11">{a_value:g}</text>')
        for row_index, z_value in enumerate(reversed(z_values)):
            y = y0 + row_index * cell_h + cell_h / 2 + 4
            lines.append(f'<text x="{x0 - 10}" y="{y:.2f}" text-anchor="end" font-family="Arial" font-size="11">{z_value:g}</text>')
            for col, a_value in enumerate(a_values):
                x = x0 + col * cell_w
                y_cell = y0 + row_index * cell_h
                row_data = by_d[d_value].get((a_value, z_value))
                fill = "url(#missing-hatch)"
                label = ""
                stroke = "#ffffff"
                title_text = f"d={d_value}, a={a_value:g}, z={z_value:g}: missing"
                if row_data is not None:
                    metric_value = as_float(row_data, metric)
                    status = str(row_data.get("status", ""))
                    success = as_float(row_data, "final_success_rate")
                    if status == "ok" and metric_value is not None:
                        fill = color_for(metric_value, vmin, vmax)
                        label = fmt_number(metric_value)
                    else:
                        stroke = "#b54b4b"
                        label = "" if success is None else f"{success:.2f}"
                    title_text = (
                        f"d={d_value}, a={a_value:g}, z={z_value:g}, status={status}, "
                        f"{metric}={metric_value}, success={success}"
                    )
                lines.append(f'<g><title>{svg_escape(title_text)}</title>')
                lines.append(
                    f'<rect x="{x:.2f}" y="{y_cell:.2f}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
                )
                if label:
                    lines.append(
                        f'<text x="{x + cell_w / 2:.2f}" y="{y_cell + cell_h / 2 + 4:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#111">{svg_escape(label)}</text>'
                    )
                if row_data is not None and row_data.get("status") != "ok":
                    lines.append(
                        f'<path d="M{x + 4:.2f} {y_cell + 4:.2f} L{x + cell_w - 4:.2f} {y_cell + cell_h - 4:.2f} M{x + cell_w - 4:.2f} {y_cell + 4:.2f} L{x + 4:.2f} {y_cell + cell_h - 4:.2f}" stroke="#9f3434" stroke-width="1.3"/>'
                    )
                lines.append("</g>")
        lines.append(
            f'<text x="{x0 + panel_w / 2:.2f}" y="{y0 + panel_h + 34}" text-anchor="middle" font-family="Arial" font-size="13">circular a</text>'
        )
        lines.append(
            f'<text transform="translate({x0 - 58} {y0 + panel_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="13">z</text>'
        )

    bar_x = left + panel_w + 54
    bar_y = top
    bar_w = 22
    bar_h = min(260, height - top - bottom)
    for i in range(bar_h):
        t = 1.0 - i / max(1, bar_h - 1)
        value = vmin + (vmax - vmin) * t
        lines.append(f'<rect x="{bar_x}" y="{bar_y + i}" width="{bar_w}" height="1" fill="{color_for(value, vmin, vmax)}"/>')
    lines.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="none" stroke="#333"/>')
    for tick in range(6):
        t = tick / 5
        value = vmax - (vmax - vmin) * t
        y = bar_y + bar_h * t
        lines.append(f'<line x1="{bar_x + bar_w}" y1="{y:.2f}" x2="{bar_x + bar_w + 5}" y2="{y:.2f}" stroke="#333"/>')
        lines.append(f'<text x="{bar_x + bar_w + 9}" y="{y + 4:.2f}" font-family="Arial" font-size="11">{fmt_number(value)}</text>')
    lines.append(f'<text x="{bar_x}" y="{bar_y - 12}" font-family="Arial" font-size="12" font-weight="700">{svg_escape(metric)}</text>')
    lines.append(f'<rect x="{bar_x}" y="{bar_y + bar_h + 24}" width="{bar_w}" height="18" fill="url(#missing-hatch)" stroke="#999"/>')
    lines.append(f'<text x="{bar_x + bar_w + 9}" y="{bar_y + bar_h + 38}" font-family="Arial" font-size="11">not ok / missing</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    statuses = Counter(row.get("status", "") for row in rows if d_filter is None or as_int(row, "d") in d_filter)
    return {
        "d_values": d_values,
        "a_values": a_values,
        "z_values": z_values,
        "metric_min": vmin,
        "metric_max": vmax,
        "statuses": statuses,
    }


def write_source_summary(path: Path, input_path: Path, stats: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2 Plot Source Summary\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- d values: {', '.join(str(value) for value in stats['d_values'])}\n")
        handle.write(f"- a values: {', '.join(f'{value:g}' for value in stats['a_values'])}\n")
        handle.write(f"- z values: {', '.join(str(value) for value in stats['z_values'])}\n")
        handle.write(f"- Metric range: {stats['metric_min']:.6g} to {stats['metric_max']:.6g}\n")
        handle.write("- Status counts:\n")
        for status, count in sorted(stats["statuses"].items()):
            handle.write(f"  - {status}: {count}\n")
        handle.write("- Output format: dependency-free SVG\n")


def write_z_star_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "d",
        "k",
        "l",
        "a_star",
        "z_star",
        "z_theory",
        "delta_z",
        "R_w30_at_star",
        "best_M_at_star",
        "status",
        "final_success_rate",
        "final_ci_low",
        "final_ci_high",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            z_star = int(row["z_star"])
            z_theory = int(row["z_theory"])
            writer.writerow(
                {
                    "d": row.get("d", ""),
                    "k": row.get("k", ""),
                    "l": row.get("l", ""),
                    "a_star": row.get("a_star", ""),
                    "z_star": z_star,
                    "z_theory": z_theory,
                    "delta_z": z_star - z_theory,
                    "R_w30_at_star": row.get("R_w30_at_star", ""),
                    "best_M_at_star": row.get("best_M_at_star", ""),
                    "status": row.get("status", ""),
                    "final_success_rate": row.get("final_success_rate", ""),
                    "final_ci_low": row.get("final_ci_low", ""),
                    "final_ci_high": row.get("final_ci_high", ""),
                }
            )


def write_z_star_svg(path: Path, rows: list[dict[str, Any]], *, title: str) -> dict[str, Any]:
    if not rows:
        raise SystemExit("no rows available for Figure 2(b)")

    width = 860
    height = 520
    left = 76
    right = 220
    top = 58
    bottom = 76
    plot_w = width - left - right
    plot_h = height - top - bottom
    d_values = [float(row["d"]) for row in rows]
    z_values = [float(row["z_star"]) for row in rows] + [float(row["z_theory"]) for row in rows]
    x_lo = min(d_values)
    x_hi = max(d_values)
    y_lo = max(0.0, min(z_values) - 0.8)
    y_hi = max(z_values) + 0.8

    def x_pos(value: float) -> float:
        return scale(value, x_lo, x_hi, left, left + plot_w, log_scale=True)

    def y_pos(value: float) -> float:
        return scale(value, y_lo, y_hi, top + plot_h, top)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="32" font-family="Arial" font-size="21" font-weight="700">{svg_escape(title)}</text>',
        f'<text x="{left}" y="52" font-family="Arial" font-size="13" fill="#555">all Figure 2(a) cells are treated as eligible when selecting z_star</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
    ]

    for row in rows:
        x = x_pos(float(row["d"]))
        lines.append(f'<line x1="{x:.2f}" y1="{top + plot_h}" x2="{x:.2f}" y2="{top + plot_h + 5}" stroke="#222"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_h + 23}" text-anchor="middle" font-family="Arial" font-size="12">{row["d"]}</text>')
    y_tick_count = max(2, math.ceil(y_hi - y_lo) + 1)
    for tick in range(y_tick_count):
        value = math.floor(y_lo) + tick
        if value < y_lo - 1e-9 or value > y_hi + 1e-9:
            continue
        y = y_pos(value)
        lines.append(f'<line x1="{left - 5}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#222"/>')
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#eeeeee"/>')
        lines.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12">{value:g}</text>')

    z_star_points = [(x_pos(float(row["d"])), y_pos(float(row["z_star"]))) for row in rows]
    z_theory_points = [(x_pos(float(row["d"])), y_pos(float(row["z_theory"]))) for row in rows]
    star_path = " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(z_star_points))
    theory_path = " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(z_theory_points))
    lines.append(f'<path d="{star_path}" fill="none" stroke="#1f77b4" stroke-width="2.6"/>')
    lines.append(f'<path d="{theory_path}" fill="none" stroke="#d62728" stroke-width="2.4" stroke-dasharray="7 5"/>')
    for row, (x, y) in zip(rows, z_star_points):
        title_text = (
            f"d={row['d']}, a_star={float(row['a_star']):g}, z_star={row['z_star']}, "
            f"z_theory={row['z_theory']}, status={row.get('status', '')}, R={float(row['R_w30_at_star']):.6g}"
        )
        lines.append(f'<g><title>{svg_escape(title_text)}</title>')
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#1f77b4" stroke="#1f77b4" stroke-width="2"/>')
        lines.append("</g>")
    for x, y in z_theory_points:
        lines.append(f'<rect x="{x - 4:.2f}" y="{y - 4:.2f}" width="8" height="8" fill="#d62728"/>')

    lines.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 24}" text-anchor="middle" font-family="Arial" font-size="14">d</text>')
    lines.append(f'<text transform="translate(22 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="14">z</text>')
    legend_x = left + plot_w + 36
    legend_y = top + 18
    lines.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 26}" y2="{legend_y}" stroke="#1f77b4" stroke-width="2.6"/>')
    lines.append(f'<circle cx="{legend_x + 13}" cy="{legend_y}" r="5" fill="#1f77b4"/>')
    lines.append(f'<text x="{legend_x + 36}" y="{legend_y + 4}" font-family="Arial" font-size="13">empirical z_star</text>')
    lines.append(f'<line x1="{legend_x}" y1="{legend_y + 26}" x2="{legend_x + 26}" y2="{legend_y + 26}" stroke="#d62728" stroke-width="2.4" stroke-dasharray="7 5"/>')
    lines.append(f'<rect x="{legend_x + 9}" y="{legend_y + 22}" width="8" height="8" fill="#d62728"/>')
    lines.append(f'<text x="{legend_x + 36}" y="{legend_y + 30}" font-family="Arial" font-size="13">heuristic z_theory</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rows": rows, "d_values": [int(row["d"]) for row in rows]}


def parse_d_values(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Figure 2 from Figure 2(a) summary.csv.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig2_az_grid" / "summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_figures")
    parser.add_argument("--d-values", default=None, help="Optional comma-separated d values to plot. Defaults to all completed d values.")
    parser.add_argument("--metric", default="best_R_w30", help="Metric field used for heatmap colors.")
    parser.add_argument("--only", default="all", choices=["all", "2a", "2b"], help="Which Figure 2 panel(s) to write.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    d_filter = parse_d_values(args.d_values)
    suffix = "" if d_filter is None else "_" + "_".join(str(value) for value in sorted(d_filter))
    if args.only in {"all", "2a"}:
        output = args.output_dir / f"figure2a_az_heatmap{suffix}.svg"
        stats = write_heatmap_svg(
            output,
            rows,
            metric=args.metric,
            d_filter=d_filter,
            title="Figure 2(a): Circular a/z Heatmap",
        )
        summary = args.output_dir / f"figure2_source_summary{suffix}.md"
        write_source_summary(summary, args.input, stats)
        print(f"wrote {output}")
        print(f"wrote {summary}")
    if args.only in {"all", "2b"}:
        selected = best_rows_by_d(rows, metric=args.metric, d_filter=d_filter)
        output = args.output_dir / f"figure2b_z_star{suffix}.svg"
        source = args.output_dir / f"figure2b_z_star_source{suffix}.csv"
        write_z_star_svg(output, selected, title="Figure 2(b): z_star(d)")
        write_z_star_csv(source, selected)
        print(f"wrote {output}")
        print(f"wrote {source}")


if __name__ == "__main__":
    main()
