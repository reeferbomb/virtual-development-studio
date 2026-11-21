import unittest
from copy import deepcopy

from command_center.forecast import forecast
from command_center.provenance import spec_digest
from command_center.scheduler import MAX_TASKS
from command_center.task_store import _projection


PROJECT = {'id': 'wave-test', 'spec': {'seed': 25}}
DIGEST = spec_digest(PROJECT['spec'])


def task(identifier, role='gameplay', *, priority=3, after=(), status='pending', gate='manual'):
    return dict(id=identifier, title=identifier, role=role, priority=priority, gate=gate,
                depends_on=list(after), status=status, attempts=int(status != 'pending'),
                evidence=['Verified'] if status == 'completed' else [],
                reason='Needs review' if status == 'blocked' else None,
                job_id='a' * 32 if gate == 'build' and status == 'completed' else None)


def board(tasks, saved_digest=DIGEST):
    record = dict(project_id=PROJECT['id'], spec_sha256=saved_digest, revision=4, tasks=tasks)
    return _projection(PROJECT['id'], DIGEST, record)


class ForecastTests(unittest.TestCase):
    def test_running_holds_its_role_and_dependencies_unlock_next_wave(self):
        tasks = [
            task('queued', priority=5),
            task('already-running', status='running', gate='build'),
            task('finished', 'content', status='completed'),
            task('b-ui', 'ui', priority=4),
            task('a-ui', 'ui', priority=4, after=['finished']),
            task('join', 'verification', after=['already-running', 'a-ui']),
            task('low-ui', 'ui', priority=1),
        ]
        snapshot = board(tasks)
        project = deepcopy(PROJECT)
        before = deepcopy((project, snapshot))
        result = forecast(project, snapshot)
        self.assertEqual(result['waves'], [
            {'wave': 1, 'task_ids': ['already-running', 'a-ui']},
            {'wave': 2, 'task_ids': ['queued', 'b-ui', 'join']},
            {'wave': 3, 'task_ids': ['low-ui']},
        ])
        self.assertEqual((result['status'], result['minimum_dependency_waves'],
                          result['remaining_tasks'], result['unscheduled']), ('current', 2, 6, []))
        self.assertEqual(forecast(project, board(list(reversed(tasks)))), result)
        self.assertEqual(forecast(project, snapshot), result)
        result['waves'][0]['task_ids'].clear()
        self.assertEqual((project, snapshot), before)

    def test_blocked_branch_never_unlocks_its_transitive_dependents(self):
        snapshot = board([
            task('independent', after=['already-done']),
            task('blocked-branch', after=['blocker', 'independent']),
            task('grandchild', after=['blocked-branch']),
            task('blocker', status='blocked'),
            task('already-done', status='completed', gate='build'),
        ])
        result = forecast(PROJECT, snapshot)
        self.assertEqual(result['waves'], [{'wave': 1, 'task_ids': ['independent']}])
        self.assertEqual(result['unscheduled'], ['blocked-branch', 'blocker', 'grandchild'])
        self.assertEqual((result['remaining_tasks'], result['minimum_dependency_waves']), (4, None))
        only_blocked = forecast(PROJECT, board([task('blocker', status='blocked')]))
        self.assertEqual(only_blocked['waves'], [])
        self.assertEqual(only_blocked['unscheduled'], ['blocker'])

    def test_empty_boards_and_completed_work(self):
        empty = _projection(PROJECT['id'], DIGEST, None)
        for snapshot, status, revision in [(empty, 'empty', 0), (board([]), 'current', 4),
                (board([task('shipped', status='completed')]), 'current', 4)]:
            with self.subTest(status=status, tasks=snapshot['tasks']):
                result = forecast(PROJECT, snapshot)
                self.assertEqual(result, dict(project_id=PROJECT['id'], spec_sha256=DIGEST,
                    board_revision=revision, status=status, waves=[], unscheduled=[], remaining_tasks=0,
                    minimum_dependency_waves=0, note=result['note']))
                self.assertTrue(result['note'].strip())

    def test_foreign_stale_tampered_and_unreadable_snapshots(self):
        snapshot = board([task('ready')])
        stale = forecast(PROJECT, board([task('old-work')], saved_digest='0' * 64))
        self.assertEqual((stale['status'], stale['board_revision'], stale['waves'], stale['unscheduled'],
                          stale['minimum_dependency_waves']), ('stale', 4, [], [], None))
        for invalid in (None, {}, dict(snapshot, ready_task_ids=[]), dict(snapshot, assignments=[]),
                        dict(snapshot, state='stale'), dict(snapshot, project_id='foreign'),
                        dict(snapshot, spec_sha256='0' * 64), dict(snapshot, revision=True),
                        dict(snapshot, summary=dict(snapshot['summary'], ready=True)),
                        dict(snapshot, tasks=[task('cycle', after=['cycle'])]),
                        dict(snapshot, tasks=[task('one', status='running'), task('two', status='running')])):
            with self.subTest(board=invalid):
                result = forecast(PROJECT, invalid)
                self.assertEqual(result, dict(project_id=PROJECT['id'], spec_sha256=DIGEST,
                    board_revision=None, status='unavailable', waves=[], unscheduled=[], remaining_tasks=0,
                    minimum_dependency_waves=None, note=result['note']))
                self.assertTrue(result['note'].strip())
        for project in (None, {}, dict(PROJECT, id='../project'), dict(PROJECT, spec=[]),
                        dict(PROJECT, spec={'bad': float('nan')})):
            with self.subTest(project=project):
                self.assertEqual(forecast(project, snapshot)['status'], 'unavailable')

    def test_longest_supported_chain(self):
        chain = [task(f't-{i}', after=[f't-{i - 1}'] if i else []) for i in range(MAX_TASKS)]
        result = forecast(PROJECT, board(chain[::-1]))
        self.assertEqual(result['minimum_dependency_waves'], MAX_TASKS)
        self.assertEqual(result['waves'], [{'wave': i + 1, 'task_ids': [f't-{i}']} for i in range(MAX_TASKS)])


if __name__ == '__main__':
    unittest.main()
