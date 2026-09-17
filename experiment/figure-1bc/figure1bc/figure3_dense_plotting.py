"""Wide-canvas renderer for the 5x11 dense Figure 3 profile."""

from typing import Any, Mapping, Sequence

from .figure3_plotting import _panel_group, _text
from .plotting import COLOR_STOPS, _hex_color


DENSE_PANEL_WIDTH = 700
DENSE_PANEL_HEIGHT = 300
DENSE_COLUMNS = 3
DENSE_ROWS = 4
DENSE_COMPOSITE_WIDTH = DENSE_PANEL_WIDTH * DENSE_COLUMNS + 90
DENSE_COMPOSITE_HEIGHT = DENSE_PANEL_HEIGHT * DENSE_ROWS + 45
DENSE_GRID_X = 72
DENSE_GRID_Y = 76
DENSE_CELL_W = 52
DENSE_CELL_H = 33


def build_dense_panel_svg(
    rows: Sequence[Mapping[str, Any]],
    panel_config: Mapping[str, Any],
) -> str:
    group = _panel_group(
        rows,
        panel_config,
        grid_x=DENSE_GRID_X,
        grid_y=DENSE_GRID_Y,
        cell_w=DENSE_CELL_W,
        cell_h=DENSE_CELL_H,
    )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            % (DENSE_PANEL_WIDTH, DENSE_PANEL_HEIGHT, DENSE_PANEL_WIDTH, DENSE_PANEL_HEIGHT),
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            group,
            "</svg>",
            "",
        ]
    )


def build_dense_composite_svg(
    rows_by_panel: Mapping[str, Sequence[Mapping[str, Any]]],
    panel_configs: Sequence[Mapping[str, Any]],
) -> str:
    if len(panel_configs) != 12 or set(rows_by_panel) != {
        str(item["panel"]) for item in panel_configs
    }:
        raise ValueError("complete dense Figure 3 requires exactly 12 panels")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (
            DENSE_COMPOSITE_WIDTH,
            DENSE_COMPOSITE_HEIGHT,
            DENSE_COMPOSITE_WIDTH,
            DENSE_COMPOSITE_HEIGHT,
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<defs><linearGradient id="figure3-success" x1="0" y1="1" x2="0" y2="0">',
    ]
    for value, rgb in COLOR_STOPS:
        lines.append('<stop offset="%.0f%%" stop-color="%s"/>' % (value * 100, _hex_color(rgb)))
    lines.append("</linearGradient></defs>")
    for index, config in enumerate(panel_configs):
        panel = str(config["panel"])
        x = (index % DENSE_COLUMNS) * DENSE_PANEL_WIDTH
        y = (index // DENSE_COLUMNS) * DENSE_PANEL_HEIGHT
        lines.append('<g transform="translate(%d,%d)">' % (x, y))
        lines.append(
            _panel_group(
                rows_by_panel[panel],
                config,
                grid_x=DENSE_GRID_X,
                grid_y=DENSE_GRID_Y,
                cell_w=DENSE_CELL_W,
                cell_h=DENSE_CELL_H,
            )
        )
        lines.append("</g>")
    colorbar_x = DENSE_PANEL_WIDTH * DENSE_COLUMNS + 28
    colorbar_y = DENSE_GRID_Y
    colorbar_h = 300
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
            DENSE_COMPOSITE_WIDTH / 2,
            DENSE_COMPOSITE_HEIGHT - 14,
            "Exploratory wide-axis dense11 heatmaps; yellow cells are frozen predictions",
            size=13,
        )
    )
    lines.extend(["</svg>", ""])
    return "\n".join(lines)
