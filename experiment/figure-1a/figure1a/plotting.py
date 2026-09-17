"""Deterministic SVG rendering for the completed Figure 1(a)."""

import csv
import html
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from . import constants as const
from .artifacts import atomic_write_json, atomic_write_text, sha256_file


WIDTH = 2100
HEIGHT = 700
PANEL_X = (80, 760, 1440)
PANEL_Y = 88
PANEL_W = 590
PANEL_H = 500

CLEAN_WIDTH = 1950
CLEAN_HEIGHT = 600
CLEAN_PANEL_X = (55, 700, 1345)
CLEAN_PANEL_Y = 38
CLEAN_PANEL_W = 585
CLEAN_PANEL_H = 500

STYLE = {
    "iid": {"label": "iid", "color": "#2166ac", "dash": "", "marker": "circle"},
    "naive": {"label": "SC-naive", "color": "#b2182b", "dash": "10,7", "marker": "square"},
    "circular": {"label": "SC-circular", "color": "#1b7837", "dash": "3,6", "marker": "triangle"},
}

WILSON95_FILL = {
    "iid": "#d9e8f5",
    "naive": "#f5dcdf",
    "circular": "#dcefe3",
}


def _text(x: float, y: float, value: str, *, size: int = 18, anchor: str = "middle",
          weight: int = 400, rotate: int = 0) -> str:
    transform = ' transform="rotate(%d %.2f %.2f)"' % (rotate, x, y) if rotate else ""
    return ('<text x="%.2f" y="%.2f" text-anchor="%s" font-family="Arial,Helvetica,sans-serif" '
            'font-size="%d" font-weight="%d" fill="#202020"%s>%s</text>' %
            (x, y, anchor, size, weight, transform, html.escape(value)))


def _marker(x: float, y: float, mode: str) -> str:
    color = STYLE[mode]["color"]
    if STYLE[mode]["marker"] == "circle":
        return '<circle cx="%.2f" cy="%.2f" r="3.6" fill="%s"/>' % (x, y, color)
    if STYLE[mode]["marker"] == "square":
        return '<rect x="%.2f" y="%.2f" width="7.2" height="7.2" fill="%s"/>' % (x - 3.6, y - 3.6, color)
    return '<polygon points="%.2f,%.2f %.2f,%.2f %.2f,%.2f" fill="%s"/>' % (
        x, y - 4.4, x - 4.2, y + 3.6, x + 4.2, y + 3.6, color
    )


def _convert(
    svg: Path,
    png: Path,
    pdf: Path,
    *,
    png_width: int = 4200,
    png_height: int = 1400,
) -> None:
    commands = (
        ("rsvg-convert", "-w", str(png_width), "-h", str(png_height), "-o", str(png), str(svg)),
        ("rsvg-convert", "-f", "pdf", "-o", str(pdf), str(svg)),
    )
    for command in commands:
        completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0:
            raise RuntimeError("rsvg-convert failed: %s" % completed.stderr.decode(errors="replace"))


def _build_svg(
    rows: Sequence[Mapping[str, Any]],
    *,
    ci_fill: Optional[Mapping[str, str]] = None,
    ci_fill_opacity: float = 0.10,
    clean_layout: bool = False,
) -> Tuple[str, List[Dict[str, Any]]]:
    width = CLEAN_WIDTH if clean_layout else WIDTH
    height = CLEAN_HEIGHT if clean_layout else HEIGHT
    panel_x = CLEAN_PANEL_X if clean_layout else PANEL_X
    panel_y = CLEAN_PANEL_Y if clean_layout else PANEL_Y
    panel_w = CLEAN_PANEL_W if clean_layout else PANEL_W
    panel_h = CLEAN_PANEL_H if clean_layout else PANEL_H
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' %
        (width, height, width, height),
        '<rect width="100%%" height="100%%" fill="#ffffff"/>',
    ]
    if not clean_layout:
        parts.append(_text(WIDTH / 2, 35, "XYZ-Sketch sharp threshold", size=25, weight=600))
    threshold_markers = []
    for panel_index, (k, ell) in enumerate(const.PANELS):
        x0 = panel_x[panel_index]
        panel_rows = [row for row in rows if (row["k"], row["ell"]) == (k, ell)]
        r_values = [float(row["R_w30"]) for row in panel_rows]
        raw_min, raw_max = min(r_values), max(r_values)
        padding = 0.05 * (raw_max - raw_min)
        xmin, xmax = raw_min - padding, raw_max + padding
        sx = lambda value: x0 + (float(value) - xmin) / (xmax - xmin) * panel_w
        sy = lambda value: panel_y + (1.0 - float(value)) * panel_h
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="none" stroke="#303030" stroke-width="1.4"/>' %
                     (x0, panel_y, panel_w, panel_h))
        for tick in range(6):
            probability = tick / 5
            y = sy(probability)
            if clean_layout:
                parts.append(
                    '<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#303030" stroke-width="1"/>'
                    % (x0 - 5, y, x0, y)
                )
            else:
                parts.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#d9d9d9" stroke-width="1"/>' %
                             (x0, y, x0 + panel_w, y))
            if panel_index == 0:
                parts.append(_text(x0 - 12, y + 6, "%.1f" % probability, size=15, anchor="end"))
        for tick in range(5):
            value = xmin + tick * (xmax - xmin) / 4
            x = sx(value)
            if clean_layout:
                parts.append(
                    '<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#303030" stroke-width="1"/>'
                    % (x, panel_y + panel_h, x, panel_y + panel_h + 5)
                )
            else:
                parts.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="#e4e4e4" stroke-width="1"/>' %
                             (x, panel_y, x, panel_y + panel_h))
            parts.append(_text(x, panel_y + panel_h + 25, "%.3f" % value, size=14))
        y90 = sy(0.9)
        parts.append('<line x1="%d" y1="%.2f" x2="%d" y2="%.2f" stroke="#555555" '
                     'stroke-width="1.4" stroke-dasharray="8,6"/>' % (x0, y90, x0 + panel_w, y90))
        for mode in const.MODES:
            curve = sorted((row for row in panel_rows if row["mode"] == mode), key=lambda row: row["M"])
            upper = [(sx(row["R_w30"]), sy(row["ci_high"])) for row in curve]
            lower = [(sx(row["R_w30"]), sy(row["ci_low"])) for row in reversed(curve)]
            polygon = " ".join("%.2f,%.2f" % point for point in upper + lower)
            color = STYLE[mode]["color"]
            fill = ci_fill[mode] if ci_fill is not None else color
            parts.append(
                '<polygon points="%s" fill="%s" fill-opacity="%.2f" stroke="none"/>'
                % (polygon, fill, ci_fill_opacity)
            )
            points = [(sx(row["R_w30"]), sy(row["success_rate"])) for row in curve]
            dash = ' stroke-dasharray="%s"' % STYLE[mode]["dash"] if STYLE[mode]["dash"] else ""
            parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.5"%s/>' %
                         (" ".join("%.2f,%.2f" % point for point in points), color, dash))
            parts.extend(_marker(x, y, mode) for x, y in points)
            crossing = next((row for row in curve if row["success_rate"] >= 0.9), None)
            if crossing:
                x = sx(crossing["R_w30"])
                parts.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="%s" '
                             'stroke-width="1.2" stroke-dasharray="3,5" opacity="0.7"/>' %
                             (x, panel_y, x, panel_y + panel_h, color))
                threshold_markers.append({
                    "k": k, "ell": ell, "mode": mode,
                    "M": int(crossing["M"]), "R_w30": float(crossing["R_w30"]),
                })
        title_y = 25 if clean_layout else 72
        x_label_y = 592 if clean_layout else 645
        parts.append(_text(x0 + panel_w / 2, title_y, "(k, ell) = (%d, %d)" % (k, ell), size=21, weight=600))
        parts.append(_text(x0 + panel_w / 2, x_label_y, "Communication rate R", size=18))
    y_label_x = 16 if clean_layout else 24
    parts.append(_text(y_label_x, panel_y + panel_h / 2, "Decode success probability", size=18, rotate=-90))
    legend_x, legend_y = (72, 65) if clean_layout else (95, 112)
    for index, mode in enumerate(const.MODES):
        y = legend_y + index * 29
        color = STYLE[mode]["color"]
        dash = ' stroke-dasharray="%s"' % STYLE[mode]["dash"] if STYLE[mode]["dash"] else ""
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="2.5"%s/>' %
                     (legend_x, y, legend_x + 36, y, color, dash))
        parts.append(_marker(legend_x + 18, y, mode))
        parts.append(_text(legend_x + 46, y + 6, STYLE[mode]["label"], size=15, anchor="start"))
    if not clean_layout:
        parts.append(_text(WIDTH / 2, 686,
            "Reduced-cardinality revision: d=10,000, |A|=|B|=2d; 100 trials/point; Wilson 95% CI",
            size=15))
    parts.append("</svg>")
    return "\n".join(parts), threshold_markers


def _validated_plot_rows(dense_run: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    state = json.loads((dense_run / "run_state.json").read_text())
    summary = json.loads((dense_run / "dense_summary.json").read_text())
    if state.get("status") != "complete" or summary.get("status") != "complete" \
            or not summary.get("all_points_have_100_trials"):
        raise ValueError("plotting requires a complete 100-trial dense run")
    if sha256_file(dense_run / "aggregate.csv") != summary["artifact_sha256"]["aggregate.csv"]:
        raise ValueError("aggregate.csv hash mismatch")
    rows: List[Dict[str, Any]] = []
    with (dense_run / "aggregate.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append({
                "k": int(row["k"]), "ell": int(row["ell"]), "mode": row["mode"],
                "M": int(row["M"]), "R_w30": float(row["R_w30"]),
                "success_rate": float(row["success_rate"]), "ci_low": float(row["ci_low"]),
                "ci_high": float(row["ci_high"]),
            })
    if len(rows) != summary["point_count"]:
        raise ValueError("aggregate row count mismatch")
    return rows, summary


def render_figure1a(dense_run: Path) -> Dict[str, Any]:
    dense_run = dense_run.resolve()
    rows, summary = _validated_plot_rows(dense_run)
    config = json.loads((dense_run / "run_config.json").read_text())
    svg_text, threshold_markers = _build_svg(rows)
    svg = dense_run / "figure1a.svg"
    png = dense_run / "figure1a.png"
    pdf = dense_run / "figure1a.pdf"
    atomic_write_text(svg, svg_text)
    _convert(svg, png, pdf)
    source = """# Figure 1(a) plot source manifest

- Dense run: `{run}`
- Protocol: `{protocol}`
- Workload: reduced-cardinality revision (`|A|=|B|=2d`)
- Boundary strategy: `{strategy}`
- Aggregate CSV SHA-256: `{aggregate}`
- Dense summary SHA-256: `{summary}`
- Plotting source SHA-256: `{plot_source}`

The plot reads only the completed 100-trial dense aggregate. It applies no smoothing,
monotonic fitting, point deletion, or manually moved threshold marker.
""".format(
        run=dense_run, protocol=const.PROTOCOL_VERSION, strategy=config["boundary_strategy"],
        aggregate=sha256_file(dense_run / "aggregate.csv"),
        summary=sha256_file(dense_run / "dense_summary.json"),
        plot_source=sha256_file(Path(__file__)),
    )
    atomic_write_text(dense_run / "plot_source_manifest.md", source)
    manifest = {
        "status": "complete", "protocol_version": const.PROTOCOL_VERSION,
        "workload_label": "reduced-cardinality revision", "canvas_pixels": [WIDTH, HEIGHT],
        "png_pixels": [4200, 1400], "aggregate_csv_sha256": sha256_file(dense_run / "aggregate.csv"),
        "dense_summary_sha256": sha256_file(dense_run / "dense_summary.json"),
        "boundary_strategy": config["boundary_strategy"], "threshold_markers": threshold_markers,
        "outputs": {name: sha256_file(dense_run / name) for name in ("figure1a.svg", "figure1a.pdf", "figure1a.png")},
        "plot_source_manifest_sha256": sha256_file(dense_run / "plot_source_manifest.md"),
        "plotting_source_sha256": sha256_file(Path(__file__)),
    }
    atomic_write_json(dense_run / "plot_manifest.json", manifest)
    return manifest


def render_figure1a_wilson95(dense_run: Path) -> Dict[str, Any]:
    """Render an additional light-band Wilson 95% CI variant without replacing Figure 1(a)."""
    dense_run = dense_run.resolve()
    rows, summary = _validated_plot_rows(dense_run)
    output_names = (
        "figure1a-wilson95.svg",
        "figure1a-wilson95.pdf",
        "figure1a-wilson95.png",
        "figure1a-wilson95-manifest.json",
    )
    existing = [name for name in output_names if (dense_run / name).exists()]
    if existing:
        raise FileExistsError("refusing to overwrite Wilson 95% variant: %s" % ", ".join(existing))

    svg_text, threshold_markers = _build_svg(
        rows,
        ci_fill=WILSON95_FILL,
        ci_fill_opacity=0.78,
    )
    svg = dense_run / "figure1a-wilson95.svg"
    png = dense_run / "figure1a-wilson95.png"
    pdf = dense_run / "figure1a-wilson95.pdf"
    atomic_write_text(svg, svg_text)
    _convert(svg, png, pdf)
    manifest = {
        "status": "complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "variant": "light_wilson_95_ci_bands",
        "trials_per_point": 100,
        "ci_method": "Wilson score interval",
        "ci_level": 0.95,
        "ci_fill": WILSON95_FILL,
        "ci_fill_opacity": 0.78,
        "aggregate_csv_sha256": sha256_file(dense_run / "aggregate.csv"),
        "dense_summary_sha256": sha256_file(dense_run / "dense_summary.json"),
        "plotting_source_sha256": sha256_file(Path(__file__)),
        "threshold_markers": threshold_markers,
        "outputs": {
            path.name: sha256_file(path)
            for path in (svg, pdf, png)
        },
    }
    atomic_write_json(dense_run / "figure1a-wilson95-manifest.json", manifest)
    return manifest


def render_figure1a_wilson95_clean(dense_run: Path) -> Dict[str, Any]:
    """Render the compact, grid-free Wilson 95% CI publication variant."""
    dense_run = dense_run.resolve()
    rows, summary = _validated_plot_rows(dense_run)
    output_names = (
        "figure1a-wilson95-clean.svg",
        "figure1a-wilson95-clean.pdf",
        "figure1a-wilson95-clean.png",
        "figure1a-wilson95-clean-manifest.json",
    )
    existing = [name for name in output_names if (dense_run / name).exists()]
    if existing:
        raise FileExistsError("refusing to overwrite clean Wilson 95% variant: %s" % ", ".join(existing))

    svg_text, threshold_markers = _build_svg(
        rows,
        ci_fill=WILSON95_FILL,
        ci_fill_opacity=0.78,
        clean_layout=True,
    )
    svg = dense_run / "figure1a-wilson95-clean.svg"
    png = dense_run / "figure1a-wilson95-clean.png"
    pdf = dense_run / "figure1a-wilson95-clean.pdf"
    atomic_write_text(svg, svg_text)
    _convert(svg, png, pdf, png_width=3900, png_height=1200)
    manifest = {
        "status": "complete",
        "protocol_version": const.PROTOCOL_VERSION,
        "variant": "compact_grid_free_light_wilson_95_ci_bands",
        "canvas_pixels": [CLEAN_WIDTH, CLEAN_HEIGHT],
        "png_pixels": [3900, 1200],
        "trials_per_point": 100,
        "ci_method": "Wilson score interval",
        "ci_level": 0.95,
        "ci_fill": WILSON95_FILL,
        "ci_fill_opacity": 0.78,
        "headline_visible": False,
        "revision_footer_visible": False,
        "background_grid_visible": False,
        "aggregate_csv_sha256": sha256_file(dense_run / "aggregate.csv"),
        "dense_summary_sha256": sha256_file(dense_run / "dense_summary.json"),
        "plotting_source_sha256": sha256_file(Path(__file__)),
        "threshold_markers": threshold_markers,
        "outputs": {path.name: sha256_file(path) for path in (svg, pdf, png)},
    }
    atomic_write_json(dense_run / "figure1a-wilson95-clean-manifest.json", manifest)
    return manifest
