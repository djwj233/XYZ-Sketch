import unittest
from pathlib import Path

from figure1bc.engine import CppEngine
from figure1bc.evaluation import evaluate_point
from figure1bc.evaluation import classify_point
from figure1bc.model import CalibrationCandidate
from figure1bc.threshold import load_threshold


ENGINE = Path(__file__).resolve().parent.parent / "build" / "figure1bc_engine"


@unittest.skipUnless(ENGINE.exists(), "C++ engine has not been built")
class EngineEquivalenceTests(unittest.TestCase):
    def test_global_one_excludes_only_invalid_candidates(self):
        threshold = load_threshold()
        legal = CalibrationCandidate(100, 650).placement(20, threshold)
        invalid = CalibrationCandidate(100, 150).placement(20, threshold)
        self.assertEqual(
            "global_one",
            classify_point(
                (legal, invalid),
                {legal.candidate_id: 100, invalid.candidate_id: 0},
                100,
            ),
        )
        self.assertEqual(
            "global_zero",
            classify_point(
                (legal, invalid),
                {legal.candidate_id: 0, invalid.candidate_id: 0},
                100,
            ),
        )

    def test_cpp_audited_placement_golden_fixture(self):
        engine = CppEngine(ENGINE)
        self.assertEqual((5, 6, 7, (4,)), engine.place_fixture(10, 0.2, 1, (8, 3, 8)))
        self.assertEqual((5, 6, 7, (4, 5)), engine.place_fixture(10, 0.2, 1, (8, 3, 4)))

    def test_cpp_matches_independent_python_reference(self):
        threshold = load_threshold()
        specs = (
            CalibrationCandidate(100, 650).placement(20, threshold),
            CalibrationCandidate(125, 650).placement(20, threshold),
            CalibrationCandidate(100, 150).placement(20, threshold),
        )
        arguments = {
            "run_id": "golden",
            "stage": "smoke",
            "domain": "calibration_coarse",
            "d": 12,
            "M": 20,
            "specs": specs,
            "trials": 5,
            "threshold_sha256": threshold.sha256,
            "m_grid_phase": "golden",
        }
        reference = evaluate_point(**arguments)
        accelerated = evaluate_point(**arguments, engine=CppEngine(ENGINE))
        self.assertEqual(reference, accelerated)
        self.assertEqual(10, len(reference.trial_rows))
        shared = [row for row in reference.group_rows if row["status"] == "ok"]
        self.assertTrue(all(len(row["candidate_ids"]) == 2 for row in shared))

    def test_invalid_candidates_share_one_raw_failure_row(self):
        threshold = load_threshold()
        specs = (
            CalibrationCandidate(100, 150).placement(20, threshold),
            CalibrationCandidate(125, 150).placement(20, threshold),
        )
        result = evaluate_point(
            run_id="invalid-golden",
            stage="smoke",
            domain="calibration_coarse",
            d=12,
            M=20,
            specs=specs,
            trials=3,
            threshold_sha256=threshold.sha256,
            m_grid_phase="golden",
            engine=CppEngine(ENGINE),
        )
        self.assertEqual(3, len(result.trial_rows))
        self.assertEqual(1, len(result.group_rows))
        self.assertEqual(2, len(result.group_rows[0]["candidate_ids"]))
        self.assertTrue(all(row["candidate_count"] == 2 for row in result.trial_rows))
        self.assertTrue(all(row["status"] == "invalid_placement" for row in result.trial_rows))

    def test_domains_produce_independent_streams(self):
        engine = CppEngine(ENGINE)
        threshold = load_threshold()
        spec = CalibrationCandidate(100, 650).placement(20, threshold)
        coarse = evaluate_point(
            run_id="x",
            stage="x",
            domain="calibration_coarse",
            d=12,
            M=20,
            specs=(spec,),
            trials=1,
            threshold_sha256=threshold.sha256,
            m_grid_phase="x",
            engine=engine,
        )
        fine = evaluate_point(
            run_id="x",
            stage="x",
            domain="calibration_fine",
            d=12,
            M=20,
            specs=(spec,),
            trials=1,
            threshold_sha256=threshold.sha256,
            m_grid_phase="x",
            engine=engine,
        )
        self.assertNotEqual(
            coarse.trial_rows[0]["placement_words_sha256"],
            fine.trial_rows[0]["placement_words_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
