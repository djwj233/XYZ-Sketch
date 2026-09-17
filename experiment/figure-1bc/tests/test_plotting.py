import unittest

from figure1bc import constants as const
from figure1bc.plotting import build_heatmap_svg


class PlottingTests(unittest.TestCase):
    def test_heatmap_contains_complete_base_grid_and_sparse_prediction(self):
        rows = []
        for a_units in const.HOLDOUT_A_UNITS:
            for z in const.HOLDOUT_Z:
                rows.append(
                    {
                        "d": 3000,
                        "M": 596,
                        "a": a_units / 1000.0,
                        "z": z,
                        "success_rate": (a_units + z) % 101 / 100.0,
                        "is_frozen_prediction": False,
                    }
                )
        rows.append(
            {
                "d": 3000,
                "M": 596,
                "a": 0.7243668166820519,
                "z": 3,
                "success_rate": 0.98,
                "is_frozen_prediction": True,
            }
        )
        svg = build_heatmap_svg(rows, figure="figure1b", label="sealed holdout, scale 1")
        self.assertIn("d = 3,000, M = 596, k = 2, ell = 6", svg)
        self.assertIn("0.724", svg)
        self.assertIn('stroke="#ffd400"', svg)
        self.assertIn("0.98", svg)
        self.assertEqual(68, svg.count("<rect x="))


if __name__ == "__main__":
    unittest.main()
