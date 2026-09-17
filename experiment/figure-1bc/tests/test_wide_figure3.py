import unittest

from figure1bc.figure3 import CENTER_COLUMN, CENTER_ROW_ASCENDING, FIGURE3_PANELS
from figure1bc.figure3_wide import QUALITY_RULE, panel_quality, wide_axes, wide_panel_specs
from figure1bc.figure3_dense_plotting import build_dense_composite_svg, build_dense_panel_svg
from figure1bc.figure3_square_plotting import build_square_composite_svg, build_square_panel_svg


FROZEN = {
    "C_cal": 0.875,
    "gamma_cal": 0.9,
    "a_cal": 0.7243668166820519,
}


class WideFigure3Tests(unittest.TestCase):
    def test_rounds_are_centered_and_second_round_is_wider(self):
        a_one, z_one = wide_axes(FROZEN["a_cal"], 2, 1)
        a_two, z_two = wide_axes(FROZEN["a_cal"], 2, 2)
        self.assertEqual(FROZEN["a_cal"], a_one[CENTER_COLUMN])
        self.assertEqual(FROZEN["a_cal"], a_two[CENTER_COLUMN])
        self.assertEqual(2, z_one[CENTER_ROW_ASCENDING])
        self.assertEqual(2, z_two[CENTER_ROW_ASCENDING])
        self.assertEqual((0, 1, 2, 5, 12), z_one)
        self.assertEqual((0, 1, 2, 8, 24), z_two)
        self.assertLess(a_two[0], a_one[0])
        self.assertGreater(a_two[-1], a_one[-1])

    def test_dense_profile_has_same_range_and_eleven_columns(self):
        a_wide, z_wide = wide_axes(FROZEN["a_cal"], 5, 1)
        a_dense, z_dense = wide_axes(FROZEN["a_cal"], 5, 3)
        self.assertEqual(11, len(a_dense))
        self.assertAlmostEqual(a_wide[0], a_dense[0], places=15)
        self.assertAlmostEqual(a_wide[-1], a_dense[-1], places=15)
        self.assertEqual(z_wide, z_dense)
        self.assertEqual(FROZEN["a_cal"], a_dense[5])

    def test_square_profile_has_seven_legal_z_rows(self):
        a_values, z_values = wide_axes(FROZEN["a_cal"], 2, 4)
        self.assertEqual(7, len(a_values))
        self.assertEqual((0, 1, 2, 3, 5, 8, 12), z_values)
        self.assertEqual(FROZEN["a_cal"], a_values[3])
        self.assertEqual(2, z_values[2])

    def test_every_panel_has_exact_frozen_center(self):
        for expansion_round in (1, 2):
            for panel, _d, M, _domain in FIGURE3_PANELS:
                specs, a_values, z_values = wide_panel_specs(
                    panel, FROZEN, M, expansion_round
                )
                selected = [spec for spec in specs if spec.is_frozen_prediction]
                self.assertEqual(35, len(specs))
                self.assertEqual(1, len(selected))
                self.assertEqual(a_values[CENTER_COLUMN], selected[0].a)
                self.assertEqual(z_values[CENTER_ROW_ASCENDING], selected[0].z)

    def test_quality_rule_requires_advantage_and_contrast(self):
        rows = [
            {
                "success_rate": 0.30 if index < 20 else 0.70,
                "is_frozen_prediction": False,
            }
            for index in range(34)
        ]
        rows.append({"success_rate": 0.95, "is_frozen_prediction": True})
        result = panel_quality(rows)
        self.assertTrue(result["passes"])
        self.assertGreaterEqual(
            result["low_cell_fraction"], QUALITY_RULE["minimum_low_cell_fraction"]
        )
        flat = [
            {"success_rate": 1.0, "is_frozen_prediction": index == 17}
            for index in range(35)
        ]
        flat_result = panel_quality(flat)
        self.assertFalse(flat_result["passes"])
        self.assertFalse(flat_result["checks"]["low_cell_fraction"])
        self.assertFalse(flat_result["checks"]["selected_minus_median"])

    def test_dense_renderer_contains_twelve_complete_5x11_panels(self):
        configs = []
        rows_by_panel = {}
        for panel, d, M, domain in FIGURE3_PANELS:
            specs, a_values, z_values = wide_panel_specs(panel, FROZEN, M, 3)
            configs.append(
                {
                    "panel": panel,
                    "d": d,
                    "M": M,
                    "engine_seed_domain": domain,
                    "a_values": list(a_values),
                    "z_values_ascending": list(z_values),
                    "center_column_zero_based": 5,
                    "center_row_ascending_zero_based": 2,
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
        panel_svg = build_dense_panel_svg(rows_by_panel["a"], configs[0])
        self.assertEqual(55, panel_svg.count('data-cell="true"'))
        composite = build_dense_composite_svg(rows_by_panel, configs)
        self.assertEqual(12 * 55, composite.count('data-cell="true"'))
        self.assertEqual(12, composite.count('stroke="#ffd400"'))

    def test_square_renderer_contains_twelve_complete_7x7_panels(self):
        configs = []
        rows_by_panel = {}
        for panel, d, M, domain in FIGURE3_PANELS:
            specs, a_values, z_values = wide_panel_specs(panel, FROZEN, M, 4)
            configs.append(
                {
                    "panel": panel,
                    "d": d,
                    "M": M,
                    "engine_seed_domain": domain,
                    "a_values": list(a_values),
                    "z_values_ascending": list(z_values),
                    "center_column_zero_based": 3,
                    "center_row_ascending_zero_based": 2,
                    "vertical_center_required": False,
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
        panel_svg = build_square_panel_svg(rows_by_panel["a"], configs[0])
        self.assertEqual(49, panel_svg.count('data-cell="true"'))
        composite = build_square_composite_svg(rows_by_panel, configs)
        self.assertEqual(12 * 49, composite.count('data-cell="true"'))
        self.assertEqual(12, composite.count('stroke="#ffd400"'))


if __name__ == "__main__":
    unittest.main()
