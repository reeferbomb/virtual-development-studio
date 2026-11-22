import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from command_center.lab_engine_import import _installed_godot, _offline_prefix
from command_center.provenance import spec_digest
from gameplay.world_lab import runner


class LivingWorldLabTests(unittest.TestCase):
    def marker(self):
        return {'schema_version': 1, 'source_sha256': 'a' * 64, 'passed': True,
                'reports': [{'id': domain, 'checks': [
                    {'id': key, 'passed': True, 'detail': 'Observed.'} for key in runner.CHECKS[domain]],
                    'metrics': {}} for domain in runner.DOMAINS]}

    def raw(self, doc):
        return runner.MARKER + json.dumps(doc).encode()

    def test_strict_marker(self):
        doc = self.marker()
        self.assertEqual(runner._parse_marker(self.raw(doc), 0, 'a' * 64), doc)
        for change in ('source', 'domain', 'check', 'missing', 'passed', 'duplicate'):
            bad = copy.deepcopy(doc)
            if change == 'source': bad['source_sha256'] = 'b' * 64
            if change == 'domain': bad['reports'][0]['id'] = 'npc'
            if change == 'check': bad['reports'][0]['checks'][0]['id'] = 'unknown'
            if change == 'missing': bad['reports'][0]['checks'].pop()
            if change == 'passed': bad['reports'][0]['checks'][0]['passed'] = False
            if change == 'duplicate': bad['reports'][0]['checks'][1]['id'] = bad['reports'][0]['checks'][0]['id']
            with self.subTest(change=change), self.assertRaises(ValueError): runner._parse_marker(self.raw(bad), 0, 'a' * 64)
        for raw in (self.raw(doc) + b'\n' + self.raw(doc), b'ERROR: runtime\n' + self.raw(doc),
                    b'GRAVEFORGE_RUNTIME_QA ' + json.dumps(doc).encode()):
            with self.assertRaises(ValueError): runner._parse_marker(raw, 0, 'a' * 64)

    def test_private_export_exact_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.engine_runner, '_runtime') as execute:
            target = Path(directory) / 'world'
            result = runner.run(target)
            execute.assert_not_called()
            self.assertEqual(result['status'], 'exported')
            self.assertEqual(result['source_sha256'], spec_digest(result['files']))
            self.assertEqual({row['path'] for row in result['files']}, set(runner.FILES))
            for row in result['files']:
                data = (target / row['path']).read_bytes()
                self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (row['bytes'], row['sha256']))
            self.assertEqual(json.loads((target / 'reports/report.json').read_text()), result)
            with self.assertRaises(ValueError): runner.run(target)
            with self.assertRaises(ValueError): runner.run(runner.ROOT / 'unsafe-world')

    def test_unavailable_or_failed_first_run_does_not_retry(self):
        for status in ('unavailable', 'failed'):
            with tempfile.TemporaryDirectory() as directory, patch.object(
                    runner.engine_runner, '_runtime', return_value={'status': status}) as execute:
                result = runner.run(Path(directory) / 'world', engine=True)
                self.assertEqual(result['status'], status)
                self.assertEqual(execute.call_count, 1)
                self.assertNotIn('repeat_sha256', result['runtime'])

    def test_repeat_mismatch_is_not_certified(self):
        first = {'status': 'passed', 'godot_version': '4.7', 'qa': self.marker()}
        second = copy.deepcopy(first)
        second['qa']['reports'][0]['metrics']['value'] = 1
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.engine_runner, '_runtime',
                side_effect=[first, second]) as execute:
            report = runner.run(Path(directory) / 'world', engine=True)
            self.assertEqual(execute.call_count, 2)
            self.assertEqual(execute.call_args_list[1].kwargs['log_name'], 'qa-repeat.log')
            self.assertEqual(report['status'], 'failed')
            self.assertNotIn('repeat_sha256', report['runtime'])

    def test_source_tamper_prevents_repeat(self):
        def tamper(output, digest, **kwargs):
            (output / 'decision.gd').write_text('changed')
            return {'status': 'passed'}
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.engine_runner, '_runtime',
                side_effect=tamper) as execute:
            report = runner.run(Path(directory) / 'world', engine=True)
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(execute.call_count, 1)

    def test_two_real_godot_runs(self):
        engine, prefix = _installed_godot(), _offline_prefix()
        if not engine or not prefix or subprocess.run([*prefix, 'true'], capture_output=True, timeout=5).returncode:
            self.skipTest('Local Godot and network isolation required')
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'world'
            report = runner.run(target, engine=True)
            logs = '\n'.join((target / 'reports' / name).read_text(errors='replace')[-8000:]
                             for name in ('qa.log', 'qa-repeat.log') if (target / 'reports' / name).exists())
            self.assertEqual(report['status'], 'passed', str(report['runtime']) + '\n' + logs)
            first, second = report['runtime']['runs']
            self.assertEqual(first['qa'], second['qa'])
            self.assertEqual(report['runtime']['repeat_sha256'], spec_digest(first['qa']))
            self.assertEqual(sum(len(row['checks']) for row in first['qa']['reports']), sum(map(len, runner.CHECKS.values())))
            for result, log in ((first, 'qa.log'), (second, 'qa-repeat.log')):
                self.assertEqual(result['log_sha256'], hashlib.sha256((target / 'reports' / log).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
