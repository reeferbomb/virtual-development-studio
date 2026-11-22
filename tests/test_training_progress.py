import copy
import unittest

from command_center.training_lab import assess_submission, lab_catalog
from command_center.training_progress import summarize_progress


class PracticeProgressTests(unittest.TestCase):
    def setUp(self):
        self.catalog = lab_catalog()
        self.example = next(e['example'] for e in self.catalog['exercises'] if e['id'] == 'interface')

    def snapshot(self, records):
        return {'revision': len(records), 'lab_sha256': self.catalog['lab_sha256'],
                'records': records, 'note': 'test fixture'}

    def test_empty_ledger_shows_assigned_exercises_without_claiming_competence(self):
        result = summarize_progress(self.snapshot([]))
        self.assertEqual(result['revision'], 0)
        self.assertEqual(result['summary']['records'], 0)
        self.assertEqual(len(result['roles']), 6)
        self.assertTrue(all(r['assigned_exercises'] > 0 and r['reviewed_exercises'] == 0
                            for r in result['roles']))
        assignments = sum(r['assigned_exercises'] for r in result['roles'])
        self.assertEqual(assignments, sum(len(e['roles']) for e in lab_catalog()['exercises']))
        self.assertEqual(assignments, 189)
        from command_center.training_records import MAX_RECORDS
        # Leave room for all earlier catalogs' complete role/exercise
        # coverage and one fresh current submission per assignment.
        self.assertGreater(MAX_RECORDS, 39 + 64 + 93 + 119 + 148 + 177 + assignments)

    def test_reference_failed_pending_historical_and_duplicate_evidence_do_not_inflate_coverage(self):
        changed = copy.deepcopy(self.example)
        changed['states']['full'] = 'All occupied slots are visible.'
        passed = assess_submission('interface', changed)
        self.assertEqual(passed['status'], 'pass')
        failed = copy.deepcopy(changed)
        failed['screens'][0]['widgets'][0]['rect'][3] = 1
        basic = {'exercise_id': 'interface', 'role': 'ui', 'current': True,
                 'reference': False, 'review': {'decision': 'accepted'}, 'report': passed,
                 'submission': {'private': 'must never leave the summary'}}
        records = [basic, copy.deepcopy(basic), dict(basic, review=None),
                   dict(basic, current=False), dict(basic, reference=True),
                   dict(basic, report=assess_submission('interface', failed), review={'decision': 'rejected'})]
        result = summarize_progress(self.snapshot(records))
        self.assertEqual(result['summary'], {'records': 6, 'current': 5, 'historical': 1,
                         'reference': 1, 'pending': 1, 'accepted': 3, 'rejected': 1,
                         'qualifying_distinct': 1})
        ui = next(r for r in result['roles'] if r['role'] == 'ui')
        self.assertEqual(ui['reviewed_exercises'], 1)
        self.assertEqual(ui['qualifying_distinct'], 1)
        self.assertNotIn('private', str(result))
        self.assertTrue(all(r['reviewed_exercises'] == 0 for r in result['roles'] if r['role'] != 'ui'))

    def test_snapshot_from_another_catalog_is_not_current_progress(self):
        snapshot = self.snapshot([])
        snapshot['lab_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            summarize_progress(snapshot)


if __name__ == '__main__':
    unittest.main()
