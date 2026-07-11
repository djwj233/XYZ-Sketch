#!/usr/bin/env python3
"""Plot the fixed-M peeling-simulation communication frontier for Figure 1(b)."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("tests/results/paper_fig1b_fixed_m/summary.csv")
DEFAULT_OUTPUT_DIR = Path("tests/results/paper_figures/figure1b_fixed_m")


def read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, Any], key: str) -> float:
    value = float(row[key])
    if not math.isfinite(value):
        raise ValueError(f"non-finite {key}: {row[key]}")
    return value


def boolean(row: dict[str, Any], key: str) -> bool:
    value = str(row.get(key, "")).strip().lower()
    if value in {"true", "1", "yes"}:
        return True
    if value in {"false", "0", "no"}:
        return False
    raise ValueError(f"invalid boolean {key}: {row.get(key)!r}")


def svg_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def validate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        raise SystemExit("input contains no rows")
    required = {
        "d",
        "M",
        "bits",
        "bits_per_difference",
        "field_C_over_d",
        "R_w30",
        "success_rate",
        "target_met",
        "status",
        "circular_a",
        "z",
    }
    missing = required - set(rows[0])
    if missing:
        raise SystemExit(f"input is missing fields: {sorted(missing)}")
    ordered = sorted(rows, key=lambda row: int(float(row["d"])))
    d_values = [int(float(row["d"])) for row in ordered]
    if len(set(d_values)) != len(d_values):
        raise SystemExit("input contains duplicate d values")
    for row in ordered:
        if number(row, "d") <= 0 or number(row, "R_w30") <= 0:
            raise SystemExit("d and R_w30 must be positive")
        boolean(row, "target_met")
    return ordered


def accepted_segments(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for row in rows:
        accepted = row.get("status") == "ok" and boolean(row, "target_met")
        if accepted:
            current.append(row)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def write_svg(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    y_field: str,
    title: str,
    y_label: str,
    log_y: bool,
) -> None:
    width = 860
    height = 540
    left = 86
    right = 38
    top = 62
    bottom = 76
    plot_w = width - left - right
    plot_h = height - top - bottom
    x_values = [number(row, "d") for row in rows]
    y_values = [number(row, y_field) for row in rows]
    x_lo = math.log10(min(x_values))
    x_hi = math.log10(max(x_values))
    if log_y:
        y_lo = math.log10(min(y_values))
        y_hi = math.log10(max(y_values))
        y_pad = max(0.04, (y_hi - y_lo) * 0.06)
        y_lo -= y_pad
        y_hi += y_pad
    else:
        y_data_lo = min(y_values)
        y_data_hi = max(y_values)
        y_pad = max(0.03, (y_data_hi - y_data_lo) * 0.12)
        y_lo = max(0.0, y_data_lo - y_pad)
        y_hi = y_data_hi + y_pad

    def x_pos(value: float) -> float:
        return left + (math.log10(value) - x_lo) / (x_hi - x_lo) * plot_w

    def y_pos(value: float) -> float:
        if log_y:
            value = math.log10(value)
        return top + (y_hi - value) / (y_hi - y_lo) * plot_h

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="30" font-family="Arial" font-size="20" font-weight="700">{svg_escape(title)}</text>',
        f'<text x="{left}" y="49" font-family="Arial" font-size="11" fill="#555">k=2, l=6; 100-trial target = 0.9; '
        f'{"both axes are logarithmic" if log_y else "x-axis is logarithmic"}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#222"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#222"/>',
    ]

    for index in range(6):
        value = y_lo + (y_hi - y_lo) * index / 5
        tick_value = 10**value if log_y else value
        y = y_pos(tick_value)
        tick_label = f"{tick_value:.2g}" if log_y else f"{tick_value:.3f}"
        lines.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_w}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        lines.append(f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11">{tick_label}</text>')

    for row in rows:
        d_value = number(row, "d")
        x = x_pos(d_value)
        label = f"10^{round(math.log10(d_value))}" if abs(math.log10(d_value) - round(math.log10(d_value))) < 1e-9 else f"{int(d_value):,}"
        lines.append(f'<line x1="{x:.2f}" y1="{top + plot_h}" x2="{x:.2f}" y2="{top + plot_h + 5}" stroke="#222"/>')
        lines.append(f'<text x="{x:.2f}" y="{top + plot_h + 23}" text-anchor="middle" font-family="Arial" font-size="10">{label}</text>')

    for segment in accepted_segments(rows):
        if len(segment) >= 2:
            points = " ".join(f"{x_pos(number(row, 'd')):.2f},{y_pos(number(row, y_field)):.2f}" for row in segment)
            lines.append(f'<polyline points="{points}" fill="none" stroke="#166534" stroke-width="2.5"/>')

    for row in rows:
        d_value = number(row, "d")
        y_value = number(row, y_field)
        x = x_pos(d_value)
        y = y_pos(y_value)
        target_met = row.get("status") == "ok" and boolean(row, "target_met")
        title = (
            f"d={int(d_value)}, M={int(number(row, 'M'))}, a={number(row, 'circular_a'):.6g}, "
            f"z={int(number(row, 'z'))}, success={number(row, 'success_rate'):.3f}, "
            f"{y_field}={y_value:.6g}"
        )
        lines.append(f'<g><title>{svg_escape(title)}</title>')
        if target_met:
            lines.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="#166534" stroke="white" stroke-width="1.5"/>')
        else:
            lines.append(f'<line x1="{x - 6:.2f}" y1="{y - 6:.2f}" x2="{x + 6:.2f}" y2="{y + 6:.2f}" stroke="#b91c1c" stroke-width="3"/>')
            lines.append(f'<line x1="{x - 6:.2f}" y1="{y + 6:.2f}" x2="{x + 6:.2f}" y2="{y - 6:.2f}" stroke="#b91c1c" stroke-width="3"/>')
        lines.append("</g>")

    lines.extend(
        [
            f'<text x="{left + plot_w / 2:.2f}" y="{height - 22}" text-anchor="middle" font-family="Arial" font-size="13">difference size d</text>',
            f'<text transform="translate(24 {top + plot_h / 2:.2f}) rotate(-90)" text-anchor="middle" font-family="Arial" font-size="13">{y_label}</text>',
            f'<circle cx="{left + plot_w - 196}" cy="{top + 16}" r="5" fill="#166534"/>',
            f'<text x="{left + plot_w - 184}" y="{top + 20}" font-family="Arial" font-size="11">success >= 0.9</text>',
            f'<line x1="{left + plot_w - 68}" y1="{top + 11}" x2="{left + plot_w - 56}" y2="{top + 23}" stroke="#b91c1c" stroke-width="3"/>',
            f'<line x1="{left + plot_w - 68}" y1="{top + 23}" x2="{left + plot_w - 56}" y2="{top + 11}" stroke="#b91c1c" stroke-width="3"/>',
            f'<text x="{left + plot_w - 50}" y="{top + 20}" font-family="Arial" font-size="11">below target</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_source_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_source_md(path: Path, input_path: Path, rows: list[dict[str, Any]]) -> None:
    accepted = sum(1 for row in rows if row.get("status") == "ok" and boolean(row, "target_met"))
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Figure 1(b) Fixed-M Source\n\n")
        handle.write(f"- Input: `{input_path}`\n")
        handle.write(f"- Rows: {len(rows)}\n")
        handle.write(f"- Target met: {accepted}\n")
        handle.write(f"- Below target or failed: {len(rows) - accepted}\n")
        handle.write("- Model: circular hypergraph peeling simulation\n")
        handle.write("- M search performed by this experiment: no\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot the fixed-M Figure 1(b) peeling frontier.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"input does not exist: {args.input}")
    rows = validate_rows(read_rows(args.input))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg_path = args.output_dir / "figure1b_fixed_m.svg"
    source_csv = args.output_dir / "figure1b_fixed_m_source.csv"
    source_md = args.output_dir / "figure1b_fixed_m_source.md"
    communication_svg_path = args.output_dir / "figure1b_total_communication.svg"
    communication_per_d_svg_path = args.output_dir / "figure1b_communication_per_difference.svg"
    field_communication_per_d_svg_path = args.output_dir / "figure1b_Ml_per_d.svg"
    write_svg(
        svg_path,
        rows,
        y_field="R_w30",
        title="Figure 1(b): Fixed-M peeling frontier",
        y_label="R_w30",
        log_y=False,
    )
    write_svg(
        communication_svg_path,
        rows,
        y_field="bits",
        title="Figure 1(b): Total communication",
        y_label="&#x1D506; (bits)",
        log_y=True,
    )
    write_svg(
        communication_per_d_svg_path,
        rows,
        y_field="bits_per_difference",
        title="Figure 1(b): Communication per difference",
        y_label="&#x1D506; / d (bits)",
        log_y=False,
    )
    write_svg(
        field_communication_per_d_svg_path,
        rows,
        y_field="field_C_over_d",
        title="Figure 1(b): Field communication per difference",
        y_label="M l / d",
        log_y=False,
    )
    write_source_csv(source_csv, rows)
    write_source_md(source_md, args.input, rows)
    print(f"wrote {svg_path}")
    print(f"wrote {communication_svg_path}")
    print(f"wrote {communication_per_d_svg_path}")
    print(f"wrote {field_communication_per_d_svg_path}")
    print(f"wrote {source_csv}")
    print(f"wrote {source_md}")


if __name__ == "__main__":
    main()
