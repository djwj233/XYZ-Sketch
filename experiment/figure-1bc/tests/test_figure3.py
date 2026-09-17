import tempfile
import unittest
from pathlib import Path

from figure1bc.figure3 import (
    CENTER_COLUMN,
    CENTER_ROW_ASCENDING,
    FIGURE3_PANELS,
    centered_axes,
    figure3_config,
    panel_specs,
)
from figure1bc.figure3_plotting import build_composite_svg, build_panel_svg, validate_panel_rows


FROZEN = {
    "C_cal": 0.875,
    "gamma_cal": 0.9,
    "a_cal": 0.7243668166820519,
}


class Figure3Tests(unittest.TestCase):
    def test_centered_axes_keep_prediction_at_geometric_center(self):
        a_values, z_values = centered_axes(FROZEN["a_cal"], 2)
        self.assertEqual(7, len(a_values))
        self.assertEqual(5, len(z_values))
        self.assertEqual(FROZEN["a_cal"], a_values[CENTER_COLUMN])
        self.assertEqual(2, z_values[CENTER_ROW_ASCENDING])
        self.assertEqual((0, 1, 2, 3, 4), z_values)

    def test_all_twelve_panels_have_one_selected_center(self):
        for panel, _d, M, _domain in FIGURE3_PANELS:
            specs, a_values, z_values = panel_specs(panel, FROZEN, M)
            selected = [spec for spec in specs if spec.is_frozen_prediction]
            self.assertEqual(35, len(specs))
            self.assertEqual(1, len(selected))
            self.assertEqual(a_values[CENTER_COLUMN], selected[0].a)
            self.assertEqual(z_values[CENTER_ROW_ASCENDING], selected[0].z)

    def test_renderer_refuses_noncenter_selected_cell(self):
        specs, a_values, z_values = panel_specs("e", FROZEN, 596)
        config = {
            "panel": "e",
            "d": 3000,
            "M": 596,
            "a_values": list(a_values),
            "z_values_ascending": list(z_values),
            "center_column_zero_based": CENTER_COLUMN,
            "center_row_ascending_zero_based": CENTER_ROW_ASCENDING,
        }
        rows = []
        for spec in specs:
            rows.append(
                {
                    "d": 3000,
                    "M": 596,
                    "a": spec.a,
                    "z": spec.z,
                    "success_rate": 0.5,
                    "is_frozen_prediction": spec.is_frozen_prediction,
                }
            )
        selected = next(row for row in rows if row["is_frozen_prediction"])
        selected["is_frozen_prediction"] = False
        rows[0]["is_frozen_prediction"] = True
        with self.assertRaisesRegex(ValueError, "center"):
            validate_panel_rows(rows, config)

    def test_panel_and_composite_contain_complete_measured_grids(self):
        configs = []
        rows_by_panel = {}
        for panel, d, M, domain in FIGURE3_PANELS:
            specs, a_values, z_values = panel_specs(panel, FROZEN, M)
            configs.append(
                {
                    "panel": panel,
                    "d": d,
                    "M": M,
                    "engine_seed_domain": domain,
                    "a_values": list(a_values),
                    "z_values_ascending": list(z_values),
                    "center_column_zero_based": CENTER_COLUMN,
                    "center_row_ascending_zero_based": CENTER_ROW_ASCENDING,
                }
            )
            rows_by_panel[panel] = [
                {
                    "d": d,
                    "M": M,
                    "a": spec.a,
                    "z": spec.z,
                    "success_rate": 0.5,
                    "is_frozen_prediction": spec.is_frozen_prediction,
                }
                for spec in specs
            ]
        panel_svg = build_panel_svg(rows_by_panel["a"], configs[0])
        self.assertEqual(35, panel_svg.count('data-cell="true"'))
        self.assertEqual(1, panel_svg.count('stroke="#ffd400"'))
        composite = build_composite_svg(rows_by_panel, configs)
        self.assertEqual(12 * 35, composite.count('data-cell="true"'))
        self.assertEqual(12, composite.count('stroke="#ffd400"'))


if __name__ == "__main__":
    unittest.main()
