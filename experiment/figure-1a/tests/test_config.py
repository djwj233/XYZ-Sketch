import hashlib
import math
import unittest

from figure1a import constants as const
from figure1a.config import (
    PanelParameters,
    derive_seed,
    extended_m_values,
    initial_m_values,
    load_frozen,
    load_thresholds,
)


class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen, _ = load_frozen(const.DEFAULT_FROZEN_PATH)
        cls.thresholds = load_thresholds()

    def test_seed_uses_canonical_literal(self):
        material = b"figure1a|114514|coarse|2|3|7|dataset_identity"
        expected = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
        self.assertEqual(expected, derive_seed("coarse", 2, 3, 7, "dataset_identity"))

    def test_frozen_centers(self):
        expected = {
            (2, 3): {"iid": 3884, "naive": 3724, "circular": 3606},
            (2, 6): {"iid": 2026, "naive": 1830, "circular": 1758},
            (3, 4): {"iid": 3641, "naive": 2695, "circular": 2634},
        }
        for panel, centers in expected.items():
            parameters = PanelParameters.create(*panel, self.thresholds, self.frozen)
            self.assertAlmostEqual(
                parameters.circular_a,
                parameters.C * parameters.c_peel / parameters.c_orient,
            )
            for mode, center in centers.items():
                self.assertEqual(center, parameters.center(mode))
                values = initial_m_values(parameters, mode)
                self.assertIn(center, values)
                self.assertTrue(all((value - center) % const.COARSE_STEP[panel[1]] == 0 for value in values))

    def test_extensions_stay_aligned_and_disjoint(self):
        parameters = PanelParameters.create(2, 6, self.thresholds, self.frozen)
        initial = set(initial_m_values(parameters, "circular"))
        lower = set(extended_m_values(parameters, "circular", 1, "lower"))
        upper = set(extended_m_values(parameters, "circular", 1, "upper"))
        self.assertFalse(initial & lower)
        self.assertFalse(initial & upper)
        self.assertFalse(lower & upper)


if __name__ == "__main__":
    unittest.main()
