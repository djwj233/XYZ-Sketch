import hashlib
import unittest

from figure2 import constants as const
from figure2.config import (
    actual_external_cells,
    candidate_budget,
    coarse_candidates,
    derive_seed,
    possible_fine_candidates,
    rounded_resource,
)


class ConfigTests(unittest.TestCase):
    def test_seed_literal(self):
        expected = int.from_bytes(
            hashlib.sha256(b"figure2|114514|resource_discovery|100|7|identity").digest()[:8], "big"
        )
        self.assertEqual(expected, derive_seed("resource_discovery", 100, 7, "identity"))

    def test_rounding_and_external_cells(self):
        self.assertEqual(33, rounded_resource(333, 100))
        self.assertEqual(4, actual_external_cells(2))
        self.assertEqual(228, actual_external_cells(150))

    def test_candidate_counts_and_budget(self):
        self.assertEqual(16, len(coarse_candidates("xyz", 1000)))
        self.assertEqual(21, len(coarse_candidates("external_iblt", 1000)))
        self.assertEqual(23, len(coarse_candidates("project_iblt", 1000)))
        budget = candidate_budget()
        self.assertEqual(list(const.DIFFERENCES), budget["d_values"])
        for algorithm in budget["algorithms"]:
            self.assertLessEqual(
                algorithm["global_maximum_updates"], algorithm["protocol_update_bound"]
            )

    def test_fine_resources_are_globally_distinct_from_coarse(self):
        for algorithm in const.RATIO_GRIDS:
            for d in (100, 300, 1000):
                coarse = coarse_candidates(algorithm, d)
                coarse_ids = {
                    row["actual_cells"] if algorithm == "external_iblt" else row["resource"]
                    for row in coarse
                }
                for interval in possible_fine_candidates(algorithm, d):
                    fine_ids = [
                        row["actual_cells"] if algorithm == "external_iblt" else row["resource"]
                        for row in interval["candidates"]
                    ]
                    self.assertFalse(coarse_ids & set(fine_ids))
                    self.assertEqual(len(fine_ids), len(set(fine_ids)))

    def test_external_iblt_keeps_smallest_expected_value_for_actual_cells(self):
        row = next(
            candidate for candidate in coarse_candidates("external_iblt", 100)
            if candidate["actual_cells"] == 84
        )
        self.assertEqual(54, row["resource"])
        self.assertEqual(535, row["expected_ratio_units"])
        self.assertEqual(535, row["ratio_units"])
        self.assertEqual(550, row["grid_ratio_units"])
        self.assertFalse(any(
            candidate["actual_cells"] == 84
            for interval in possible_fine_candidates("external_iblt", 100)
            for candidate in interval["candidates"]
        ))


if __name__ == "__main__":
    unittest.main()
