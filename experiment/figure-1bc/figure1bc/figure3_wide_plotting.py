"""Renderer for objective wide-axis Figure 3 exploration rounds."""

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .artifacts import atomic_write_json, sha256_file
from .figure3_plotting import (
    COMPOSITE_HEIGHT,
    COMPOSITE_WIDTH,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    _atomic_svg,
    _convert,
    _parsed_rows,
    build_composite_svg,
    build_panel_svg,
)
from .figure3_wide import WIDE_PROTOCOL_VERSION
from .figure3_dense_plotting import (
    DENSE_COMPOSITE_HEIGHT,
    DENSE_COMPOSITE_WIDTH,
    DENSE_PANEL_HEIGHT,
    DENSE_PANEL_WIDTH,
    build_dense_composite_svg,
    build_dense_panel_svg,
)
from .figure3_square_plotting import (
    SQUARE_COMPOSITE_HEIGHT,
    SQUARE_COMPOSITE_WIDTH,
    SQUARE_PANEL_HEIGHT,
    SQUARE_PANEL_WIDTH,
    build_square_composite_svg,
    build_square_panel_svg,
)


def render_wide_figure3(run_path: Path) -> Dict[str, Any]:
    root = run_path.resolve()
    state = json.loads((root / "run_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "complete":
        raise ValueError("wide Figure 3 plotting requires a complete data artifact")
    config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    if config.get("protocol_version") != WIDE_PROTOCOL_VERSION:
        raise ValueError("unsupported wide Figure 3 protocol")
    expansion_round = int(config["expansion_round"])
    rows = _parsed_rows(root / "aggregate.csv")
    rows_by_panel: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        stage = str(row["stage"])
        if not stage.startswith("figure3") or len(stage) != len("figure3a"):
            raise ValueError("aggregate contains a non-Figure-3 stage")
        rows_by_panel.setdefault(stage[-1], []).append(row)
    panel_configs = list(config["panels"])
    profile = config.get("resolution_profile")
    if profile == "dense11":
        panel_builder = build_dense_panel_svg
        composite_builder = build_dense_composite_svg
        panel_width, panel_height = DENSE_PANEL_WIDTH, DENSE_PANEL_HEIGHT
        composite_width, composite_height = DENSE_COMPOSITE_WIDTH, DENSE_COMPOSITE_HEIGHT
    elif profile == "square7":
        panel_builder = build_square_panel_svg
        composite_builder = build_square_composite_svg
        panel_width, panel_height = SQUARE_PANEL_WIDTH, SQUARE_PANEL_HEIGHT
        composite_width, composite_height = SQUARE_COMPOSITE_WIDTH, SQUARE_COMPOSITE_HEIGHT
    else:
        panel_builder = build_panel_svg
        composite_builder = build_composite_svg
        panel_width, panel_height = PANEL_WIDTH, PANEL_HEIGHT
        composite_width, composite_height = COMPOSITE_WIDTH, COMPOSITE_HEIGHT
    plot_root = root / ("plots-wide-round%d" % expansion_round)
    plot_root.mkdir(parents=False, exist_ok=False)
    outputs: Dict[str, str] = {}
    for panel_config in panel_configs:
        panel = str(panel_config["panel"])
        svg_path = plot_root / ("figure3%s.svg" % panel)
        pdf_path = plot_root / ("figure3%s.pdf" % panel)
        png_path = plot_root / ("figure3%s.png" % panel)
        _atomic_svg(svg_path, panel_builder(rows_by_panel[panel], panel_config))
        _convert(svg_path, pdf_path, "pdf", panel_width, panel_height)
        _convert(svg_path, png_path, "png", panel_width, panel_height)
        for path in (svg_path, pdf_path, png_path):
            outputs[path.name] = sha256_file(path)
    composite_svg = plot_root / "figure3.svg"
    composite_pdf = plot_root / "figure3.pdf"
    composite_png = plot_root / "figure3.png"
    _atomic_svg(composite_svg, composite_builder(rows_by_panel, panel_configs))
    _convert(composite_svg, composite_pdf, "pdf", composite_width, composite_height)
    _convert(composite_svg, composite_png, "png", composite_width, composite_height)
    for path in (composite_svg, composite_pdf, composite_png):
        outputs[path.name] = sha256_file(path)
    manifest = {
        "status": "complete",
        "protocol_version": WIDE_PROTOCOL_VERSION,
        "expansion_round": expansion_round,
        "resolution_profile": config.get("resolution_profile"),
        "exploratory_axis_expansion": True,
        "figure3_run": str(root),
        "aggregate_sha256": sha256_file(root / "aggregate.csv"),
        "run_config_sha256": sha256_file(root / "run_config.json"),
        "renderer_sha256": sha256_file(Path(__file__)),
        "outputs": outputs,
    }
    atomic_write_json(plot_root / "plot_manifest.json", manifest, exclusive=True)
    return manifest
