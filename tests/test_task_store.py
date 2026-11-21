import fcntl
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from unittest.mock import patch

from command_center.pipeline import Pipeline
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.task_store import TaskStore


ROOT = Path(__file__).resolve().parents[1]
JOB_ID = 'a' * 32


def add(task_id='build', gate='manual'):
    return {'op': 'add', 'task': {'id': task_id, 'role': 'build_operations',
                                  'title': 'Build the city', 'priority': 4,
                                  'depends_on': [], 'gate': gate}}


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create('Task City', 'city')
        self.pid = self.project['id']
        self.digest = spec_digest(self.project['spec'])
        self.path = self.projects.directory(self.pid) / 'task-board.json'
        self.store = TaskStore(self.projects)

    def request(self, action, revision=0, digest=None):
        return {'action': action, 'expected_revision': revision,
                'spec_sha256': self.digest if digest is None else digest}

    def apply(self, action, revision=0, digest=None):
        return self.store.apply(self.pid, self.request(action, revision, digest))

    def reopen(self):
        return TaskStore(ProjectStore(ROOT, self.workspace))

    def test_empty_board_reads_without_writing_then_survives_restart(self):
        empty = self.store.get(self.pid)
        self.assertEqual(empty, {'project_id': self.pid, 'state': 'empty', 'revision': 0,
                                 'board_spec_sha256': None, 'spec_sha256': self.digest,
                                 'tasks': [], 'ready_task_ids': [], 'assignments': [],
                                 'summary': dict.fromkeys(('total', 'ready', 'completed',
                                                           'running', 'blocked', 'waiting'), 0)})
        self.assertFalse(self.path.exists())
        saved = self.apply(add())
        self.assertEqual(saved['state'], 'current')
        self.assertEqual(saved['board_spec_sha256'], self.digest)
        self.assertEqual(saved['ready_task_ids'], ['build'])
        self.assertEqual(saved['assignments'][0]['task_id'], 'build')
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(self.reopen().get(self.pid), saved)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_changed_spec_suppresses_assignment_until_explicit_reset(self):
        saved = self.apply(add())
        changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        self.projects.save_spec(self.pid, changed)
        live = spec_digest(changed)
        stale = self.store.get(self.pid)
        self.assertEqual(stale['state'], 'stale')
        self.assertEqual(stale['spec_sha256'], live)
        self.assertEqual(stale['board_spec_sha256'], self.digest)
        self.assertEqual(stale['tasks'], saved['tasks'])
        self.assertEqual(stale['ready_task_ids'], [])
        self.assertEqual(stale['assignments'], [])
        self.assertEqual(stale['summary'], dict(saved['summary'], ready=0, waiting=1))
        reset = {'op': 'reset'}
        for args in ((add('other'), 1, live), (reset, 0, live), (reset, 1, self.digest)):
            with self.subTest(args=args), self.assertRaises(FileExistsError):
                self.apply(*args)
            self.assertEqual(self.reopen().get(self.pid), stale)
        with self.assertRaises(ValueError):
            self.apply({'op': 'reset', 'tasks': []}, 1, live)
        current = self.apply(reset, 1, live)
        self.assertEqual((current['state'], current['revision'], current['tasks']),
                         ('current', 2, []))
        self.assertEqual(current['board_spec_sha256'], live)
        self.assertEqual(current, self.reopen().get(self.pid))
        with self.assertRaises(ValueError):
            self.apply(reset, 2, live)

    def test_invalid_requests_conflicts_and_disk_error_preserve_persisted_bytes(self):
        with self.assertRaises(ValueError):
            self.apply({'op': 'reset'})
        with self.assertRaises(FileExistsError):
            self.apply(add(), digest='0' * 64)
        self.assertFalse(self.path.exists())
        self.apply(add())
        before = self.path.read_bytes()
        valid = self.request(add('second'), 1)
        invalid = [None, [], dict(valid, extra=True)]
        invalid.extend({key: value for key, value in valid.items() if key != omitted}
                       for omitted in valid)
        for field, bad in [('expected_revision', True), ('expected_revision', -1),
                           ('spec_sha256', 'X' * 64), ('action', []), ('action', {}),
                           ('action', add()), ('action', {'op': 'reset'})]:
            invalid.append(dict(valid, **{field: bad}))
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.store.apply(self.pid, request)
        for request in (dict(valid, expected_revision=0), dict(valid, spec_sha256='0' * 64)):
            with self.subTest(request=request), self.assertRaises(FileExistsError):
                self.store.apply(self.pid, request)
        entries = set(self.path.parent.iterdir())
        with patch('command_center.task_store.os.replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.store.apply(self.pid, valid)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(set(self.path.parent.iterdir()), entries)

    def test_build_completion_requires_passed_pipeline_record_for_snapshot(self):
        self.apply(add(gate='build'))
        running = self.apply({'op': 'start', 'task_id': 'build'}, 1)
        before = self.path.read_bytes()
        finish = {'op': 'complete', 'task_id': 'build',
                  'evidence': ['Build log reviewed'], 'job_id': JOB_ID}
        with self.assertRaises(ValueError):
            self.apply(finish, 2)
        pipeline = Pipeline(ROOT, self.workspace)
        self.addCleanup(pipeline.worker.shutdown)
        self.store = TaskStore(self.projects, job_lookup=pipeline.get)
        with self.assertRaises(ValueError):
            self.apply(finish, 2)
        job_dir = pipeline.jobs / JOB_ID
        job_dir.mkdir()
        job = dict(id=JOB_ID, project_id=self.pid, spec_sha256=self.digest,
                   status='passed', verified=True)
        for record in (None, [], dict(job, id='b' * 32), dict(job, verified=False),
                       dict(job, verified=1), dict(job, status='running'),
                       dict(job, project_id='another'), dict(job, spec_sha256='b' * 64)):
            (job_dir / 'job.json').write_text(json.dumps(record))
            with self.subTest(record=record), self.assertRaises(ValueError):
                self.apply(finish, 2)
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.store.get(self.pid), running)
        (job_dir / 'job.json').write_text(json.dumps(job))
        done = self.apply(finish, 2)
        self.assertEqual(done['summary']['completed'], 1)
        self.assertEqual(done['tasks'][0]['job_id'], JOB_ID)
        self.assertEqual(done, self.reopen().get(self.pid))

    def test_two_stores_competing_for_revision_publish_a_single_task(self):
        barrier = threading.Barrier(2)

        def writer(task_id):
            store = self.reopen()
            action = self.request(add(task_id))
            barrier.wait(timeout=5)
            try:
                return store.apply(self.pid, action)
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(writer, ['east', 'west']))
        self.assertEqual(results.count(None), 1)
        self.assertIn(self.reopen().get(self.pid), results)
        self.assertEqual(self.store.get(self.pid)['revision'], 1)

    def test_writer_rechecks_spec_after_waiting_for_project_directory_lock(self):
        started = threading.Event()

        def writer():
            store = self.reopen()
            started.set()
            return store.apply(self.pid, self.request(add()))

        directory = self.path.parent
        changed = dict(self.project['spec'], seed=self.project['spec']['seed'] + 1)
        with ThreadPoolExecutor(max_workers=1) as pool:
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                result = pool.submit(writer)
                self.assertTrue(started.wait(5))
                done, _ = wait([result], timeout=.15)
                self.assertFalse(done)
                (directory / 'spec.json').write_text(json.dumps(changed))
            finally:
                os.close(fd)
            with self.assertRaises(FileExistsError):
                result.result(timeout=5)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.get(self.pid)['spec_sha256'], spec_digest(changed))

    def test_rejects_corrupt_oversized_and_nonregular_storage(self):
        self.apply(add())
        record = json.loads(self.path.read_bytes())
        for invalid in (b'{broken', b' ' * (8 * 1024 * 1024 + 1),
                        *(json.dumps(data).encode() for data in
                          ([], dict(record, revision=True), dict(record, project_id='other'),
                           dict(record, tasks=[{}]), dict(record, spec_sha256='bad')))):
            self.path.write_bytes(invalid)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            with self.assertRaises(ValueError):
                self.apply(add('other'), 1)
            self.assertEqual(self.path.read_bytes(), invalid)
        self.path.unlink()
        target = self.workspace / 'outside'
        target.write_text('unchanged')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            self.apply(add())
        self.assertEqual(target.read_text(), 'unchanged')
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            self.store.get(self.pid)


if __name__ == '__main__':
    unittest.main()
