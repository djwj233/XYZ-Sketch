import unittest

from figure1bc.simulator import (
    PlacementGeometry,
    generate_trial_words,
    peel_supports,
    place_edge,
    placement_word,
)


class SimulatorTests(unittest.TestCase):
    def test_audited_placement_golden_fixture(self):
        geometry = PlacementGeometry.create(10, 0.2, 1)
        self.assertEqual(5, geometry.range_length)
        self.assertEqual(6, geometry.naive_base_range)
        self.assertEqual(7, geometry.circular_base_range)
        self.assertEqual((4,), place_edge((8, 3, 8), geometry))
        self.assertEqual((4, 5), place_edge((8, 3, 4), geometry))

    def test_seed_words_and_stream_are_fixed(self):
        arguments = (114514, "calibration_coarse", 12, 20, 0, 0)
        self.assertEqual(1899902350, placement_word(*arguments, "anchor_word"))
        self.assertEqual(3377961282, placement_word(*arguments, "offset_word_1"))
        self.assertEqual(2533198725, placement_word(*arguments, "offset_word_2"))
        trial = generate_trial_words(114514, "calibration_coarse", 12, 20, 0)
        self.assertEqual(
            "b6402b5e704035b9351e7a6c0635d6ab5ae168f6f3d1ec30516ae69ac07e5b88",
            trial.stream_sha256,
        )

    def test_peeling_success_and_nonpeelable_core(self):
        success = peel_supports(3, ((0, 1), (1, 2)))
        self.assertTrue(success.success)
        self.assertEqual(0, success.residual_edges)

        failure = peel_supports(2, tuple((0, 1) for _ in range(7)))
        self.assertFalse(failure.success)
        self.assertEqual(7, failure.residual_edges)

    def test_support_validation_rejects_duplicates(self):
        with self.assertRaises(ValueError):
            peel_supports(2, ((0, 0),))


if __name__ == "__main__":
    unittest.main()

