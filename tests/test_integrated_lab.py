from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from command_center.lab_engine_import import _installed_godot, _offline_prefix
from command_center.provenance import spec_digest
from gameplay.integrated_lab import runner


DIGEST = 'a' * 64


def marker():
    return {'schema_version': 1, 'source_sha256': DIGEST, 'passed': True, 'reports': [{
        'id': 'integrated', 'checks': [{'id': key, 'passed': True, 'detail': 'Observed.'}
                                      for key in runner.CHECKS['integrated']], 'metrics': {}}]}


def raw(document):
    return runner.MARKER + json.dumps(document).encode()


class IntegratedLabTests(unittest.TestCase):
    def test_marker_is_bound_to_source_domain_coverage_and_exit(self):
        document = marker()
        self.assertEqual(runner._parse_marker(raw(document), 0, DIGEST), document)
        for mutate in (
            lambda d: d.update(source_sha256='b' * 64),
            lambda d: d.update(schema_version=True),
            lambda d: d.update(passed=False),
            lambda d: d['reports'].append(deepcopy(d['reports'][0])),
            lambda d: d['reports'][0].update(id='world'),
            lambda d: d['reports'][0].update(metrics=[]),
            lambda d: d['reports'][0]['checks'].pop(),
            lambda d: d['reports'][0]['checks'][0].update(id='unexpected-check'),
            lambda d: d['reports'][0]['checks'][0].update(passed=1),
            lambda d: d['reports'][0]['checks'][0].update(detail=''),
            lambda d: d['reports'][0]['checks'][0].update(id=d['reports'][0]['checks'][1]['id']),
        ):
            bad = marker()
            mutate(bad)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                runner._parse_marker(raw(bad), 0, DIGEST)
        for output in (b'', b'SCRIPT ERROR: invalid\n' + raw(document), raw(document) + b'\n' + raw(document),
                       b'GRAVEFORGE_WORLD_QA ' + json.dumps(document).encode(),
                       runner.MARKER + b'{"passed":true,"passed":false}'):
            with self.subTest(output=output[:120]), self.assertRaises(ValueError):
                runner._parse_marker(output, 0, DIGEST)
        with self.assertRaises(ValueError):
            runner._parse_marker(raw(document), 1, DIGEST)
        document['passed'] = document['reports'][0]['checks'][0]['passed'] = False
        self.assertEqual(runner._parse_marker(raw(document), 1, DIGEST), document)

    def test_reports_exact_privately_exported_sources_and_requires_fresh_path(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner.engine_runner, '_runtime') as execute:
            root = Path(directory)
            output = root / 'integrated'
            report = runner.run(output)
            execute.assert_not_called()
            self.assertEqual(report['status'], 'exported')
            self.assertEqual(report['runtime']['status'], 'not_requested')
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual(report['source_sha256'], spec_digest(report['files']))
            self.assertEqual({row['path'] for row in report['files']}, set(runner.FILES))
            self.assertEqual({path.name for path in output.iterdir()}, {*runner.FILES, 'reports'})
            for row in report['files']:
                actual = (output / row['path']).read_bytes()
                self.assertEqual((row['bytes'], row['sha256']), (len(actual), hashlib.sha256(actual).hexdigest()))
            self.assertEqual(json.loads((output / 'reports/report.json').read_text()), report)
            alias = root / 'alias'
            alias.symlink_to(output, target_is_directory=True)
            for path in (output, alias / 'new', runner.ROOT / 'unsafe-integrated-test'):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    runner.run(path)

    def test_first_failure_or_unavailable_stops_before_repeat(self):
        for status in ('failed', 'unavailable'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory, patch.object(
                    runner.engine_runner, '_runtime', return_value={'status': status}) as execute:
                report = runner.run(Path(directory) / 'integrated', engine=True)
                self.assertEqual(report['status'], status)
                self.assertEqual(len(report['runtime']['runs']), 1)
                execute.assert_called_once()
                self.assertNotIn('repeat_sha256', report['runtime'])

    def test_repeat_failure_unavailable_version_or_measurement_change_cannot_pass(self):
        for change in ('failed', 'unavailable', 'version', 'metrics', 'metric-type'):
            first = {'status': 'passed', 'godot_version': '4.7.2', 'qa': marker()}
            second = deepcopy(first)
            if change in ('failed', 'unavailable'):
                second['status'] = change
            elif change == 'version':
                second['godot_version'] = '4.7.3'
            elif change == 'metrics':
                second['qa']['reports'][0]['metrics']['extra'] = 1
            else:
                first['qa']['reports'][0]['metrics']['ready'] = True
                second['qa']['reports'][0]['metrics']['ready'] = 1
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory, patch.object(
                    runner.engine_runner, '_runtime', side_effect=[first, second]) as execute:
                report = runner.run(Path(directory) / 'integrated', engine=True)
                self.assertEqual(report['status'], 'unavailable' if change == 'unavailable' else 'failed')
                self.assertEqual(execute.call_count, 2)
                self.assertEqual(execute.call_args_list[1].kwargs['log_name'], 'qa-repeat.log')
                self.assertNotIn('repeat_sha256', report['runtime'])

    def test_source_tamper_detected_after_each_run(self):
        for tamper_on_run in (1, 2):
            def tamper(output, digest, **kwargs):
                if execute.call_count == tamper_on_run:
                    (output / 'main.tscn').write_text('changed')
                return {'status': 'passed', 'godot_version': '4.7.2', 'qa': marker()}

            with self.subTest(run=tamper_on_run), tempfile.TemporaryDirectory() as directory, patch.object(
                    runner.engine_runner, '_runtime', side_effect=tamper) as execute:
                report = runner.run(Path(directory) / 'integrated', engine=True)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(execute.call_count, tamper_on_run)
                self.assertIn('changed after engine QA', report['runtime']['reason'])
                self.assertNotIn('repeat_sha256', report['runtime'])

    def test_two_real_godot_processes(self):
        engine, offline = _installed_godot(), _offline_prefix()
        if not engine or not offline or subprocess.run([*offline, 'true'], capture_output=True, timeout=5).returncode:
            self.skipTest('Local Godot and Linux network isolation required')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'integrated'
            report = runner.run(output, engine=True)
            logs = [output / 'reports' / name for name in ('qa.log', 'qa-repeat.log')]
            detail = '\n'.join(log.read_text(errors='replace')[-6000:] for log in logs if log.exists())
            self.assertEqual(report['status'], 'passed', str(report['runtime']) + '\n' + detail)
            first, second = report['runtime']['runs']
            self.assertEqual(first['qa'], second['qa'])
            self.assertEqual(first['godot_version'], second['godot_version'])
            self.assertEqual(report['runtime']['repeat_sha256'], spec_digest(first['qa']))
            self.assertEqual(first['qa']['source_sha256'], report['source_sha256'])
            checks = first['qa']['reports'][0]['checks']
            self.assertEqual({row['id'] for row in checks}, set(runner.CHECKS['integrated']))
            self.assertTrue(all(row['passed'] for row in checks))
            for result, log in zip((first, second), logs, strict=True):
                self.assertEqual(result['log_sha256'], hashlib.sha256(log.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
