import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center.defect_store import DefectStore
from command_center.projects import ProjectStore
from command_center.server import StudioService


ROOT = Path(__file__).resolve().parents[1]


class SprintConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        workspace = Path(temporary.name)
        self.service = StudioService(ROOT, workspace)
        self.project_id = self.service.projects.create('Independent writer', 'city')['id']
        self.writer = DefectStore(ProjectStore(ROOT, workspace))
        self.digest = self.writer.get(self.project_id)['spec_sha256']

    def add_critical_defect(self):
        self.writer.apply(self.project_id, {
            'expected_revision': 0, 'spec_sha256': self.digest,
            'action': {'op': 'add', 'severity': 'critical', 'title': 'Portal blocks exit',
                       'description': 'Walking through the exit portal fails.',
                       'evidence': ['Observed the failure in a playtest.']},
        })

    def test_non_object_saved_spec_blocks_preview_and_apply(self):
        project_dir = self.service.projects.directory(self.project_id)
        (project_dir / 'spec.json').write_text('[]', encoding='utf-8')
        before = self.service.tasks.get(self.project_id)
        preview = self.service.sprint(self.project_id)
        self.assertEqual(preview['status'], 'blocked')
        self.assertEqual(preview['tasks'], [])
        with self.assertRaises(FileExistsError):
            self.service.apply_sprint(self.project_id, {
                'expected_revision': before['revision'], 'spec_sha256': before['spec_sha256'],
                'plan_id': preview['plan_id'],
            })
        self.assertEqual(self.service.tasks.get(self.project_id), before)
        self.assertFalse((project_dir / 'task-board.json').exists())

    def test_independent_defect_write_between_plan_validation_and_board_commit(self):
        preview = self.service.sprint(self.project_id)
        original_board = self.service.tasks.get(self.project_id)
        commit = self.service.tasks.apply

        def interleave(*args, **kwargs):
            self.add_critical_defect()
            updated = self.service.sprint(self.project_id)
            self.assertNotEqual(updated['plan_id'], preview['plan_id'])
            self.assertEqual(updated['board_revision'], preview['board_revision'])
            build = next(task for task in updated['tasks'] if task['id'] == 'supervisor-build')
            self.assertIn('supervisor-defects', build['depends_on'])
            return commit(*args, **kwargs)

        with patch.object(self.service.tasks, 'apply', side_effect=interleave):
            with self.assertRaises(FileExistsError):
                self.service.apply_sprint(self.project_id, {
                    'expected_revision': preview['board_revision'], 'spec_sha256': self.digest,
                    'plan_id': preview['plan_id'],
                })
        self.assertEqual(self.service.tasks.get(self.project_id), original_board)
        self.assertEqual(self.writer.get(self.project_id)['revision'], 1)

    def test_independent_defect_write_between_audit_read_and_history_commit(self):
        original_history = self.service.evidence_history.get(self.project_id)
        commit = self.service.evidence_history.capture

        def interleave(project_id, data, audit, **kwargs):
            self.assertEqual(audit['status'], 'pending')
            self.add_critical_defect()
            self.assertEqual(self.service.supervisor(self.project_id)['status'], 'blocked')
            return commit(project_id, data, audit, **kwargs)

        with patch.object(self.service.evidence_history, 'capture', side_effect=interleave):
            with self.assertRaises(FileExistsError):
                self.service.capture_evidence(self.project_id, {
                    'expected_revision': 0, 'spec_sha256': self.digest,
                    'note': 'Observed the current project.',
                })
        self.assertEqual(self.service.evidence_history.get(self.project_id), original_history)
        self.assertEqual(self.writer.get(self.project_id)['revision'], 1)


if __name__ == '__main__':
    unittest.main()
