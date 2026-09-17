"""Deterministic post-processing for Figure 1(b)(c) holdout heatmaps."""

import csv
import hashlib
import html
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from . import constants as const
from .artifacts import atomic_write_json, sha256_file


WIDTH = 820
HEIGHT = 650
GRID_X = 108
GRID_Y = 110
CELL_W = 76
CELL_H = 40
PREDICTION_GAP = 24
COLORBAR_W = 24

COLOR_STOPS = (
    (0.00, (178, 24, 43)),
    (0.25, (239, 138, 98)),
    (0.50, (247, 247, 247)),
    (0.75, (127, 191, 123)),
    (1.00, (27, 120, 55)),
)


def _interpolate_color(rate: float) -> Tuple[int, int, int]:
    value = min(1.0, max(0.0, rate))
    for index in range(1, len(COLOR_STOPS)):
        left_value, left = COLOR_STOPS[index - 1]
        right_value, right = COLOR_STOPS[index]
        if value <= right_value:
            fraction = (value - left_value) / (right_value - left_value)
            return tuple(
                round(left[channel] + fraction * (right[channel] - left[channel]))
                for channel in range(3)
            )
    return COLOR_STOPS[-1][1]


def _hex_color(rgb: Tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _text_color(rgb: Tuple[int, int, int]) -> str:
    luminance = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255.0
    return "#ffffff" if luminance < 0.52 else "#202020"


def _svg_text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 14,
    anchor: str = "middle",
    weight: int = 400,
    fill: str = "#202020",
    rotate: int = 0,
) -> str:
    transform = ' transform="rotate(%d %.2f %.2f)"' % (rotate, x, y) if rotate else ""
    return (
        '<text x="%.2f" y="%.2f" text-anchor="%s" font-family="Arial, Helvetica, sans-serif" '
        'font-size="%d" font-weight="%d" fill="%s"%s>%s</text>'
        % (x, y, anchor, size, weight, fill, transform, html.escape(value))
    )


def _format_a(value: float) -> str:
    if value == 0.0:
        return "0"
    if value in (0.1, 0.2, 0.3, 0.4, 0.5):
        return "%.1f" % value
    return "%.3f" % value


def build_heatmap_svg(
    rows: Sequence[Mapping[str, Any]],
    *,
    figure: str,
    label: str,
) -> str:
    if not rows:
        raise ValueError("heatmap requires aggregate rows")
    d_values = {int(row["d"]) for row in rows}
    m_values = {int(row["M"]) for row in rows}
    if len(d_values) != 1 or len(m_values) != 1:
        raise ValueError("one heatmap must contain one fixed (d,M)")
    d = d_values.pop()
    M = m_values.pop()
    base_rows = [row for row in rows if not bool(row["is_frozen_prediction"])]
    predictions = [row for row in rows if bool(row["is_frozen_prediction"])]
    if len(predictions) != 1:
        raise ValueError("one heatmap must contain exactly one frozen prediction")
    prediction = predictions[0]

    base_a = sorted({float(row["a"]) for row in base_rows})
    z_values = sorted({int(row["z"]) for row in base_rows}, reverse=True)
    if base_a != [value / 1000.0 for value in const.HOLDOUT_A_UNITS]:
        raise ValueError("holdout a grid differs from the audited protocol")
    if tuple(sorted(z_values)) != tuple(sorted(const.HOLDOUT_Z)):
        raise ValueError("holdout z grid differs from the audited protocol")
    if len(base_rows) != len(base_a) * len(z_values):
        raise ValueError("base heatmap grid is incomplete")
    lookup = {(float(row["a"]), int(row["z"])): float(row["success_rate"]) for row in base_rows}

    base_width = len(base_a) * CELL_W
    prediction_x = GRID_X + base_width + PREDICTION_GAP
    grid_right = prediction_x + CELL_W
    colorbar_x = grid_right + 66
    grid_height = len(z_values) * CELL_H
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (WIDTH, HEIGHT, WIDTH, HEIGHT),
        '<rect width="100%%" height="100%%" fill="#ffffff"/>',
        '<defs><linearGradient id="success-scale" x1="0" y1="1" x2="0" y2="0">',
    ]
    for value, rgb in COLOR_STOPS:
        lines.append('<stop offset="%.0f%%" stop-color="%s"/>' % (value * 100, _hex_color(rgb)))
    lines.extend(["</linearGradient></defs>"])
    lines.append(
        _svg_text(
            (GRID_X + grid_right) / 2,
            34,
            "d = %s, M = %s, k = 2, ell = 6" % (format(d, ","), format(M, ",")),
            size=20,
            weight=700,
        )
    )
    lines.append(
        _svg_text(
            (GRID_X + grid_right) / 2,
            61,
            "%s | C/D calibrated on d < 3,000" % label,
            size=13,
            fill="#555555",
        )
    )

    for column, a_value in enumerate(base_a):
        x = GRID_X + column * CELL_W
        lines.append(_svg_text(x + CELL_W / 2, GRID_Y - 16, _format_a(a_value), size=13))
        for row_index, z in enumerate(z_values):
            y = GRID_Y + row_index * CELL_H
            rate = lookup[(a_value, z)]
            rgb = _interpolate_color(rate)
            lines.append(
                '<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#ffffff" stroke-width="1.4"/>'
                % (x, y, CELL_W, CELL_H, _hex_color(rgb))
            )
            lines.append(
                _svg_text(
                    x + CELL_W / 2,
                    y + CELL_H / 2 + 5,
                    "%.2f" % rate,
                    size=13,
                    weight=600,
                    fill=_text_color(rgb),
                )
            )

    prediction_a = float(prediction["a"])
    prediction_z = int(prediction["z"])
    if prediction_z not in z_values:
        raise ValueError("frozen prediction z lies outside the displayed z grid")
    pred_y = GRID_Y + z_values.index(prediction_z) * CELL_H
    pred_rate = float(prediction["success_rate"])
    pred_rgb = _interpolate_color(pred_rate)
    lines.append(_svg_text(prediction_x + CELL_W / 2, GRID_Y - 16, _format_a(prediction_a), size=13))
    lines.append(
        '<rect x="%d" y="%d" width="%d" height="%d" fill="%s" stroke="#ffd400" stroke-width="4"/>'
        % (prediction_x, pred_y, CELL_W, CELL_H, _hex_color(pred_rgb))
    )
    lines.append(
        _svg_text(
            prediction_x + CELL_W / 2,
            pred_y + CELL_H / 2 + 5,
            "%.2f" % pred_rate,
            size=13,
            weight=700,
            fill=_text_color(pred_rgb),
        )
    )

    for row_index, z in enumerate(z_values):
        y = GRID_Y + row_index * CELL_H
        lines.append(_svg_text(GRID_X - 15, y + CELL_H / 2 + 5, str(z), size=13, anchor="end"))
    lines.append(_svg_text(GRID_X - 68, GRID_Y + grid_height / 2, "z", size=16, rotate=-90))
    lines.append(_svg_text((GRID_X + grid_right) / 2, GRID_Y + grid_height + 42, "a", size=16))

    lines.append(
        '<rect x="%d" y="%d" width="%d" height="%d" fill="url(#success-scale)" stroke="#555555" stroke-width="1"/>'
        % (colorbar_x, GRID_Y, COLORBAR_W, grid_height)
    )
    lines.append(_svg_text(colorbar_x + COLORBAR_W / 2, GRID_Y - 16, "success", size=12))
    for tick in (1.0, 0.8, 0.6, 0.4, 0.2, 0.0):
        y = GRID_Y + (1.0 - tick) * grid_height
        lines.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#444444"/>' % (
            colorbar_x + COLORBAR_W, y, colorbar_x + COLORBAR_W + 6, y
        ))
        lines.append(_svg_text(colorbar_x + COLORBAR_W + 11, y + 4, "%.1f" % tick, size=11, anchor="start"))

    lines.append(_svg_text(WIDTH / 2, HEIGHT - 25, "(%s)" % figure[-1], size=18))
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def _atomic_render_svg(svg_path: Path, svg: str) -> None:
    if svg_path.exists():
        raise FileExistsError(str(svg_path))
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % svg_path.name, dir=str(svg_path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(svg)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(svg_path))
    finally:
        if temporary.exists():
            temporary.unlink()


def _convert_svg(svg_path: Path, output_path: Path, output_format: str) -> None:
    if output_path.exists():
        raise FileExistsError(str(output_path))
    command = ["rsvg-convert", "--format", output_format, "--output", str(output_path)]
    if output_format == "png":
        command.extend(["--width", str(WIDTH * 2), "--height", str(HEIGHT * 2)])
    command.append(str(svg_path))
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))


def render_holdout(holdout_run: Path) -> Dict[str, Any]:
    root = holdout_run.resolve()
    state = json.loads((root / "run_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete":
        raise ValueError("plotting requires a complete holdout artifact")
    rows = list(csv.DictReader((root / "aggregate.csv").open(encoding="utf-8", newline="")))
    outputs: Dict[str, str] = {}
    for figure, domain, _d, _M, label in const.HOLDOUT_SCALES:
        domain_rows: List[Dict[str, Any]] = []
        for row in rows:
            if row["domain"] != domain:
                continue
            parsed = dict(row)
            parsed["d"] = int(row["d"])
            parsed["M"] = int(row["M"])
            parsed["a"] = float(row["a"])
            parsed["z"] = int(row["z"])
            parsed["success_rate"] = float(row["success_rate"])
            parsed["is_frozen_prediction"] = row["is_frozen_prediction"] == "True"
            domain_rows.append(parsed)
        svg = build_heatmap_svg(domain_rows, figure=figure, label=label)
        svg_path = root / (figure + ".svg")
        pdf_path = root / (figure + ".pdf")
        png_path = root / (figure + ".png")
        _atomic_render_svg(svg_path, svg)
        _convert_svg(svg_path, pdf_path, "pdf")
        _convert_svg(svg_path, png_path, "png")
        for path in (svg_path, pdf_path, png_path):
            outputs[path.name] = sha256_file(path)
    manifest = {
        "status": "complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "holdout_run": str(root),
        "aggregate_sha256": sha256_file(root / "aggregate.csv"),
        "frozen_parameters_sha256": json.loads(
            (root / "holdout_summary.json").read_text(encoding="utf-8")
        )["frozen_parameters_sha256"],
        "renderer_sha256": sha256_file(Path(__file__)),
        "outputs": outputs,
    }
    atomic_write_json(root / "plot_manifest.json", manifest, exclusive=True)
    return manifest

