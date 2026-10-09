"""Unexpected process failures must fail the run; recorded timeouts remain data."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_measurements


class RunnerFailureTests(unittest.TestCase):
    def check_run(self, executable, arguments, timeout, expected=None, raises=True):
        # Keep test artifacts for inspection instead of deleting directories.
        root = Path(tempfile.mkdtemp(prefix='xyz-runner-check-'))
        (root / 'scripts/jobs').mkdir(parents=True)
        (root / 'scripts/inputs.json').write_text(json.dumps({'input': {'N': 200}}))
        job = {'id': 0, 'engine': 'test', 'd': 100, 'trial': 0,
               'dataset': 'input', 'args': arguments, 'timeout': timeout}
        if expected:
            job['expected_paper'] = expected
        (root / 'scripts/jobs/test.jsonl').write_text(json.dumps(job) + '\n')
        output = root / 'output'
        output.mkdir()
        args = argparse.Namespace(d=None, method=None, kind=None, limit=None,
                                  dry_run=False, smoke=False, workers=1,
                                  cpu=min(os.sched_getaffinity(0)), data_root=root)
        with patch.object(run_measurements, 'ROOT', root), \
                patch.object(run_measurements, 'build', return_value=executable), \
                patch.object(run_measurements, 'dataset', return_value=root / 'input'), \
                contextlib.redirect_stdout(io.StringIO()):
            if raises:
                with self.assertRaises(RuntimeError):
                    run_measurements.run('test', args, output)
            else:
                run_measurements.run('test', args, output)
        validation = json.loads((output / 'validation.json').read_text())
        self.assertEqual(validation['validation_failures'], int(raises))
        self.assertTrue((output / 'records/000000.json').exists())
        return validation

    def test_process_error(self):
        self.check_run('/bin/false', [], 10)

    def test_empty_output(self):
        self.check_run('/bin/true', [], 10)

    def test_unexpected_timeout(self):
        self.check_run('/bin/sleep', ['1'], 0.05)

    def test_recorded_timeout(self):
        result = self.check_run('/bin/sleep', ['1'], 0.05,
                                {'failure_reason': 'timeout'}, raises=False)
        self.assertEqual(result['expected_timeouts'], 1)


if __name__ == '__main__':
    unittest.main()
