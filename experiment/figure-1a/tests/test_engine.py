import unittest

from figure1a import constants as const
from figure1a.config import PanelParameters, load_frozen, load_thresholds, make_spec
from figure1a.engine import CppEngine


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = CppEngine(const.EXPERIMENT_DIR / "build" / "figure1a_engine")
        cls.frozen, _ = load_frozen(const.DEFAULT_FROZEN_PATH)
        cls.thresholds = load_thresholds()

    def test_self_test(self):
        result = self.engine.self_test()
        self.assertIn('"residual_equivalence":true', result)
        self.assertIn('"golden_accounting":true', result)

    def test_real_core_smoke_all_panels_and_modes(self):
        for k, ell in const.PANELS:
            parameters = PanelParameters.create(k, ell, self.thresholds, self.frozen)
            specs = [make_spec(parameters, mode, 160) for mode in const.MODES]
            evaluated = self.engine.evaluate(
                phase="smoke-test", k=k, ell=ell, trial_index=0, specs=specs,
                set_size=40, difference=20, workers=3,
            )
            self.assertEqual(8, len(evaluated.dataset))
            for spec in specs:
                row = evaluated.results[spec.config_id]
                self.assertTrue(row["success"])
                self.assertEqual(spec.logical_state_bits, row["logical_state_bits"])
                self.assertEqual(spec.total_payload_bits, row["total_payload_bits"])


if __name__ == "__main__":
    unittest.main()
