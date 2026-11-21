import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.planning_smoke import check_planning


class PlanningIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('godot'), 'Godot required for real build')
    def test_blueprint_blocker_recovery_and_real_release_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            result = check_planning(Path(directory))
        self.assertEqual(result['planned_tasks'], 6)
        self.assertTrue(result['duplicate_apply_rejected'])
        self.assertTrue(result['blocker_propagated'])
        self.assertTrue(result['verified_build'])
        self.assertTrue(result['completed_forecast'])
        self.assertTrue(result['preflight_integrity'])
        self.assertTrue(result['stale_preflight_rejected'])


if __name__ == '__main__':
    unittest.main()
