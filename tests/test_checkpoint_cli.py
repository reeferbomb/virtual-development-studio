import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from command_center.projects import ProjectStore
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[1]


class CheckpointCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)
        project = ProjectStore(ROOT, self.workspace).create('CLI project', 'multiplayer')
        self.identifier = project['id']
        self.payload = {
            'expected_revision': 0,
            'spec_sha256': spec_digest(project['spec']),
            'elapsed_seconds': 300,
            'status': 'paused',
            'completed_work': ['Reviewed the fixed multiplayer specification.'],
            'verification_evidence': ['Confirmed the specification contains an empty object.'],
            'remaining_work': ['Run the multiplayer smoke test.'],
            'next_action': 'Run the multiplayer smoke test in the test workspace.',
        }

    def cli(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, '-m', 'command_center.checkpoint_cli', '--workspace',
             str(self.workspace), *args],
            cwd=ROOT, input=stdin, capture_output=True, text=True, timeout=15)

    def show(self):
        result = self.cli('show', self.identifier)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_file_and_stdin_share_persisted_revision_and_detect_conflicts(self):
        self.assertEqual(self.show()['revision'], 0)
        source = self.workspace / 'checkpoint-input.json'
        source.write_text(json.dumps(self.payload), encoding='utf-8')
        result = self.cli('save', self.identifier, '--input', str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.assertEqual(saved, self.show())
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(saved['checkpoint']['next_action'], self.payload['next_action'])

        conflict = self.cli('save', self.identifier, '--input', '-', stdin=json.dumps(self.payload))
        self.assertNotEqual(conflict.returncode, 0)
        self.assertTrue(json.loads(conflict.stderr)['error'])
        self.assertEqual(self.show(), saved)

        updated = dict(self.payload, expected_revision=1, elapsed_seconds=400)
        result = self.cli('save', self.identifier, '--input', '-', stdin=json.dumps(updated))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.show())
        self.assertEqual(json.loads(result.stdout)['remaining_seconds'], 17600)

    def test_bad_json_and_oversized_input_leave_checkpoint_untouched(self):
        original = self.show()
        for invalid in ('{', '[]', json.dumps(self.payload) + ' ' * (1024 * 1024)):
            result = self.cli('save', self.identifier, '--input', '-', stdin=invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')
            self.assertTrue(json.loads(result.stderr)['error'])
        self.assertEqual(self.show(), original)

    def test_missing_input_argument_reports_usage_error_as_json(self):
        result = self.cli('save', self.identifier)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--input', json.loads(result.stderr)['error'])
