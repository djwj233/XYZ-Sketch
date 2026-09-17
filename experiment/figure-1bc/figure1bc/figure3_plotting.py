"""Deterministic SVG/PDF/PNG renderer for the centered Appendix Figure 3."""

import csv
import html
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .artifacts import atomic_write_json, sha256_file
from .figure3 import CENTER_COLUMN, CENTER_ROW_ASCENDING, FIGURE3_PANELS, FIGURE3_PROTOCOL_VERSION
from .plotting import COLOR_STOPS, _hex_color, _interpolate_color, _text_color


PANEL_WIDTH = 500
PANEL_HEIGHT = 280
COMPOSITE_COLUMNS = 3
COMPOSITE_ROWS = 4
COMPOSITE_WIDTH = PANEL_WIDTH * COMPOSITE_COLUMNS + 90
COMPOSITE_HEIGHT = PANEL_HEIGHT * COMPOSITE_ROWS + 45
GRID_X = 64
GRID_Y = 72
CELL_W = 48
CELL_H = 31


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 11,
    anchor: str = "middle",
    weight: int = 400,
    fill: str = "#202020",
    rotate: int = 0,
) -> str:
    transform = ' transform="rotate(%d %.2f %.2f)"' % (rotate, x, y) if rotate else ""
    return (
        '<text x="%.2f" y="%.2f" text-anchor="%s" '
        'font-family="Arial, Helvetica, sans-serif" font-size="%d" '
        'font-weight="%d" fill="%s"%s>%s</text>'
        % (x, y, anchor, size, weight, fill, transform, html.escape(value))
    )


def _format_a(value: float) -> str:
    return "%.3f" % value


def _parsed_rows(path: Path) -> List[Dict[str, Any]]:
    parsed_rows: List[Dict[str, Any]] = []
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            parsed = dict(row)
            for name in ("d", "M", "z", "trials", "successes"):
                parsed[name] = int(row[name])
            for name in ("a", "z_raw", "success_rate", "ci_low", "ci_high"):
                parsed[name] = float(row[name])
            parsed["is_frozen_prediction"] = row["is_frozen_prediction"] == "True"
            parsed_rows.append(parsed)
    return parsed_rows


def validate_panel_rows(
    rows: Sequence[Mapping[str, Any]],
    panel_config: Mapping[str, Any],
) -> Tuple[List[float], List[int], Mapping[str, Any]]:
    expected_a = [float(value) for value in panel_config["a_values"]]
    expected_z = [int(value) for value in panel_config["z_values_ascending"]]
    expected_count = len(expected_a) * len(expected_z)
    if len(rows) != expected_count:
        raise ValueError("Figure 3 panel grid is incomplete")
    if {int(row["d"]) for row in rows} != {int(panel_config["d"])}:
        raise ValueError("Figure 3 panel d differs from run_config")
    if {int(row["M"]) for row in rows} != {int(panel_config["M"])}:
        raise ValueError("Figure 3 panel M differs from run_config")
    observed = {(float(row["a"]), int(row["z"])) for row in rows}
    expected = {(a, z) for a in expected_a for z in expected_z}
    if observed != expected:
        raise ValueError("Figure 3 panel axes differ from run_config")
    selected = [row for row in rows if bool(row["is_frozen_prediction"])]
    if len(selected) != 1:
        raise ValueError("Figure 3 panel must have exactly one selected cell")
    center = selected[0]
    center_column = int(panel_config["center_column_zero_based"])
    center_row = int(panel_config["center_row_ascending_zero_based"])
    if center_column != len(expected_a) // 2 or len(expected_a) % 2 != 1:
        raise ValueError("run_config center column is not geometric center")
    vertical_center_required = bool(panel_config.get("vertical_center_required", True))
    if vertical_center_required and (
        center_row != len(expected_z) // 2 or len(expected_z) % 2 != 1
    ):
        raise ValueError("run_config center row is not geometric center")
    if expected_a[center_column] != float(center["a"]):
        raise ValueError("selected a is not the center column")
    if expected_z[center_row] != int(center["z"]):
        raise ValueError("selected z is not the center row")
    return expected_a, expected_z, center


def _panel_group(
    rows: Sequence[Mapping[str, Any]],
    panel_config: Mapping[str, Any],
    *,
    grid_x: int = GRID_X,
    grid_y: int = GRID_Y,
    cell_w: int = CELL_W,
    cell_h: int = CELL_H,
) -> str:
    a_values, z_ascending, selected = validate_panel_rows(rows, panel_config)
    z_values = list(reversed(z_ascending))
    lookup = {(float(row["a"]), int(row["z"])): row for row in rows}
    panel = str(panel_config["panel"])
    d = int(panel_config["d"])
    M = int(panel_config["M"])
    selected_a = float(selected["a"])
    selected_z = int(selected["z"])
    selected_rate = float(selected["success_rate"])
    lines = [
        _text(
            16,
            20,
            "(%s) d = %s, M = %s" % (panel, format(d, ","), format(M, ",")),
            size=13,
            anchor="start",
            weight=700,
        ),
        _text(
            16,
            40,
            "selected = (%.3f, %d), measured = %.2f" % (selected_a, selected_z, selected_rate),
            size=10,
            anchor="start",
            fill="#555555",
        ),
    ]
    for column, a in enumerate(a_values):
        x = grid_x + column * cell_w
        lines.append(_text(x + cell_w / 2, grid_y - 9, _format_a(a), size=9))
        for row_index, z in enumerate(z_values):
            y = grid_y + row_index * cell_h
            row = lookup[(a, z)]
            rate = float(row["success_rate"])
            rgb = _interpolate_color(rate)
            is_selected = bool(row["is_frozen_prediction"])
            stroke = "#ffd400" if is_selected else "#ffffff"
            stroke_width = 3.2 if is_selected else 1.0
            lines.append(
                '<rect data-cell="true" x="%d" y="%d" width="%d" height="%d" '
                'fill="%s" stroke="%s" stroke-width="%.1f"/>'
                % (x, y, cell_w, cell_h, _hex_color(rgb), stroke, stroke_width)
            )
            lines.append(
                _text(
                    x + cell_w / 2,
                    y + cell_h / 2 + 4,
                    "%.2f" % rate,
                    size=9,
                    weight=700 if is_selected else 600,
                    fill=_text_color(rgb),
                )
            )
    for row_index, z in enumerate(z_values):
        y = grid_y + row_index * cell_h
        lines.append(_text(grid_x - 9, y + cell_h / 2 + 4, str(z), size=9, anchor="end"))
    lines.append(_text(grid_x - 42, grid_y + len(z_values) * cell_h / 2, "z", size=11, rotate=-90))
    lines.append(_text(grid_x + len(a_values) * cell_w / 2, grid_y + len(z_values) * cell_h + 27, "a", size=11))
    return "\n".join(lines)


def build_panel_svg(
    rows: Sequence[Mapping[str, Any]],
    panel_config: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            % (PANEL_WIDTH, PANEL_HEIGHT, PANEL_WIDTH, PANEL_HEIGHT),
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            _panel_group(rows, panel_config),
            "</svg>",
            "",
        ]
    )


def build_composite_svg(
    rows_by_panel: Mapping[str, Sequence[Mapping[str, Any]]],
    panel_configs: Sequence[Mapping[str, Any]],
) -> str:
    if len(panel_configs) != 12 or set(rows_by_panel) != {str(item["panel"]) for item in panel_configs}:
        raise ValueError("complete Figure 3 requires exactly 12 panels")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (COMPOSITE_WIDTH, COMPOSITE_HEIGHT, COMPOSITE_WIDTH, COMPOSITE_HEIGHT),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<defs><linearGradient id="figure3-success" x1="0" y1="1" x2="0" y2="0">',
    ]
    for value, rgb in COLOR_STOPS:
        lines.append('<stop offset="%.0f%%" stop-color="%s"/>' % (value * 100, _hex_color(rgb)))
    lines.extend(["</linearGradient></defs>"])
    for index, config in enumerate(panel_configs):
        panel = str(config["panel"])
        x = (index % COMPOSITE_COLUMNS) * PANEL_WIDTH
        y = (index // COMPOSITE_COLUMNS) * PANEL_HEIGHT
        lines.append('<g transform="translate(%d,%d)">' % (x, y))
        lines.append(_panel_group(rows_by_panel[panel], config))
        lines.append("</g>")
    colorbar_x = PANEL_WIDTH * COMPOSITE_COLUMNS + 28
    colorbar_y = 72
    colorbar_h = 280
    lines.append(
        '<rect x="%d" y="%d" width="22" height="%d" fill="url(#figure3-success)" '
        'stroke="#555555" stroke-width="1"/>' % (colorbar_x, colorbar_y, colorbar_h)
    )
    lines.append(_text(colorbar_x + 11, colorbar_y - 13, "success", size=10))
    for tick in (1.0, 0.8, 0.6, 0.4, 0.2, 0.0):
        y = colorbar_y + (1.0 - tick) * colorbar_h
        lines.append(
            '<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#444444"/>'
            % (colorbar_x + 22, y, colorbar_x + 28, y)
        )
        lines.append(_text(colorbar_x + 34, y + 4, "%.1f" % tick, size=9, anchor="start"))
    lines.append(
        _text(
            COMPOSITE_WIDTH / 2,
            COMPOSITE_HEIGHT - 14,
            "Selected fixed-M peeling-success heatmaps; yellow cells are frozen predictions",
            size=13,
        )
    )
    lines.extend(["</svg>", ""])
    return "\n".join(lines)


def _atomic_svg(path: Path, value: str) -> None:
    if path.exists():
        raise FileExistsError(str(path))
    descriptor, temporary_name = tempfile.mkstemp(prefix=".%s." % path.name, dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    finally:
        if temporary.exists():
            temporary.unlink()


def _convert(svg_path: Path, output_path: Path, output_format: str, width: int, height: int) -> None:
    if output_path.exists():
        raise FileExistsError(str(output_path))
    command = ["rsvg-convert", "--format", output_format, "--output", str(output_path)]
    if output_format == "png":
        command.extend(["--width", str(width * 2), "--height", str(height * 2)])
    command.append(str(svg_path))
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", "replace"))


def render_figure3(run_path: Path) -> Dict[str, Any]:
    root = run_path.resolve()
    state = json.loads((root / "run_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete":
        raise ValueError("Figure 3 plotting requires a complete data artifact")
    config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    if config.get("protocol_version") != FIGURE3_PROTOCOL_VERSION:
        raise ValueError("unsupported Figure 3 protocol version")
    rows = _parsed_rows(root / "aggregate.csv")
    rows_by_panel: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        stage = str(row["stage"])
        if not stage.startswith("figure3") or len(stage) != len("figure3a"):
            raise ValueError("aggregate contains a non-Figure-3 stage")
        rows_by_panel.setdefault(stage[-1], []).append(row)
    panel_configs = list(config["panels"])
    plot_root = root / "plots-centered-v1"
    plot_root.mkdir(parents=False, exist_ok=False)
    outputs: Dict[str, str] = {}
    for panel_config in panel_configs:
        panel = str(panel_config["panel"])
        svg_path = plot_root / ("figure3%s.svg" % panel)
        pdf_path = plot_root / ("figure3%s.pdf" % panel)
        png_path = plot_root / ("figure3%s.png" % panel)
        _atomic_svg(svg_path, build_panel_svg(rows_by_panel[panel], panel_config))
        _convert(svg_path, pdf_path, "pdf", PANEL_WIDTH, PANEL_HEIGHT)
        _convert(svg_path, png_path, "png", PANEL_WIDTH, PANEL_HEIGHT)
        for path in (svg_path, pdf_path, png_path):
            outputs[path.name] = sha256_file(path)
    composite_svg = plot_root / "figure3.svg"
    composite_pdf = plot_root / "figure3.pdf"
    composite_png = plot_root / "figure3.png"
    _atomic_svg(composite_svg, build_composite_svg(rows_by_panel, panel_configs))
    _convert(composite_svg, composite_pdf, "pdf", COMPOSITE_WIDTH, COMPOSITE_HEIGHT)
    _convert(composite_svg, composite_png, "png", COMPOSITE_WIDTH, COMPOSITE_HEIGHT)
    for path in (composite_svg, composite_pdf, composite_png):
        outputs[path.name] = sha256_file(path)
    manifest = {
        "status": "complete",
        "protocol_version": FIGURE3_PROTOCOL_VERSION,
        "figure3_run": str(root),
        "aggregate_sha256": sha256_file(root / "aggregate.csv"),
        "run_config_sha256": sha256_file(root / "run_config.json"),
        "renderer_sha256": sha256_file(Path(__file__)),
        "selected_cell_zero_based_ascending": [CENTER_ROW_ASCENDING, CENTER_COLUMN],
        "layout": {"columns": COMPOSITE_COLUMNS, "rows": COMPOSITE_ROWS},
        "outputs": outputs,
    }
    atomic_write_json(plot_root / "plot_manifest.json", manifest, exclusive=True)
    return manifest
