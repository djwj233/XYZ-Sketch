import unittest

from figure1bc.relative import relative_score_candidates
from figure1bc.statistics import wilson_interval


class StatisticsTests(unittest.TestCase):
    def test_wilson_interval_endpoints(self):
        low0, high0 = wilson_interval(0, 100)
        low1, high1 = wilson_interval(100, 100)
        self.assertEqual(0.0, low0)
        self.assertAlmostEqual(0.03699349820698568, high0)
        self.assertAlmostEqual(0.9630065017930143, low1)
        self.assertEqual(1.0, high1)

    def test_relative_score_uses_fixed_paired_points_and_equal_d_weight(self):
        rows = []
        candidates = (
            ("C0100-G0200", 0.1, 0.2, ((100, 10, 90), (100, 20, 80), (200, 20, 70))),
            ("C0125-G0200", 0.125, 0.2, ((100, 10, 80), (100, 20, 90), (200, 20, 90))),
        )
        for candidate_id, C, gamma, observations in candidates:
            for d, M, successes in observations:
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "C": C,
                        "gamma": gamma,
                        "d": d,
                        "M": M,
                        "successes": successes,
                        "trials": 100,
                    }
                )
        winner, scores = relative_score_candidates(rows, training_d=(100, 200))
        self.assertEqual("C0125-G0200", winner.candidate_id)
        self.assertEqual(2, len(scores))
        self.assertEqual(1, scores[0]["rank"])
        self.assertTrue(scores[0]["is_selected"])

    def test_uninformative_fixed_points_are_excluded(self):
        rows = []
        for candidate_id, C, successes in (
            ("C0100-G0200", 0.1, (100, 80)),
            ("C0125-G0200", 0.125, (100, 90)),
        ):
            for M, value in zip((10, 20), successes):
                rows.append(
                    {
                        "candidate_id": candidate_id,
                        "C": C,
                        "gamma": 0.2,
                        "d": 100,
                        "M": M,
                        "successes": value,
                        "trials": 100,
                    }
                )
        winner, scores = relative_score_candidates(rows, training_d=(100,))
        self.assertEqual("C0125-G0200", winner.candidate_id)
        self.assertEqual(1, winner.informative_points)


if __name__ == "__main__":
    unittest.main()

