"""Cross-component release and portfolio acceptance tests with a genuine Godot build."""
import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.orchestration_smoke import check_portfolio, check_queue, check_release


class OrchestrationIntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='studio-orchestration-test-')
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)

    def test_portfolio_recommends_only_available_specialists_across_projects(self):
        report = check_portfolio(self.workspace)
        self.assertEqual(report['winning_project'], 'portfolio-beta')
        self.assertNotIn('architecture', report['roles_after_claim'])
        self.assertEqual(report['recovered_project'], 'portfolio-alpha')

    def test_queue_dispatch_order_cancel_and_retry(self):
        report = check_queue(self.workspace)
        self.assertEqual(report['queued_priorities'], [5, 4, 1])
        self.assertEqual(report['completion_order'], [5, 4, 1])
        self.assertEqual(report['canceled'], 1)
        self.assertEqual(report['passed'], 4)

    @unittest.skipUnless(shutil.which('godot'), 'World build requires Godot')
    def test_real_verified_job_promotion_persistence_and_integrity(self):
        report = check_release(self.workspace)
        self.assertEqual(report['job_status'], 'passed')
        self.assertEqual(report['priority'], 5)
        self.assertEqual(report['restored_release_state'], 'current')
        self.assertEqual(report['tampered_release_state'], 'invalid')
        self.assertEqual(report['edited_release_state'], 'stale')
