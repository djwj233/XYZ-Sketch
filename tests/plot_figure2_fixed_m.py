#!/usr/bin/env python3
"""Dependency-free SVG heatmaps for the new fixed-M Figure 2(a) simulation."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SUCCESS_PALETTE = [
    "#b2182b",
    "#ef8a62",
    "#fddbc7",
    "#f7f7f7",
    "#d9f0d3",
    "#7fbf7b",
    "#1b7837",
]

DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL = 1.2081
DEFAULT_MARKER_C = (1.0 / 3.0) / DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL
DEFAULT_MARKER_D = 0.5
DEFAULT_MARKER_DELTA = 0.1


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
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
    except (TypeError, ValueError):
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


def color_for_success(value: float) -> str:
    t = max(0.0, min(1.0, value))
    scaled = t * (len(SUCCESS_PALETTE) - 1)
    index = min(len(SUCCESS_PALETTE) - 2, int(math.floor(scaled)))
    return mix(SUCCESS_PALETTE[index], SUCCESS_PALETTE[index + 1], scaled - index)


def heuristic_a(*, c_constant: float, c_orient_over_c_peel: float) -> float:
    value = c_constant * c_orient_over_c_peel
    if not (0.0 <= value < 1.0):
        raise ValueError(f"heuristic a must be in [0, 1): {value}")
    return value


def heuristic_z_for_m(m_value: int, a_value: float, *, d_constant: float, delta: float) -> float:
    if m_value <= 0:
        raise ValueError(f"M must be positive: {m_value}")
    if not (0.0 <= a_value < 1.0):
        raise ValueError(f"a_value must be in [0, 1): {a_value}")
    if not (0.0 < delta < 1.0):
        raise ValueError(f"delta must be in (0, 1): {delta}")
    return d_constant * ((1.0 - a_value) ** (2.0 / 3.0)) * (
        (m_value / math.log(1.0 / delta)) ** (1.0 / 3.0)
    )


def parse_int_set(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def collect_by_d(
    rows: list[dict[str, Any]],
    *,
    metric: str,
    d_filter: set[int] | None,
) -> tuple[dict[int, dict[int, dict[tuple[float, int], dict[str, Any]]]], list[float], list[int]]:
    by_d: dict[int, dict[int, dict[tuple[float, int], dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    a_values: set[float] = set()
    z_values: set[int] = set()
    for row in rows:
        d_value = as_int(row, "d")
        m_value = as_int(row, "M")
        a_value = as_float(row, "circular_a")
        z_value = as_int(row, "z")
        metric_value = as_float(row, metric)
        if d_value is None or m_value is None or a_value is None or z_value is None or metric_value is None:
            continue
        if d_filter is not None and d_value not in d_filter:
            continue
        by_d[d_value][m_value][(a_value, z_value)] = row
        a_values.add(a_value)
        z_values.add(z_value)
    return by_d, sorted(a_values), sorted(z_values)


def write_d_heatmap_svg(
    path: Path,
    *,
    d_value: int,
    panels: dict[int, dict[tuple[float, int], dict[str, Any]]],
    a_values: list[float],
    z_values: list[int],
    metric: str,
    marker_a_value: float,
    marker_d_constant: float,
    marker_delta: float,
) -> dict[str, Any]:
    if not panels:
        raise SystemExit(f"no panels for d={d_value}")
    cell_w = 48
    cell_h = 25
    left = 96
    top = 102
    panel_gap = 58
    right = 182
    bottom = 64
    m_values = sorted(panels)
    panel_axes = {
        m_value: (
            sorted({item[0] for item in panels[m_value]}),
            sorted({item[1] for item in panels[m_value]}),
        )
        for m_value in m_values
    }
    panel_w = cell_w * max(len(axes[0]) for axes in panel_axes.values())
    panel_h = cell_h * max(len(axes[1]) for axes in panel_axes.values())
    width = left + panel_w + right
    height = top + len(m_values) * panel_h + (len(m_values) - 1) * panel_gap + bottom

    metric_values = [
        as_float(row, metric)
        for panel in panels.values()
        for row in panel.values()
        if row.get("status") == "ok" and as_float(row, metric) is not None
    ]
    valid_metric_values = [value for value in metric_values if value is not None]
    best = max(valid_metric_values) if valid_metric_values else 0.0
    worst = min(valid_metric_values) if valid_metric_values else 0.0

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        '<pattern id="missing-hatch" width="8" height="8" patternUnits="userSpaceOnUse">',
        '<rect width="8" height="8" fill="#f2f2f2"/>',
        '<path d="M-2 8 L8 -2 M0 10 L10 0" stroke="#c9c9c9" stroke-width="1"/>',
        "</pattern>",
        "</defs>",
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="34" font-family="Arial" font-size="21" font-weight="700">Figure 2(a) fixed-M peeling heatmap, d = {d_value}</text>',
        f'<text x="{left}" y="58" font-family="Arial" font-size="13" fill="#555">color = {svg_escape(metric)}; yellow box = nearest tested cell to fitted heuristic</text>',
    ]

    for panel_index, m_value in enumerate(m_values):
        panel = panels[m_value]
        sample_row = next(iter(panel.values()))
        c_value = as_float(sample_row, "field_C_over_d") or 0.0
        marker_z = heuristic_z_for_m(
            m_value,
            marker_a_value,
            d_constant=marker_d_constant,
            delta=marker_delta,
        )
        panel_a_values, panel_z_values = panel_axes[m_value]
        nearest_a = min(panel_a_values, key=lambda value: (abs(value - marker_a_value), value))
        nearest_z = min(panel_z_values, key=lambda value: (abs(value - marker_z), value))
        marker_cell = (nearest_a, nearest_z)
        x0 = left
        y0 = top + panel_index * (panel_h + panel_gap)
        lines.append(
            f'<text x="{x0}" y="{y0 - 36}" font-family="Arial" font-size="15" font-weight="700">M = {m_value}, M*l/d = {c_value:.4g}</text>'
        )
        lines.append(
            f'<text x="{x0}" y="{y0 - 19}" font-family="Arial" font-size="11" fill="#555">fitted heuristic = ({marker_a_value:.4f},{marker_z:.2f}); marked cell = ({nearest_a:g},{nearest_z})</text>'
        )
        for col, a_value in enumerate(panel_a_values):
            x = x0 + col * cell_w + cell_w / 2
            lines.append(f'<text x="{x:.2f}" y="{y0 - 5}" text-anchor="middle" font-family="Arial" font-size="10">{a_value:g}</text>')
        for row_index, z_value in enumerate(reversed(panel_z_values)):
            y = y0 + row_index * cell_h + cell_h / 2 + 4
            lines.append(f'<text x="{x0 - 10}" y="{y:.2f}" text-anchor="end" font-family="Arial" font-size="10">{z_value:g}</text>')
            for col, a_value in enumerate(panel_a_values):
                x = x0 + col * cell_w
                y_cell = y0 + row_index * cell_h
                row_data = panel.get((a_value, z_value))
                fill = "url(#missing-hatch)"
                label = ""
                stroke = "#ffffff"
                title_text = f"d={d_value}, M={m_value}, a={a_value:g}, z={z_value}: missing"
                if row_data is not None:
                    status = str(row_data.get("status", ""))
                    metric_value = as_float(row_data, metric)
                    successes = as_int(row_data, "successes")
                    trials = as_int(row_data, "trials")
                    if status == "ok" and metric_value is not None:
                        fill = color_for_success(metric_value)
                        label = f"{metric_value:.2f}"
                    else:
                        stroke = "#a33a3a"
                    title_text = (
                        f"d={d_value}, M={m_value}, a={a_value:g}, z={z_value}, "
                        f"status={status}, {metric}={metric_value}, successes={successes}, trials={trials}"
                    )
                lines.append(f'<g><title>{svg_escape(title_text)}</title>')
                lines.append(
                    f'<rect x="{x:.2f}" y="{y_cell:.2f}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
                )
                if (a_value, z_value) == marker_cell:
                    lines.append(
                        f'<rect x="{x + 2:.2f}" y="{y_cell + 2:.2f}" width="{cell_w - 4}" height="{cell_h - 4}" fill="none" stroke="#ffd400" stroke-width="3"/>'
                    )
                if label:
                    lines.append(
                        f'<text x="{x + cell_w / 2:.2f}" y="{y_cell + cell_h / 2 + 4:.2f}" text-anchor="middle" font-family="Arial" font-size="10" fill="#111">{label}</text>'
                    )
                if row_data is not None and row_data.get("status") != "ok":
                    lines.append(
                        f'<path d="M{x + 4:.2f} {y_cell + 4:.2f} L{x + cell_w - 4:.2f} {y_cell + cell_h - 4:.2f} M{x + cell_w - 4:.2f} {y_cell + 4:.2f} L{x + 4:.2f} {y_cell + cell_h - 4:.2f}" stroke="#9f3434" stroke-width="1.3"/>'
                    )
                lines.append("</g>")
        lines.append(
            f'<text x="{x0 + panel_w / 2:.2f}" y="{y0 + panel_h + 30}" text-anchor="middle" font-family="Arial" font-size="12">circular a</text>'
        )
        lines.append(
            f'<text transform="translate({x0 - 56} {y0 + panel_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="12">z</text>'
        )

    bar_x = left + panel_w + 50
    bar_y = top
    bar_w = 22
    bar_h = min(280, height - top - bottom)
    for i in range(bar_h):
        t = 1.0 - i / max(1, bar_h - 1)
        lines.append(f'<rect x="{bar_x}" y="{bar_y + i}" width="{bar_w}" height="1" fill="{color_for_success(t)}"/>')
    lines.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="none" stroke="#333"/>')
    for tick in range(6):
        value = 1.0 - tick / 5
        y = bar_y + bar_h * tick / 5
        lines.append(f'<line x1="{bar_x + bar_w}" y1="{y:.2f}" x2="{bar_x + bar_w + 5}" y2="{y:.2f}" stroke="#333"/>')
        lines.append(f'<text x="{bar_x + bar_w + 9}" y="{y + 4:.2f}" font-family="Arial" font-size="11">{value:.1f}</text>')
    lines.append(f'<text x="{bar_x}" y="{bar_y - 12}" font-family="Arial" font-size="12" font-weight="700">{svg_escape(metric)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "d": d_value,
        "m_values": m_values,
        "panel_count": len(m_values),
        "cell_count": sum(len(panel) for panel in panels.values()),
        "metric_min": worst,
        "metric_max": best,
    }


def write_index(path: Path, input_path: Path, stats: list[dict[str, Any]], *, include_2b: bool = False) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 2(a) Fixed-M Heatmap Outputs\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write("- Metric: `peeling_success_rate`\n\n")
        if include_2b:
            handle.write("Figure 2(b) outputs:\n\n")
            handle.write("- `figure2b_fixed_m_z_star.svg`\n")
            handle.write("- `figure2b_fixed_m_z_star_source.csv`\n\n")
        handle.write("| d | panels | cells | M values | metric min | metric max | svg |\n")
        handle.write("| ---: | ---: | ---: | --- | ---: | ---: | --- |\n")
        for item in stats:
            d_value = int(item["d"])
            svg_name = f"figure2a_fixed_m_d{d_value}.svg"
            handle.write(
                f"| {d_value} | {item['panel_count']} | {item['cell_count']} | "
                f"{','.join(str(value) for value in item['m_values'])} | "
                f"{item['metric_min']:.6g} | {item['metric_max']:.6g} | `{svg_name}` |\n"
            )


def scale(value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> float:
    if abs(in_hi - in_lo) < 1e-15:
        return (out_lo + out_hi) / 2
    return out_lo + (value - in_lo) * (out_hi - out_lo) / (in_hi - in_lo)


def select_figure2b_rows(
    rows: list[dict[str, Any]],
    *,
    metric: str,
    d_filter: set[int] | None,
    target: float,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        d_value = as_int(row, "d")
        m_value = as_int(row, "M")
        metric_value = as_float(row, metric)
        if d_value is None or m_value is None or metric_value is None:
            continue
        if d_filter is not None and d_value not in d_filter:
            continue
        grouped[(d_value, m_value)].append(row)

    selected: list[dict[str, Any]] = []
    for (d_value, m_value), group in sorted(grouped.items()):
        best_success = max(group, key=lambda row: (as_float(row, metric) or -1.0, as_int(row, "z") or 0, as_float(row, "circular_a") or 0.0))
        eligible = [row for row in group if (as_float(row, metric) or 0.0) >= target and row.get("status") == "ok"]
        if eligible:
            chosen = max(
                eligible,
                key=lambda row: (
                    as_int(row, "z") or 0,
                    as_float(row, metric) or 0.0,
                    as_float(row, "circular_a") or 0.0,
                ),
            )
            selection_status = "target_met"
        else:
            chosen = best_success
            selection_status = "below_target"
        result = {
            **chosen,
            "d": d_value,
            "M": m_value,
            "C_over_d": as_float(chosen, "field_C_over_d") or (m_value * (as_int(chosen, "l") or 0) / float(d_value)),
            "z_star": as_int(chosen, "z") or 0,
            "a_star": as_float(chosen, "circular_a") or 0.0,
            "star_success": as_float(chosen, metric) or 0.0,
            "best_success": as_float(best_success, metric) or 0.0,
            "best_success_z": as_int(best_success, "z") or 0,
            "best_success_a": as_float(best_success, "circular_a") or 0.0,
            "selection_status": selection_status,
        }
        selected.append(result)
    return selected


def write_figure2b_source(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "d",
        "M",
        "C_over_d",
        "a_star",
        "z_star",
        "star_success",
        "selection_status",
        "best_success",
        "best_success_a",
        "best_success_z",
        "trials",
        "successes",
        "ci_low",
        "ci_high",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_figure2b_svg(path: Path, rows: list[dict[str, Any]], *, target: float) -> dict[str, Any]:
    if not rows:
        raise SystemExit("no rows available for Figure 2(b)")
    width = 920
    height = 560
    left = 78
    right = 210
    top = 62
    bottom = 74
    plot_w = width - left - right
    plot_h = height - top - bottom
    d_values = sorted({int(row["d"]) for row in rows})
    c_values = [float(row["C_over_d"]) for row in rows]
    z_values = [float(row["z_star"]) for row in rows]
    x_lo = min(c_values)
    x_hi = max(c_values)
    y_lo = max(0.0, min(z_values) - 0.8)
    y_hi = max(z_values) + 0.8
    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#8c564b", "#e377c2"]

    def x_pos(value: float) -> float:
        return scale(value, x_lo, x_hi, left, left + plot_w)

    def y_pos(value: float) -> float:
        return scale(value, y_lo, y_hi, top + plot_h, top)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="32" font-family="Arial" font-size="21" font-weight="700">Figure 2(b): max stable z under fixed M</text>',
        f'<text x="{left}" y="52" font-family="Arial" font-size="13" fill="#555">z_star = largest z with peeling_success_rate >= {target:g}; x = M*l/d</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
    ]

    for tick in range(6):
        value = x_lo + (x_hi - x_lo) * tick / 5
        x = x_pos(value)
        lines.append(f'<line x1="{x:.2f}" y1="{top + plot_h}" x2="{x:.2f}" y2="{top + plot_h + 5}" stroke="#222"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_h + 23}" text-anchor="middle" font-family="Arial" font-size="12">{value:.2f}</text>')
    y_start = math.floor(y_lo)
    y_end = math.ceil(y_hi)
    for value in range(y_start, y_end + 1):
        if value < y_lo - 1e-9 or value > y_hi + 1e-9:
            continue
        y = y_pos(value)
        lines.append(f'<line x1="{left - 5}" y1="{y:.2f}" x2="{left}" y2="{y:.2f}" stroke="#222"/>')
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#eeeeee"/>')
        lines.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="12">{value}</text>')

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["d"])].append(row)
    for color_index, d_value in enumerate(d_values):
        color = colors[color_index % len(colors)]
        series = sorted(grouped[d_value], key=lambda row: float(row["C_over_d"]))
        points = [(x_pos(float(row["C_over_d"])), y_pos(float(row["z_star"]))) for row in series]
        path_data = " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(points))
        lines.append(f'<path d="{path_data}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        for row, (x, y) in zip(series, points):
            below = row.get("selection_status") != "target_met"
            fill = "white" if below else color
            title_text = (
                f"d={d_value}, M={row['M']}, C={float(row['C_over_d']):.6g}, "
                f"a_star={float(row['a_star']):.6g}, z_star={row['z_star']}, "
                f"success={float(row['star_success']):.6g}, status={row['selection_status']}"
            )
            lines.append(f'<g><title>{svg_escape(title_text)}</title>')
            lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.6" fill="{fill}" stroke="{color}" stroke-width="2"/>')
            if below:
                lines.append(f'<path d="M{x - 3.5:.2f} {y - 3.5:.2f} L{x + 3.5:.2f} {y + 3.5:.2f} M{x + 3.5:.2f} {y - 3.5:.2f} L{x - 3.5:.2f} {y + 3.5:.2f}" stroke="{color}" stroke-width="1.2"/>')
            lines.append("</g>")

    lines.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 24}" text-anchor="middle" font-family="Arial" font-size="14">M*l/d</text>')
    lines.append(f'<text transform="translate(24 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="14">z_star</text>')
    legend_x = left + plot_w + 36
    legend_y = top + 18
    for color_index, d_value in enumerate(d_values):
        y = legend_y + color_index * 23
        color = colors[color_index % len(colors)]
        lines.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 25}" y2="{y}" stroke="{color}" stroke-width="2.4"/>')
        lines.append(f'<circle cx="{legend_x + 13}" cy="{y}" r="4.6" fill="{color}" stroke="{color}"/>')
        lines.append(f'<text x="{legend_x + 34}" y="{y + 4}" font-family="Arial" font-size="13">d = {d_value}</text>')
    y = legend_y + len(d_values) * 23 + 14
    lines.append(f'<circle cx="{legend_x + 13}" cy="{y}" r="4.6" fill="white" stroke="#333" stroke-width="2"/>')
    lines.append(f'<path d="M{legend_x + 9.5} {y - 3.5} L{legend_x + 16.5} {y + 3.5} M{legend_x + 16.5} {y - 3.5} L{legend_x + 9.5} {y + 3.5}" stroke="#333" stroke-width="1.2"/>')
    lines.append(f'<text x="{legend_x + 34}" y="{y + 4}" font-family="Arial" font-size="13">below target</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rows": len(rows), "d_values": d_values, "target": target}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot fixed-M Figure 2(a) peeling success heatmaps.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig2_fixed_m_sim" / "summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_figures" / "figure2a_fixed_m")
    parser.add_argument("--metric", default="peeling_success_rate")
    parser.add_argument("--d-values", default=None, help="Optional comma-separated d values.")
    parser.add_argument("--target-success-rate", type=float, default=0.9)
    parser.add_argument("--marker-c", type=float, default=DEFAULT_MARKER_C)
    parser.add_argument(
        "--marker-c-orient-over-c-peel",
        type=float,
        default=DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    )
    parser.add_argument("--marker-d", type=float, default=DEFAULT_MARKER_D)
    parser.add_argument("--marker-delta", type=float, default=DEFAULT_MARKER_DELTA)
    parser.add_argument("--only", default="all", choices=["all", "2a", "2b"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.marker_c < 0.0:
        raise SystemExit("--marker-c must be non-negative")
    if args.marker_c_orient_over_c_peel <= 0.0:
        raise SystemExit("--marker-c-orient-over-c-peel must be positive")
    if args.marker_d < 0.0:
        raise SystemExit("--marker-d must be non-negative")
    if not (0.0 < args.marker_delta < 1.0):
        raise SystemExit("--marker-delta must be in (0, 1)")
    marker_a_value = heuristic_a(
        c_constant=args.marker_c,
        c_orient_over_c_peel=args.marker_c_orient_over_c_peel,
    )
    rows = read_rows(args.input)
    d_filter = parse_int_set(args.d_values)
    by_d, a_values, z_values = collect_by_d(rows, metric=args.metric, d_filter=d_filter)
    if not by_d:
        raise SystemExit("no rows available for plotting")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.only in {"all", "2a"}:
        stats: list[dict[str, Any]] = []
        for d_value in sorted(by_d):
            output = args.output_dir / f"figure2a_fixed_m_d{d_value}.svg"
            stats.append(
                write_d_heatmap_svg(
                    output,
                    d_value=d_value,
                    panels=by_d[d_value],
                    a_values=a_values,
                    z_values=z_values,
                    metric=args.metric,
                    marker_a_value=marker_a_value,
                    marker_d_constant=args.marker_d,
                    marker_delta=args.marker_delta,
                )
            )
            print(f"wrote {output}")
        index = args.output_dir / "figure2a_fixed_m_index.md"
        write_index(index, args.input, stats, include_2b=args.only == "all")
        print(f"wrote {index}")
    if args.only in {"all", "2b"}:
        selected = select_figure2b_rows(rows, metric=args.metric, d_filter=d_filter, target=args.target_success_rate)
        output = args.output_dir / "figure2b_fixed_m_z_star.svg"
        source = args.output_dir / "figure2b_fixed_m_z_star_source.csv"
        write_figure2b_svg(output, selected, target=args.target_success_rate)
        write_figure2b_source(source, selected)
        print(f"wrote {output}")
        print(f"wrote {source}")


if __name__ == "__main__":
    main()
