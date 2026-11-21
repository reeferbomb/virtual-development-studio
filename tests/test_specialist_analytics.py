import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from command_center.dispatch import default_profile
from command_center.handoff_store import HandoffStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.specialist_analytics import specialist_analytics
from command_center.task_store import TaskStore
from command_center.work_orders import work_orders


class SpecialistAnalyticsTests(unittest.TestCase):
    project = {'id': 'relay', 'spec': {'seed': 17}}
    digest = spec_digest(project['spec'])
    old_digest = spec_digest({'seed': 16})

    def report(self, number, order, review, outcome, delay=None, role='content', digest=None):
        created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=number)
        return dict(id=f'{number:032x}', order_id=f'{order:064x}', task_id=f'task-{order}',
                    role=role, attempt=1, board_revision=2, spec_sha256=digest or self.digest,
                    created_at=created.isoformat(), outcome=outcome, summary='Private report',
                    evidence=['Private evidence'], changed_paths=['private-file'], next_action='Private action',
                    review=review, review_note=None if review == 'pending' else 'Private review',
                    reviewed_at=None if delay is None else (created + timedelta(seconds=delay)).isoformat())

    def history(self, *reports):
        return dict(project_id='relay', spec_sha256=self.digest,
                    revision=len(reports) + sum(item['review'] != 'pending' for item in reports),
                    items=sorted(reports, key=lambda item: item['created_at'], reverse=True))

    def test_counts_current_reports_and_distinct_orders_in_profile_order(self):
        history = self.history(self.report(1, 1, 'accepted', 'completed', 0),
                               self.report(2, 1, 'accepted', 'progress', 30.5),
                               self.report(3, 2, 'accepted', 'blocked', 120),
                               self.report(4, 2, 'rejected', 'blocked', 9.25),
                               self.report(5, 2, 'pending', 'completed'),
                               self.report(6, 3, 'rejected', 'completed', 90001, role='verification'),
                               self.report(7, 4, 'accepted', 'progress', 300, digest=self.old_digest))
        original = deepcopy(history)
        result = specialist_analytics(self.project, history)
        self.assertEqual(set(result), {'project_id', 'spec_sha256', 'status', 'handoff_revision',
                                       'historical_count', 'roles', 'note'})
        self.assertEqual((result['project_id'], result['spec_sha256'], result['status'],
                          result['handoff_revision'], result['historical_count']),
                         ('relay', self.digest, 'current', 13, 1))
        self.assertEqual([row['role'] for row in result['roles']], [r['id'] for r in default_profile()['roles']])
        rows = {row['role']: row for row in result['roles']}
        self.assertEqual(rows['content'], dict(role='content', submitted=5, accepted=3, rejected=1, pending=1,
                                               unique_orders=2, completed=1, blocked=1, progress=1,
                                               median_review_seconds=19.875))
        self.assertEqual(rows['verification'], dict(role='verification', submitted=1, accepted=0, rejected=1,
                                                    pending=0, unique_orders=1, completed=0, blocked=0,
                                                    progress=0, median_review_seconds=90001))
        for role in ('architecture', 'gameplay', 'ui', 'build_operations'):
            self.assertEqual(rows[role], dict(role=role, submitted=0, accepted=0, rejected=0, pending=0,
                                               unique_orders=0, completed=0, blocked=0, progress=0,
                                               median_review_seconds=None))
        self.assertNotIn('private', str(result).lower())
        self.assertEqual(history, original)

    def test_empty_historical_only_and_pending_only_are_distinguished(self):
        old = self.report(1, 1, 'accepted', 'blocked', 900, digest=self.old_digest)
        pending = self.report(2, 2, 'pending', 'progress')
        for reports, status, historical in [((), 'empty', 0), ((old,), 'empty', 1),
                                             ((old, pending), 'current', 1)]:
            with self.subTest(status=status, historical=historical):
                history = self.history(*reports)
                result = specialist_analytics(self.project, history)
                self.assertEqual((result['status'], result['historical_count'], result['handoff_revision']),
                                 (status, historical, history['revision']))
                self.assertEqual(sum(row['pending'] for row in result['roles']), int(pending in reports))
                self.assertEqual(len(result['roles']), 6)
                self.assertTrue(all(row['median_review_seconds'] is None for row in result['roles']))

    def test_corrupt_historical_or_current_data_and_cross_scope_fail_closed(self):
        current = self.report(1, 1, 'accepted', 'progress', 7)
        old = self.report(2, 2, 'rejected', 'completed', 3, digest=self.old_digest)
        history = self.history(current, old)
        bad_inputs = (None, {}, dict(history, project_id='other'), dict(history, spec_sha256=self.old_digest),
                      dict(history, revision=True), self.history(current, dict(old, evidence=[])),
                      self.history(dict(current, reviewed_at='2026-01-01T23:59:59+00:00')),
                      self.history(dict(current, reviewed_at='2026-01-02T01:00:00+01:00')),
                      self.history(current, dict(old, order_id=current['order_id'])))
        for ledger in bad_inputs:
            with self.subTest(ledger=ledger):
                result = specialist_analytics(self.project, ledger)
                self.assertEqual((result['project_id'], result['spec_sha256']), ('relay', self.digest))
                self.assertEqual((result['status'], result['roles'], result['historical_count'],
                                  result['handoff_revision']), ('unavailable', [], None, None))

    def test_invalid_project_identity_exposes_no_metrics(self):
        for project in (None, {}, {'id': 'bad/id', 'spec': {}}, {'id': 'relay'}, {'id': 'relay', 'spec': []},
                        {'id': 'relay', 'spec': {'seed': float('nan')}}):
            with self.subTest(project=project):
                result = specialist_analytics(project, self.history())
                self.assertEqual((result['status'], result['roles'], result['historical_count'],
                                  result['handoff_revision']), ('unavailable', [], None, None))

    def test_reopens_real_ledger_with_repeated_reports_on_one_claim(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as workspace:
            projects = ProjectStore(root, Path(workspace))
            project = projects.create('Station', 'city')
            pid = project['id']
            digest = spec_digest(project['spec'])

            def request(revision, **action):
                return dict(action=action, expected_revision=revision, spec_sha256=digest)

            tasks = TaskStore(projects)
            tasks.apply(pid, request(0, op='add', task=dict(id='map', title='Draw map', role='content',
                                                            priority=3, gate='manual', depends_on=[])))
            board = tasks.apply(pid, request(1, op='start', task_id='map'))
            order = work_orders(project, board)['orders'][0]
            report = dict(op='submit', task_id='map', order_id=order['order_id'], outcome='completed',
                          summary='Map drawn.', evidence=['map.svg'], changed_paths=['map.svg'],
                          next_action='Inspect the map.')
            store = HandoffStore(projects)
            first = store.apply(pid, request(0, **report))['items'][0]['id']
            store.apply(pid, request(1, **report))
            store.apply(pid, request(2, op='review', handoff_id=first, decision='accepted', note='Checked map.'))
            reopened = ProjectStore(root, Path(workspace))
            history = HandoffStore(reopened).get(pid)
            result = specialist_analytics(reopened.get(pid), history)
            content = next(row for row in result['roles'] if row['role'] == 'content')
            self.assertEqual((result['status'], result['handoff_revision'], result['historical_count']),
                             ('current', 3, 0))
            self.assertEqual((content['submitted'], content['accepted'], content['completed'],
                              content['pending'], content['unique_orders']), (2, 1, 1, 1, 1))
            self.assertGreaterEqual(content['median_review_seconds'], 0)


if __name__ == '__main__':
    unittest.main()
