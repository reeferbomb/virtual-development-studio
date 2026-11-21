import unittest
from copy import deepcopy

from command_center.dependency_impact import dependency_impact
from command_center.provenance import spec_digest
from command_center.task_store import _projection


PROJECT = {'id': 'studio', 'spec': {'seed': 25}}
DIGEST = spec_digest(PROJECT['spec'])


def task(task_id, *dependencies, status='pending', role='content'):
    return dict(id=task_id, title=task_id, role=role, priority=3, gate='manual',
                depends_on=list(dependencies), status=status, attempts=int(status != 'pending'),
                evidence=['Reviewed'] if status == 'completed' else [], job_id=None,
                reason='Waiting for review' if status == 'blocked' else None)


def board(tasks, saved=DIGEST):
    record = dict(project_id='studio', revision=7, spec_sha256=saved, tasks=tasks)
    return _projection('studio', DIGEST, record)


class DependencyImpactTests(unittest.TestCase):
    def test_board_without_a_record_and_current_board_without_tasks(self):
        for snapshot, status, revision in [(_projection('studio', DIGEST, None), 'empty', 0),
                                           (board([]), 'current', 7)]:
            with self.subTest(status=status):
                result = dependency_impact(PROJECT, snapshot)
                self.assertEqual(set(result), {'project_id', 'spec_sha256', 'board_revision', 'status',
                                                'blocked', 'affected_task_ids', 'critical_chain', 'note'})
                self.assertEqual((result['project_id'], result['spec_sha256']), ('studio', DIGEST))
                self.assertEqual((result['status'], result['board_revision']), (status, revision))
                self.assertEqual((result['blocked'], result['affected_task_ids'], result['critical_chain']),
                                 ([], [], []))
                self.assertIsInstance(result['note'], str)
                self.assertTrue(result['note'].strip())

    def test_stale_board_keeps_revision_and_withholds_historical_task_details(self):
        snapshot = board([task('old-art', status='blocked')], saved='f' * 64)
        result = dependency_impact(PROJECT, snapshot)
        self.assertEqual((result['status'], result['board_revision'], result['spec_sha256']),
                         ('stale', 7, DIGEST))
        self.assertEqual((result['blocked'], result['affected_task_ids'], result['critical_chain']),
                         ([], [], []))
        self.assertNotIn('old-art', repr(result))

    def test_foreign_and_inconsistent_projections_fail_closed(self):
        snapshot = board([task('one', status='blocked'), task('two', 'one')])
        cyclic = deepcopy(snapshot)
        cyclic['tasks'][0]['depends_on'] = ['two']
        unknown = deepcopy(snapshot)
        unknown['tasks'][1]['depends_on'] = ['missing']
        for invalid in (None, [], {}, dict(snapshot, project_id='other'), dict(snapshot, spec_sha256='f' * 64),
                        dict(snapshot, board_spec_sha256='f' * 64), dict(snapshot, state='empty'),
                        dict(snapshot, revision=True), dict(snapshot, revision=0),
                        dict(snapshot, ready_task_ids=['two']), dict(snapshot, tasks=snapshot['tasks'] * 2),
                        dict(snapshot, summary=dict(snapshot['summary'], blocked=True)), cyclic, unknown):
            with self.subTest(invalid=invalid):
                result = dependency_impact(PROJECT, invalid)
                self.assertEqual((result['project_id'], result['spec_sha256']), ('studio', DIGEST))
                self.assertEqual((result['status'], result['board_revision']), ('unavailable', None))
                self.assertEqual((result['blocked'], result['affected_task_ids'], result['critical_chain']),
                                 ([], [], []))

    def test_malformed_project_withholds_board_details(self):
        snapshot = board([task('one', status='blocked')])
        for invalid in (None, [], {}, dict(PROJECT, id='../other'), dict(PROJECT, spec=[]),
                        dict(PROJECT, spec={'number': float('nan')})):
            with self.subTest(project=invalid):
                result = dependency_impact(invalid, snapshot)
                self.assertEqual((result['status'], result['board_revision'], result['spec_sha256']),
                                 ('unavailable', None, None))
                self.assertEqual((result['blocked'], result['affected_task_ids'], result['critical_chain']),
                                 ([], [], []))

    def test_shared_downstream_tasks_count_once_per_blocker_and_in_the_union(self):
        snapshot = board([task('ship', 'audio', 'art'), task('art', 'assets'),
                          task('isolated', status='blocked', role='ui'), task('audio', 'assets', 'mix'),
                          task('assets', 'design', status='blocked'), task('mix', status='blocked'),
                          task('design', status='completed'), task('unrelated', status='running')])
        original = deepcopy((PROJECT, snapshot))
        result = dependency_impact(PROJECT, snapshot)
        self.assertEqual(result['blocked'], [
            dict(task_id='assets', role='content', reason='Waiting for review',
                 affected_task_ids=['art', 'audio', 'ship'], affected_count=3),
            dict(task_id='isolated', role='ui', reason='Waiting for review',
                 affected_task_ids=[], affected_count=0),
            dict(task_id='mix', role='content', reason='Waiting for review',
                 affected_task_ids=['audio', 'ship'], affected_count=2),
        ])
        self.assertEqual(result['affected_task_ids'], ['art', 'audio', 'ship'])
        self.assertEqual(dependency_impact(PROJECT, snapshot), result)
        result['affected_task_ids'].clear()
        result['blocked'][0]['affected_task_ids'].clear()
        self.assertEqual((PROJECT, snapshot), original)

    def test_remaining_chain_uses_depth_then_lexical_path_across_all_work(self):
        # The longest paths start at b or z. At b, w and x lead to equally long tails.
        tasks = [task('z'), task('z-next', 'z'), task('a-z-end', 'z-next'),
                 task('b', 'done', status='running'), task('x', 'b'), task('w', 'b'),
                 task('a-x-end', 'x'), task('z-w-end', 'w'), task('done', status='completed'),
                 task('a', status='blocked'), task('a-next', 'a')]
        for ordered in (tasks, list(reversed(tasks))):
            with self.subTest(order=[t['id'] for t in ordered]):
                result = dependency_impact(PROJECT, board(ordered))
                self.assertEqual(result['critical_chain'], ['b', 'w', 'z-w-end'])
                self.assertEqual(result['affected_task_ids'], ['a-next'])

    def test_no_remaining_work_and_single_pending_task(self):
        for tasks, expected in [([task('done', status='completed')], []),
                                ([task('only', 'done'), task('done', status='completed')], ['only'])]:
            with self.subTest(expected=expected):
                result = dependency_impact(PROJECT, board(tasks))
                self.assertEqual(result['critical_chain'], expected)
                self.assertEqual((result['blocked'], result['affected_task_ids']), ([], []))
