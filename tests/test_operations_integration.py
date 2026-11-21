import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.operations_smoke import check_operations


class OperationsIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('godot'), 'Godot required for real build')
    def test_claim_handoff_release_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            result = check_operations(Path(directory))
        self.assertTrue(result['build_verified'])
        self.assertTrue(result['stale_order_rejected'])
        self.assertTrue(result['handoff_did_not_complete_task'])
        self.assertTrue(result['recovery_verified'])
        self.assertTrue(result['historical_review_rejected'])


if __name__ == '__main__':
    unittest.main()
