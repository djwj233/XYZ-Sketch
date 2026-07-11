#!/usr/bin/env python3
"""Dependency-free SVG plots for paper Figure 1.

The plotting code intentionally keeps the raw experiment points visible but makes
paper-facing curves easier to read: Figure 1(a) is faceted by tuple and uses a
monotone fit for the sharp-threshold trend, while Figure 1(b) can read either the
merged frontier summary or per-tuple shard summaries.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


MODE_LABEL = {
    "random": "iid",
    "naive": "SC-naive",
    "spatial": "SC",
    "circular": "SC-circular",
}
MODE_ORDER = {"iid": 0, "SC-naive": 1, "SC": 1, "SC-circular": 2}
MODE_COLOR = {"iid": "#2563eb", "SC-naive": "#dc2626", "SC": "#9333ea", "SC-circular": "#059669"}
MODE_DASH = {"iid": "", "SC-naive": "7 4", "SC": "7 4", "SC-circular": "2 4"}
TUPLE_COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2"]


def svg_escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_frontier_rows(path: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    rows = read_csv(path)
    if rows:
        return rows, [path]
    base = path.parent
    shard_paths = sorted((base / "shards").glob("*/summary.csv"))
    merged: list[dict[str, Any]] = []
    for shard_path in shard_paths:
        merged.extend(read_csv(shard_path))
    return merged, shard_paths


def numeric(row: dict[str, Any], key: str) -> float | None:
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


def int_text(value: Any) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def tuple_key(row: dict[str, Any]) -> tuple[int, int]:
    return (int(float(row.get("k", 0))), int(float(row.get("l", 0))))


def tuple_label_from_key(key: tuple[int, int]) -> str:
    return f"({key[0]},{key[1]})"


def mode_label(mode: str) -> str:
    return MODE_LABEL.get(mode, mode or "unknown")


def mode_sort(label: str) -> tuple[int, str]:
    return (MODE_ORDER.get(label, 99), label)



def tuple_sort(key: tuple[int, int]) -> tuple[int, int]:
    preferred = {(2, 3): 0, (2, 6): 1, (3, 4): 2}
    return (preferred.get(key, 99), key[0] * 100 + key[1])


def scale_linear(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    if abs(hi - lo) < 1e-15:
        return (out_lo + out_hi) / 2.0
    return out_lo + (value - lo) * (out_hi - out_lo) / (hi - lo)


def scale_log(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    return scale_linear(math.log10(max(value, 1e-12)), math.log10(max(lo, 1e-12)), math.log10(max(hi, 1e-12)), out_lo, out_hi)


def nice_bounds(values: Iterable[float], pad_fraction: float = 0.08, include_zero: bool = False) -> tuple[float, float]:
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return (0.0, 1.0)
    lo = min(values)
    hi = max(values)
    if include_zero:
        lo = min(lo, 0.0)
        hi = max(hi, 0.0)
    if abs(hi - lo) < 1e-15:
        pad = abs(hi) * 0.08 + 1e-9
    else:
        pad = (hi - lo) * pad_fraction
    return lo - pad, hi + pad


def fmt_tick(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value:.0e}".replace("e+0", "e").replace("e+", "e")
    if abs(value) >= 1000:
        return f"{value:.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{value:.3g}"


def polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(points))


def isotonic_fit(points: list[dict[str, Any]]) -> list[float]:
    """PAVA monotone nondecreasing fit for Bernoulli success rates."""
    if not points:
        return []
    blocks: list[dict[str, float]] = []
    for point in points:
        weight = max(1.0, float(point.get("trials") or 1.0))
        mean = min(1.0, max(0.0, float(point["y"])))
        blocks.append({"weight": weight, "mean": mean, "count": 1})
        while len(blocks) >= 2 and blocks[-2]["mean"] > blocks[-1]["mean"]:
            last = blocks.pop()
            prev = blocks.pop()
            weight_sum = prev["weight"] + last["weight"]
            blocks.append({
                "weight": weight_sum,
                "mean": (prev["mean"] * prev["weight"] + last["mean"] * last["weight"]) / weight_sum,
                "count": prev["count"] + last["count"],
            })
    fitted: list[float] = []
    for block in blocks:
        fitted.extend([block["mean"]] * int(block["count"]))
    return fitted


def collect_sharp(rows: Iterable[dict[str, Any]]) -> dict[tuple[int, int], dict[str, list[dict[str, Any]]]]:
    facets: dict[tuple[int, int], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("record_type") not in ("aggregate", ""):
            continue
        if row.get("status") != "ok":
            continue
        x = numeric(row, "R_w30")
        y = numeric(row, "success_rate")
        if x is None or y is None:
            continue
        mode = mode_label(str(row.get("mode", "")))
        facets[tuple_key(row)][mode].append({
            "x": x,
            "y": y,
            "lo": numeric(row, "ci_low"),
            "hi": numeric(row, "ci_high"),
            "M": numeric(row, "M"),
            "trials": numeric(row, "trials") or 1.0,
        })
    return {
        facet: {mode: sorted(points, key=lambda item: item["x"]) for mode, points in modes.items() if points}
        for facet, modes in facets.items()
        if modes
    }


def collect_thresholds(rows: Iterable[dict[str, Any]]) -> dict[tuple[int, int], dict[str, dict[str, float]]]:
    result: dict[tuple[int, int], dict[str, dict[str, float]]] = defaultdict(dict)
    for row in rows:
        if row.get("status") != "ok":
            continue
        x90 = numeric(row, "point_R_w30_90") or numeric(row, "ci_low_R_w30_90")
        width = numeric(row, "transition_width_C_over_d")
        if x90 is None:
            continue
        result[tuple_key(row)][mode_label(str(row.get("mode", "")))] = {"x90": x90, "width": width or 0.0}
    return result


def write_figure1a(path: Path, raw_rows: list[dict[str, Any]], summary_rows: list[dict[str, Any]]) -> None:
    facets = collect_sharp(raw_rows)
    thresholds = collect_thresholds(summary_rows)
    facet_keys = sorted(facets, key=tuple_sort)
    width = 4200
    height = 1380
    left = 255
    right = 125
    top = 245
    bottom = 275
    gap = 150
    panel_h = height - top - bottom
    panel_w = (width - left - right - gap * max(0, len(facet_keys) - 1)) / max(1, len(facet_keys))
    y_ticks = [0.0, 0.25, 0.5, 0.75, 0.9, 1.0]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    for facet_index, facet in enumerate(facet_keys):
        panel_left = left + facet_index * (panel_w + gap)
        panel_right = panel_left + panel_w
        all_points = [point for points in facets[facet].values() for point in points]
        x_values = [point["x"] for point in all_points]
        x_values.extend(meta["x90"] for meta in thresholds.get(facet, {}).values())
        x_lo, x_hi = nice_bounds(x_values, pad_fraction=0.06)

        def x_pos(value: float) -> float:
            return scale_linear(value, x_lo, x_hi, panel_left, panel_right)

        def y_pos(value: float) -> float:
            return scale_linear(value, 0.0, 1.0, top + panel_h, top)

        lines.append(f'<rect x="{panel_left:.2f}" y="{top}" width="{panel_w:.2f}" height="{panel_h}" fill="#ffffff" stroke="#111827" stroke-width="5.0"/>')
        lines.append(f'<text x="{(panel_left + panel_right) / 2:.2f}" y="{top - 16}" text-anchor="middle" font-family="Arial" font-size="82" font-weight="700">(k,l) = {tuple_label_from_key(facet)}</text>')
        for tick in y_ticks:
            y = y_pos(tick)
            color = "#4b5563" if abs(tick - 0.9) < 1e-12 else "#d1d5db"
            dash = ' stroke-dasharray="8 7"' if abs(tick - 0.9) < 1e-12 else ""
            lines.append(f'<line x1="{panel_left:.2f}" y1="{y:.2f}" x2="{panel_right:.2f}" y2="{y:.2f}" stroke="{color}" stroke-width="3.0"{dash}/>')
            if facet_index == 0:
                lines.append(f'<text x="{panel_left - 10:.2f}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="58" fill="#111827">{fmt_tick(tick)}</text>')
        for tick in [x_lo + (x_hi - x_lo) * i / 3.0 for i in range(4)]:
            x = x_pos(tick)
            lines.append(f'<line x1="{x:.2f}" y1="{top + panel_h}" x2="{x:.2f}" y2="{top + panel_h + 9}" stroke="#111827" stroke-width="3.4"/>')
            lines.append(f'<text x="{x:.2f}" y="{top + panel_h + 102}" text-anchor="middle" font-family="Arial" font-size="58" fill="#111827">{fmt_tick(tick)}</text>')

        for mode in sorted(facets[facet], key=mode_sort):
            points = facets[facet][mode]
            color = MODE_COLOR.get(mode, "#555")
            for point in points:
                lines.append(f'<circle cx="{x_pos(point["x"]):.2f}" cy="{y_pos(point["y"]):.2f}" r="4.2" fill="{color}" opacity="0.40"/>')
            fitted = isotonic_fit(points)
            trend = [(x_pos(point["x"]), y_pos(fit)) for point, fit in zip(points, fitted)]
            dash = MODE_DASH.get(mode, "")
            dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
            lines.append(f'<path d="{polyline(trend)}" fill="none" stroke="{color}" stroke-width="9.5" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>')
            stride = max(1, math.ceil(len(points) / 10))
            for point, fit in list(zip(points, fitted))[::stride]:
                lines.append(f'<circle cx="{x_pos(point["x"]):.2f}" cy="{y_pos(fit):.2f}" r="7.0" fill="white" stroke="{color}" stroke-width="4.0"/>')
            meta = thresholds.get(facet, {}).get(mode)
            if meta:
                x90 = x_pos(meta["x90"])
                lines.append(f'<line x1="{x90:.2f}" y1="{top}" x2="{x90:.2f}" y2="{top + panel_h}" stroke="{color}" stroke-width="4.2" opacity="0.72" stroke-dasharray="7 8"/>')

    lines.append(f'<text x="{left + (width - left - right) / 2:.2f}" y="{height - 24}" text-anchor="middle" font-family="Arial" font-size="72" fill="#111827">communication R_w30 = bits / (30 d)</text>')
    lines.append(f'<text transform="translate(92 {top + panel_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="72" fill="#111827">success rate</text>')
    legend_x = width - right - 1725
    legend_y = 118
    modes = sorted({mode for facet in facets.values() for mode in facet}, key=mode_sort)
    legend_offsets = {"iid": 0, "SC-naive": 485, "SC": 485, "SC-circular": 1120}
    for index, mode in enumerate(modes):
        x = legend_x + legend_offsets.get(mode, index * 140)
        y = legend_y
        color = MODE_COLOR.get(mode, "#555")
        dash = MODE_DASH.get(mode, "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(f'<line x1="{x}" y1="{y}" x2="{x + 165}" y2="{y}" stroke="{color}" stroke-width="12.0"{dash_attr}/>')
        lines.append(f'<text x="{x + 175}" y="{y + 22}" font-family="Arial" font-size="62" fill="#111827">{svg_escape(mode)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect_frontier(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        d = numeric(row, "d")
        y = numeric(row, "best_R_w30") or numeric(row, "point_R_w30_90")
        if d is None or y is None or d <= 0:
            continue
        key = tuple_key(row)
        mode = mode_label(str(row.get("mode", "")))
        label = f"{tuple_label_from_key(key)} {mode}"
        series[label].append({
            "x": d,
            "y": y,
            "lo": numeric(row, "uncertain_R_w30_min") or numeric(row, "ci_low_R_w30_90"),
            "hi": numeric(row, "uncertain_R_w30_max"),
            "status": row.get("status", ""),
            "tuple": key,
            "mode": mode,
        })
    return {label: sorted(points, key=lambda item: item["x"]) for label, points in series.items() if points}


def frontier_color(label: str, labels: list[str]) -> str:
    tuple_part = label.split()[0]
    tuples = sorted({item.split()[0] for item in labels})
    return TUPLE_COLORS[tuples.index(tuple_part) % len(TUPLE_COLORS)]


def frontier_dash(label: str) -> str:
    for mode, dash in MODE_DASH.items():
        if mode in label or MODE_LABEL.get(mode, "") in label:
            return dash
    return ""


def write_figure1b(path: Path, rows: list[dict[str, Any]]) -> None:
    series = collect_frontier(rows)
    width = 2850
    height = 1500
    left = 255
    right = 760
    top = 160
    bottom = 230
    plot_w = width - left - right
    plot_h = height - top - bottom
    labels = sorted(series)
    all_x = [point["x"] for points in series.values() for point in points]
    all_y = [point[value] for points in series.values() for point in points for value in ("y", "lo", "hi") if point.get(value) is not None]
    x_lo, x_hi = (min(all_x), max(all_x)) if all_x else (100.0, 10000.0)
    y_lo, y_hi = nice_bounds(all_y, pad_fraction=0.10)

    def x_pos(value: float) -> float:
        return scale_log(value, x_lo, x_hi, left, left + plot_w)

    def y_pos(value: float) -> float:
        return scale_linear(value, y_lo, y_hi, top + plot_h, top)

    x_ticks = sorted(set(all_x))
    if len(x_ticks) > 9:
        stride = max(1, math.ceil(len(x_ticks) / 9))
        x_ticks = x_ticks[::stride]
        if all_x and max(all_x) not in x_ticks:
            x_ticks.append(max(all_x))
    y_ticks = [y_lo + (y_hi - y_lo) * i / 5.0 for i in range(6)]
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="92" font-weight="700" fill="#111827">Figure 1(b): Communication Frontier</text>',
        f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#ffffff" stroke="#111827" stroke-width="3.2"/>',
    ]
    for tick in x_ticks:
        x = x_pos(tick)
        lines.append(f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" y2="{top + plot_h}" stroke="#d1d5db" stroke-width="1.7"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_h + 92}" text-anchor="middle" font-family="Arial" font-size="58" fill="#111827">{fmt_tick(tick)}</text>')
    for tick in y_ticks:
        y = y_pos(tick)
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#d1d5db" stroke-width="1.7"/>')
        lines.append(f'<text x="{left - 26}" y="{y + 20:.2f}" text-anchor="end" font-family="Arial" font-size="58" fill="#111827">{fmt_tick(tick)}</text>')
    for label in labels:
        points = series[label]
        color = frontier_color(label, labels)
        dash = frontier_dash(label)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        trend = [(x_pos(point["x"]), y_pos(point["y"])) for point in points]
        lines.append(f'<path d="{polyline(trend)}" fill="none" stroke="{color}" stroke-width="5.0" stroke-linecap="round" stroke-linejoin="round"{dash_attr}/>')
        for point in points:
            x = x_pos(point["x"])
            y = y_pos(point["y"])
            if point.get("lo") is not None and point.get("hi") is not None:
                y1 = y_pos(float(point["lo"]))
                y2 = y_pos(float(point["hi"]))
                lines.append(f'<line x1="{x:.2f}" y1="{y1:.2f}" x2="{x:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-width="2.1" opacity="0.65"/>')
            if point.get("status") == "ok":
                lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6.2" fill="white" stroke="{color}" stroke-width="2.8"/>')
            else:
                lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7.4" fill="white" stroke="{color}" stroke-width="2.8"/>')
                lines.append(f'<line x1="{x - 3.1:.2f}" y1="{y - 3.1:.2f}" x2="{x + 3.1:.2f}" y2="{y + 3.1:.2f}" stroke="{color}" stroke-width="2.2"/>')
                lines.append(f'<line x1="{x - 3.1:.2f}" y1="{y + 3.1:.2f}" x2="{x + 3.1:.2f}" y2="{y - 3.1:.2f}" stroke="{color}" stroke-width="2.2"/>')
    lines.append(f'<text x="{left + plot_w / 2:.2f}" y="{height - 24}" text-anchor="middle" font-family="Arial" font-size="72" fill="#111827">d (log scale)</text>')
    lines.append(f'<text transform="translate(92 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="72" fill="#111827">R_w30 at 90% success</text>')
    legend_x = left + plot_w + 28
    legend_y = top
    for index, label in enumerate(labels):
        y = legend_y + index * 92
        color = frontier_color(label, labels)
        dash = frontier_dash(label)
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 132}" y2="{y}" stroke="{color}" stroke-width="8.0"{dash_attr}/>')
        lines.append(f'<text x="{legend_x + 165}" y="{y + 20}" font-family="Arial" font-size="58" fill="#111827">{svg_escape(label)}</text>')
    unresolved = sum(1 for points in series.values() for point in points if point.get("status") != "ok")
    if unresolved:
        y = legend_y + (len(labels) + 1) * 92
        lines.append(f'<circle cx="{legend_x + 10}" cy="{y}" r="7.4" fill="white" stroke="#111827" stroke-width="2.8"/>')
        lines.append(f'<text x="{legend_x + 70}" y="{y + 7}" font-family="Arial" font-size="20" fill="#111827">unresolved final check</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_source_summary(path: Path, sharp_input: Path, sharp_summary: Path, frontier_input: Path, frontier_sources: list[Path], sharp_rows: list[dict[str, Any]], sharp_summary_rows: list[dict[str, Any]], frontier_rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 1 Plot Source Summary\n\n")
        handle.write(f"- Figure 1(a) raw input: `{sharp_input}`\n")
        handle.write(f"- Figure 1(a) raw rows read: {len(sharp_rows)}\n")
        handle.write(f"- Figure 1(a) summary input: `{sharp_summary}`\n")
        handle.write(f"- Figure 1(a) summary rows read: {len(sharp_summary_rows)}\n")
        handle.write(f"- Figure 1(b) requested input: `{frontier_input}`\n")
        if frontier_sources:
            handle.write("- Figure 1(b) actual source files:\n")
            for source in frontier_sources:
                handle.write(f"  - `{source}`\n")
        handle.write(f"- Figure 1(b) rows read: {len(frontier_rows)}\n")
        handle.write(f"- Figure 1(b) unresolved rows marked, not hidden: {sum(1 for row in frontier_rows if row.get('status') != 'ok')}\n")
        handle.write("- Output format: dependency-free SVG.\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot Figure 1 from XYZ sharp-threshold and frontier CSV outputs.")
    parser.add_argument("--sharp-input", type=Path, default=Path("tests") / "results" / "paper_fig1_sharp_threshold" / "raw.csv")
    parser.add_argument("--sharp-summary", type=Path, default=Path("tests") / "results" / "paper_fig1_sharp_threshold" / "summary.csv")
    parser.add_argument("--frontier-input", type=Path, default=Path("tests") / "results" / "paper_fig1_frontier" / "summary.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("tests") / "results" / "paper_figures")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sharp_rows = read_csv(args.sharp_input)
    sharp_summary_rows = read_csv(args.sharp_summary)
    frontier_rows, frontier_sources = read_frontier_rows(args.frontier_input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not sharp_rows:
        raise SystemExit(f"no Figure 1(a) rows found: {args.sharp_input}")
    figure1a = args.output_dir / "figure1a_sharp_threshold.svg"
    write_figure1a(figure1a, sharp_rows, sharp_summary_rows)
    print(f"wrote {figure1a}")
    if frontier_rows:
        figure1b = args.output_dir / "figure1b_frontier.svg"
        write_figure1b(figure1b, frontier_rows)
        print(f"wrote {figure1b}")
    else:
        print(f"skipped Figure 1(b): no rows found at {args.frontier_input} or shard summaries")
    summary = args.output_dir / "figure1_source_summary.md"
    write_source_summary(summary, args.sharp_input, args.sharp_summary, args.frontier_input, frontier_sources, sharp_rows, sharp_summary_rows, frontier_rows)
    print(f"wrote {summary}")


if __name__ == "__main__":
    main()
