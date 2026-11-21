import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from command_center.dispatch import default_profile
from command_center.handoff_store import HandoffStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.specialist_memory import specialist_memory
from command_center.task_store import TaskStore
from command_center.work_orders import work_orders


class SpecialistMemoryTests(unittest.TestCase):
    project = {'id': 'relay', 'spec': {'seed': 17}}
    digest = spec_digest(project['spec'])
    old_digest = spec_digest({'seed': 16})

    def item(self, number, role='architecture', review='accepted', digest=None,
             review_minute=None, outcome='progress'):
        origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return dict(id=f'{number:032x}', order_id=f'{number:064x}', task_id=f'task-{number}',
                    attempt=1, role=role, board_revision=2, spec_sha256=digest or self.digest,
                    created_at=(origin + timedelta(minutes=number)).isoformat(),
                    outcome=outcome, summary=f'Report {number}', evidence=[f'Replay {number}'],
                    changed_paths=['project/scene.json'], next_action=f'Review replay {number}',
                    review=review, review_note=None if review == 'pending' else 'Lead inspected replay.',
                    reviewed_at=None if review == 'pending' else
                    (origin + timedelta(minutes=review_minute or number)).isoformat())

    def history(self, *items):
        return dict(project_id=self.project['id'], spec_sha256=self.digest,
                    revision=len(items) + sum(item['review'] != 'pending' for item in items),
                    items=sorted(items, key=lambda item: item['created_at'], reverse=True))

    def test_only_current_accepted_reports_become_memory(self):
        accepted = self.item(1, outcome='blocked')
        accepted['next_action'] = '$(touch sentinel) <script> example text'
        other = self.item(2, 'gameplay', outcome='completed')
        history = self.history(accepted, other, self.item(3, review='rejected'),
                               self.item(4, review='pending'), self.item(5, digest=self.old_digest),
                               self.item(6, review='pending', digest=self.old_digest))
        original = deepcopy(history)
        result = specialist_memory(self.project, history)
        self.assertEqual(set(result), {'project_id', 'spec_sha256', 'status', 'handoff_revision',
                                       'roles', 'historical_count', 'note'})
        self.assertEqual((result['project_id'], result['spec_sha256'], result['status'],
                          result['handoff_revision'], result['historical_count']),
                         ('relay', self.digest, 'current', history['revision'], 2))
        self.assertEqual([row['role'] for row in result['roles']],
                         [role['id'] for role in default_profile()['roles']])
        expected = {key: accepted[key] for key in
                    ('task_id', 'attempt', 'outcome', 'summary', 'evidence', 'next_action', 'reviewed_at')}
        expected['handoff_id'] = accepted['id']
        roles = {row['role']: row for row in result['roles']}
        self.assertEqual(roles['architecture'], dict(role='architecture', accepted_count=1, memories=[expected]))
        self.assertEqual(roles['gameplay']['memories'][0]['handoff_id'], other['id'])
        self.assertEqual(roles['content'], dict(role='content', accepted_count=0, memories=[]))
        self.assertEqual(sum(row['accepted_count'] for row in result['roles']), 2)
        for number in (3, 4, 5, 6):
            self.assertNotIn(f'Report {number}', str(result))
        roles['architecture']['memories'][0]['evidence'].append('Client edit')
        self.assertEqual(history, original)

    def test_five_most_recent_reviews_per_role_with_full_counts(self):
        architecture = [self.item(n) for n in range(1, 8)]
        architecture[0] = self.item(1, review_minute=20)
        gameplay = self.item(8, 'gameplay')
        result = specialist_memory(self.project, self.history(*architecture, gameplay))
        roles = {row['role']: row for row in result['roles']}
        self.assertEqual(roles['architecture']['accepted_count'], 7)
        self.assertEqual([memory['task_id'] for memory in roles['architecture']['memories']],
                         ['task-1', 'task-7', 'task-6', 'task-5', 'task-4'])
        self.assertEqual([memory['task_id'] for memory in roles['gameplay']['memories']], ['task-8'])

    def test_valid_ledger_without_current_acceptance_is_empty(self):
        for items, historical in [((), 0), ((self.item(1, digest=self.old_digest),
                                              self.item(2, review='pending'), self.item(3, review='rejected')), 1)]:
            history = self.history(*items)
            with self.subTest(items=items):
                result = specialist_memory(self.project, history)
                self.assertEqual((result['status'], result['historical_count'], result['handoff_revision']),
                                 ('empty', historical, history['revision']))
                self.assertEqual(len(result['roles']), len(default_profile()['roles']))
                self.assertTrue(all(row['accepted_count'] == 0 and row['memories'] == []
                                    for row in result['roles']))

    def test_invalid_or_mismatched_ledger_exposes_no_counts_or_records(self):
        good = self.history(self.item(1), self.item(2, digest=self.old_digest))
        corrupt = deepcopy(good)
        corrupt['items'][0]['changed_paths'] = ['../unsafe']
        for history in (None, {}, dict(good, project_id='other'), dict(good, spec_sha256=self.old_digest),
                        dict(good, revision=True), corrupt):
            with self.subTest(history=history):
                result = specialist_memory(self.project, history)
                self.assertEqual((result['project_id'], result['spec_sha256'], result['status']),
                                 ('relay', self.digest, 'unavailable'))
                self.assertEqual((result['roles'], result['handoff_revision'], result['historical_count']),
                                 ([], None, None))

    def test_unusable_project_identity_is_unavailable(self):
        for project in (None, {}, {'id': 'bad/id', 'spec': {}}, {'id': 'relay'}, {'id': 'relay', 'spec': []},
                        {'id': 'relay', 'spec': {'seed': float('nan')}}):
            with self.subTest(project=project):
                result = specialist_memory(project, self.history(self.item(1)))
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['roles'], [])
                self.assertIsNone(result['handoff_revision'])

    def test_memory_rebuilds_from_the_persisted_ledger_after_restart(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as workspace:
            projects = ProjectStore(root, Path(workspace))
            project = projects.create('Relay', 'city')
            pid, digest = project['id'], spec_digest(project['spec'])

            def request(revision, **action):
                return dict(action=action, expected_revision=revision, spec_sha256=digest)

            tasks = TaskStore(projects)
            tasks.apply(pid, request(0, op='add', task=dict(id='street', title='Check traffic',
                        role='verification', priority=3, gate='manual', depends_on=[])))
            board = tasks.apply(pid, request(1, op='start', task_id='street'))
            order = work_orders(project, board)['orders'][0]
            store = HandoffStore(projects)
            submitted = store.apply(pid, request(0, op='submit', task_id='street', order_id=order['order_id'],
                                    outcome='progress', summary='Traffic clears.', evidence=['Replay 37'],
                                    changed_paths=[], next_action='Check at rush hour.'))
            handoff_id = submitted['items'][0]['id']
            history = store.apply(pid, request(1, op='review', handoff_id=handoff_id, decision='accepted',
                                               note='Reviewed replay 37.'))

            directory = projects.directory(pid)

            def files():
                return {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.iterdir() if p.is_file()}

            before = files()
            expected = specialist_memory(project, history)
            reopened = ProjectStore(root, Path(workspace))
            actual = specialist_memory(reopened.get(pid), HandoffStore(reopened).get(pid))
            self.assertEqual(actual, expected)
            verification = next(row for row in actual['roles'] if row['role'] == 'verification')
            self.assertEqual([memory['handoff_id'] for memory in verification['memories']], [handoff_id])
            self.assertEqual(files(), before)


if __name__ == '__main__':
    unittest.main()
