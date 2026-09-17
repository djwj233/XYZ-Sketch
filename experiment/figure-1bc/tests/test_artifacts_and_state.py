import json
import math
import tempfile
import unittest
from pathlib import Path

from figure1bc.artifacts import RunDirectory, canonical_json_bytes
from figure1bc.calibration import Bracket, MPoint, identify_bracket
from figure1bc.holdout import holdout_specs
from figure1bc.threshold import load_threshold


class ArtifactAndStateTests(unittest.TestCase):
    def test_canonical_json_is_sorted_and_rejects_nonfinite(self):
        self.assertEqual(b'{"a":1,"b":2}\n', canonical_json_bytes({"b": 2, "a": 1}))
        with self.assertRaises(ValueError):
            canonical_json_bytes({"value": math.nan})

    def test_terminal_run_cannot_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run"
            run = RunDirectory.create(path, "created", {"run_id": "test"})
            run.transition("created", "failed")
            with self.assertRaises(RuntimeError):
                RunDirectory.open_for_resume(path)

    def test_bracket_uses_contiguous_prefix_and_suffix(self):
        points = {}
        for M, classification, rho in (
            (10, "global_zero", 100_000),
            (20, "global_zero", 200_000),
            (30, "transition", 300_000),
            (40, "global_one", 400_000),
            (50, "global_one", 500_000),
        ):
            points[M] = MPoint(
                d=100,
                M=M,
                requested_rho_units={rho},
                phases={"test"},
                classification=classification,
            )
        bracket = identify_bracket(points)
        self.assertEqual(Bracket(100, 20, 40, 200_000, 400_000), bracket)
        points[10].classification = "transition"
        self.assertIsNone(identify_bracket(points))

    def test_holdout_grid_adds_exact_prediction_once(self):
        frozen = {"C_cal": 0.276, "gamma_cal": 0.4, "a_cal": 0.228486}
        specs = holdout_specs(frozen, 596)
        self.assertEqual(67, len(specs))
        self.assertEqual(1, sum(spec.is_frozen_prediction for spec in specs))
        self.assertEqual(66, sum(spec.C is None for spec in specs))

    def test_threshold_artifact_is_the_audited_file(self):
        threshold = load_threshold()
        self.assertAlmostEqual(4.93764536242195, threshold.c_peel)
        self.assertAlmostEqual(5.964436239513146, threshold.c_orient)


if __name__ == "__main__":
    unittest.main()

