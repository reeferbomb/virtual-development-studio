import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from command_center.evidence_history import EvidenceHistory
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.quality_trends import quality_trends
from command_center.supervisor import audit_project


class QualityTrendsTests(unittest.TestCase):
    project = {'id': 'city', 'spec': {'seed': 7}}
    digest = spec_digest(project['spec'])
    old_digest = spec_digest({'seed': 6})

    def audit(self, status='pass'):
        audit = audit_project(self.project, [], None, None, None, None)
        for check in audit['checks']:
            check['status'] = status
        audit['status'] = {'fail': 'blocked', 'warn': 'attention', 'pending': 'pending', 'pass': 'pass'}[status]
        return audit

    def capture(self, number, status='pass', digest=None):
        audit = self.audit(status)
        return dict(id=f'{number:032x}', spec_sha256=digest or self.digest,
                    created_at='2026-09-20T12:00:00+00:00', status=audit['status'],
                    checks=audit['checks'], note=f'Private capture note {number}')

    def history(self, *items):
        return dict(project_id=self.project['id'], spec_sha256=self.digest, revision=len(items), items=list(items))

    def test_latest_current_capture_and_gate_ids_determine_comparison(self):
        old = self.capture(3, 'pending', self.old_digest)
        baseline = self.capture(2, 'warn')
        baseline['checks'].reverse()
        earlier = self.capture(1)
        history = self.history(old, baseline, earlier)
        audit = self.audit('warn')
        audit['checks'][0]['status'] = 'pending'
        audit['checks'][1]['status'] = 'fail'
        audit['status'] = 'blocked'
        gate_ids = [row['id'] for row in audit['checks']]
        audit['checks'].reverse()
        before = deepcopy((self.project, audit, history))

        result = quality_trends(self.project, audit, history)
        self.assertEqual(set(result), {'project_id', 'spec_sha256', 'status', 'history_revision', 'baseline_id',
                                       'baseline_status', 'live_status', 'summary', 'checks', 'historical_count', 'note'})
        self.assertEqual((result['project_id'], result['spec_sha256'], result['status'], result['history_revision'],
                          result['baseline_id'], result['baseline_status'], result['live_status'], result['historical_count']),
                         ('city', self.digest, 'current', 3, baseline['id'], 'attention', 'blocked', 1))
        self.assertEqual(result['summary'], dict(improved=1, regressed=1, unchanged=4))
        self.assertEqual([row['id'] for row in result['checks']], gate_ids)
        self.assertEqual(result['checks'][0], dict(id='build', label='Current-spec build', baseline_status='warn',
                                                  live_status='pending', trend='improved'))
        self.assertEqual(result['checks'][1]['trend'], 'regressed')
        self.assertTrue(all(row['trend'] == 'unchanged' for row in result['checks'][2:]))
        self.assertEqual(result, quality_trends(self.project, audit, history))
        for private in (old['id'], self.old_digest, earlier['id'], 'Private capture note', 'Evidence source'):
            self.assertNotIn(private, json.dumps(result))
        self.assertEqual(before, (self.project, audit, history))

    def test_every_pair_in_the_gate_status_order(self):
        order = ['fail', 'warn', 'pending', 'pass']
        for before, baseline in enumerate(order):
            for after, live in enumerate(order):
                with self.subTest(baseline=baseline, live=live):
                    result = quality_trends(self.project, self.audit(live), self.history(self.capture(1, baseline)))
                    trend = 'improved' if after > before else 'regressed' if after < before else 'unchanged'
                    self.assertEqual(result['summary'][trend], 6)
                    self.assertTrue(all(row['trend'] == trend for row in result['checks']))

    def test_absent_baseline_is_distinct_from_unchanged_gates(self):
        audit = self.audit('pass')
        old = self.capture(1, 'fail', self.old_digest)
        for history in (self.history(), self.history(old)):
            with self.subTest(revision=history['revision']):
                result = quality_trends(self.project, audit, history)
                self.assertEqual(result['status'], 'empty')
                self.assertEqual(result['history_revision'], history['revision'])
                self.assertEqual(result['historical_count'], len(history['items']))
                self.assertEqual(result['live_status'], 'pass')
                self.assertIsNone(result['baseline_id'])
                self.assertIsNone(result['baseline_status'])
                self.assertEqual(result['summary'], dict(improved=0, regressed=0, unchanged=0))
                self.assertEqual(result['checks'], [])
                self.assertNotIn(old['id'], json.dumps(result))

    def test_invalid_project_or_either_source_prevents_all_comparisons(self):
        audit = self.audit()
        history = self.history(self.capture(2), self.capture(1, digest=self.old_digest))
        bad_old = deepcopy(history)
        bad_old['items'][1]['note'] = ''
        inputs = [(project, audit, history) for project in (None, {}, dict(id='../x', spec={}),
                                                            dict(id='city', spec={'bad': float('nan')}))]
        inputs.extend((self.project, bad, history) for bad in (None, {}, dict(audit, recommendations={}),
                       dict(audit, checks=audit['checks'][:-1]), dict(audit, status='attention'),
                       dict(audit, spec_sha256=self.old_digest), dict(audit, project_id='other')))
        inputs.extend((self.project, audit, bad) for bad in (None, {}, bad_old, dict(history, project_id='other'),
                      dict(history, spec_sha256=self.old_digest), dict(history, revision=True)))
        for project, current, captures in inputs:
            with self.subTest(project=project, current=current, captures=captures):
                result = quality_trends(project, current, captures)
                self.assertEqual(result['status'], 'unavailable')
                self.assertEqual(result['checks'], [])
                for key in ('history_revision', 'historical_count', 'baseline_id', 'baseline_status', 'live_status'):
                    self.assertIsNone(result[key])

    def test_reopened_evidence_store_and_actual_supervisor_audit(self):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(__file__).resolve().parents[1]
            projects = ProjectStore(root, Path(workspace))
            project = projects.create('Trend review', 'city')
            pid = project['id']
            baseline = audit_project(project, None, None, None, None, None)
            request = dict(expected_revision=0, spec_sha256=baseline['spec_sha256'], note='Observed initial gates.')
            EvidenceHistory(projects).capture(pid, request, baseline)
            live = audit_project(project, [], None, None, None, None)
            reopened = ProjectStore(root, Path(workspace))
            directory = reopened.directory(pid)

            def files():
                return {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in directory.iterdir() if p.is_file()}

            before = files()
            result = quality_trends(reopened.get(pid), live, EvidenceHistory(reopened).get(pid))
            self.assertEqual(result['summary'], dict(improved=1, regressed=0, unchanged=5))
            self.assertEqual(result['checks'][0]['baseline_status'], 'fail')
            self.assertEqual(result['checks'][0]['live_status'], 'pending')
            self.assertEqual(files(), before)


if __name__ == '__main__':
    unittest.main()
