import json
import unittest

from figure1a import constants as const
from figure1a.artifacts import sha256_file
from figure1a.config import load_frozen
from figure1a.dense import build_dense_config, dense_grid


class DenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coarse = const.EXPERIMENT_DIR / "results" / "coarse" / \
            "figure1a-20260716T153109Z-99bbe7a-9b10f88e383f" / "recovery-canonical-json-v1"

    def test_grid_uses_fixed_step_and_covers_plateaus(self):
        candidates = json.loads((self.coarse / "dense_boundary_candidates.json").read_text())
        for curve in candidates["curves"]:
            values, metadata = dense_grid(curve, "transition")
            self.assertTrue(all(
                right - left == metadata["dense_step"] for left, right in zip(values, values[1:])
            ))
            self.assertLessEqual(metadata["target_end_M"], values[-1])
            self.assertLess(metadata["end_alignment_overshoot"], metadata["dense_step"])

    def test_transition_manifest_is_smaller_than_literal_extrema(self):
        frozen, frozen_sha256 = load_frozen(const.DEFAULT_FROZEN_PATH)
        engine = const.EXPERIMENT_DIR / "build" / "figure1a_engine"
        transition = build_dense_config(
            self.coarse, frozen, frozen_sha256, sha256_file(engine), "transition"
        )
        literal = build_dense_config(
            self.coarse, frozen, frozen_sha256, sha256_file(engine), "literal_extrema"
        )
        self.assertEqual(307, transition["point_count"])
        self.assertGreater(literal["point_count"], 2000)
        self.assertEqual(transition["point_count"] * 100, transition["logical_point_trials"])


if __name__ == "__main__":
    unittest.main()
