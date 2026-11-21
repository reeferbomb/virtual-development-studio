"""Automated quality-check exit codes and fail-closed response handling."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from command_center.acceptance import _LABELS
from command_center.quality_cli import main, report_exit_code


def report(status='ready'):
    checks = [dict(id=key, label=label, status='pass', evidence='Observed.',
                   role='verification', next_action='Retain evidence.') for key, label in _LABELS.items()]
    if status in ('pending', 'blocked'):
        checks[0]['status'] = 'pending' if status == 'pending' else 'fail'
    return dict(project_id='sample', spec_sha256='a' * 64, status=status,
                summary={state: sum(row['status'] == state for row in checks)
                         for state in ('pass', 'pending', 'fail')}, checks=checks, note='Local quality observations.')


class QualityCliTests(unittest.TestCase):
    def test_ready_pending_blocked_exit_codes(self):
        self.assertEqual(report_exit_code('sample', report()), 0)
        self.assertEqual(report_exit_code('sample', report('pending')), 1)
        self.assertEqual(report_exit_code('sample', report('blocked')), 1)

    def test_rejects_inconsistent_malformed_or_foreign_evidence(self):
        valid = report()
        variants = [None, dict(valid, project_id='other'), dict(valid, status='blocked'),
                    dict(valid, spec_sha256='unverified'), dict(valid, checks=[]),
                    dict(valid, checks=[valid['checks'][0]] * len(_LABELS)),
                    dict(valid, summary=dict(pass_=7, pending=0, fail=0)),
                    dict(valid, summary={'pass': True, 'pending': 0, 'fail': 0})]
        for variant in variants:
            self.assertEqual(report_exit_code('sample', variant), 2)

    def test_main_outputs_report_but_never_false_pass(self):
        valid = report('pending')
        output = io.StringIO()
        with patch('command_center.quality_cli.fetch_report', return_value=valid), redirect_stdout(output):
            self.assertEqual(main(['sample', '--port', '8123']), 1)
        self.assertEqual(json.loads(output.getvalue()), valid)
        with patch('command_center.quality_cli.fetch_report', side_effect=OSError), redirect_stdout(io.StringIO()):
            self.assertEqual(main(['sample']), 2)
