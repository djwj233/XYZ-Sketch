import unittest

from figure2 import constants as const
from figure2.correction import corrected_payload, migrate_points


class CorrectionTests(unittest.TestCase):
    def test_payload_rule_keeps_only_upstream_cpisync_control(self):
        self.assertEqual((0.0, 3000.0), corrected_payload("minisketch", 3000.0))
        self.assertEqual((328.0, 3360.0), corrected_payload("cpisync", 3032.0))

    def test_migration_reaccounts_confirmed_points_and_clears_old_timing(self):
        points = []
        operating = []
        for d in const.DIFFERENCES:
            for algorithm in const.ALGORITHMS:
                confirmed = not (algorithm == "minisketch" and d == 10_000)
                points.append({
                    "algorithm": algorithm,
                    "d": d,
                    "status": "confirmed" if confirmed else "timeout",
                    "state_bits": 3000 if confirmed else None,
                    "control_bits": 999 if confirmed else None,
                    "total_payload_bits": 3999 if confirmed else None,
                    "R_w30": 99.0 if confirmed else None,
                    "timing_status": "complete",
                    "decode_ns_per_difference_conditional_mean": 1.0,
                })
                operating.append({
                    "algorithm": algorithm, "d": d, "resource": d,
                    "candidate_id": "selected", "status": "selected",
                })
        migrated = migrate_points({"points": points}, operating)
        mini = next(row for row in migrated if row["algorithm"] == "minisketch" and row["d"] == 100)
        self.assertEqual(0, mini["control_bits"])
        self.assertEqual(3000, mini["total_payload_bits"])
        self.assertEqual(1.0, mini["R_w30"])
        self.assertNotIn("decode_ns_per_difference_conditional_mean", mini)
        cpisync = next(row for row in migrated if row["algorithm"] == "cpisync" and row["d"] == 100)
        self.assertEqual(328, cpisync["control_bits"])
        self.assertEqual(3328, cpisync["total_payload_bits"])
        missing = next(row for row in migrated if row["algorithm"] == "minisketch" and row["d"] == 10_000)
        self.assertIsNone(missing["total_payload_bits"])
        self.assertEqual("not_run_not_confirmed", missing["timing_status"])


if __name__ == "__main__":
    unittest.main()
