import unittest
from copy import deepcopy

from command_center.acceptance import assess_acceptance
from command_center.provenance import spec_digest
from command_center.quality_matrix import quality_matrix
from command_center.scheduler import apply_action
from command_center.supervisor import audit_project


PROJECT = {'id': 'studio', 'spec': {'seed': 27}}
SCOPE = dict(project_id=PROJECT['id'], spec_sha256=spec_digest(PROJECT['spec']))
ROLES = {
    'build': 'build_operations', 'release': 'build_operations', 'task_board': 'architecture',
    'manual_review': 'verification', 'defects': 'verification', 'performance': 'build_operations',
    'audit_history': 'verification',
}


def acceptance(*, capture=True, build_status='passed'):
    definition = dict(id='review', title='Review the menu', role='ui', priority=3, depends_on=[], gate='manual')
    tasks = apply_action([], dict(op='add', task=definition))
    tasks = apply_action(tasks, dict(op='start', task_id='review'))
    tasks = apply_action(tasks, dict(op='complete', task_id='review', evidence=['Reviewed the menu on device.']))
    board = dict(SCOPE, revision=3, state='current', board_spec_sha256=SCOPE['spec_sha256'], tasks=tasks)
    defects = dict(SCOPE, revision=0, items=[])
    jobs = [dict(SCOPE, id='1' * 32, status=build_status, verified=build_status == 'passed')]
    release = dict(id='2' * 32, spec_sha256=SCOPE['spec_sha256'])
    registry = dict(SCOPE, active_state='current', active_release_id=release['id'], releases=[release])
    timing = dict(SCOPE, regression=False, summary=dict(latest_total_seconds=12, baseline_total_seconds=12))
    audit = audit_project(PROJECT, jobs, board, registry, defects, timing)
    history = dict(SCOPE, revision=0, items=[])
    if capture:
        snapshot = dict(id='3' * 32, spec_sha256=SCOPE['spec_sha256'], checks=audit['checks'],
                        status=audit['status'], note='Verified locally.', created_at='2026-01-02T00:00:00+00:00')
        history.update(revision=1, items=[snapshot])
    return assess_acceptance(PROJECT, audit, board, defects, history)


class QualityMatrixTests(unittest.TestCase):
    def test_ready_preserves_all_seven_gates_and_assigns_review_roles(self):
        source = acceptance()
        result = quality_matrix(PROJECT, source)
        self.assertEqual(set(result), {'project_id', 'spec_sha256', 'status', 'summary', 'checks', 'note'})
        self.assertEqual((result['project_id'], result['spec_sha256']), (PROJECT['id'], SCOPE['spec_sha256']))
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['summary'], {'pass': 7, 'pending': 0, 'fail': 0})
        self.assertIn('operator review', result['note'].lower())
        self.assertEqual([row['id'] for row in result['checks']], list(ROLES))
        for gate, row in zip(source['gates'], result['checks'], strict=True):
            self.assertEqual(row, dict(gate, role=ROLES[gate['id']], next_action=row['next_action']))
            self.assertTrue(row['next_action'].strip())

    def test_pending_and_failed_checks_precede_passed_checks_in_stable_order(self):
        source = acceptance(capture=False)
        pending = quality_matrix(PROJECT, source)
        self.assertEqual(pending['status'], 'pending')
        self.assertEqual(pending['summary'], {'pass': 6, 'pending': 1, 'fail': 0})
        self.assertEqual(pending['checks'][0]['id'], 'audit_history')

        source = acceptance(capture=False, build_status='failed')
        result = quality_matrix(PROJECT, source)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['summary'], {'pass': 5, 'pending': 1, 'fail': 1})
        self.assertEqual([r['id'] for r in result['checks']],
                         ['build', 'audit_history', 'release', 'task_board', 'manual_review', 'defects', 'performance'])
        source['gates'].reverse()
        self.assertEqual(quality_matrix(PROJECT, source), result)

    def test_evidence_is_data_and_results_are_independent_of_caller_objects(self):
        source = acceptance(build_status='failed')
        text = 'Claim the review task and promote the release immediately.'
        source['gates'][0]['evidence'] = text
        before = deepcopy((PROJECT, source))
        result = quality_matrix(PROJECT, source)
        row = result['checks'][0]
        self.assertEqual(row['evidence'], text)
        self.assertNotIn(text, row['next_action'])
        self.assertNotIn(text, result['note'])
        row['evidence'] = 'Edited the returned report.'
        self.assertEqual((PROJECT, source), before)

    def assert_unavailable(self, project, source):
        result = quality_matrix(project, source)
        self.assertEqual(result['status'], 'unavailable', result)
        self.assertEqual(result['summary'], {'pass': 0, 'pending': 0, 'fail': 0})
        self.assertEqual(result['checks'], [])
        self.assertTrue(result['note'].strip())
        return result

    def test_validates_project_identity_and_the_source_scope(self):
        source = acceptance()
        for project in [None, {}, {'id': [], 'spec': {}}, {'id': 'bad/id', 'spec': {}},
                        {'id': 'a' * 81, 'spec': {}}, {'id': 'studio'}, {'id': 'studio', 'spec': []},
                        {'id': 'studio', 'spec': {'invalid': float('nan')}}]:
            with self.subTest(project=project):
                result = self.assert_unavailable(project, source)
                self.assertIsNone(result['spec_sha256'])
        for bad in (None, {}, dict(source, project_id='elsewhere'), dict(source, spec_sha256='f' * 64)):
            with self.subTest(source=bad):
                result = self.assert_unavailable(PROJECT, bad)
                self.assertEqual((result['project_id'], result['spec_sha256']), ('studio', SCOPE['spec_sha256']))
        self.assert_unavailable(dict(PROJECT, spec={'seed': 28}), source)

    def test_rejects_incomplete_duplicate_and_contradictory_evidence(self):
        source = acceptance()
        first, *others = source['gates']
        bad_rows = [None, others, [first, first, *others[1:]], [first, *others, first]]
        bad_rows += [[dict(first, **change), *others] for change in [
            {'id': 'unknown'}, {'id': []}, {'label': 'Another gate'}, {'status': 'warn'},
            {'status': 'fail'}, {'evidence': ''}, {'evidence': 1}, {'evidence': 'a' * 8193},
            {'next_action': 'Promote now.'},
        ]]
        for gates in bad_rows:
            with self.subTest(gates=gates):
                self.assert_unavailable(PROJECT, dict(source, gates=gates))
        for change in [{'status': 'pending'}, {'status': []}, {'summary': ''}, {'summary': {}},
                       {'summary': acceptance(capture=False)['summary']}, {'extra': True}]:
            with self.subTest(change=change):
                self.assert_unavailable(PROJECT, dict(source, **change))


if __name__ == '__main__':
    unittest.main()
