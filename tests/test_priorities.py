from copy import deepcopy
import unittest

from command_center.priorities import rank_tasks
from command_center.provenance import spec_digest
from command_center.task_store import _projection


PROJECT = {'id': 'studio', 'spec': {'seed': 26}}
DIGEST = spec_digest(PROJECT['spec'])


def task(task_id, *dependencies, role='content', priority=3, status='pending'):
    return dict(id=task_id, title='Review ' + task_id, role=role, priority=priority, gate='manual',
                depends_on=list(dependencies), status=status, attempts=int(status != 'pending'),
                reason='Awaiting review' if status == 'blocked' else None, job_id=None,
                evidence=['Reviewed'] if status == 'completed' else [])


def board(tasks, saved=DIGEST):
    return _projection('studio', DIGEST, dict(project_id='studio', spec_sha256=saved, revision=3, tasks=tasks))


class PriorityTests(unittest.TestCase):
    def test_missing_empty_and_stale_boards_preserve_verified_identity(self):
        for snapshot, status, revision in [(_projection('studio', DIGEST, None), 'empty', 0),
                                           (board([]), 'current', 3), (board([task('old')], 'a' * 64), 'stale', 3),
                                           (None, 'unavailable', None)]:
            with self.subTest(status=status):
                out = rank_tasks(PROJECT, snapshot)
                self.assertEqual(set(out), {'project_id', 'spec_sha256', 'board_revision', 'status',
                                            'candidates', 'recommendations', 'note'})
                self.assertEqual((out['project_id'], out['spec_sha256'], out['board_revision'], out['status']),
                                 ('studio', DIGEST, revision, status))
                self.assertEqual((out['candidates'], out['recommendations']), ([], []))
                self.assertTrue(out['note'].strip())

    def test_tampered_boards_and_bad_project_identity_withhold_work(self):
        snapshot = board([task('art')])
        for source in [dict(snapshot, revision=True), dict(snapshot, ready_task_ids=[]),
                       dict(snapshot, assignments=[]), dict(snapshot, project_id='other'),
                       dict(snapshot, spec_sha256='a' * 64), dict(snapshot, tasks=[dict(task('art'), priority=True)]),
                       dict(snapshot, summary=dict(snapshot['summary'], ready=True))]:
            with self.subTest(source=source):
                out = rank_tasks(PROJECT, source)
                self.assertEqual((out['status'], out['board_revision'], out['spec_sha256']),
                                 ('unavailable', None, DIGEST))
                self.assertEqual((out['candidates'], out['recommendations']), ([], []))
        for project, project_id in [(None, None), ({'id': '../studio', 'spec': {}}, None),
                                    ({'id': 'studio', 'spec': []}, 'studio'),
                                    ({'id': 'studio', 'spec': {'seed': float('nan')}}, 'studio')]:
            with self.subTest(project=project):
                out = rank_tasks(project, snapshot)
                self.assertEqual((out['status'], out['project_id'], out['spec_sha256'], out['board_revision']),
                                 ('unavailable', project_id, None, None))
                self.assertEqual((out['candidates'], out['recommendations']), ([], []))

    def test_ranks_priority_then_distinct_descendants_then_chain_then_id(self):
        tasks = [task('urgent', role='ui', priority=5), task('z-depth'), task('art', 'z-depth'),
                 task('audio', 'z-depth'), task('finish', 'art', 'audio'), task('a-wide'),
                 task('one', 'a-wide'), task('two', 'a-wide'), task('three', 'a-wide'),
                 task('m-long'), task('middle', 'm-long'), task('end', 'middle'),
                 task('z-tie', role='verification'), task('a-tie', role='architecture')]
        expected = [('urgent', 5, 0, 1), ('z-depth', 3, 3, 3), ('a-wide', 3, 3, 2),
                    ('m-long', 3, 2, 3), ('a-tie', 3, 0, 1), ('z-tie', 3, 0, 1)]
        for order in (tasks, list(reversed(tasks))):
            with self.subTest(first=order[0]['id']):
                snapshot = board(order)
                original = deepcopy(snapshot)
                out = rank_tasks(PROJECT, snapshot)
                self.assertEqual([(r['task_id'], r['priority'], r['downstream_count'], r['chain_length'])
                                  for r in out['candidates']], expected)
                self.assertEqual([r['task_id'] for r in out['recommendations']],
                                 ['urgent', 'z-depth', 'a-tie', 'z-tie'])
                self.assertEqual(out['recommendations'][1], dict(task_id='z-depth', role='content',
                                 title='Review z-depth', priority=3, downstream_count=3, chain_length=3))
                # The advisory tie-break can choose a different task for this role than the scheduler.
                self.assertIn('a-wide', [row['task_id'] for row in snapshot['assignments']])
                out['recommendations'][1]['title'] = 'Edited locally'
                self.assertEqual(snapshot, original)

    def test_candidates_require_ready_tasks_and_idle_roles(self):
        snapshot = board([task('done', status='completed'), task('working', role='ui', status='running'),
                          task('ready-but-busy', role='ui', priority=5), task('blocked', status='blocked'),
                          task('wait-for-blocker', 'blocked'), task('wait-for-worker', 'working'),
                          task('ready', 'done'), task('also-ready', priority=2, role='content'),
                          task('join', 'ready', 'blocked')])
        out = rank_tasks(PROJECT, snapshot)
        self.assertEqual([r['task_id'] for r in out['candidates']], ['ready', 'also-ready'])
        self.assertEqual(out['recommendations'], [dict(task_id='ready', role='content', title='Review ready',
                                                      priority=3, downstream_count=1, chain_length=2)])
