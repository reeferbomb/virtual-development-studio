import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cinematic.production import runner


EXAMPLES = runner.ROOT / 'cinematic/production/examples'
PLAN = EXAMPLES / 'nightfall_plan.json'
BINDINGS = EXAMPLES / 'nightfall_bindings.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def marker(production_sha256, failed=False):
    return {
        'schema_version': 1,
        'production_sha256': production_sha256,
        'pass': not failed,
        'checks': [{'id': name, 'name': name, 'status': 'failed' if failed else 'passed', 'detail': ''}
                   for name in sorted(runner.QA_CHECKS)],
    }


def marker_line(value):
    return runner.QA_MARKER + b' ' + json.dumps(value).encode() + b'\n'


class ProductionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_strict_json_rejects_malformed_private_input(self):
        for data in (b'\xff', b'{"asset":1,"asset":2}', b'{"asset":NaN}', b'{"asset":Infinity}',
                     b'{"asset":1e400}', b'{"asset":"\\ud800"}', b'[]', b'{',
                     b'{"asset":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}'):
            with self.subTest(data=data[:40]):
                path = self.tmp / 'plan.json'
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'Plan'):
                    runner._read_input(path, 'Plan')

    def test_bounded_read_refuses_symlink_and_fifo(self):
        path = self.tmp / 'source.json'
        path.write_bytes(b' ' * runner.MAX_BYTES + b'{}')
        with self.assertRaisesRegex(ValueError, 'limit'):
            runner._read_input(path, 'Plan')
        link = self.tmp / 'link.json'
        link.symlink_to(path)
        fifo = self.tmp / 'fifo.json'
        os.mkfifo(fifo)
        for target in (link, fifo, self.tmp):
            with self.subTest(target=target.name), self.assertRaisesRegex(ValueError, 'regular file'):
                runner._read_input(target, 'Plan')

    def test_output_rejects_checkout_and_existing_or_linked_path(self):
        with self.assertRaisesRegex(ValueError, 'outside'):
            runner._output_path(runner.ROOT / 'generated-evidence')
        real = self.tmp / 'existing'
        real.mkdir()
        (real / 'keep').write_text('original')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            runner._output_path(real)
        self.assertEqual((real / 'keep').read_text(), 'original')
        link = self.tmp / 'linked'
        link.symlink_to(runner.ROOT, target_is_directory=True)
        broken = self.tmp / 'broken'
        broken.symlink_to(self.tmp / 'missing')
        for path in (link / 'generated-evidence', broken, link / '../generated-evidence'):
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                runner._output_path(path)

    def test_marker_requires_unique_coherent_digest_bound_checks(self):
        identity = '1' * 64
        good = marker(identity)
        self.assertEqual(runner._parse_qa(b'Info\n' + marker_line(good), 0, identity), good)
        failed = marker(identity, failed=True)
        self.assertEqual(runner._parse_qa(marker_line(failed), 1, identity), failed)
        row = good['checks'][0]
        cases = (
            (b'', 0),
            (marker_line(good) * 2, 0),
            (marker_line(good) + runner.QA_MARKER + b'\n', 0),
            (marker_line(good), 1),
            (marker_line(failed), 0),
            (marker_line(dict(good, checks=[])), 0),
            (marker_line(dict(good, checks=[row])), 0),
            (marker_line(dict(good, checks=good['checks'] + [row])), 0),
            (marker_line(dict(good, checks=[dict(row, status=[])])), 0),
            (marker_line(dict(good, checks=[dict(row, name='  ')])), 0),
            (marker_line(dict(good, production_sha256='0' * 64)), 0),
            (marker_line(dict(good, schema_version=True)), 0),
            (marker_line(dict(failed, **{'pass': True})), 0),
            (runner.QA_MARKER + b' {"pass": true, "pass": true}\n', 0),
        )
        for output, code in cases:
            with self.subTest(code=code, output=output[-100:]), self.assertRaises(ValueError):
                runner._parse_qa(output, code, identity)

    def test_data_only_export_records_every_original_byte(self):
        project = self.tmp / 'production'
        with patch.object(runner, '_installed_godot', side_effect=AssertionError('must be opt-in')):
            report = runner.run_production(PLAN, BINDINGS, project)
        self.assertEqual(report['status'], 'exported')
        self.assertEqual(report['runtime']['status'], 'not_requested')
        self.assertEqual(report, json.loads((project / 'reports/report.json').read_text()))
        self.assertEqual(project.stat().st_mode & 0o777, 0o700)
        compiled = json.loads((project / 'production.json').read_text())
        self.assertEqual(compiled, {'schema_version': 1, 'plan': json.loads(PLAN.read_text()),
                                   'bindings': json.loads(BINDINGS.read_text())})
        self.assertEqual(report['inputs'], {'plan_sha256': digest(PLAN), 'bindings_sha256': digest(BINDINGS)})
        inventory = {row['path']: row['sha256'] for row in report['files']}
        for relative in inventory:
            self.assertEqual(digest(project / relative), inventory[relative])
        self.assertEqual(set(inventory), {*runner.TEMPLATE_FILES, 'production.json', 'LICENSE',
                                         'assets/provenance.json', *runner.ASSET_FILES})
        provenance = json.loads((project / 'assets/provenance.json').read_text())
        self.assertEqual(provenance['source_manifest_sha256'], runner.FIXTURE_MANIFEST_SHA256)
        self.assertEqual({f"assets/{row['path']}": row['sha256'] for row in provenance['assets']},
                         {asset: inventory[asset] for asset in runner.ASSET_FILES})
        self.assertNotIn(str(self.tmp), json.dumps(report))

    def test_bad_source_manifest_refuses_to_create_an_export(self):
        project = self.tmp / 'production'
        with patch.object(runner, 'FIXTURE_MANIFEST_SHA256', '0' * 64), self.assertRaisesRegex(ValueError, 'manifest'):
            runner.run_production(PLAN, BINDINGS, project)
        self.assertFalse(project.exists())

    def test_missing_offline_engine_preserves_export_without_a_pass(self):
        project = self.tmp / 'production'
        with patch.object(runner, '_offline_prefix', return_value=None), patch.object(
                runner, '_run_bounded', side_effect=AssertionError('no networked fallback')), contextlib.redirect_stdout(
                io.StringIO()) as stdout:
            code = runner.main([str(PLAN), str(BINDINGS), '--output', str(project), '--engine'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['status'], 'unavailable')
        self.assertTrue((project / 'production.json').is_file())
        self.assertEqual(json.loads((project / 'reports/report.json').read_text())['runtime']['status'], 'unavailable')

    def test_runtime_errors_and_mutated_inputs_cannot_report_pass(self):
        for scenario in ('import-error', 'import-no-remap', 'qa-error', 'qa-mutate', 'pass'):
            with self.subTest(scenario=scenario):
                project = self.tmp / scenario

                def simulate(command, directory, env, **limits):
                    self.assertEqual(directory, project)
                    self.assertEqual(command[:2], ['/usr/bin/unshare', '/usr/bin/godot'])
                    self.assertNotIn('--log-file', command)
                    self.assertNotEqual(env['HOME'], os.environ.get('HOME'))
                    self.assertTrue(env['XDG_CONFIG_HOME'].startswith(str(project / 'reports')))
                    self.assertLessEqual(limits['timeout'], 60)
                    if '--version' in command:
                        output = b'4.7.2.stable.official.ed1daf0bf\n'
                    elif '--import' in command:
                        output = b'ERROR: Failed import\n' if scenario == 'import-error' else b'Imported\n'
                        if scenario != 'import-no-remap':
                            for asset in runner.ASSET_FILES:
                                (project / (asset + '.import')).touch()
                    else:
                        self.assertNotIn(scenario, ('import-error', 'import-no-remap'))
                        self.assertEqual(command[-2:], ['--script', 'res://production_qa.gd'])
                        output = marker_line(marker(digest(project / 'production.json')))
                        if scenario == 'qa-error':
                            output += b'SCRIPT ERROR: Godot failed\n'
                        if scenario == 'qa-mutate':
                            (project / 'production.json').write_text('{}')
                    return subprocess.CompletedProcess(command, 0, stdout=output)

                with patch.object(runner, '_offline_prefix', return_value=['/usr/bin/unshare']), patch.object(
                        runner, '_installed_godot', return_value='/usr/bin/godot'), patch.object(
                        runner, '_run_bounded', side_effect=simulate):
                    report = runner.run_production(PLAN, BINDINGS, project, engine=True)
                self.assertEqual(report['status'], 'passed' if scenario == 'pass' else 'failed', report)
                self.assertTrue((project / 'reports/import.log').is_file())
                self.assertEqual(report, json.loads((project / 'reports/report.json').read_text()))

    @unittest.skipUnless(sys.platform == 'linux', 'Godot runner uses Linux process groups')
    def test_process_timeout_and_output_cap(self):
        for code, seconds, error in (('import time; time.sleep(30)', 0.1, 'timed out'),
                                     ('import os; os.write(1, b"x" * 10000)', 3, 'output limit')):
            with self.subTest(error=error), self.assertRaisesRegex(RuntimeError, error):
                runner._run_bounded([sys.executable, '-I', '-c', code], self.tmp, {}, timeout=seconds, max_output=128)


if __name__ == '__main__':
    unittest.main()
