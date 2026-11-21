"""Supervisor acceptance through its HTTP surface and real build records."""
import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.supervisor_smoke import check_defects, check_verified_build


class SupervisorIntegrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='studio-supervisor-test-')
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name)

    def test_critical_defect_blocks_then_resolves_and_survives_restart(self):
        report = check_defects(self.workspace)
        self.assertEqual(report['blocked_status'], 'blocked')
        self.assertEqual(report['restored_status'], 'resolved')
        self.assertEqual(report['historical_resolved'], 1)

    @unittest.skipUnless(shutil.which('godot'), 'Real build requires Godot')
    def test_audit_and_profile_observe_real_verified_build_and_corruption(self):
        report = check_verified_build(self.workspace)
        self.assertEqual(report['build_check'], 'pass')
        self.assertEqual(report['release_check'], 'pass')
        self.assertEqual(report['tampered_status'], 'blocked')
        self.assertGreaterEqual(report['build_seconds'], 0)
        self.assertIsNone(report['regression'])
