#!/usr/bin/env python3
"""Dependency-free, paper-facing SVG plots for Figure 3."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ALGORITHM_STYLES = {
    "xyz_v2": {"label": "XYZ-Sketch", "color": "#0057ff", "dash": "", "marker": "circle"},
    "xyz_v1": {"label": "XYZ-Sketch v1", "color": "#7c3aed", "dash": "7 4", "marker": "circle"},
    "minisketch": {"label": "minisketch", "color": "#00a651", "dash": "", "marker": "square"},
    "iblt": {"label": "IBLT", "color": "#e60000", "dash": "7 4", "marker": "square"},
    "riblt": {"label": "Rateless IBLT", "color": "#ff8c00", "dash": "2 4", "marker": "diamond"},
    "cpisync": {"label": "CPISync", "color": "#00a3c7", "dash": "9 3 2 3", "marker": "diamond"},
    "negentropy": {"label": "Negentropy", "color": "#4b5563", "dash": "4 4", "marker": "triangle"},
}
FALLBACK_COLORS = ["#9333ea", "#0f766e", "#be123c", "#475569"]
ALGORITHM_ORDER = {name: index for index, name in enumerate(ALGORITHM_STYLES)}


def svg_escape(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def numeric(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def algorithm_name(row: dict[str, Any]) -> str:
    return str(row.get("algorithm", "unknown"))


def algorithm_style(name: str) -> dict[str, str]:
    if name in ALGORITHM_STYLES:
        return ALGORITHM_STYLES[name]
    index = sum(ord(char) for char in name) % len(FALLBACK_COLORS)
    return {"label": name, "color": FALLBACK_COLORS[index], "dash": "", "marker": "circle"}


def algorithm_sort(name: str) -> tuple[int, str]:
    return (ALGORITHM_ORDER.get(name, 99), name)


def metric_is_available(row: dict[str, Any], y_field: str) -> bool:
    value = numeric(row, y_field)
    if value is None or value <= 0:
        return False
    if y_field == "update_avg_s_per_element":
        encode = numeric(row, "encode_avg_s")
        return encode is not None and encode > 0
    return True


def collect_series(
    rows: Iterable[dict[str, Any]], y_field: str, *, include_unresolved: bool
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[algorithm_name(row)].append(row)

    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for name, algorithm_rows in grouped.items():
        break_before = False
        algorithm_rows.sort(key=lambda row: numeric(row, "d") or math.inf)
        for row in algorithm_rows:
            status = str(row.get("status", ""))
            d_value = numeric(row, "d")
            y_value = numeric(row, y_field)
            has_value = (
                d_value is not None
                and d_value > 0
                and y_value is not None
                and y_value > 0
                and metric_is_available(row, y_field)
            )
            should_show = status == "ok" or (include_unresolved and status == "unresolved")
            if not has_value or not should_show:
                break_before = True
                continue
            series[name].append(
                {
                    "x": d_value,
                    "y": y_value,
                    "status": status,
                    "success": numeric(row, "final_success_rate"),
                    "break_before": break_before,
                }
            )
            break_before = False
    return {name: sorted(points, key=lambda point: point["x"]) for name, points in series.items() if points}


def unavailable_algorithms(rows: Iterable[dict[str, Any]], y_field: str) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("status", "")) in {"ok", "unresolved"}:
            grouped[algorithm_name(row)].append(row)
    unavailable = [name for name, items in grouped.items() if not any(metric_is_available(row, y_field) for row in items)]
    return sorted(unavailable, key=algorithm_sort)


def scale_log(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    log_lo = math.log10(lo)
    log_hi = math.log10(hi)
    if abs(log_hi - log_lo) < 1e-15:
        return (out_lo + out_hi) / 2.0
    return out_lo + (math.log10(value) - log_lo) * (out_hi - out_lo) / (log_hi - log_lo)


def log_bounds(values: Iterable[float], padding: float = 0.07) -> tuple[float, float]:
    positive = [value for value in values if value > 0 and math.isfinite(value)]
    if not positive:
        return (1.0, 10.0)
    lo_log = math.log10(min(positive))
    hi_log = math.log10(max(positive))
    if abs(hi_log - lo_log) < 1e-12:
        lo_log -= 0.25
        hi_log += 0.25
    else:
        pad = (hi_log - lo_log) * padding
        lo_log -= pad
        hi_log += pad
    return (10**lo_log, 10**hi_log)


def log_ticks(lo: float, hi: float, *, dense: bool) -> list[float]:
    multipliers = (1, 2, 5) if dense else (1,)
    start = math.floor(math.log10(lo)) - 1
    end = math.ceil(math.log10(hi)) + 1
    ticks = [multiplier * 10**power for power in range(start, end + 1) for multiplier in multipliers]
    return [tick for tick in ticks if lo <= tick <= hi]


def format_tick(value: float) -> str:
    if value == 0:
        return "0"
    exponent = math.floor(math.log10(abs(value)))
    mantissa = value / 10**exponent
    if exponent >= 4 or exponent <= -3:
        superscripts = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
        exponent_text = str(exponent).translate(superscripts)
        if abs(mantissa - 1.0) < 1e-10:
            return f"10{exponent_text}"
        return f"{mantissa:g}×10{exponent_text}"
    if abs(value) >= 100:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.3g}"


def scientific_tick_parts(value: float) -> tuple[str, str] | None:
    if value == 0:
        return None
    exponent = math.floor(math.log10(abs(value)))
    mantissa = value / 10**exponent
    if not (exponent >= 4 or exponent <= -3):
        return None
    if abs(mantissa - 1.0) < 1e-10:
        return ("10", str(exponent))
    return (f"{mantissa:g}×10", str(exponent))


def tick_text_svg(
    *,
    x: float,
    y: float,
    value: float,
    anchor: str,
    font_size: int,
    fill: str = "#000000",
    weight: str = "400",
) -> str:
    parts = scientific_tick_parts(value)
    if parts is None:
        return (
            f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" '
            f'font-family="Arial, sans-serif" font-size="{font_size}" '
            f'fill="{fill}" font-weight="{weight}">{format_tick(value)}</text>'
        )
    base, exponent = parts
    exponent_size = max(1, round(font_size * 0.84))
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{font_size}" '
        f'fill="{fill}" font-weight="{weight}">{svg_escape(base)}'
        f'<tspan baseline-shift="super" font-size="{exponent_size}">{svg_escape(exponent)}</tspan>'
        f'</text>'
    )


def line_path(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(points))


def accepted_segments(points: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for point in points:
        if point["status"] == "ok":
            if point.get("break_before") and current:
                segments.append(current)
                current = []
            current.append(point)
        else:
            if current:
                segments.append(current)
                current = []
    if current:
        segments.append(current)
    return segments


def marker_svg(marker: str, x: float, y: float, color: str, *, unresolved: bool, tooltip: str) -> list[str]:
    fill = "white" if unresolved else color
    lines = [f"<g><title>{svg_escape(tooltip)}</title>"]
    if marker == "square":
        lines.append(f'<rect x="{x - 11:.2f}" y="{y - 11:.2f}" width="22" height="22" fill="{fill}" stroke="{color}" stroke-width="2.2"/>')
    elif marker == "diamond":
        lines.append(f'<path d="M {x:.2f} {y - 12:.2f} L {x + 12:.2f} {y:.2f} L {x:.2f} {y + 12:.2f} L {x - 12:.2f} {y:.2f} Z" fill="{fill}" stroke="{color}" stroke-width="2.2"/>')
    elif marker == "triangle":
        lines.append(f'<path d="M {x:.2f} {y - 12:.2f} L {x + 12:.2f} {y + 11:.2f} L {x - 12:.2f} {y + 7:.2f} Z" fill="{fill}" stroke="{color}" stroke-width="2.2"/>')
    else:
        lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="11" fill="{fill}" stroke="{color}" stroke-width="2.2"/>')
    if unresolved:
        lines.append(f'<line x1="{x - 5:.2f}" y1="{y - 5:.2f}" x2="{x + 5:.2f}" y2="{y + 5:.2f}" stroke="{color}" stroke-width="2.2"/>')
        lines.append(f'<line x1="{x - 5:.2f}" y1="{y + 5:.2f}" x2="{x + 5:.2f}" y2="{y - 5:.2f}" stroke="{color}" stroke-width="2.2"/>')
    lines.append("</g>")
    return lines


def write_svg(
    path: Path,
    rows: list[dict[str, Any]],
    y_field: str,
    title: str,
    y_label: str,
    *,
    include_unresolved: bool,
) -> None:
    series = collect_series(rows, y_field, include_unresolved=include_unresolved)
    width = 1280
    height = 740
    left = 168
    right = 395
    top = 108
    bottom = 126
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_x = [point["x"] for points in series.values() for point in points]
    all_y = [point["y"] for points in series.values() for point in points]
    x_lo, x_hi = log_bounds(all_x, padding=0.025)
    y_lo, y_hi = log_bounds(all_y, padding=0.09)

    def x_pos(value: float) -> float:
        return scale_log(value, x_lo, x_hi, left, left + plot_w)

    def y_pos(value: float) -> float:
        return scale_log(value, y_lo, y_hi, top + plot_h, top)

    x_ticks = log_ticks(x_lo, x_hi, dense=False)
    y_ticks = log_ticks(y_lo, y_hi, dense=True)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left + plot_w / 2:.2f}" y="58" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="600">{svg_escape(title)}</text>',
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#475569" stroke-width="2.2"/>',
    ]
    for tick in x_ticks:
        x = x_pos(tick)
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#cbd5e1" stroke-width="1.2"/>')
        lines.append(tick_text_svg(x=x, y=top + plot_h + 28, value=tick, anchor="middle", font_size=72))
    for tick in y_ticks:
        y = y_pos(tick)
        exponent = math.log10(tick)
        major = abs(exponent - round(exponent)) < 1e-10
        color = "#64748b" if major else "#cbd5e1"
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="{color}" stroke-width="1.2"/>')
        lines.append(tick_text_svg(x=left - 16, y=y + 4, value=tick, anchor="end", font_size=30))

    names = sorted(series, key=algorithm_sort)
    for name in names:
        points = series[name]
        style = algorithm_style(name)
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        for segment in accepted_segments(points):
            if len(segment) >= 2:
                path_data = line_path([(x_pos(point["x"]), y_pos(point["y"])) for point in segment])
                lines.append(f'<path d="{path_data}" fill="none" stroke="{style["color"]}" stroke-width="6.0" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>')
        for point in points:
            success = point.get("success")
            success_text = "unknown" if success is None else f"{success:.3g}"
            tooltip = f'{style["label"]}: d={point["x"]:g}, value={point["y"]:.6g}, final success={success_text}, status={point["status"]}'
            lines.extend(
                marker_svg(
                    style["marker"],
                    x_pos(point["x"]),
                    y_pos(point["y"]),
                    style["color"],
                    unresolved=point["status"] != "ok",
                    tooltip=tooltip,
                )
            )

    lines.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 34}" text-anchor="middle" font-family="Arial, sans-serif" font-size="36" font-weight="400">difference size d (log scale)</text>')
    lines.append(f'<text transform="translate(48 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial, sans-serif" font-size="36" font-weight="400">{svg_escape(y_label)}</text>')
    legend_x = left + plot_w + 28
    legend_y = top + 15
    for index, name in enumerate(names):
        style = algorithm_style(name)
        y = legend_y + index * 44
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        lines.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 48}" y2="{y}" stroke="{style["color"]}" stroke-width="4.0"{dash_attr}/>')
        lines.extend(marker_svg(style["marker"], legend_x + 24, y, style["color"], unresolved=False, tooltip=style["label"]))
        lines.append(f'<text x="{legend_x + 62}" y="{y + 8}" font-family="Arial, sans-serif" font-size="28" font-weight="600">{svg_escape(style["label"])}</text>')

    note_y = legend_y + len(names) * 44 + 28
    unresolved_count = sum(1 for points in series.values() for point in points if point["status"] != "ok")
    if unresolved_count:
        lines.extend(marker_svg("circle", legend_x + 13, note_y, "#4b5563", unresolved=True, tooltip="Final validation below target"))
        lines.append(f'<text x="{legend_x + 34}" y="{note_y + 8}" font-family="Arial, sans-serif" font-size="22" fill="#111827" font-weight="600">below 90% final check</text>')
        note_y += 42
    unavailable = unavailable_algorithms(rows, y_field)
    if unavailable:
        labels = ", ".join(algorithm_style(name)["label"] for name in unavailable)
        unavailable_label = "update timing unavailable:" if y_field == "update_avg_s_per_element" else "metric unavailable:"
        lines.append(f'<text x="{legend_x}" y="{note_y}" font-family="Arial, sans-serif" font-size="22" fill="#374151" font-weight="600">{unavailable_label}</text>')
        lines.append(f'<text x="{legend_x}" y="{note_y + 24}" font-family="Arial, sans-serif" font-size="22" fill="#374151" font-weight="600">{svg_escape(labels)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


COMBINED_PLOTS = [
    ("best_R_w30", "Space overhead", "space overhead R"),
    ("update_avg_s_per_element", "Update time", "update time per input element"),
    ("decode_avg_s_per_difference", "Decode time", "decode time per difference"),
]


def draw_combined_panel(
    lines: list[str],
    rows: list[dict[str, Any]],
    y_field: str,
    title: str,
    y_label: str,
    *,
    x0: float,
    top: float,
    plot_w: float,
    plot_h: float,
    x_bounds: tuple[float, float],
    include_unresolved: bool,
) -> set[str]:
    series = collect_series(rows, y_field, include_unresolved=include_unresolved)
    all_y = [point["y"] for points in series.values() for point in points]
    y_lo, y_hi = log_bounds(all_y, padding=0.10)
    x_lo, x_hi = x_bounds

    def x_pos(value: float) -> float:
        return scale_log(value, x_lo, x_hi, x0, x0 + plot_w)

    def y_pos(value: float) -> float:
        return scale_log(value, y_lo, y_hi, top + plot_h, top)

    lines.append(f'<text x="{x0 + plot_w / 2:.2f}" y="{top - 105:.2f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="112" font-weight="500">{svg_escape(title)}</text>')
    lines.append(f'<rect x="{x0}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#475569" stroke-width="2.2"/>')

    for tick in log_ticks(x_lo, x_hi, dense=False):
        x = x_pos(tick)
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#cbd5e1" stroke-width="1.8"/>')
        lines.append(tick_text_svg(x=x, y=top + plot_h + 86, value=tick, anchor="middle", font_size=78))

    for tick in log_ticks(y_lo, y_hi, dense=(y_field == "best_R_w30")):
        y = y_pos(tick)
        exponent = math.log10(tick)
        major = abs(exponent - round(exponent)) < 1e-10
        color = "#64748b" if major else "#cbd5e1"
        lines.append(f'<line x1="{x0}" y1="{y:.2f}" x2="{x0 + plot_w}" y2="{y:.2f}" stroke="{color}" stroke-width="1.8"/>')
        lines.append(tick_text_svg(x=x0 - 32, y=y + 16, value=tick, anchor="end", font_size=72))

    names = sorted(series, key=algorithm_sort)
    for name in names:
        points = series[name]
        style = algorithm_style(name)
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        for segment in accepted_segments(points):
            if len(segment) >= 2:
                path_data = line_path([(x_pos(point["x"]), y_pos(point["y"])) for point in segment])
                lines.append(f'<path d="{path_data}" fill="none" stroke="{style["color"]}" stroke-width="6.0" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>')
        for point in points:
            success = point.get("success")
            success_text = "unknown" if success is None else f"{success:.3g}"
            tooltip = f'{style["label"]}: d={point["x"]:g}, value={point["y"]:.6g}, final success={success_text}, status={point["status"]}'
            lines.extend(marker_svg(style["marker"], x_pos(point["x"]), y_pos(point["y"]), style["color"], unresolved=point["status"] != "ok", tooltip=tooltip))

    lines.append(f'<text x="{x0 + plot_w / 2:.2f}" y="{top + plot_h + 185:.2f}" text-anchor="middle" font-family="Arial, sans-serif" font-size="76" font-weight="400">difference size d</text>')
    lines.append(f'<text transform="translate({x0 - 178:.2f} {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial, sans-serif" font-size="76" font-weight="400">{svg_escape(y_label)}</text>')
    return set(names)


def write_combined_svg(path: Path, rows: list[dict[str, Any]], *, include_unresolved: bool) -> None:
    width = 5150
    height = 1880
    top = 260
    plot_h = 900
    plot_w = 1200
    gap = 370
    panel_x = [315, 315 + plot_w + gap, 315 + 2 * (plot_w + gap)]

    all_x = []
    for field, _, _ in COMBINED_PLOTS:
        series = collect_series(rows, field, include_unresolved=include_unresolved)
        all_x.extend(point["x"] for points in series.values() for point in points)
    x_bounds = log_bounds(all_x, padding=0.025)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    legend_names: set[str] = set()
    for x0, (field, title, y_label) in zip(panel_x, COMBINED_PLOTS):
        legend_names.update(
            draw_combined_panel(
                lines,
                rows,
                field,
                title,
                y_label,
                x0=x0,
                top=top,
                plot_w=plot_w,
                plot_h=plot_h,
                x_bounds=x_bounds,
                include_unresolved=include_unresolved,
            )
        )

    names = sorted(legend_names, key=algorithm_sort)
    legend_y = 1608
    label_widths = {
        "xyz_v2": 760,
        "minisketch": 720,
        "iblt": 460,
        "riblt": 900,
        "cpisync": 670,
        "negentropy": 820,
        "xyz_v1": 820,
    }
    slots = [label_widths.get(name, 720) for name in names]
    start_x = (width - sum(slots)) / 2
    x = start_x
    for index, name in enumerate(names):
        style = algorithm_style(name)
        dash_attr = f' stroke-dasharray="{style["dash"]}"' if style["dash"] else ""
        lines.append(f'<line x1="{x:.2f}" y1="{legend_y}" x2="{x + 138:.2f}" y2="{legend_y}" stroke="{style["color"]}" stroke-width="6.0"{dash_attr}/>')
        lines.extend(marker_svg(style["marker"], x + 69, legend_y, style["color"], unresolved=False, tooltip=style["label"]))
        lines.append(f'<text x="{x + 172:.2f}" y="{legend_y + 25}" font-family="Arial, sans-serif" font-size="78" font-weight="500">{svg_escape(style["label"])}</text>')
        x += slots[index]

    lines.append('</svg>')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_source_summary(path: Path, input_path: Path, rows: list[dict[str, Any]], include_unresolved: bool) -> None:
    status_counts = Counter(str(row.get("status", "missing")) for row in rows)
    algorithm_counts = Counter(algorithm_name(row) for row in rows)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 3 Plot Source Summary\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- Rows read: {len(rows)}\n")
        handle.write(f"- Algorithms: {', '.join(f'{name}={count}' for name, count in sorted(algorithm_counts.items(), key=lambda item: algorithm_sort(item[0])))}\n")
        handle.write(f"- Statuses: {', '.join(f'{name}={count}' for name, count in sorted(status_counts.items()))}\n")
        handle.write(f"- Unresolved candidate markers shown: {'yes' if include_unresolved else 'no'}\n")
        handle.write("- Filled markers and connecting lines: rows passing the 90% final validation.\n")
        if include_unresolved:
            handle.write("- Open crossed markers: measured candidates whose final validation did not reach 90%; they are not connected.\n")
        else:
            handle.write("- Rows below the 90% final validation are hidden and still break connecting lines.\n")
        handle.write("- Figure 3(a): log-log axes; R_w30 = transmitted bits / (30*d).\n")
        handle.write("- Figure 3(b,c): log-log axes. Zero timing values are treated as unavailable, not as zero cost.\n")
        handle.write("- final_ci_low/final_ci_high are success-rate intervals, not communication-threshold error bars, so they are not drawn on the R axis.\n")
        for field in ("best_R_w30", "update_avg_s_per_element", "decode_avg_s_per_difference"):
            missing = unavailable_algorithms(rows, field)
            if missing:
                handle.write(f"- No positive `{field}` measurements for: {', '.join(algorithm_style(name)['label'] for name in missing)}.\n")
        handle.write("- Output format: dependency-free SVG.\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot paper Figure 3 from compare-frontier CSV or JSONL output.")
    parser.add_argument("--input", type=Path, default=Path("tests") / "results" / "paper_fig3_compare_frontier" / "summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_figures")
    parser.add_argument("--hide-unresolved", action="store_true", help="Hide measured candidates that failed final 90% validation.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_rows(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    include_unresolved = not args.hide_unresolved
    plots = [
        ("best_R_w30", "figure3a_communication.svg", "Space overhead", "space overhead R"),
        ("update_avg_s_per_element", "figure3b_update_cost.svg", "Update time", "update time per input element"),
        ("decode_avg_s_per_difference", "figure3c_decode_cost.svg", "Decode time", "decode time per difference"),
    ]
    for field, filename, title, y_label in plots:
        output = args.output_dir / filename
        write_svg(output, rows, field, title, y_label, include_unresolved=include_unresolved)
        print(f"wrote {output}")
    combined_output = args.output_dir / "figure3_combined.svg"
    write_combined_svg(combined_output, rows, include_unresolved=include_unresolved)
    print(f"wrote {combined_output}")
    summary = args.output_dir / "figure3_source_summary.md"
    write_source_summary(summary, args.input, rows, include_unresolved)
    print(f"wrote {summary}")


if __name__ == "__main__":
    main()
