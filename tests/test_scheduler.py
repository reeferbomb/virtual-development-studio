import copy
import unittest

from command_center.dispatch import default_profile
from command_center.scheduler import apply_action, schedule, validate_tasks


def definition(identifier='alpha', **changes):
    return {
        'id': identifier, 'title': 'Review the scene', 'role': 'architecture',
        'priority': 3, 'depends_on': [], 'gate': 'manual', **changes,
    }


def record(identifier='alpha', **changes):
    return {
        **definition(identifier), 'status': 'pending', 'evidence': [],
        'reason': None, 'job_id': None, 'attempts': 0, **changes,
    }


class SchedulerTests(unittest.TestCase):
    def test_empty_and_independent_add(self):
        self.assertIsNone(validate_tasks([]))
        self.assertEqual(schedule([]), {
            'summary': dict(total=0, completed=0, ready=0, running=0, blocked=0, waiting=0),
            'ready_task_ids': [], 'assignments': [],
        })
        original = [record()]
        action = {'op': 'add', 'task': definition('beta', depends_on=['alpha'])}
        saved = apply_action(original, action)
        self.assertEqual(saved, [record(), record('beta', depends_on=['alpha'])])
        saved[0]['evidence'].append('new')
        saved[1]['depends_on'].clear()
        self.assertEqual(original, [record()])
        self.assertEqual(action['task']['depends_on'], ['alpha'])

    def test_order_and_capacity_across_all_roles(self):
        roles = default_profile()['roles']
        tasks = [record('task-' + str(i), role=r['id'], priority=1 + i % 5) for i, r in enumerate(roles)]
        tasks.extend([
            record('a-review', role='verification', priority=3),
            record('waiting', depends_on=['task-0']),
            record('finished', status='completed', evidence=['ok'], attempts=1),
            record('busy', role='content', status='running', attempts=1),
            record('blocker', role='ui', status='blocked', attempts=1, reason='Review requested'),
        ])
        ready = ['task-4', 'task-3', 'a-review', 'task-2', 'task-1', 'task-0', 'task-5']
        result = schedule(tasks)
        self.assertEqual(result, schedule(list(reversed(tasks))))
        self.assertEqual(result['ready_task_ids'], ready)
        self.assertEqual(result['summary'], dict(total=11, ready=7, running=1, blocked=1, completed=1, waiting=1))
        by_id = {t['id']: t for t in tasks}
        by_role = {r['id']: r for r in roles}
        expected = []
        for task_id in ['task-3', 'a-review', 'task-1', 'task-0', 'task-5']:
            role_id = by_id[task_id]['role']
            role = by_role[role_id]
            expected.append(dict(task_id=task_id, role=role_id, model_id=role['model_id'],
                                 reasoning_effort=role['reasoning_effort']))
        self.assertEqual(result['assignments'], expected)

    def test_sequential_starts_and_dependency_release(self):
        tasks = [record(), record('another'), record('beta', role='ui', depends_on=['alpha'])]
        running = apply_action(tasks, {'op': 'start', 'task_id': 'alpha'})
        for task_id in ('alpha', 'another', 'beta'):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                apply_action(running, {'op': 'start', 'task_id': task_id})
        self.assertEqual(running[0]['attempts'], 1)
        self.assertEqual(schedule(running)['assignments'], [])
        evidence = ['Verified the scene']
        done = apply_action(running, {'op': 'complete', 'task_id': 'alpha', 'evidence': evidence})
        self.assertEqual(done[0], record(status='completed', evidence=evidence, attempts=1))
        evidence.append('external change')
        self.assertEqual(done[0]['evidence'], ['Verified the scene'])
        self.assertEqual(schedule(done)['ready_task_ids'], ['another', 'beta'])

    def test_block_reassign_and_retry(self):
        running = apply_action([record()], {'op': 'start', 'task_id': 'alpha'})
        blocked = apply_action(running, {'op': 'block', 'task_id': 'alpha', 'reason': 'Missing source'})
        self.assertEqual(blocked[0], record(status='blocked', reason='Missing source', attempts=1))
        moved = apply_action(blocked, {'op': 'reassign', 'task_id': 'alpha', 'role': 'verification'})
        self.assertEqual(moved[0], blocked[0] | {'role': 'verification'})
        pending = apply_action(moved, {'op': 'requeue', 'task_id': 'alpha'})
        self.assertEqual(pending[0], record(role='verification', attempts=1))
        moved_back = apply_action(pending, {'op': 'reassign', 'task_id': 'alpha', 'role': 'architecture'})
        retry = apply_action(moved_back, {'op': 'start', 'task_id': 'alpha'})
        self.assertEqual(retry[0]['attempts'], 2)
        self.assertEqual(apply_action(retry, {'op': 'requeue', 'task_id': 'alpha'}), [record(attempts=2)])

    def test_build_gate_and_manual_evidence(self):
        build = [record(status='running', attempts=1, gate='build')]
        manual = [record(status='running', attempts=1)]
        job_id = 'ab12' * 8
        completion = {'op': 'complete', 'task_id': 'alpha', 'evidence': ['passed']}
        done = apply_action(build, completion | {'job_id': job_id}, build_verified=True)
        self.assertEqual(done, [record(status='completed', attempts=1, gate='build', evidence=['passed'], job_id=job_id)])
        for tasks, action, verified in (
            (build, completion, True), (build, completion | {'job_id': job_id}, False),
            (build, completion | {'job_id': job_id}, 1), (build, completion | {'job_id': 'bad'}, True),
            (manual, completion | {'job_id': job_id}, True), (manual, completion | {'job_id': None}, False),
            (manual, completion | {'evidence': []}, False), (manual, completion | {'evidence': [' ']}, False),
        ):
            with self.subTest(action=action, verified=verified), self.assertRaises(ValueError):
                apply_action(tasks, action, build_verified=verified)

    def test_schema_limits_and_shape_errors_are_value_errors(self):
        invalid_fields = {
            'id': [None, 'A', '-bad', 'a--b', 'x' * 65], 'title': ['', '  ', 'x' * 121, '\ud800'],
            'role': [['ui'], 'other'], 'priority': [False, 0, 6, 3.0], 'status': [[], 'ready'],
            'gate': [[], 'auto'], 'attempts': [False, -1, 1.0], 'job_id': [[], 'A' * 32],
            'depends_on': [(), [3], ['missing'], ['alpha']],
            'reason': [[], ' ', 'x' * 513], 'evidence': [(), [None], ['x' * 513], ['ok'] * 9],
        }
        for field, invalid in invalid_fields.items():
            for value in invalid:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    validate_tasks([record(**{field: value})])
        valid_max = [record('t-' + str(i)) for i in range(100)]
        self.assertIsNone(validate_tasks(valid_max))
        for invalid in (None, (), [None], [record(extra=True)], [definition()], valid_max + [record()]):
            with self.subTest(invalid=type(invalid)), self.assertRaises(ValueError):
                validate_tasks(invalid)

    def test_boundary_lengths_for_active_state_fields(self):
        running = [record(status='running', attempts=1)]
        completion = {'op': 'complete', 'task_id': 'alpha', 'evidence': ['é' * 512] * 8}
        self.assertEqual(len(apply_action(running, completion)[0]['evidence']), 8)
        for entries in (['é' * 513], ['ok'] * 9, [''], [' '], [42]):
            with self.subTest(entries=len(entries)), self.assertRaises(ValueError):
                apply_action(running, completion | {'evidence': entries})
        block = {'op': 'block', 'task_id': 'alpha', 'reason': 'é' * 512}
        self.assertEqual(apply_action(running, block)[0]['reason'], block['reason'])
        for reason in ('é' * 513, '', ' ', 42):
            with self.subTest(reason=type(reason)), self.assertRaises(ValueError):
                apply_action(running, block | {'reason': reason})
        longest = definition('x' * 64, title='é' * 120)
        self.assertEqual(apply_action([], {'op': 'add', 'task': longest})[0]['id'], longest['id'])

    def test_all_prerequisites_must_complete(self):
        tasks = [
            record('first', status='completed', attempts=1, evidence=['ok']),
            record('second', role='ui', status='running', attempts=1),
            record('join', depends_on=['first', 'second']),
        ]
        self.assertEqual(schedule(tasks)['summary']['waiting'], 1)
        with self.assertRaises(ValueError):
            apply_action(tasks, {'op': 'start', 'task_id': 'join'})
        done = apply_action(tasks, {'op': 'complete', 'task_id': 'second', 'evidence': ['done']})
        self.assertEqual(schedule(done)['ready_task_ids'], ['join'])

    def test_unreachable_states_and_invalid_graphs(self):
        for tasks in (
            [record(), record()],
            [record(), record('b', depends_on=['alpha', 'alpha'])],
            [record(depends_on=['b']), record('b', depends_on=['c']), record('c', depends_on=['alpha'])],
            [record(status='running', attempts=1), record('b', status='running', attempts=1)],
            [record(), record('b', depends_on=['alpha'], status='running', attempts=1)],
            [record(status='running')], [record(reason='waiting')], [record(evidence=['premature'])],
            [record(status='blocked', attempts=1)], [record(status='completed', attempts=1)],
            [record(status='completed', attempts=1, gate='build', evidence=['passed'])],
            [record(status='completed', attempts=1, job_id='a' * 32, evidence=['passed'])],
        ):
            with self.subTest(tasks=tasks), self.assertRaises(ValueError):
                validate_tasks(tasks)

    def test_rejected_actions_and_finished_tasks_stay_unchanged(self):
        pending_actions = (
            None, [], {}, {'op': []}, {'op': 'delete', 'task_id': 'alpha'},
            {'op': 'start'}, {'op': 'start', 'task_id': []}, {'op': 'start', 'task_id': 'missing'},
            {'op': 'start', 'task_id': 'alpha', 'role': 'ui'},
            {'op': 'add', 'task': record('new')}, {'op': 'add', 'task': definition()},
            {'op': 'add', 'task': definition('new', depends_on=['missing'])},
            {'op': 'complete', 'task_id': 'alpha', 'evidence': ['early']},
            {'op': 'block', 'task_id': 'alpha', 'reason': 'early'},
            {'op': 'requeue', 'task_id': 'alpha'}, {'op': 'reassign', 'task_id': 'alpha', 'role': []},
        )
        for action in pending_actions:
            tasks = [record()]
            with self.subTest(action=action), self.assertRaises(ValueError):
                apply_action(tasks, action)
            self.assertEqual(tasks, [record()])
        done = [record(status='completed', attempts=1, evidence=['preserved'])]
        for op, extra in (
            ('start', {}), ('block', {'reason': 'late'}), ('requeue', {}),
            ('complete', {'evidence': ['late']}), ('reassign', {'role': 'ui'}),
        ):
            before = copy.deepcopy(done)
            with self.subTest(op=op), self.assertRaises(ValueError):
                apply_action(done, {'op': op, 'task_id': 'alpha', **extra})
            self.assertEqual(done, before)
