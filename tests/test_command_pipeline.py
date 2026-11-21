import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from command_center.pipeline import Pipeline
from command_center.provenance import spec_digest


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ws = self.root / 'workspace'
        self.project = self.ws / 'projects' / 'arena'
        self.project.mkdir(parents=True)
        (self.project / 'project.json').write_text(json.dumps({'id': 'arena', 'kind': 'multiplayer'}))
        (self.project / 'spec.json').write_text('{}')
        self.script = self.root / 'multiplayer' / 'build.py'
        self.script.parent.mkdir()
        self.script.write_text("""
import pathlib, sys
if '--verify' in sys.argv:
    print('verified')
    sys.exit(0 if (pathlib.Path(sys.argv[-1])/'manifest.json').exists() else 1)
out = pathlib.Path(sys.argv[-1])
out.mkdir()
(out/'manifest.json').write_text('{}')
print('built')
""")
        self.pipeline = Pipeline(self.root, self.ws)
        self.addCleanup(self.pipeline.worker.shutdown)

    def finish(self, job):
        for _ in range(250):
            state = self.pipeline.get(job['id'])
            if state['status'] not in ('running', 'queued'):
                return state
            time.sleep(.02)
        self.fail('job did not finish')

    def test_build_verify_snapshot_and_persistence(self):
        job = self.pipeline.submit(self.project)
        (self.project/'spec.json').write_text('{"changed":true}')
        state = self.finish(job)
        self.assertEqual(state['status'], 'passed')
        self.assertEqual(len(state['commands']), 2)
        self.assertEqual(state['manifest_sha256'], hashlib.sha256(b'{}').hexdigest())
        self.assertIn('verified', self.pipeline.log(job['id']))
        self.assertEqual(json.loads((self.ws/'jobs'/job['id']/'spec.json').read_text()), {})
        self.assertEqual(Pipeline(self.root, self.ws).list()[0], state)

    def test_failed_verification(self):
        self.script.write_text(self.script.read_text().replace('sys.exit(0 if', 'sys.exit(7 if'))
        state = self.finish(self.pipeline.submit(self.project))
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['commands'][-1]['exit_code'], 7)

    def test_builds_record_scenarios_only_for_the_shipped_specs(self):
        streamed = {'seed': 237, 'chunk_size': 32, 'radius': 1, 'capacity': 40}
        city = {'seed': 237, 'blocks': 4, 'block_size': 48, 'traffic': 12, 'civilians': 20}
        fixtures = {'unified': streamed, 'living': streamed, 'city': city, 'vertical': city,
                    'advanced': city, 'frontline': city}
        for kind, fixture in fixtures.items():
            with self.subTest(kind=kind):
                changed = dict(fixture, seed=238)
                flag = f'--{kind}-qa'
                key = f'{kind}_qa'
                report_name = f'{kind}-qa.json'
                report = {'pass': True}
                builder = self.root / kind
                builder.mkdir()
                (builder / 'demo_spec.json').write_text(json.dumps(fixture))
                (builder / 'build.py').write_text(self.script.read_text() + f"""
if {flag!r} in sys.argv:
    reports = out/'reports'
    reports.mkdir()
    (reports / {report_name!r}).write_text({json.dumps(report)!r})
""")
                (self.project / 'project.json').write_text(json.dumps({'id': 'arena', 'kind': kind}))
                (self.project / 'spec.json').write_text(json.dumps(fixture))
                state = self.finish(self.pipeline.submit(self.project))
                self.assertEqual(state['status'], 'passed')
                self.assertTrue(state['verified'])
                self.assertIn(flag, state['commands'][0]['argv'])
                self.assertEqual(state['spec_sha256'], spec_digest(fixture))
                self.assertEqual(state[key], report)

                (self.project / 'spec.json').write_text(json.dumps(changed))
                state = self.finish(self.pipeline.submit(self.project))
                self.assertEqual(state['status'], 'passed')
                self.assertTrue(state['verified'])
                self.assertNotIn(flag, state['commands'][0]['argv'])
                self.assertEqual(state['spec_sha256'], spec_digest(changed))
                self.assertNotIn(key, state)

    def test_escape_rejected(self):
        with self.assertRaises(ValueError):
            self.pipeline.submit(self.root)
        with self.assertRaises((KeyError, ValueError)):
            self.pipeline.get('../projects')

    def test_interrupted_state_on_restart(self):
        state = self.finish(self.pipeline.submit(self.project))
        path = self.ws/'jobs'/state['id']/'job.json'
        state.update(status='running', verified=False, finished_at=None, output=None)
        path.write_text(json.dumps(state))
        recovered = Pipeline(self.root, self.ws).get(state['id'])
        self.assertEqual(recovered['status'], 'failed')
        self.assertFalse(recovered['verified'])
        self.assertTrue(recovered['finished_at'])

    def test_serial_jobs_and_timeout(self):
        from unittest.mock import patch
        self.script.write_text("import time\ntime.sleep(3)\n")
        with patch('command_center.pipeline.TIMEOUT_SECONDS', .1):
            first = self.pipeline.submit(self.project)
            second = self.pipeline.submit(self.project)
            a, b = self.finish(first), self.finish(second)
        self.assertGreaterEqual(b['started_at'], a['finished_at'])
        self.assertTrue(a['commands'][0]['timed_out'])
        self.assertFalse(b['verified'])

    def test_queue_priority_fifo_cancel_and_retry(self):
        started = threading.Event()
        resume = threading.Event()
        build_commands = self.pipeline._commands

        def held_commands(kind, directory):
            started.set()
            self.assertTrue(resume.wait(10))
            return build_commands(kind, directory)

        with patch.object(self.pipeline, '_commands', held_commands):
            first = self.pipeline.submit(self.project)
            try:
                self.assertTrue(started.wait(5))
                with self.assertRaises(FileExistsError):
                    self.pipeline.cancel(first['id'])
                with self.assertRaises(FileExistsError):
                    self.pipeline.retry(first['id'])
                low = self.pipeline.submit(self.project, 1)
                high = self.pipeline.submit(self.project, 5)
                other = self.pipeline.submit(self.project, 5)
                canceled = self.pipeline.cancel(low['id'])
                self.assertEqual(canceled['status'], 'canceled')
                with self.assertRaises(FileExistsError):
                    self.pipeline.cancel(low['id'])
                retried = self.pipeline.retry(low['id'])
                self.assertEqual(retried['retry_of'], low['id'])
                self.assertNotEqual(retried['id'], low['id'])
                self.assertEqual(retried['priority'], 1)
                view = self.pipeline.queue()
                self.assertEqual(view['running']['id'], first['id'])
                self.assertEqual([j['id'] for j in view['queued']], [high['id'], other['id'], retried['id']])
                self.assertEqual(view['counts'], dict(queued=3, running=1, passed=0, failed=0, canceled=1))
                second = Pipeline(self.root, self.ws)
                self.addCleanup(second.worker.shutdown)
                self.assertEqual(second.queue()['running']['id'], first['id'])
            finally:
                resume.set()
            done = [self.finish(job) for job in (first, high, other, retried)]
        self.assertEqual([j['status'] for j in done], ['passed'] * 4)
        for previous, following in zip(done, done[1:]):
            self.assertGreaterEqual(following['started_at'], previous['finished_at'])
        self.assertEqual(self.pipeline.queue()['counts']['canceled'], 1)
        self.assertFalse((self.ws / 'jobs' / low['id'] / 'build.log').exists())
        with self.assertRaises(FileExistsError):
            self.pipeline.retry(high['id'])

    def test_invalid_priority_and_stale_retry(self):
        for value in (False, True, 0, 6, 1.5, '4', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.pipeline.submit(self.project, value)
        self.script.write_text('raise SystemExit(1)')
        failed = self.finish(self.pipeline.submit(self.project, 4))
        self.assertEqual(failed['status'], 'failed')
        (self.project / 'spec.json').write_text('{"edited":true}')
        with self.assertRaises(FileExistsError):
            self.pipeline.retry(failed['id'])
        self.assertEqual(len(self.pipeline.list()), 1)
        (self.project / 'spec.json').write_text('{}')
        (self.ws / 'jobs' / failed['id'] / 'spec.json').write_text('{"edited":true}')
        with self.assertRaises(ValueError):
            self.pipeline.retry(failed['id'])

    def test_restart_dispatches_safe_legacy_snapshot_and_rejects_corrupt_one(self):
        # Hold the executor before its first claim to simulate durable queued records
        # left by another process. Shut it down after the reopened pipeline finishes.
        gate = threading.Event()
        self.pipeline.worker.submit(gate.wait, 10)
        try:
            valid = self.pipeline.submit(self.project)
            invalid = self.pipeline.submit(self.project, 5)
            directory = self.ws / 'jobs'
            legacy_path = directory / valid['id'] / 'job.json'
            legacy = json.loads(legacy_path.read_text())
            legacy.pop('priority')
            legacy.pop('queue_sequence')
            legacy_path.write_text(json.dumps(legacy))
            (directory / invalid['id'] / 'spec.json').write_text('{"tampered":true}')
            (self.project / 'spec.json').write_text('{"edited":true}')
            reopened = Pipeline(self.root, self.ws)
            self.addCleanup(reopened.worker.shutdown)
            self.assertEqual(self.finish(invalid)['status'], 'failed')
            self.assertFalse((directory / invalid['id'] / 'build.log').exists())
            done = self.finish(valid)
            self.assertEqual(done['priority'], 3)
            self.assertEqual(done['status'], 'passed')
            self.assertEqual(len(done['commands']), 2)
        finally:
            gate.set()

    def test_completion_between_recovery_scan_and_lease_is_preserved(self):
        passed = self.finish(self.pipeline.submit(self.project))
        stale_read = dict(passed, status='running', verified=False)
        self.pipeline._recover_running([stale_read])
        self.assertEqual(stale_read, passed)
        self.assertEqual(self.pipeline.get(passed['id']), passed)

    def test_even_successful_verifier_cannot_seal_missing_manifest(self):
        self.script.write_text("import pathlib, sys\nif '--verify' not in sys.argv: pathlib.Path(sys.argv[-1]).mkdir()")
        finished = self.finish(self.pipeline.submit(self.project))
        self.assertEqual(finished['status'], 'failed')
        self.assertIn('manifest.json', finished['error'])
        self.assertFalse(finished['verified'])

    def test_recovery_after_worker_process_dies_waits_for_its_surviving_builder(self):
        # The first builder deliberately outlives the process that launched it.
        self.script.write_text("""
import fcntl, os, pathlib, sys, time
if '--verify' in sys.argv:
    sys.exit(0)
root = pathlib.Path.cwd()
out = pathlib.Path(sys.argv[-1])
with (root / 'builder-guard').open('a') as guard:
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if not (root / 'first-started').exists():
        (root / 'first-started').write_text(out.parent.name)
        until = time.monotonic() + 15
        while not (root / 'release-first').exists() and time.monotonic() < until:
            time.sleep(.02)
    out.mkdir()
    (out / 'manifest.json').write_text('{}')
""")
        code = """
import json, pathlib, sys, time
from command_center.pipeline import Pipeline
root = pathlib.Path(sys.argv[1])
p = Pipeline(root, root / 'workspace')
project = root / 'workspace' / 'projects' / 'arena'
ids = [p.submit(project)['id'] for _ in range(2)]
(root / 'submitted').write_text(json.dumps(ids))
time.sleep(20)
"""
        service = subprocess.Popen([sys.executable, '-c', code, str(self.root)],
                                   cwd=Path(__file__).resolve().parents[1])
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if (self.root / 'submitted').is_file() and (self.root / 'first-started').is_file():
                    break
                time.sleep(.02)
            first, second = json.loads((self.root / 'submitted').read_text())
            self.assertEqual((self.root / 'first-started').read_text(), first)
            service.kill()
            service.wait(timeout=5)
            reopened = Pipeline(self.root, self.ws)
            self.addCleanup(reopened.worker.shutdown)
            self.assertEqual(reopened.get(first)['status'], 'failed')
            deadline = time.monotonic() + 5
            while reopened.get(second)['status'] == 'queued' and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(reopened.get(second)['status'], 'running')
            self.assertFalse((self.ws / 'jobs' / second / 'build.log').exists())
            (self.root / 'release-first').touch()
            self.assertEqual(self.finish({'id': second})['status'], 'passed')
            self.assertEqual(reopened.get(first)['status'], 'failed')
        finally:
            (self.root / 'release-first').touch()
            if service.poll() is None:
                service.kill()
            service.wait(timeout=5)
