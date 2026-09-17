#!/usr/bin/env python3

import math
import unittest

from thresholds import compute_threshold, poisson_pmf, poisson_tail


# Appendix Table 3. Each tuple is c_peel/c_orient, rounded to four decimals.
TABLE_3 = {
    1: [
        (0.0000, 0.5000),
        (0.8185, 0.9179),
        (0.7723, 0.9768),
        (0.7018, 0.9924),
        (0.6371, 0.9974),
        (0.5818, 0.9991),
    ],
    2: [
        (1.6755, 1.7940),
        (1.5528, 1.9764),
        (1.3336, 1.9965),
        (1.1578, 1.9994),
        (1.0216, 1.9999),
        (0.9146, 2.0000),
    ],
    3: [
        (2.5747, 2.8775),
        (2.1745, 2.9919),
        (1.8109, 2.9994),
        (1.5457, 3.0000),
        (1.3488, 3.0000),
        (1.1977, 3.0000),
    ],
    4: [
        (3.3996, 3.9215),
        (2.7467, 3.9970),
        (2.2498, 3.9999),
        (1.9022, 4.0000),
        (1.6492, 4.0000),
        (1.4574, 4.0000),
    ],
    5: [
        (4.1827, 4.9478),
        (3.2894, 4.9989),
        (2.6654, 5.0000),
        (2.2395, 5.0000),
        (1.9333, 5.0000),
        (1.7030, 5.0000),
    ],
    6: [
        (4.9376, 5.9644),
        (3.8117, 5.9996),
        (3.0651, 6.0000),
        (2.5635, 6.0000),
        (2.2060, 6.0000),
        (1.9386, 6.0000),
    ],
    7: [
        (5.6721, 6.9754),
        (4.3189, 6.9998),
        (3.4528, 7.0000),
        (2.8776, 7.0000),
        (2.4703, 7.0000),
        (2.1668, 7.0000),
    ],
    8: [
        (6.3905, 7.9828),
        (4.8143, 7.9999),
        (3.8312, 8.0000),
        (3.1840, 8.0000),
        (2.7279, 8.0000),
        (2.3892, 8.0000),
    ],
}


class PoissonTests(unittest.TestCase):
    def test_tail_matches_direct_sum(self) -> None:
        for xi in (0.1, 1.0, 3.5, 10.0):
            for threshold in range(1, 10):
                direct = 1.0 - sum(poisson_pmf(xi, value) for value in range(threshold))
                self.assertAlmostEqual(poisson_tail(xi, threshold), direct, places=13)

    def test_tail_recurrence(self) -> None:
        for xi in (0.25, 2.5, 8.0):
            for threshold in range(1, 8):
                difference = poisson_tail(xi, threshold) - poisson_tail(xi, threshold + 1)
                self.assertAlmostEqual(difference, poisson_pmf(xi, threshold), places=13)


class ThresholdTests(unittest.TestCase):
    def test_entire_appendix_table_3(self) -> None:
        for ell, expected_row in TABLE_3.items():
            for offset, (expected_peel, expected_orient) in enumerate(expected_row):
                k = offset + 2
                with self.subTest(k=k, ell=ell):
                    result = compute_threshold(k, ell)
                    self.assertAlmostEqual(result.c_peel, expected_peel, places=4)
                    self.assertAlmostEqual(result.c_orient, expected_orient, places=4)

    def test_special_case(self) -> None:
        result = compute_threshold(2, 1)
        self.assertEqual(result.c_peel, 0.0)
        self.assertEqual(result.c_orient, 0.5)
        self.assertEqual(result.peel_xi, 0.0)
        self.assertEqual(result.orient_xi, 0.0)

    def test_threshold_invariants(self) -> None:
        for ell in range(1, 9):
            for k in range(2, 8):
                result = compute_threshold(k, ell)
                with self.subTest(k=k, ell=ell):
                    self.assertTrue(math.isfinite(result.c_peel))
                    self.assertTrue(math.isfinite(result.c_orient))
                    self.assertLessEqual(result.c_peel, result.c_orient)
                    self.assertLessEqual(result.c_orient, float(ell) + 1e-10)
                    if (k, ell) != (2, 1):
                        self.assertLess(abs(result.peel_residual), 1e-12)
                        self.assertLess(abs(result.orient_residual), 1e-10)

    def test_principal_operating_points(self) -> None:
        expected = {
            (2, 3): (2.5747013735, 2.8774628058),
            (2, 6): (4.9376453624, 5.9644362395),
            (3, 4): (2.7467258764, 3.9970126256),
        }
        for pair, values in expected.items():
            with self.subTest(pair=pair):
                result = compute_threshold(*pair)
                self.assertAlmostEqual(result.c_peel, values[0], places=9)
                self.assertAlmostEqual(result.c_orient, values[1], places=9)


if __name__ == "__main__":
    unittest.main()
