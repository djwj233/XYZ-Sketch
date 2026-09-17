import unittest

from figure2.config import profile_manifest
from figure2.engine import Figure2Engines
from figure2.validation import golden_results, smoke_results


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engines = Figure2Engines()

    def test_wire_goldens(self):
        result = golden_results(self.engines)
        self.assertEqual("passed", result["status"])
        self.assertEqual(2, result["tests"]["minisketch"]["implementation"])

    def test_shared_dataset_smoke(self):
        result = smoke_results(self.engines, profile_manifest())
        self.assertEqual(6, len(result["algorithms"]))
        self.assertTrue(all(row["success"] for row in result["algorithms"]))


if __name__ == "__main__":
    unittest.main()
