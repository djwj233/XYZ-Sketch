"""Square-canvas renderer for the legal 7x7 Figure 3 profile."""

from typing import Any, Mapping, Sequence

from .figure3_plotting import _panel_group, _text
from .plotting import COLOR_STOPS, _hex_color


SQUARE_PANEL_WIDTH = 500
SQUARE_PANEL_HEIGHT = 420
SQUARE_COLUMNS = 3
SQUARE_ROWS = 4
SQUARE_COMPOSITE_WIDTH = SQUARE_PANEL_WIDTH * SQUARE_COLUMNS + 90
SQUARE_COMPOSITE_HEIGHT = SQUARE_PANEL_HEIGHT * SQUARE_ROWS + 45
SQUARE_GRID_X = 70
SQUARE_GRID_Y = 76
SQUARE_CELL = 42


def build_square_panel_svg(
    rows: Sequence[Mapping[str, Any]],
    panel_config: Mapping[str, Any],
) -> str:
    group = _panel_group(
        rows,
        panel_config,
        grid_x=SQUARE_GRID_X,
        grid_y=SQUARE_GRID_Y,
        cell_w=SQUARE_CELL,
        cell_h=SQUARE_CELL,
    )
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
            % (SQUARE_PANEL_WIDTH, SQUARE_PANEL_HEIGHT, SQUARE_PANEL_WIDTH, SQUARE_PANEL_HEIGHT),
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            group,
            "</svg>",
            "",
        ]
    )


def build_square_composite_svg(
    rows_by_panel: Mapping[str, Sequence[Mapping[str, Any]]],
    panel_configs: Sequence[Mapping[str, Any]],
) -> str:
    if len(panel_configs) != 12 or set(rows_by_panel) != {
        str(item["panel"]) for item in panel_configs
    }:
        raise ValueError("complete square Figure 3 requires exactly 12 panels")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        % (
            SQUARE_COMPOSITE_WIDTH,
            SQUARE_COMPOSITE_HEIGHT,
            SQUARE_COMPOSITE_WIDTH,
            SQUARE_COMPOSITE_HEIGHT,
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<defs><linearGradient id="figure3-success" x1="0" y1="1" x2="0" y2="0">',
    ]
    for value, rgb in COLOR_STOPS:
        lines.append('<stop offset="%.0f%%" stop-color="%s"/>' % (value * 100, _hex_color(rgb)))
    lines.append("</linearGradient></defs>")
    for index, config in enumerate(panel_configs):
        panel = str(config["panel"])
        x = (index % SQUARE_COLUMNS) * SQUARE_PANEL_WIDTH
        y = (index // SQUARE_COLUMNS) * SQUARE_PANEL_HEIGHT
        lines.append('<g transform="translate(%d,%d)">' % (x, y))
        lines.append(
            _panel_group(
                rows_by_panel[panel],
                config,
                grid_x=SQUARE_GRID_X,
                grid_y=SQUARE_GRID_Y,
                cell_w=SQUARE_CELL,
                cell_h=SQUARE_CELL,
            )
        )
        lines.append("</g>")
    colorbar_x = SQUARE_PANEL_WIDTH * SQUARE_COLUMNS + 28
    colorbar_y = SQUARE_GRID_Y
    colorbar_h = SQUARE_CELL * 7
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
            SQUARE_COMPOSITE_WIDTH / 2,
            SQUARE_COMPOSITE_HEIGHT - 14,
            "Exploratory legal 7x7 heatmaps; yellow cells are frozen predictions",
            size=13,
        )
    )
    lines.extend(["</svg>", ""])
    return "\n".join(lines)
