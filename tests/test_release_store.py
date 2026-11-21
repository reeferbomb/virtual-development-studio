import fcntl
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from command_center.pipeline import Pipeline
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest
from command_center.release_store import REGISTRY, ReleaseStore
from factory import build as factory


ROOT = Path(__file__).resolve().parents[1]
FIRST = 'a' * 32
SECOND = 'b' * 32
THIRD = 'c' * 32


class ReleaseStoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        self.projects = ProjectStore(ROOT, self.workspace)
        self.pipeline = Pipeline(ROOT, self.workspace)
        self.addCleanup(self.pipeline.worker.shutdown)
        self.store = ReleaseStore(self.projects, self.pipeline)
        self.project = self.projects.create('Release City', 'city')
        self.pid = self.project['id']
        self.spec = self.project['spec']
        self.digest = spec_digest(self.spec)
        self.path = self.projects.directory(self.pid) / REGISTRY

    def build(self, job_id=FIRST, *, sealed=True, spec=None):
        spec = self.spec if spec is None else spec
        directory = self.pipeline.jobs / job_id
        directory.mkdir()
        factory.write_json(directory / 'spec.json', spec)
        output = directory / 'output'
        assets = output / 'assets'
        assets.mkdir(parents=True)
        (assets / 'scene.tscn').write_text(job_id)
        seal = self.seal(output)
        job = dict(id=job_id, project_id=self.pid, kind='city', status='passed', verified=True,
                   created_at='2026-01-01T00:00:00+00:00', spec_sha256=spec_digest(spec),
                   output=f'jobs/{job_id}/output')
        if sealed:
            job['manifest_sha256'] = seal
        factory.write_json(directory / 'job.json', job)
        return output, job

    @staticmethod
    def seal(output):
        manifest = output / 'manifest.json'
        factory.write_json(manifest, dict(schema=1, status='passed', files=factory.inventory(output)))
        return factory.hash_file(manifest)

    def apply(self, action, revision=0, digest=None):
        return self.store.apply(self.pid, dict(expected_revision=revision,
                                               spec_sha256=self.digest if digest is None else digest,
                                               action=action))

    def promote(self, job=FIRST, revision=0, digest=None):
        return self.apply(dict(op='promote', job_id=job), revision, digest)

    def activate(self, release, revision, digest=None):
        return self.apply(dict(op='activate', release_id=release), revision, digest)

    def test_explicit_promotion_activation_and_restart(self):
        empty = self.store.get(self.pid)
        self.assertEqual(empty, dict(project_id=self.pid, releases=[], revision=0,
                                     spec_sha256=self.digest, active_state='empty', active_release_id=None))
        output, _ = self.build(sealed=False)
        self.assertEqual(empty, self.store.get(self.pid))
        self.assertFalse(self.path.exists())
        first = self.promote()
        release = first['releases'][0]
        self.assertEqual(release['id'], first['active_release_id'])
        self.assertEqual(release['manifest_sha256'], factory.hash_file(output / 'manifest.json'))
        self.assertEqual(release['output'], f'jobs/{FIRST}/output')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.build(SECOND)
        second = self.promote(SECOND, 1)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['releases'][0], release)
        self.assertNotEqual(second['active_release_id'], release['id'])
        third = self.activate(release['id'], 2)
        self.assertEqual(third, dict(second, revision=3, active_release_id=release['id']))
        unchanged = self.path.read_bytes()
        self.assertEqual(self.activate(release['id'], 3), third)
        with self.assertRaises(ValueError):
            self.promote(FIRST, 3)
        self.assertEqual(self.path.read_bytes(), unchanged)
        reopened_pipeline = Pipeline(ROOT, self.workspace)
        self.addCleanup(reopened_pipeline.worker.shutdown)
        reopened = ReleaseStore(ProjectStore(ROOT, self.workspace), reopened_pipeline)
        self.assertEqual(reopened.get(self.pid), third)

    def test_rehashed_tampering_detected_before_promotion_and_after_legacy_release(self):
        output, job = self.build()
        scene = output / 'assets/scene.tscn'
        scene.write_text('changed')
        with self.assertRaises(ValueError):
            self.promote()
        self.seal(output)
        self.assertEqual(factory.verify_package(output), [])
        with self.assertRaisesRegex(ValueError, 'verified build'):
            self.promote()
        self.assertFalse(self.path.exists())
        del job['manifest_sha256']
        factory.write_json(output.parent / 'job.json', job)
        first = self.promote()
        release = first['active_release_id']
        before = self.path.read_bytes()
        manifest = output / 'manifest.json'
        original = manifest.read_bytes()
        manifest.write_bytes(original + b'\n')
        self.assertEqual(factory.verify_package(output), [])
        self.assertEqual(self.store.get(self.pid)['active_state'], 'invalid')
        with self.assertRaisesRegex(ValueError, 'recorded seal'):
            self.activate(release, 1)
        self.assertEqual(before, self.path.read_bytes())
        manifest.write_bytes(original)
        self.assertEqual(self.store.get(self.pid), first)
        scene.write_text('another edit')
        self.assertEqual(self.store.get(self.pid)['active_state'], 'invalid')

    def test_stale_release_and_current_spec_promotion_preserve_history(self):
        self.build()
        initial = self.promote()
        release = initial['active_release_id']
        changed = dict(self.spec, seed=self.spec['seed'] + 1)
        digest = spec_digest(changed)
        self.projects.save_spec(self.pid, changed)
        self.assertEqual(self.store.get(self.pid), dict(initial, spec_sha256=digest, active_state='stale'))
        self.build(SECOND)
        for operation in (lambda: self.promote(SECOND, 1, digest), lambda: self.activate(release, 1, digest)):
            with self.assertRaises(ValueError):
                operation()
        with self.assertRaises(FileExistsError):
            self.promote(SECOND, 1, self.digest)
        self.build(THIRD, spec=changed)
        new = self.promote(THIRD, 1, digest)
        self.assertEqual(new['revision'], 2)
        self.assertEqual(new['releases'][0], initial['releases'][0])
        self.assertEqual(new['active_state'], 'current')
        self.projects.save_spec(self.pid, self.spec)
        self.assertEqual(self.activate(release, 2)['active_state'], 'current')

    def test_job_identity_snapshot_output_and_claims_checked(self):
        output, job = self.build()
        jobfile = output.parent / 'job.json'
        for update in (dict(id=SECOND), dict(project_id='other'), dict(kind='assets'),
                       dict(status='running'), dict(status='failed'), dict(verified=1),
                       dict(verified=False), dict(spec_sha256='1' * 64),
                       dict(output=f'jobs/{SECOND}/output'), dict(output=str(output)),
                       dict(output=f'jobs/{FIRST}/../{FIRST}/output'), dict(manifest_sha256=None)):
            factory.write_json(jobfile, dict(job, **update))
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.promote()
        factory.write_json(jobfile, job)
        factory.write_json(output.parent / 'spec.json', {})
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            self.promote()
        with self.assertRaises(ValueError):
            self.promote(SECOND)
        self.assertFalse(self.path.exists())

    def test_client_cannot_supply_release_evidence_or_mutate_history(self):
        self.build()
        for act in (None, {}, {'op': 'delete'}, {'op': 'promote', 'job_id': '../outside'},
                    {'op': 'promote', 'job_id': FIRST, 'verified': True},
                    {'op': 'activate', 'release_id': THIRD},
                    {'op': 'activate', 'release_id': FIRST, 'manifest_sha256': self.digest}):
            with self.subTest(act=act), self.assertRaises(ValueError):
                self.apply(act)
        for rev in (-1, True, '0'):
            with self.subTest(rev=rev), self.assertRaises(ValueError):
                self.promote(revision=rev)
        with self.assertRaises(FileExistsError):
            self.promote(revision=1)
        with self.assertRaises(FileExistsError):
            self.promote(digest='0' * 64)
        self.assertFalse(self.path.exists())

    def test_corrupt_registry_symlinks_and_nonregular_files_fail_closed(self):
        output, _ = self.build()
        first = self.promote()
        recorded = self.path.read_bytes()
        old = json.loads(recorded)
        corrupt = [dict(old, active_release_id=THIRD), dict(old, project_id='elsewhere'),
                   dict(old, releases=old['releases'] * 2, revision=2), dict(old, revision=True),
                   dict(old, releases=[dict(old['releases'][0], output='/escape')])]
        for raw in (b'{', *(json.dumps(item).encode() for item in corrupt)):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.store.get(self.pid)
            with self.assertRaises(ValueError):
                self.promote(SECOND, 1)
            self.assertEqual(self.path.read_bytes(), raw)
        self.path.unlink()
        outside = self.workspace / 'elsewhere'
        outside.write_bytes(recorded)
        self.path.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.store.get(self.pid)
        self.assertEqual(outside.read_bytes(), recorded)
        self.path.unlink()
        os.mkfifo(self.path)
        with self.assertRaises(ValueError):
            self.store.get(self.pid)
        self.path.unlink()
        self.path.write_bytes(recorded)
        for path in (output / 'assets/scene.tscn', output / 'assets', output / 'manifest.json',
                     output, output.parent / 'job.json', output.parent / 'spec.json', output.parent):
            moved = path.with_name(path.name + '.saved')
            path.rename(moved)
            try:
                path.symlink_to(moved)
                with self.subTest(path=path):
                    self.assertEqual(self.store.get(self.pid)['active_state'], 'invalid')
                    with self.assertRaises(ValueError):
                        self.activate(first['active_release_id'], 1)
            finally:
                path.unlink()
                moved.rename(path)
        self.assertEqual(self.store.get(self.pid), first)
        os.mkfifo(output / 'unlisted.pipe')
        self.assertEqual(self.store.get(self.pid)['active_state'], 'invalid')
        self.assertEqual(self.path.read_bytes(), recorded)

    def test_live_job_lease_returns_without_waiting_for_build_completion(self):
        output, _ = self.build()
        with ThreadPoolExecutor(max_workers=1) as pool:
            lease = os.open(output.parent, os.O_DIRECTORY)
            try:
                fcntl.flock(lease, fcntl.LOCK_EX)
                result = pool.submit(self.promote)
                with self.assertRaisesRegex(ValueError, 'still in use'):
                    result.result(timeout=2)
            finally:
                os.close(lease)
        self.assertFalse(self.path.exists())

    def test_spec_writes_and_promotion_use_the_same_lock(self):
        self.build()
        started = threading.Event()
        def promote():
            started.set()
            return self.promote()

        with ThreadPoolExecutor(max_workers=1) as pool:
            directory = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                fcntl.flock(directory, fcntl.LOCK_EX)
                future = pool.submit(promote)
                self.assertTrue(started.wait(2))
                with self.assertRaises(TimeoutError):
                    future.result(timeout=.05)
                changed = dict(self.spec, seed=self.spec['seed'] + 1)
                factory.write_json(self.path.parent / 'spec.json', changed)
            finally:
                os.close(directory)
            with self.assertRaises(FileExistsError):
                future.result(timeout=2)
        self.assertFalse(self.path.exists())

    def test_changes_during_verification_and_loss_of_modern_seal_rejected(self):
        output, job = self.build()
        verifier = factory.verify_package
        def mutate(verified_snapshot):
            (output / 'assets/scene.tscn').write_text('changed while hashing')
            return verifier(verified_snapshot)

        with patch.object(factory, 'verify_package', side_effect=mutate), self.assertRaises(ValueError):
            self.promote()
        self.seal(output)
        job.pop('manifest_sha256')
        factory.write_json(output.parent / 'job.json', dict(job, queue_sequence=1))
        with self.assertRaisesRegex(ValueError, 'verified build'):
            self.promote()
        self.assertFalse(self.path.exists())

    def test_atomic_failure_and_compare_and_swap_across_instances(self):
        self.build()
        self.build(SECOND)
        with patch('command_center.release_store.os.replace', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                self.promote()
        self.assertEqual(set(self.path.parent.iterdir()),
                         {self.path.parent / 'project.json', self.path.parent / 'spec.json'})
        barrier = threading.Barrier(2)
        def write(job):
            store = ReleaseStore(ProjectStore(ROOT, self.workspace), self.pipeline)
            barrier.wait(timeout=5)
            try:
                return store.apply(self.pid, dict(expected_revision=0, spec_sha256=self.digest,
                                                  action=dict(op='promote', job_id=job)))
            except FileExistsError:
                return None

        with ThreadPoolExecutor(max_workers=2) as threads:
            results = list(threads.map(write, [FIRST, SECOND]))
        self.assertEqual(results.count(None), 1)
        self.assertIn(self.store.get(self.pid), results)

    def test_real_pipeline_job_can_be_promoted(self):
        with tempfile.TemporaryDirectory() as fake_root:
            builder = Path(fake_root) / 'multiplayer/build.py'
            builder.parent.mkdir()
            builder.write_text("""
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[-1])
if '--verify' in sys.argv:
    sys.exit(0 if (out/'manifest.json').is_file() else 1)
out.mkdir()
payload = b'release test'
(out/'asset.txt').write_bytes(payload)
entry = dict(path='asset.txt', bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
(out/'manifest.json').write_text(json.dumps(dict(schema=1, status='passed', files=[entry])))
""")
            pipeline = Pipeline(Path(fake_root), self.workspace)
            self.addCleanup(pipeline.worker.shutdown)
            project = self.projects.create('Relay', 'multiplayer')
            job = pipeline.submit(self.projects.directory(project['id']))
            pipeline.worker.shutdown()
            self.assertEqual(pipeline.get(job['id'])['status'], 'passed')
            store = ReleaseStore(self.projects, pipeline)
            release = store.apply(project['id'], dict(spec_sha256=spec_digest({}), expected_revision=0,
                                                       action=dict(op='promote', job_id=job['id'])))
            self.assertEqual(release['active_state'], 'current')
            self.assertEqual(store.get(project['id']), release)


if __name__ == '__main__':
    unittest.main()
