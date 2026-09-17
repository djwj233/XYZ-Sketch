"""Compact square renderings for the completed Figure 2 experiment."""

import html
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import atomic_json, sha256_file


STYLES = {
    "xyz": ("XYZ-Sketch", "#2468d8", "circle"),
    "minisketch": ("minisketch", "#18a665", "square"),
    "external_iblt": ("IBLT", "#df2f2f", "triangle"),
    "riblt": ("Rateless IBLT", "#f09a18", "diamond"),
    "cpisync": ("CPISync", "#16a6bd", "down"),
    "project_iblt": ("Project IBLT (additional)", "#7651a8", "plus"),
}

PAPER_MAIN = ("xyz", "minisketch", "external_iblt", "riblt", "cpisync")
SIZE = 700
LEFT, TOP, PLOT_W, PLOT_H = 86, 72, 594, 548
COMBINED_W, COMBINED_H = 1500, 600
COMBINED_PANEL_W = 500
COMBINED_LEFT, COMBINED_TOP, COMBINED_PLOT_W, COMBINED_PLOT_H = 78, 66, 390, 365


def _plottable_rows(
    rows: Sequence[Mapping[str, Any]], algorithms: Sequence[str], field: str
) -> Sequence[Mapping[str, Any]]:
    selected = []
    for row in rows:
        if row.get("algorithm") not in algorithms or row.get(field) is None:
            continue
        if row.get("d") not in const.DIFFERENCES or row.get("status") != "confirmed":
            continue
        if field == "R_w30":
            pass
        elif field in {
            "update_ns_per_input_conditional_mean",
            "decode_ns_per_difference_conditional_mean",
        }:
            if row.get("timing_status") != "complete" \
                    or row.get("successful_datasets") != const.TIMING_DATASETS:
                continue
        else:
            raise ValueError("unknown Figure 2 plotting field")
        selected.append(row)
    return selected


def _curve_segments(
    rows: Sequence[Mapping[str, Any]], algorithm: str
) -> List[Tuple[Mapping[str, Any], ...]]:
    by_d: Dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if row["algorithm"] != algorithm:
            continue
        d = int(row["d"])
        if d in by_d:
            raise ValueError("duplicate Figure 2 point for one algorithm/d")
        by_d[d] = row
    segments: List[Tuple[Mapping[str, Any], ...]] = []
    current: List[Mapping[str, Any]] = []
    for d in const.DIFFERENCES:
        if d in by_d:
            current.append(by_d[d])
        elif current:
            segments.append(tuple(current))
            current = []
    if current:
        segments.append(tuple(current))
    return segments


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 16,
    anchor: str = "middle",
    weight: int = 400,
    rotate: int = 0,
    fill: str = "#202020",
) -> str:
    transform = ' transform="rotate(%d %.2f %.2f)"' % (rotate, x, y) if rotate else ""
    return (
        '<text x="%.2f" y="%.2f" text-anchor="%s" '
        'font-family="Arial,Helvetica,sans-serif" font-size="%d" font-weight="%d" '
        'fill="%s"%s>%s</text>'
        % (x, y, anchor, size, weight, fill, transform, html.escape(value))
    )


def _marker(x: float, y: float, algorithm: str, radius: float = 4.2) -> str:
    color, kind = STYLES[algorithm][1], STYLES[algorithm][2]
    if kind == "circle":
        return '<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s"/>' % (x, y, radius, color)
    if kind == "square":
        side = radius * 1.8
        return '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (
            x - side / 2, y - side / 2, side, side, color
        )
    if kind == "triangle":
        return '<polygon points="%.2f,%.2f %.2f,%.2f %.2f,%.2f" fill="%s"/>' % (
            x, y - radius - 0.8, x - radius - 0.8, y + radius, x + radius + 0.8, y + radius, color
        )
    if kind == "down":
        return '<polygon points="%.2f,%.2f %.2f,%.2f %.2f,%.2f" fill="%s"/>' % (
            x, y + radius + 0.8, x - radius - 0.8, y - radius, x + radius + 0.8, y - radius, color
        )
    if kind == "diamond":
        return '<polygon points="%.2f,%.2f %.2f,%.2f %.2f,%.2f %.2f,%.2f" fill="%s"/>' % (
            x, y - radius - 0.8, x - radius - 0.8, y, x, y + radius + 0.8,
            x + radius + 0.8, y, color
        )
    if kind == "cross":
        return '<path d="M %.2f %.2f L %.2f %.2f M %.2f %.2f L %.2f %.2f" stroke="%s" stroke-width="2.6"/>' % (
            x - radius, y - radius, x + radius, y + radius,
            x - radius, y + radius, x + radius, y - radius, color,
        )
    return '<path d="M %.2f %.2f h %.2f M %.2f %.2f v %.2f" stroke="%s" stroke-width="2.8"/>' % (
        x - radius, y, radius * 2, x, y - radius, radius * 2, color
    )


def _display_value(row: Mapping[str, Any], field: str) -> float:
    value = float(row[field])
    return value if field == "R_w30" else value * 1e-9


def _y_bounds(values: Sequence[float], field: str, ylog: bool) -> Tuple[float, float]:
    if not ylog:
        minimum, maximum = min(values), max(values)
        padding = 0.08 * (maximum - minimum or 1.0)
        return minimum - padding, maximum + padding
    if field == "R_w30":
        maximum = max(values)
        return (
            (math.log10(0.85), math.log10(7.0))
            if maximum <= 7.0 else
            (math.log10(0.85), float(math.ceil(math.log10(maximum))))
        )
    logs = [math.log10(value) for value in values]
    lower, upper = float(math.floor(min(logs))), float(math.ceil(max(logs)))
    if lower == upper:
        lower -= 1.0
        upper += 1.0
    return lower, upper


def _y_ticks(ymin: float, ymax: float, field: str, ylog: bool) -> Sequence[Tuple[float, str]]:
    if not ylog:
        return [
            (ymin + index * (ymax - ymin) / 5, "%.3g" % (ymin + index * (ymax - ymin) / 5))
            for index in range(6)
        ]
    if field == "R_w30":
        ticks = []
        for exponent in range(math.floor(ymin), math.ceil(ymax) + 1):
            for multiplier in (1, 2, 5):
                value = multiplier * (10 ** exponent)
                position = math.log10(value)
                if ymin <= position <= ymax:
                    ticks.append((position, "%g" % value))
        return ticks
    return [
        (float(exponent), "10^%d" % exponent)
        for exponent in range(math.ceil(ymin), math.floor(ymax) + 1)
    ]


def _svg(
    rows: Sequence[Mapping[str, Any]],
    algorithms: Sequence[str],
    field: str,
    ylabel: str,
    ylog: bool,
) -> str:
    available = list(_plottable_rows(rows, algorithms, field))
    if not available:
        raise ValueError("Figure 2 panel has no data")
    display = {(row["algorithm"], int(row["d"])): _display_value(row, field) for row in available}
    x_min, x_max = math.log10(min(const.DIFFERENCES)) - 0.08, math.log10(max(const.DIFFERENCES)) + 0.08
    y_min, y_max = _y_bounds(list(display.values()), field, ylog)
    sx = lambda d: LEFT + (math.log10(float(d)) - x_min) / (x_max - x_min) * PLOT_W
    sy = lambda value: TOP + (
        y_max - (math.log10(float(value)) if ylog else float(value))
    ) / (y_max - y_min) * PLOT_H

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="700" height="700" viewBox="0 0 700 700">',
        '<rect width="700" height="700" fill="#ffffff"/>',
        '<defs><clipPath id="plot"><rect x="%d" y="%d" width="%d" height="%d"/></clipPath></defs>'
        % (LEFT, TOP, PLOT_W, PLOT_H),
    ]
    for exponent in range(2, 7):
        x = sx(10 ** exponent)
        parts.append(
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#e2e2e2" stroke-width="1"/>'
            % (x, TOP, x, TOP + PLOT_H)
        )
        parts.append(_text(x, TOP + PLOT_H + 24, "10^%d" % exponent, size=13))
    for value, label in _y_ticks(y_min, y_max, field, ylog):
        y = TOP + (y_max - value) / (y_max - y_min) * PLOT_H
        parts.append(
            '<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#e2e2e2" stroke-width="1"/>'
            % (LEFT, y, LEFT + PLOT_W, y)
        )
        parts.append(_text(LEFT - 10, y + 5, label, size=13, anchor="end"))
    parts.append(
        '<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#303030" stroke-width="1.4"/>'
        % (LEFT, TOP, PLOT_W, PLOT_H)
    )
    parts.append('<g clip-path="url(#plot)">')
    for algorithm in algorithms:
        color = STYLES[algorithm][1]
        for segment in _curve_segments(available, algorithm):
            points = [
                (sx(row["d"]), sy(display[(algorithm, int(row["d"]))]))
                for row in segment
            ]
            if len(points) >= 2:
                parts.append(
                    '<polyline points="%s" fill="none" stroke="%s" stroke-width="2.6" '
                    'stroke-linejoin="round" stroke-linecap="round"/>'
                    % (" ".join("%.2f,%.2f" % point for point in points), color)
                )
            parts.extend(_marker(x, y, algorithm) for x, y in points)
    parts.append('</g>')

    for index, algorithm in enumerate(algorithms):
        label, color, _ = STYLES[algorithm]
        column, row_index = index % 3, index // 3
        x, y = 30 + column * 222, 20 + row_index * 28
        parts.append(
            '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2.6"/>'
            % (x, y, x + 28, y, color)
        )
        parts.append(_marker(x + 14, y, algorithm, radius=3.8))
        parts.append(_text(x + 37, y + 5, label, size=11, anchor="start"))
    parts.append(_text(LEFT + PLOT_W / 2, 680, "Difference size d", size=17))
    parts.append(_text(20, TOP + PLOT_H / 2, ylabel, size=16, rotate=-90))
    parts.append('</svg>')
    return "\n".join(parts)


def _combined_panel(
    rows: Sequence[Mapping[str, Any]],
    algorithms: Sequence[str],
    field: str,
    ylabel: str,
    title: str,
    panel_index: int,
) -> Sequence[str]:
    available = list(_plottable_rows(rows, algorithms, field))
    if not available:
        raise ValueError("Figure 2 combined panel has no data")
    display = {
        (row["algorithm"], int(row["d"])): _display_value(row, field)
        for row in available
    }
    panel_x = panel_index * COMBINED_PANEL_W
    plot_x = panel_x + COMBINED_LEFT
    x_min = math.log10(min(const.DIFFERENCES)) - 0.08
    x_max = math.log10(max(const.DIFFERENCES)) + 0.08
    y_min, y_max = _y_bounds(list(display.values()), field, True)
    sx = lambda d: plot_x + (
        math.log10(float(d)) - x_min
    ) / (x_max - x_min) * COMBINED_PLOT_W
    sy = lambda value: COMBINED_TOP + (
        y_max - math.log10(float(value))
    ) / (y_max - y_min) * COMBINED_PLOT_H
    clip_id = "combined-panel-%d" % panel_index

    parts = [
        '<clipPath id="%s"><rect x="%d" y="%d" width="%d" height="%d"/></clipPath>'
        % (clip_id, plot_x, COMBINED_TOP, COMBINED_PLOT_W, COMBINED_PLOT_H),
    ]
    for exponent in range(2, 7):
        x = sx(10 ** exponent)
        parts.append(
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#e2e2e2" stroke-width="1"/>'
            % (x, COMBINED_TOP, x, COMBINED_TOP + COMBINED_PLOT_H)
        )
        parts.append(_text(x, COMBINED_TOP + COMBINED_PLOT_H + 21, "10^%d" % exponent, size=12))
    for value, label in _y_ticks(y_min, y_max, field, True):
        y = COMBINED_TOP + (y_max - value) / (y_max - y_min) * COMBINED_PLOT_H
        parts.append(
            '<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#e2e2e2" stroke-width="1"/>'
            % (plot_x, y, plot_x + COMBINED_PLOT_W, y)
        )
        parts.append(_text(plot_x - 8, y + 4, label, size=12, anchor="end"))
    parts.append(
        '<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#303030" stroke-width="1.3"/>'
        % (plot_x, COMBINED_TOP, COMBINED_PLOT_W, COMBINED_PLOT_H)
    )
    parts.append('<g clip-path="url(#%s)">' % clip_id)
    for algorithm in algorithms:
        color = STYLES[algorithm][1]
        for segment in _curve_segments(available, algorithm):
            points = [
                (sx(row["d"]), sy(display[(algorithm, int(row["d"]))]))
                for row in segment
            ]
            if len(points) >= 2:
                parts.append(
                    '<polyline points="%s" fill="none" stroke="%s" stroke-width="2.3" '
                    'stroke-linejoin="round" stroke-linecap="round"/>'
                    % (" ".join("%.2f,%.2f" % point for point in points), color)
                )
            parts.extend(_marker(x, y, algorithm, radius=3.6) for x, y in points)
    parts.append('</g>')
    parts.append(_text(plot_x + COMBINED_PLOT_W / 2, 35, title, size=24, weight=500))
    parts.append(_text(plot_x + COMBINED_PLOT_W / 2, 485, "Difference size d", size=15))
    parts.append(_text(panel_x + 20, COMBINED_TOP + COMBINED_PLOT_H / 2, ylabel, size=14, rotate=-90))
    return parts


def _combined_svg(
    rows: Sequence[Mapping[str, Any]], algorithms: Sequence[str]
) -> str:
    panels = (
        ("R_w30", "Space overhead R", "Space overhead"),
        ("update_ns_per_input_conditional_mean", "Update time per input element (s)", "Update time"),
        ("decode_ns_per_difference_conditional_mean", "Decode time per difference (s)", "Decode time"),
    )
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (COMBINED_W, COMBINED_H, COMBINED_W, COMBINED_H),
        '<rect width="%d" height="%d" fill="#ffffff"/>' % (COMBINED_W, COMBINED_H),
        '<defs>',
    ]
    panel_parts = [
        _combined_panel(rows, algorithms, field, ylabel, title, index)
        for index, (field, ylabel, title) in enumerate(panels)
    ]
    parts.extend(panel[0] for panel in panel_parts)
    parts.append('</defs>')
    for panel in panel_parts:
        parts.extend(panel[1:])

    legend_width = 230
    legend_x = (COMBINED_W - legend_width * len(algorithms)) / 2
    legend_y = 558
    for index, algorithm in enumerate(algorithms):
        label, color, _ = STYLES[algorithm]
        x = legend_x + index * legend_width
        parts.append(
            '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="%s" stroke-width="2.5"/>'
            % (x, legend_y, x + 32, legend_y, color)
        )
        parts.append(_marker(x + 16, legend_y, algorithm, radius=3.8))
        parts.append(_text(x + 43, legend_y + 5, label, size=15, anchor="start"))
    parts.append('</svg>')
    return "\n".join(parts)


def _render_set(
    run: Path,
    rows: Sequence[Mapping[str, Any]],
    algorithms: Sequence[str],
    prefix: str,
) -> Dict[str, str]:
    panels = (
        ("a", "R_w30", "Space overhead R", True),
        ("b", "update_ns_per_input_conditional_mean", "Update time per input element (s)", True),
        ("c", "decode_ns_per_difference_conditional_mean", "Decode time per difference (s)", True),
    )
    outputs = {}
    for suffix, field, ylabel, ylog in panels:
        svg = run / (prefix + suffix + ".svg")
        svg.write_text(_svg(rows, algorithms, field, ylabel, ylog), encoding="utf-8")
        png, pdf = svg.with_suffix(".png"), svg.with_suffix(".pdf")
        commands = (
            ("rsvg-convert", "-w", "1400", "-h", "1400", "-o", str(png), str(svg)),
            ("rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)),
        )
        for command in commands:
            completed = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
            )
            if completed.returncode:
                raise RuntimeError(completed.stderr.decode(errors="replace"))
        for path in (svg, png, pdf):
            outputs[path.name] = sha256_file(path)
    return outputs


def _render_combined(
    run: Path,
    rows: Sequence[Mapping[str, Any]],
    algorithms: Sequence[str],
) -> Dict[str, str]:
    svg = run / "figure2-combined.svg"
    svg.write_text(_combined_svg(rows, algorithms), encoding="utf-8")
    png, pdf = svg.with_suffix(".png"), svg.with_suffix(".pdf")
    commands = (
        ("rsvg-convert", "-w", "3000", "-h", "1200", "-o", str(png), str(svg)),
        ("rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)),
    )
    for command in commands:
        completed = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr.decode(errors="replace"))
    return {path.name: sha256_file(path) for path in (svg, png, pdf)}


def render_figure2(run: Path, presentation: Optional[str]) -> Dict[str, Any]:
    run = run.resolve()
    if json.loads((run / "run_state.json").read_text()).get("status") != "complete":
        raise ValueError("Figure 2 plotting requires a complete formal run")
    aggregate = json.loads((run / "aggregate.json").read_text())
    rows = aggregate["points"]
    paper_main = tuple(
        algorithm for algorithm in PAPER_MAIN
        if any(row.get("algorithm") == algorithm for row in rows)
    )
    outputs = _render_set(run, rows, paper_main, "figure2")
    outputs.update(_render_combined(run, rows, paper_main))
    if presentation == "extended":
        outputs.update(_render_set(
            run, rows, PAPER_MAIN + ("project_iblt",), "figure2-extended-"
        ))
    elif presentation == "main_additional_baseline":
        outputs.update(_render_set(
            run, rows, PAPER_MAIN + ("project_iblt",), "figure2-additional-baseline-"
        ))
    elif presentation is not None:
        raise ValueError("invalid project IBLT presentation")
    manifest = {
        "status": "complete",
        "protocol_version": aggregate.get("protocol_version", const.PROTOCOL_VERSION),
        "paper_main_algorithms": list(paper_main),
        "project_iblt_presentation": presentation,
        "aggregate_sha256": sha256_file(run / "aggregate.json"),
        "refinement_protocol": aggregate.get("refinement_protocol"),
        "timing_unit": "seconds",
        "timing_confidence_bands": False,
        "plotting_source_sha256": sha256_file(Path(__file__)),
        "outputs": outputs,
    }
    atomic_json(run / "plot_manifest.json", manifest)
    return manifest
