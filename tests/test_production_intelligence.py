import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center.production_intelligence import KINDS, MAX_BYTES, analyze_bundle, example
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[1]


class ProductionIntelligenceTests(unittest.TestCase):
    def test_bundle_all_domains_and_identity(self):
        data = example()
        original = copy.deepcopy(data)
        report = analyze_bundle(data)
        self.assertEqual(data, original)
        self.assertEqual(report['missing'], [])
        self.assertEqual([part['kind'] for part in report['reports']], list(KINDS))
        self.assertEqual(report['input_sha256'], spec_digest(data))
        self.assertEqual(report['report_sha256'], spec_digest({key: value for key, value in report.items()
                                                               if key != 'report_sha256'}))
        for part in report['reports']:
            self.assertEqual(part['capture_sha256'], spec_digest(data['captures'][part['kind']]))
        self.assertEqual(report, analyze_bundle(copy.deepcopy(data)))

    def test_subset_reports_missing_never_full_pass(self):
        data = example('frame')
        report = analyze_bundle(data)
        self.assertEqual(report['missing'], [kind for kind in KINDS if kind != 'frame'])
        self.assertIn(report['status'], ('warn', 'fail'))
        self.assertEqual(len(report['reports']), 1)

    def test_unsupported_and_nonfinite_inputs(self):
        for data in (None, [], {}, {'schema_version': True, 'captures': {'frame': {}}},
                     {'schema_version': 1, 'captures': {}}, {'schema_version': 1, 'captures': {'../file': {}}},
                     {'schema_version': 1, 'captures': {'frame': {'number': float('nan')}}},
                     {'schema_version': 1, 'captures': {'frame': {'number': float('inf')}}},
                     {'schema_version': 1, 'captures': {'frame': {}}, 'extra': 0}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                analyze_bundle(data)

    def test_contradictory_producer_rejected(self):
        data = example('frame')
        with patch('command_center.production_intelligence._module') as mock:
            mock.return_value.analyze.return_value = {'schema_version': 1, 'kind': 'frame', 'status': 'pass',
                'checks': [{'id': 'bad', 'label': 'Bad', 'status': 'fail', 'detail': 'Failed'}],
                'metrics': {}, 'advisory': 'Advisory.'}
            with self.assertRaises(ValueError):
                analyze_bundle(data)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'command_center.production_intelligence_cli', *args],
                              cwd=ROOT, capture_output=True, text=True, timeout=20)

    def test_cli_example_and_analyze(self):
        sample = self.run_cli('example', 'frame')
        self.assertEqual(sample.returncode, 0, sample.stderr)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            path.write_text(sample.stdout)
            assessed = self.run_cli('analyze', str(path))
            self.assertEqual(assessed.returncode, 1, assessed.stderr)
            self.assertEqual(json.loads(assessed.stdout), analyze_bundle(json.loads(sample.stdout)))
            self.assertEqual(path.read_text(), sample.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_cli_invalid_and_missing_do_not_echo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private-file.json'
            for text in ('{"schema_version":1,"schema_version":2,"captures":{}}', '{"private-token":NaN}',
                         '{"private-token":1e999}', 'bad-private-token', ' ' * (MAX_BYTES + 1)):
                path.write_text(text)
                result = self.run_cli('analyze', str(path))
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(json.loads(result.stdout)['status'], 'unavailable')
                self.assertNotIn('private-', result.stdout)
            result = self.run_cli('analyze', str(Path(directory) / 'private-missing.json'))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('private-', result.stdout)
