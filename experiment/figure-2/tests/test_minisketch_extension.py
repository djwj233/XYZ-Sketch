import unittest

from figure2.minisketch_extension import CANDIDATE_ID, D, deterministic_point


class MiniSketchExtensionTests(unittest.TestCase):
    def test_deterministic_point_replaces_failed_probability_and_timing(self):
        source = {
            "algorithm": "minisketch",
            "d": D,
            "status": "timeout",
            "state_bits": None,
            "timing_status": "not_run_not_confirmed",
        }
        timing = {
            "timing_status": "complete",
            "successful_datasets": 5,
            "attempted_datasets": 5,
        }
        point = deterministic_point(source, timing)
        self.assertEqual("confirmed", point["status"])
        self.assertEqual("deterministic_exact_bound", point["probability_basis"])
        self.assertEqual(CANDIDATE_ID, point["candidate_id"])
        self.assertEqual(300_000, point["state_bits"])
        self.assertEqual(1.0, point["R_w30"])
        self.assertEqual("complete", point["timing_status"])


if __name__ == "__main__":
    unittest.main()
