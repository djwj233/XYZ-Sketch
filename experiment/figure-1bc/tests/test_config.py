import unittest

from figure1bc import constants as const
from figure1bc.config import (
    CalibrationConfig,
    broad_fine_candidate_grid,
    coarse_candidate_grid,
    dense_rho_grid,
    fine_axis,
    fine_candidate_grid,
    next_upper_band,
    round_ratio_times_d,
)


class ConfigTests(unittest.TestCase):
    def test_audited_candidate_grids_are_fixed_point(self):
        coarse = coarse_candidate_grid()
        self.assertEqual(21 * 21, len(coarse))
        self.assertEqual((100, 150), coarse[0])
        self.assertEqual((600, 650), coarse[-1])
        self.assertEqual(tuple(range(225, 326, 5)), fine_axis(275))
        self.assertEqual(441, len(fine_candidate_grid(275, 400)))
        broad = broad_fine_candidate_grid()
        self.assertEqual(48_200, len(broad))
        self.assertEqual((5, 5), broad[0])
        self.assertEqual((1205, 1000), broad[-1])

    def test_ratio_rounding_is_integer_half_up(self):
        self.assertEqual(596, round_ratio_times_d(198_667, 3000))
        self.assertEqual(1, round_ratio_times_d(5_000, 100))
        self.assertEqual(2, round_ratio_times_d(15_000, 100))

    def test_dense_grid_includes_non_step_endpoint(self):
        values = dense_rho_grid(80_000, 86_000)
        self.assertEqual((80_000, 82_500, 85_000, 86_000), values)

    def test_upper_expansion_is_banded_and_capped(self):
        self.assertEqual(tuple(range(460_000, 550_001, 10_000)), next_upper_band(450_000))
        self.assertEqual((1_450_000,), next_upper_band(1_440_000))
        self.assertEqual((), next_upper_band(1_450_000))

    def test_formal_config_contains_only_training_scales(self):
        config = CalibrationConfig()
        config.validate_formal()
        self.assertTrue(all(d < 3000 for d in config.training_d))
        self.assertEqual(const.TRAINING_D, config.training_d)

    def test_maximum_c_grid_point_is_legal_and_next_step_is_not(self):
        from figure1bc.threshold import load_threshold

        ratio = load_threshold().ratio
        self.assertLess(const.MAX_LEGAL_C_UNITS / 1000.0 * ratio, 1.0)
        self.assertGreaterEqual(
            (const.MAX_LEGAL_C_UNITS + const.FINE_STEP_UNITS) / 1000.0 * ratio,
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
