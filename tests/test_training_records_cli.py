import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from command_center.training_lab import MAX_BYTES, lab_catalog


ROOT = Path(__file__).resolve().parents[1]


class TrainingRecordsCliTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.workspace = self.base / 'workspace'
        self.workspace.mkdir()
        self.source = self.base / 'private-submission.json'

    def cli(self, *args, workspace=None):
        return subprocess.run(
            [sys.executable, '-m', 'command_center.training_records_cli',
             '--workspace', str(workspace or self.workspace), *map(str, args)],
            cwd=ROOT, capture_output=True, text=True, timeout=5,
        )

    def output(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def assert_error(self, result):
        self.assertEqual(result.returncode, 2, result)
        self.assertEqual(result.stdout, '')
        self.assertTrue(json.loads(result.stderr)['error'])

    def record(self, revision):
        return self.cli('record', 'game-development', 'gameplay', self.source,
                        '--expected-revision', revision)

    def test_empty_list_and_progress_do_not_create_files(self):
        snapshot = self.output(self.cli('list'))
        self.assertEqual(snapshot, {
            'revision': 0, 'lab_sha256': lab_catalog()['lab_sha256'],
            'records': [], 'note': snapshot['note'],
        })
        self.assertTrue(snapshot['note'])
        self.assertEqual(self.output(self.cli('list', workspace=os.path.relpath(self.workspace, ROOT))), snapshot)
        progress = self.output(self.cli('progress'))
        self.assertEqual(progress['revision'], 0)
        self.assertEqual(progress['summary']['records'], 0)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_record_review_and_list_share_revision(self):
        example = next(entry['example'] for entry in lab_catalog()['exercises']
                       if entry['id'] == 'game-development')
        example['steps'].append({'op': 'save', 'accepted': True, 'expected_count': 3})
        self.source.write_text(json.dumps(example), encoding='utf-8')
        saved = self.output(self.record(0))
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(len(saved['records']), 1)
        self.assertEqual(self.output(self.cli('list')), saved)
        self.assert_error(self.record(0))
        self.assertEqual(self.output(self.cli('list')), saved)

        record_id = saved['records'][0]['id']
        review = ('review', record_id, 'verification', 'accepted', 'Checked inventory transitions.')
        reviewed = self.output(self.cli(*review, '--expected-revision', 1))
        self.assertEqual(reviewed['revision'], 2)
        self.assertEqual(self.output(self.cli('list')), reviewed)
        self.assertEqual(self.output(self.cli('progress'))['summary']['accepted'], 1)
        self.assert_error(self.cli(*review, '--expected-revision', 2))
        self.assertEqual(self.output(self.cli('list')), reviewed)

    def test_failed_practice_can_be_recorded_and_rejected(self):
        self.source.write_text('{"steps":[]}', encoding='utf-8')
        saved = self.output(self.record(0))
        item, = saved['records']
        self.assertEqual(item['report']['status'], 'fail')
        self.assert_error(self.cli('review', item['id'], 'lead', 'accepted', 'Missing cases.',
                                   '--expected-revision', 1))
        reviewed = self.output(self.cli('review', item['id'], 'lead', 'rejected', 'Missing cases.',
                                        '--expected-revision', 1))
        self.assertEqual(reviewed['records'][0]['review']['decision'], 'rejected')
        self.assertEqual(self.output(self.cli('progress'))['summary']['qualifying_distinct'], 0)

    def test_invalid_submission_files_report_json_without_creating_a_record(self):
        for bad in (b'{', b'[]', b'{"steps":[],"steps":[]}', b'{"steps":[NaN]}',
                    b'{"steps":[]}\xff', b'{"steps":[]}' + b' ' * MAX_BYTES):
            with self.subTest(data=bad[:20]):
                self.source.write_bytes(bad)
                self.assert_error(self.record(0))
        self.source.unlink()
        self.assert_error(self.record(0))
        os.mkfifo(self.source)
        self.assert_error(self.record(0))
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_private_workspace_and_argument_errors(self):
        self.assert_error(self.cli('list', workspace=ROOT))
        self.assert_error(self.cli('list', workspace=ROOT / 'tests'))
        self.assert_error(self.cli('list', workspace=ROOT.parent / ROOT.name / 'tests' / '..'))
        alias = self.base / 'alias'
        alias.symlink_to(self.workspace, target_is_directory=True)
        self.assert_error(self.cli('list', workspace=alias))
        missing_revision = self.cli('record', 'game-development', 'gameplay', self.source)
        self.assert_error(missing_revision)
        self.assertIn('--expected-revision', missing_revision.stderr)
        result = self.cli('review', 'local-id', 'verification', 'private-argument', 'test',
                          '--expected-revision', 0)
        self.assert_error(result)
        self.assertNotIn('private-argument', result.stderr)
        self.assertEqual(list(self.workspace.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
