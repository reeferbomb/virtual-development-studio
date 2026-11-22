import copy
import unittest

from command_center.training_lab import assess_submission, lab_catalog
from command_center.studio_curriculum import curriculum


class CreativePlanningTrainingTests(unittest.TestCase):
    def exercise(self, identifier):
        return next(e for e in lab_catalog()['exercises'] if e['id'] == identifier)

    def test_creativity_practice_rejects_cosmetic_duplicates_and_cost_overrun(self):
        exercise = self.exercise('creative-ideation')
        self.assertEqual(assess_submission(exercise['id'],exercise['example'])['status'],'pass')
        bad = copy.deepcopy(exercise['example'])
        bad['alternatives'][1]['verbs'] = bad['alternatives'][0]['verbs'][:]
        bad['alternatives'][0]['cost'] = 9
        self.assertEqual(assess_submission(exercise['id'],bad)['status'],'fail')

    def test_planning_practice_measures_critical_path_and_requires_negative_test(self):
        exercise = self.exercise('autonomous-planning')
        self.assertEqual(assess_submission(exercise['id'],exercise['example'])['status'],'pass')
        bad = copy.deepcopy(exercise['example'])
        bad['predicted_ticks'] = 1
        for task in bad['tasks']:
            if task['high_risk']:
                task['negative_test'] = None
        self.assertEqual(assess_submission(exercise['id'],bad)['status'],'fail')

    def test_training_registered_for_all_six_roles(self):
        tracks = {t['id']:t for t in curriculum()['tracks']}
        for name in ('creative-ideation','autonomous-planning'):
            self.assertEqual(len(tracks[name]['roles']),6)
