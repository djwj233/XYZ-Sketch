#!/usr/bin/env python3
"""Combine selected fixed-M Figure 2 heatmaps into one SVG."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

from plot_figure2_fixed_m import (
    DEFAULT_MARKER_C,
    DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    DEFAULT_MARKER_D,
    DEFAULT_MARKER_DELTA,
    as_float,
    as_int,
    heuristic_a,
    heuristic_z_for_m,
    mix,
    svg_escape,
)


DEFAULT_INPUTS = [
    Path("tests/results/paper_fig2_fixed_m_sim/summary.csv"),
    Path("tests/results/paper_fig2_d100000_fixed_m_sim/summary.csv"),
    Path("tests/results/paper_fig2_large_d/d100000/fixed_m_sim/summary.csv"),
    Path("tests/results/paper_fig2_large_d/d1000000/fixed_m_sim/summary.csv"),
]

DEFAULT_SELECTION = [
    (300, 67),
    (300, 72),
    (1000, 211),
    (1000, 224),
    (3000, 596),
    (3000, 621),
    (10000, 1948),
    (10000, 2036),
    (100000, 18155),
    (100000, 18940),
    (1000000, 178767),
    (1000000, 183767),
]

LOW_SUCCESS_COLOR = "#E69F00"
HIGH_SUCCESS_COLOR = "#0072B2"


def color_for_success(value: float) -> str:
    return mix(LOW_SUCCESS_COLOR, HIGH_SUCCESS_COLOR, max(0.0, min(1.0, value)))


def parse_selection(value: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for group in value.split(";"):
        group = group.strip()
        if not group:
            continue
        if ":" not in group:
            raise argparse.ArgumentTypeError(f"invalid selection group: {group}")
        d_text, m_text = group.split(":", 1)
        d_value = int(d_text.strip())
        for part in m_text.split(","):
            if part.strip():
                result.append((d_value, int(part.strip())))
    if not result:
        raise argparse.ArgumentTypeError("selection must contain at least one d:M pair")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("selection contains duplicate d:M pairs")
    return result


def selection_text(selection: list[tuple[int, int]]) -> str:
    grouped: dict[int, list[int]] = {}
    for d_value, m_value in selection:
        grouped.setdefault(d_value, []).append(m_value)
    return ";".join(f"{d_value}:{','.join(str(value) for value in m_values)}" for d_value, m_values in grouped.items())


def read_selected_panels(
    inputs: list[Path],
    selection: list[tuple[int, int]],
) -> dict[tuple[int, int], dict[str, Any]]:
    wanted = set(selection)
    panels: dict[tuple[int, int], dict[str, Any]] = {}
    for input_path in inputs:
        with input_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for row in rows:
            d_value = as_int(row, "d")
            m_value = as_int(row, "M")
            if d_value is None or m_value is None or (d_value, m_value) not in wanted:
                continue
            copied = dict(row)
            copied["source_file"] = str(input_path)
            grouped.setdefault((d_value, m_value), []).append(copied)
        for key, panel_rows in grouped.items():
            if key in panels:
                raise SystemExit(f"selected panel {key} occurs in multiple input files")
            coordinates = {
                (as_float(row, "circular_a"), as_int(row, "z"))
                for row in panel_rows
            }
            a_values = sorted({float(value[0]) for value in coordinates if value[0] is not None})
            z_values = sorted({int(value[1]) for value in coordinates if value[1] is not None})
            if len(coordinates) != len(a_values) * len(z_values):
                raise SystemExit(f"selected panel {key} is not a complete Cartesian grid")
            panels[key] = {
                "rows": panel_rows,
                "source_file": str(input_path),
                "a_values": a_values,
                "z_values": z_values,
                "cells": {
                    (float(row["circular_a"]), int(float(row["z"]))): row
                    for row in panel_rows
                },
            }
    missing = [key for key in selection if key not in panels]
    if missing:
        raise SystemExit(f"missing selected panels: {missing}")
    return panels


def text_color(fill: str) -> str:
    value = fill.lstrip("#")
    if len(value) != 6:
        return "#111"
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    return "#fff" if luminance < 115 else "#111"


def write_combined_svg(
    path: Path,
    *,
    selection: list[tuple[int, int]],
    panels: dict[tuple[int, int], dict[str, Any]],
    columns: int,
    metric: str,
    marker_a: float,
    marker_d: float,
    marker_delta: float,
    minimal_labels: bool,
    panel_k: int | None,
    panel_l: int | None,
) -> list[dict[str, Any]]:
    cell_w = 35
    cell_h = 20
    panel_left = 48
    panel_top = 30 if minimal_labels else 52
    panel_right = 14
    panel_bottom = 34
    gap_x = 20
    gap_y = 22
    outer_left = 24
    outer_top = 24 if minimal_labels else 82
    outer_bottom = 30
    colorbar_space = 94
    max_a_count = max(len(panels[key]["a_values"]) for key in selection)
    max_z_count = max(len(panels[key]["z_values"]) for key in selection)
    max_grid_w = max_a_count * cell_w
    max_grid_h = max_z_count * cell_h
    panel_w = panel_left + max_grid_w + panel_right
    panel_h = panel_top + max_grid_h + panel_bottom
    row_count = math.ceil(len(selection) / columns)
    width = outer_left + columns * panel_w + (columns - 1) * gap_x + colorbar_space
    height = outer_top + row_count * panel_h + (row_count - 1) * gap_y + outer_bottom

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    if not minimal_labels:
        lines.extend(
            [
                f'<text x="{outer_left}" y="31" font-family="Arial" font-size="22" font-weight="700">Selected fixed-M peeling heatmaps</text>',
                f'<text x="{outer_left}" y="55" font-family="Arial" font-size="12" fill="#555">color = {svg_escape(metric)}; yellow box = fitted heuristic; each panel uses its measured grid</text>',
            ]
        )
    stats: list[dict[str, Any]] = []

    for panel_index, key in enumerate(selection):
        d_value, m_value = key
        panel = panels[key]
        a_values: list[float] = panel["a_values"]
        z_values: list[int] = panel["z_values"]
        cells: dict[tuple[float, int], dict[str, Any]] = panel["cells"]
        column = panel_index % columns
        row_number = panel_index // columns
        panel_x = outer_left + column * (panel_w + gap_x)
        panel_y = outer_top + row_number * (panel_h + gap_y)
        grid_w = len(a_values) * cell_w
        grid_h = len(z_values) * cell_h
        grid_x = panel_x + panel_left + (max_grid_w - grid_w) / 2
        grid_y = panel_y + panel_top + (max_grid_h - grid_h) / 2
        sample = next(iter(cells.values()))
        communication = as_float(sample, "field_C_over_d") or 0.0
        marker_z = heuristic_z_for_m(
            m_value,
            marker_a,
            d_constant=marker_d,
            delta=marker_delta,
        )
        marked_a = min(a_values, key=lambda value: (abs(value - marker_a), value))
        marked_z = min(z_values, key=lambda value: (abs(value - marker_z), value))
        marked_row = cells[(marked_a, marked_z)]
        marked_success = as_float(marked_row, metric) or 0.0
        panel_best = max(as_float(value, metric) or 0.0 for value in cells.values())

        panel_letter = chr(ord("a") + panel_index)
        panel_title = f'd = {d_value:,}, M = {m_value:,}'
        if panel_k is not None:
            panel_title += f', k = {panel_k}'
        if panel_l is not None:
            panel_title += f', l = {panel_l}'
        if not minimal_labels:
            panel_title = f'({panel_letter}) {panel_title}'
        lines.append(
            f'<text x="{panel_x}" y="{panel_y + 14}" font-family="Arial" font-size="14" font-weight="700">{panel_title}</text>'
        )
        if not minimal_labels:
            lines.append(
                f'<text x="{panel_x}" y="{panel_y + 31}" font-family="Arial" font-size="10" fill="#555">M*l/d = {communication:.4g}; heuristic = ({marker_a:.3f},{marker_z:.2f}); marked = ({marked_a:.3g},{marked_z})</text>'
            )

        for a_index, a_value in enumerate(a_values):
            x = grid_x + a_index * cell_w + cell_w / 2
            lines.append(
                f'<text x="{x:.2f}" y="{grid_y - 5:.2f}" text-anchor="middle" font-family="Arial" font-size="8">{a_value:.3g}</text>'
            )
        for z_index, z_value in enumerate(reversed(z_values)):
            y_cell = grid_y + z_index * cell_h
            y_text = y_cell + cell_h / 2 + 3
            lines.append(
                f'<text x="{grid_x - 7:.2f}" y="{y_text:.2f}" text-anchor="end" font-family="Arial" font-size="8">{z_value}</text>'
            )
            for a_index, a_value in enumerate(a_values):
                x_cell = grid_x + a_index * cell_w
                row_data = cells[(a_value, z_value)]
                success = as_float(row_data, metric) or 0.0
                fill = color_for_success(success)
                title = (
                    f"d={d_value}, M={m_value}, a={a_value:g}, z={z_value}, "
                    f"{metric}={success:g}, successes={row_data.get('successes')}, trials={row_data.get('trials')}"
                )
                lines.append(f'<g><title>{svg_escape(title)}</title>')
                lines.append(
                    f'<rect x="{x_cell:.2f}" y="{y_cell:.2f}" width="{cell_w}" height="{cell_h}" fill="{fill}" stroke="#fff" stroke-width="1"/>'
                )
                if (a_value, z_value) == (marked_a, marked_z):
                    lines.append(
                        f'<rect x="{x_cell + 2:.2f}" y="{y_cell + 2:.2f}" width="{cell_w - 4}" height="{cell_h - 4}" fill="none" stroke="#ffd400" stroke-width="3"/>'
                    )
                lines.append(
                    f'<text x="{x_cell + cell_w / 2:.2f}" y="{y_cell + cell_h / 2 + 3:.2f}" text-anchor="middle" font-family="Arial" font-size="8" fill="{text_color(fill)}">{success:.2f}</text>'
                )
                lines.append("</g>")
        lines.append(
            f'<text x="{grid_x + grid_w / 2:.2f}" y="{grid_y + grid_h + 19:.2f}" text-anchor="middle" font-family="Arial" font-size="10">a</text>'
        )
        lines.append(
            f'<text transform="translate({grid_x - 34:.2f} {grid_y + grid_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="10">z</text>'
        )
        stats.append(
            {
                "panel": panel_letter,
                "d": d_value,
                "M": m_value,
                "rows": len(cells),
                "a_count": len(a_values),
                "z_count": len(z_values),
                "marker_a": marked_a,
                "marker_z": marked_z,
                "marker_success": marked_success,
                "panel_best": panel_best,
                "source_file": panel["source_file"],
            }
        )

    bar_x = outer_left + columns * panel_w + (columns - 1) * gap_x + 28
    bar_y = outer_top + 26
    bar_w = 20
    bar_h = 240
    for index in range(bar_h):
        value = 1.0 - index / max(1, bar_h - 1)
        lines.append(f'<rect x="{bar_x}" y="{bar_y + index}" width="{bar_w}" height="1" fill="{color_for_success(value)}"/>')
    lines.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" fill="none" stroke="#333"/>')
    for tick in range(6):
        value = 1.0 - tick / 5
        y = bar_y + bar_h * tick / 5
        lines.append(f'<line x1="{bar_x + bar_w}" y1="{y:.2f}" x2="{bar_x + bar_w + 4}" y2="{y:.2f}" stroke="#333"/>')
        lines.append(f'<text x="{bar_x + bar_w + 8}" y="{y + 3:.2f}" font-family="Arial" font-size="9">{value:.1f}</text>')
    lines.append(f'<text x="{bar_x - 3}" y="{bar_y - 10}" font-family="Arial" font-size="10">success</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return stats


def write_source_csv(path: Path, selection: list[tuple[int, int]], panels: dict[tuple[int, int], dict[str, Any]]) -> None:
    rows = [row for key in selection for row in panels[key]["rows"]]
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_index(path: Path, svg_path: Path, source_path: Path, stats: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Selected Figure 2 Panels\n\n")
        handle.write(f"- Figure: `{svg_path.name}`\n")
        handle.write(f"- Source rows: `{source_path.name}`\n")
        handle.write(f"- Panels: `{len(stats)}`\n\n")
        handle.write("| panel | d | M | grid | marker | marker success | panel best | source |\n")
        handle.write("| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |\n")
        for item in stats:
            handle.write(
                f"| ({item['panel']}) | {item['d']} | {item['M']} | "
                f"{item['a_count']}x{item['z_count']} | ({item['marker_a']:.6g},{item['marker_z']}) | "
                f"{item['marker_success']:.3f} | {item['panel_best']:.3f} | `{item['source_file']}` |\n"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Combine selected fixed-M Figure 2 heatmaps into one SVG.")
    parser.add_argument("--input", action="append", type=Path, dest="inputs", default=None)
    parser.add_argument("--selection", type=parse_selection, default=DEFAULT_SELECTION)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--metric", default="peeling_success_rate")
    parser.add_argument("--panel-k", type=int, default=None, help="Optional k value shown in panel titles.")
    parser.add_argument("--panel-l", type=int, default=None, help="Optional l value shown in panel titles.")
    parser.add_argument(
        "--minimal-labels",
        action="store_true",
        help="Show only d and M above each panel; omit the figure header and gray annotations.",
    )
    parser.add_argument("--marker-c", type=float, default=DEFAULT_MARKER_C)
    parser.add_argument(
        "--marker-c-orient-over-c-peel",
        type=float,
        default=DEFAULT_MARKER_C_ORIENT_OVER_C_PEEL,
    )
    parser.add_argument("--marker-d", type=float, default=DEFAULT_MARKER_D)
    parser.add_argument("--marker-delta", type=float, default=DEFAULT_MARKER_DELTA)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/results/paper_figures/figure2_selected_panels"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.columns <= 0:
        raise SystemExit("--columns must be positive")
    inputs = args.inputs or DEFAULT_INPUTS
    for input_path in inputs:
        if not input_path.exists():
            raise SystemExit(f"input does not exist: {input_path}")
    marker_a = heuristic_a(
        c_constant=args.marker_c,
        c_orient_over_c_peel=args.marker_c_orient_over_c_peel,
    )
    panels = read_selected_panels(inputs, args.selection)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = args.output_dir / "figure2a_selected_panels.svg"
    source_path = args.output_dir / "figure2a_selected_panels_source.csv"
    index_path = args.output_dir / "figure2a_selected_panels_index.md"
    stats = write_combined_svg(
        svg_path,
        selection=args.selection,
        panels=panels,
        columns=args.columns,
        metric=args.metric,
        marker_a=marker_a,
        marker_d=args.marker_d,
        marker_delta=args.marker_delta,
        minimal_labels=args.minimal_labels,
        panel_k=args.panel_k,
        panel_l=args.panel_l,
    )
    write_source_csv(source_path, args.selection, panels)
    write_index(index_path, svg_path, source_path, stats)
    print(f"selection={selection_text(args.selection)}")
    print(f"wrote {svg_path}")
    print(f"wrote {source_path}")
    print(f"wrote {index_path}")


if __name__ == "__main__":
    main()
