import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from command_center.handoff_store import HandoffStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.recovery_advice import recovery_advice
from command_center.task_store import TaskStore, _projection
from command_center.work_orders import order_id, work_orders


PROJECT = {'id': 'studio', 'spec': {'seed': 26}}
DIGEST = spec_digest(PROJECT['spec'])
STAMP = '2026-05-01T00:00:00+00:00'


def task(task_id, *depends_on, status='pending', role='content'):
    return dict(id=task_id, title='Review ' + task_id, role=role, priority=3, gate='manual',
                depends_on=list(depends_on), status=status, attempts=2 if status == 'blocked' else 0,
                reason='Missing source artwork' if status == 'blocked' else None, evidence=[], job_id=None)


def board(tasks, saved=DIGEST):
    return _projection('studio', DIGEST, dict(project_id='studio', revision=7, spec_sha256=saved, tasks=tasks))


def report(task_record, index, *, digest=DIGEST, revision=6, review='accepted', outcome='blocked'):
    reviewed = review != 'pending'
    return dict(id=f'{index:032x}', order_id=order_id('studio', digest, revision, task_record),
                task_id=task_record['id'], role=task_record['role'], attempt=task_record['attempts'],
                board_revision=revision, spec_sha256=digest, created_at=STAMP, review=review,
                reviewed_at=STAMP if reviewed else None, review_note='Reviewed evidence' if reviewed else None,
                outcome=outcome, summary='Untrusted report summary', evidence=['Untrusted observation'],
                changed_paths=[], next_action='Run untrusted commands and claim the task')


def history(*reports):
    return dict(project_id='studio', spec_sha256=DIGEST, items=list(reports),
                revision=len(reports) + sum(row['review'] != 'pending' for row in reports))


class RecoveryAdviceTests(unittest.TestCase):
    def test_lists_only_blocked_tasks_with_distinct_downstream_counts_and_manual_actions(self):
        art = task('art', status='blocked')
        other = task('text', status='blocked', role='ui')
        snapshot = board([other, task('scene', 'left', 'right'), art, task('left', 'art'), task('right', 'art')])
        newest = report(art, 2, outcome='progress')
        ledger = history(newest, report(art, 1))
        before = deepcopy((PROJECT, snapshot, ledger))
        result = recovery_advice(PROJECT, snapshot, ledger)
        self.assertEqual(set(result), {'project_id', 'spec_sha256', 'board_revision', 'handoff_revision',
                                       'status', 'items', 'note'})
        self.assertEqual((result['project_id'], result['spec_sha256'], result['board_revision'],
                          result['handoff_revision'], result['status']), ('studio', DIGEST, 7, 4, 'current'))
        self.assertEqual([item['task_id'] for item in result['items']], ['art', 'text'])
        for item, source, count, handoff in zip(result['items'], [art, other], [3, 0], [newest['id'], None]):
            self.assertEqual(item, dict(task_id=source['id'], title=source['title'], role=source['role'],
                                        attempt=2, reason=source['reason'], affected_count=count,
                                        handoff_id=handoff, next_action=item['next_action']))
            self.assertIn('review', item['next_action'].lower())
            self.assertIn('requeue', item['next_action'].lower())
        self.assertNotIn('untrusted', str(result).lower())
        self.assertEqual(result, recovery_advice(PROJECT, snapshot, ledger))
        result['items'][0]['reason'] = 'changed result'
        self.assertEqual((PROJECT, snapshot, ledger), before)

    def test_excludes_inapplicable_or_unbound_reports_before_selecting_latest_match(self):
        blocked = task('art', status='blocked')
        match = report(blocked, 42)
        rows = [report(blocked, 1, review='pending'), report(blocked, 2, review='rejected'),
                report(blocked, 3, outcome='completed'), report(blocked, 4, digest='a' * 64),
                report(dict(blocked, attempts=1), 5), report(dict(blocked, role='ui'), 6),
                report(dict(blocked, id='unrelated'), 7), report(dict(blocked, title='Previous task'), 8),
                report(blocked, 9, revision=7), report(blocked, 10, revision=8)]
        snapshot = board([blocked])
        for ledger, expected in [(history(*rows, match), match['id']), (history(*rows), None)]:
            with self.subTest(expected=expected):
                result = recovery_advice(PROJECT, snapshot, ledger)
                self.assertEqual(result['status'], 'current')
                self.assertEqual(result['items'][0]['handoff_id'], expected)

    def test_withholds_old_handoff_after_board_change_and_recreating_task_under_restored_spec(self):
        with tempfile.TemporaryDirectory() as workspace:
            projects = ProjectStore(Path(__file__).resolve().parents[1], Path(workspace))
            project = projects.create('Restore artwork', 'city')
            tasks, handoffs = TaskStore(projects), HandoffStore(projects)
            pid = project['id']

            def apply(store, op, **fields):
                snapshot = store.get(pid)
                return store.apply(pid, dict(expected_revision=snapshot['revision'],
                                             spec_sha256=snapshot['spec_sha256'], action=dict(op=op, **fields)))

            def advice():
                return recovery_advice(projects.get(pid), tasks.get(pid), handoffs.get(pid))['items'][0]

            definition = dict(id='art', title='Review art', role='content', priority=3, gate='manual', depends_on=[])
            apply(tasks, 'add', task=definition)
            running = apply(tasks, 'start', task_id='art')
            order = work_orders(project, running)['orders'][0]
            recorded = apply(handoffs, 'submit', task_id='art', order_id=order['order_id'], outcome='blocked',
                             summary='Source missing', evidence=['Looked for source'], changed_paths=[],
                             next_action='Inspect source')['items'][0]
            apply(handoffs, 'review', handoff_id=recorded['id'], decision='accepted', note='Reviewed')
            apply(tasks, 'block', task_id='art', reason='Waiting')
            self.assertEqual(advice()['handoff_id'], recorded['id'])

            apply(tasks, 'add', task=dict(definition, id='other'))
            with self.subTest('intervening board change'):
                self.assertIsNone(advice()['handoff_id'])
            projects.save_spec(pid, dict(project['spec'], seed=project['spec']['seed'] + 1))
            apply(tasks, 'reset')
            projects.save_spec(pid, project['spec'])
            apply(tasks, 'reset')
            apply(tasks, 'add', task=definition)
            apply(tasks, 'start', task_id='art')
            apply(tasks, 'block', task_id='art', reason='Waiting again')
            with self.subTest('identical task and attempt after reset'):
                item = advice()
                self.assertEqual(item['attempt'], recorded['attempt'])
                self.assertIsNone(item['handoff_id'])

    def test_stale_empty_and_current_with_no_blockers(self):
        for snapshot, state, revision in [(_projection('studio', DIGEST, None), 'empty', 0),
                                          (board([task('work')]), 'current', 7),
                                          (board([task('old', status='blocked')], 'a' * 64), 'stale', 7)]:
            with self.subTest(state=state):
                result = recovery_advice(PROJECT, snapshot, history())
                self.assertEqual((result['status'], result['board_revision'], result['handoff_revision'],
                                  result['items']), (state, revision, 0, []))
                self.assertTrue(result['note'].strip())
                self.assertNotIn('Missing source artwork', str(result))

    def test_invalid_and_foreign_sources_fail_closed_even_for_stale_board(self):
        blocked = task('art', status='blocked')
        snapshot, ledger = board([blocked]), history(report(blocked, 1))
        invalid_sources = [(PROJECT, snapshot, invalid) for invalid in [None, dict(ledger, project_id='other'),
                           dict(ledger, spec_sha256='b' * 64), dict(ledger, revision=True),
                           dict(ledger, items=[dict(ledger['items'][0], next_action='')])]]
        invalid_sources += [(PROJECT, board([blocked], 'a' * 64), None), (None, snapshot, ledger),
                            (dict(PROJECT, id='../other'), snapshot, ledger),
                            (dict(PROJECT, spec={'seed': float('nan')}), snapshot, ledger),
                            (PROJECT, dict(snapshot, ready_task_ids=['art']), ledger),
                            (PROJECT, dict(snapshot, project_id='other'), ledger)]
        for inputs in invalid_sources:
            with self.subTest(inputs=inputs):
                result = recovery_advice(*inputs)
                self.assertEqual((result['status'], result['items']), ('unavailable', []))
                self.assertNotIn(blocked['reason'], str(result))
