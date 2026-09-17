import unittest

from figure2.statistics import percentile_bootstrap, wilson


class StatisticsTests(unittest.TestCase):
    def test_wilson_boundaries(self):
        low, high = wilson(90, 100)
        self.assertLess(low, 0.9)
        self.assertGreater(high, 0.9)

    def test_bootstrap_is_deterministic(self):
        values = list(range(30))
        self.assertEqual(
            percentile_bootstrap(values, seed_material="x", repetitions=100),
            percentile_bootstrap(values, seed_material="x", repetitions=100),
        )

    def test_mean_bootstrap_is_deterministic(self):
        values = list(range(30))
        self.assertEqual(
            percentile_bootstrap(
                values, seed_material="mean", repetitions=100, estimator="mean"
            ),
            percentile_bootstrap(
                values, seed_material="mean", repetitions=100, estimator="mean"
            ),
        )

    def test_bootstrap_rejects_unknown_estimator(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            percentile_bootstrap([1.0], seed_material="x", estimator="mode")


if __name__ == "__main__":
    unittest.main()
