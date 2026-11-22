import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import studio
from command_center.lab_engine_import import _installed_godot, _offline_prefix
from command_center.strict_engine_log import has_engine_error, inspect_log
from gameplay.integrated_lab import runner


DIGEST = 'a' * 64


def marker():
    checks = [{'id': key, 'passed': True, 'detail': 'Handled the example "SCRIPT ERROR: expected".'}
              for key in runner.CHECKS['integrated']]
    return runner.MARKER + json.dumps({'schema_version': 1, 'source_sha256': DIGEST, 'passed': True,
        'reports': [{'id': 'integrated', 'checks': checks,
                     'metrics': {'example': 'FAIL guard: zero failures=0', 'sample': 'WARNING: text'}}]}).encode()


class EngineLogTests(unittest.TestCase):
    def test_exit_zero_and_complete_marker_cannot_mask_failure(self):
        records = (b' ERROR: Cannot instantiate', b'  SCRIPT ERROR: Invalid assignment',
                   b'\x1b[1;31mSHADER ERROR:\x1b[0m missing symbol', b'Parse Error: Unknown identifier',
                   b'FAIL transport: unexpected station', b'[FAILED] new game', b'Assertion failed: bad state',
                   b'lobby checks=9 failures=1', b'Quest assertions finished, failures=02',
                   b'input guard failures: 3', b'Tests failed: 1')
        for record in records:
            with self.subTest(record=record):
                log = marker() + b'\r\n' + record
                self.assertTrue(has_engine_error(log))
                with self.assertRaises(ValueError):
                    runner._parse_marker(log, 0, DIGEST)

    def test_warnings_and_strings_in_proof_have_separate_semantics(self):
        log = (b'Godot Engine v4\nWARNING: expected fallback\nTests failed: 0\n'
               b'Checks failed: 0\nQuest assertions finished, failures=0\n'
               b'PASS handled embedded ERROR: text and FAIL text\n' + marker())
        self.assertTrue(runner._parse_marker(log, 0, DIGEST)['passed'])
        raw_hash, counts = inspect_log(io.BytesIO(log))
        self.assertEqual(counts, {'WARNING': 1})
        self.assertEqual(raw_hash, hashlib.sha256(log).hexdigest())

    def test_missing_partial_multiple_or_contradictory_proof_fails(self):
        good = marker()
        doc = json.loads(good[len(runner.MARKER):])
        doc['reports'][0]['checks'][0]['passed'] = False
        for log in (b'All checks passed\n', good[:-7], good + b'\n' + good,
                    runner.MARKER + json.dumps(doc).encode()):
            with self.subTest(length=len(log)), self.assertRaises(ValueError):
                runner._parse_marker(log, 0, DIGEST)

    def test_real_godot_exit_zero_with_error_and_valid_marker(self):
        engine, prefix = _installed_godot(), _offline_prefix()
        if not engine or not prefix or subprocess.run([*prefix, 'true'], capture_output=True, timeout=5).returncode:
            self.skipTest('Local Godot and network isolation required')
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'project.godot').write_text('config_version=5\n')
            (project / 'qa.gd').write_text(
                'extends SceneTree\nfunc _initialize() -> void:\n'
                '\tpush_error("Deliberate diagnostic fixture")\n'
                f'\tprint({json.dumps(marker().decode())})\n\tquit(0)\n')
            result = subprocess.run([*prefix, engine, '--headless', '--path', directory,
                                     '--log-file', str(project / 'engine.log'), '--script', 'res://qa.gd'],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn(marker(), result.stdout)
        self.assertIn('ERROR', inspect_log(io.BytesIO(result.stdout))[1])
        with self.assertRaises(ValueError):
            runner._parse_marker(result.stdout, result.returncode, DIGEST)


class StrictCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.state = self.root / 'studio.json'
        self.cli('register', 'demo', '--name', 'Demo', '--objective', 'Verify', '--source', str(self.root))
        for name, extra in (('base', []), ('next', ['--depends', 'base'])):
            self.cli('task', 'demo', name, '--title', name, '--owner', 'QA', '--acceptance', 'Verify', *extra)

    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            return studio.main(['--state', str(self.state), *args])

    def run_log(self, name, content, *, strict=True, code=0):
        cmd = f'import sys; sys.stdout.buffer.write({content!r}); sys.exit({code})'
        return self.cli('run', 'demo', name, *(['--godot-clean'] if strict else []), '--', sys.executable, '-c', cmd)

    def tasks(self):
        return json.loads(self.state.read_text())['projects'][0]['tasks']

    def test_strict_retains_raw_exit_digest_counts_and_blocks_dependents(self):
        content = (b'\xff\r\n\x1b[31mSCRIPT ERROR:\x1b[0m bad\rERROR: bad\n'
                   b'WARNING: bad\nFAIL scope\nQuest assertions finished, failures=1\n')
        self.assertEqual(self.run_log('base', content), 1)
        base, dependent = self.tasks()
        evidence = base['evidence'][-1]
        self.assertEqual((base['status'], dependent['status']), ('failed', 'pending'))
        self.assertEqual(evidence['exit_code'], 0)
        self.assertFalse(evidence['policy_passed'])
        self.assertEqual(evidence['diagnostics'], {'SCRIPT ERROR': 1, 'ERROR': 1, 'WARNING': 1, 'FAIL': 2})
        self.assertEqual(Path(evidence['log']).read_bytes(), content)
        self.assertEqual(evidence['sha256'], hashlib.sha256(content).hexdigest())
        with self.assertRaisesRegex(ValueError, 'Dependency base'):
            self.run_log('next', b'PASS')

    def test_warning_only_default_and_strict_policy_and_nonzero_exit(self):
        warning = b'WARNING: investigate\n'
        self.assertEqual(self.run_log('base', warning, strict=False), 0)
        self.assertTrue(studio.valid_evidence(self.tasks()[0]))
        self.assertEqual(self.run_log('base', warning), 1)
        self.assertEqual(self.run_log('base', b'clean\n', code=9), 1)
        self.assertEqual(self.tasks()[0]['evidence'][-1]['exit_code'], 9)

    def test_strict_clean_log_unlocks_then_changed_or_missing_log_blocks(self):
        self.assertEqual(self.run_log('base', marker() + b'\n'), 0)
        self.assertEqual(self.run_log('next', b'PASS\n'), 0)
        base, dependent = self.tasks()
        evidence = base['evidence'][-1]
        self.assertTrue(evidence['policy_passed'])
        self.assertTrue(studio.accepted(dependent, [base, dependent]))
        evidence['policy_passed'] = False
        self.assertFalse(studio.valid_evidence(base))
        evidence['policy_passed'] = True
        log = Path(evidence['log'])
        original = log.read_bytes()
        log.write_bytes(b'ERROR: stale or mismatched verdict\n')
        evidence['sha256'] = hashlib.sha256(log.read_bytes()).hexdigest()
        self.assertFalse(studio.valid_evidence(base))
        evidence['sha256'] = hashlib.sha256(original).hexdigest()
        log.write_bytes(original + b'\r\n')
        self.assertFalse(studio.accepted(dependent, [base, dependent]))
        log.unlink()
        self.assertFalse(studio.valid_evidence(base))


if __name__ == '__main__':
    unittest.main()
