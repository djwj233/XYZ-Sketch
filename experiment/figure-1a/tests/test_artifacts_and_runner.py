import json
import tempfile
import unittest
from pathlib import Path

from figure1a import constants as const
from figure1a.artifacts import atomic_write_json, canonical_json_bytes
from figure1a.config import PanelParameters, load_frozen, load_thresholds, make_spec
from figure1a.runner import PointCheckpointStore, aggregate_point


class ArtifactAndRunnerTests(unittest.TestCase):
    def test_canonical_json_rejects_nonfinite(self):
        with self.assertRaises(ValueError):
            canonical_json_bytes({"bad": float("nan")})

    def test_canonical_json_rejects_integer_object_keys(self):
        with self.assertRaises(TypeError):
            canonical_json_bytes({3: 6})

    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x.json"
            atomic_write_json(path, {"b": 2, "a": 1})
            self.assertEqual(b'{"a":1,"b":2}\n', path.read_bytes())

    def test_point_checkpoint_and_aggregate(self):
        frozen, _ = load_frozen(const.DEFAULT_FROZEN_PATH)
        parameters = PanelParameters.create(2, 3, load_thresholds(), frozen)
        spec = make_spec(parameters, "iid", 100)
        with tempfile.TemporaryDirectory() as temporary:
            store = PointCheckpointStore(Path(temporary))
            for index in range(const.COARSE_TRIALS):
                store.add(spec, {
                    "trial_index": index,
                    "success": index < 10,
                    "failure_reason": "success" if index < 10 else "decode_failed",
                    "run_id": "test",
                    "git_commit": "test",
                })
            row = aggregate_point(spec, store.trials(spec))
            self.assertEqual(10, row["successes"])
            self.assertEqual(0.5, row["success_rate"])
            self.assertEqual({"decode_failed": 10}, row["failure_counts"])


if __name__ == "__main__":
    unittest.main()
