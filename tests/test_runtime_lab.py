import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from command_center.lab_engine_import import _installed_godot, _offline_prefix
from command_center.production_intelligence import analyze_bundle
from command_center.provenance import spec_digest
from gameplay.runtime_lab import runner


class RuntimeLabTests(unittest.TestCase):
    def marker(self):
        return {'schema_version': 1, 'source_sha256': 'a' * 64, 'passed': True,
                'reports': [{'id': domain, 'checks': [
                    {'id': key, 'passed': True, 'detail': 'Observed.'} for key in runner.CHECKS[domain]],
                    'metrics': {}} for domain in runner.DOMAINS]}

    def raw(self, marker):
        return runner.MARKER + json.dumps(marker).encode()

    def test_marker_requires_identity_domain_coverage_and_consistent_outcomes(self):
        doc = self.marker()
        self.assertEqual(runner._parse_marker(self.raw(doc), 0, 'a' * 64), doc)
        for change in ('wrong-digest', 'false-summary', 'missing-domain', 'wrong-domain', 'duplicate-check',
                       'missing-checks', 'unexpected-check', 'nonbool'):
            bad = copy.deepcopy(doc)
            if change == 'wrong-digest': bad['source_sha256'] = 'b' * 64
            if change == 'false-summary': bad['passed'] = False
            if change == 'missing-domain': bad['reports'].pop()
            if change == 'wrong-domain': bad['reports'][0]['id'] = 'capture'
            if change == 'duplicate-check': bad['reports'][0]['checks'][1]['id'] = bad['reports'][0]['checks'][0]['id']
            if change == 'missing-checks': bad['reports'][0]['checks'].pop()
            if change == 'unexpected-check': bad['reports'][0]['checks'][0]['id'] = 'not-a-required-check'
            if change == 'nonbool': bad['reports'][0]['checks'][0]['passed'] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                runner._parse_marker(self.raw(bad), 0, 'a' * 64)
        raw = self.raw(doc)
        for bad in (raw + b'\n' + raw, b'SCRIPT ERROR: invalid\n' + raw, b'no marker'):
            with self.assertRaises(ValueError): runner._parse_marker(bad, 0, 'a' * 64)
        with self.assertRaises(ValueError): runner._parse_marker(raw, 1, 'a' * 64)
        doc['passed'] = doc['reports'][0]['checks'][0]['passed'] = False
        self.assertEqual(runner._parse_marker(self.raw(doc), 1, 'a' * 64), doc)

    def test_export_is_private_exact_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'project'
            with patch.object(runner, '_runtime') as runtime:
                result = runner.run(target)
                runtime.assert_not_called()
            self.assertEqual(result['status'], 'exported')
            self.assertEqual(result['source_sha256'], spec_digest(result['files']))
            self.assertEqual({entry['path'] for entry in result['files']}, set(runner.FILES))
            for entry in result['files']:
                data = (target / entry['path']).read_bytes()
                self.assertEqual(entry['bytes'], len(data))
                self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(json.loads((target / 'reports/report.json').read_text()), result)
            with self.assertRaises(ValueError): runner.run(target)
            with self.assertRaises(ValueError): runner.run(runner.ROOT / 'runtime-unsafe-test')
            alias = Path(directory) / 'alias'
            alias.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError): runner.run(alias / 'new')

    def test_missing_engine_is_not_a_pass_and_does_not_capture(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, '_offline_prefix', return_value=None):
            target = Path(directory) / 'project'
            report = runner.run(target, engine=True)
            self.assertEqual(report['status'], 'unavailable')
            self.assertFalse((target / 'reports/captures.json').exists())

    def test_changed_source_cannot_be_certified(self):
        def altered(output, digest):
            (output / 'qa.gd').write_text('changed')
            return {'status': 'passed', 'scope': runner.SCOPE}
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, '_runtime', side_effect=altered):
            result = runner.run(Path(directory) / 'project', engine=True)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('changed after engine QA', result['runtime']['reason'])

    def test_real_engine_and_intelligence_bridge(self):
        engine, prefix = _installed_godot(), _offline_prefix()
        if not engine or not prefix or subprocess.run([*prefix, 'true'], capture_output=True, timeout=5).returncode:
            self.skipTest('Local Godot and network isolation required')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'project'
            report = runner.run(target, engine=True)
            log = target / 'reports/qa.log'
            self.assertEqual(report['status'], 'passed', str(report['runtime'].get('reason')) + '\n' +
                             (log.read_text(errors='replace')[-6000:] if log.exists() else ''))
            results = report['runtime']['qa']['reports']
            self.assertEqual([item['id'] for item in results], list(runner.DOMAINS))
            self.assertTrue(all(check['passed'] for row in results for check in row['checks']))
            self.assertEqual(report['runtime']['log_sha256'], hashlib.sha256(log.read_bytes()).hexdigest())
            bundle = json.loads((target / 'reports/captures.json').read_text())
            self.assertEqual(set(bundle['captures']), {'frame', 'ui'})
            self.assertGreaterEqual(len(bundle['captures']['frame']['scenarios'][0]['frame_times_us']), 100)
            self.assertEqual(json.loads((target / 'reports/intelligence.json').read_text()), analyze_bundle(bundle))
            self.assertEqual(report['runtime']['capture_sha256'], spec_digest(bundle))


if __name__ == '__main__':
    unittest.main()
