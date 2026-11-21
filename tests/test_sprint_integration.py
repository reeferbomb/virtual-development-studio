import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.sprint_smoke import check_sprint


class SprintIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('godot'), 'Godot required for real build')
    def test_sprint_acceptance_and_history_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_sprint(Path(tmp))
            self.assertTrue(result['stale_preview_rejected'])
            self.assertEqual(result['old_snapshot_status'], 'pending')
            self.assertEqual(result['blocked_snapshot_status'], 'blocked')
            self.assertEqual(result['build_verified'], True)
            self.assertGreater(result['planned_tasks'], 0)
            self.assertEqual(result['historical_snapshots'], 2)


if __name__ == '__main__':
    unittest.main()
