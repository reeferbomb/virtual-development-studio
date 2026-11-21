import fcntl
import json
import multiprocessing
import os
import tempfile
import threading
import unittest
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from command_center.checkpoints import CheckpointStore
from command_center.projects import ProjectStore
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "river-city"


def checkpoint_update(snapshot, elapsed, action):
    return {
        "expected_revision": snapshot["revision"],
        "spec_sha256": snapshot["spec_sha256"],
        "elapsed_seconds": elapsed,
        "status": "in_progress",
        "completed_work": ["Built the city layout"],
        "verification_evidence": ["City layout validation passed"],
        "remaining_work": ["Verify the traffic simulation"],
        "next_action": action,
    }


def competing_writer(workspace, barrier, results, action):
    checkpoints = CheckpointStore(ProjectStore(ROOT, workspace))
    snapshot = checkpoints.get(PROJECT)
    update = checkpoint_update(snapshot, 360, action)
    barrier.wait(timeout=15)
    try:
        checkpoints.save(PROJECT, update)
    except FileExistsError:
        outcome = "conflict"
    else:
        outcome = "committed"
    results.put((snapshot["revision"], outcome, action))


class CheckpointConcurrencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / "workspace"
        self.projects = ProjectStore(ROOT, self.workspace)
        self.project = self.projects.create("River City", "city")
        self.checkpoints = CheckpointStore(self.projects)

    def reopen(self):
        return CheckpointStore(ProjectStore(ROOT, self.workspace))

    def seed_checkpoint(self):
        initial = self.checkpoints.get(PROJECT)
        update = checkpoint_update(initial, 300, "Inspect traffic routes")
        self.checkpoints.save(PROJECT, update)
        return self.reopen().get(PROJECT)

    def test_checkpoint_and_resume_budget_survive_restart(self):
        initial = self.checkpoints.get(PROJECT)
        self.assertEqual(initial["project_id"], PROJECT)
        self.assertEqual(initial["spec_sha256"], spec_digest(self.project["spec"]))
        self.assertEqual((initial["state"], initial["revision"], initial["checkpoint"]), ("empty", 0, None))
        self.assertEqual((initial["target_seconds"], initial["remaining_seconds"]), (18000, 18000))

        update = checkpoint_update(initial, 487, "Inspect route 17")
        self.checkpoints.save(PROJECT, update)
        resumed = self.reopen().get(PROJECT)
        self.assertEqual((resumed["state"], resumed["revision"]), ("current", 1))
        self.assertEqual((resumed["target_seconds"], resumed["remaining_seconds"]), (18000, 17513))
        for key, value in update.items():
            if key != "expected_revision":
                self.assertEqual(resumed["checkpoint"][key], value)

    def test_two_processes_competing_for_one_revision_publish_one_winner(self):
        previous = self.seed_checkpoint()
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        results = context.Queue()
        self.addCleanup(results.close)
        writers = []
        try:
            for action in ("Inspect the east route", "Inspect the west route"):
                writer = context.Process(target=competing_writer, args=(self.workspace, barrier, results, action))
                writer.start()
                writers.append(writer)
            for writer in writers:
                writer.join(timeout=20)
                self.assertEqual(writer.exitcode, 0, "Writer failed or timed out")
            outcomes = [results.get(timeout=2) for _ in writers]
        finally:
            for writer in writers:
                if writer.is_alive():
                    writer.terminate()
                writer.join()
                writer.close()

        self.assertEqual([revision for revision, _, _ in outcomes], [previous["revision"]] * 2)
        self.assertCountEqual([outcome for _, outcome, _ in outcomes], ["committed", "conflict"])
        winner = next(action for _, outcome, action in outcomes if outcome == "committed")
        persisted = self.reopen().get(PROJECT)
        self.assertEqual((persisted["state"], persisted["revision"]), ("current", previous["revision"] + 1))
        self.assertEqual(persisted["checkpoint"]["next_action"], winner)
        self.assertEqual(persisted["remaining_seconds"], 18000 - 360)

    def test_invalid_updates_preserve_persisted_bytes_and_revision(self):
        previous = self.seed_checkpoint()
        path = self.projects.directory(PROJECT) / "checkpoint.json"
        original_bytes = path.read_bytes()
        update = checkpoint_update(previous, 360, "Inspect route 17")
        for key, value in (
            ("elapsed_seconds", -1), ("elapsed_seconds", 18001), ("elapsed_seconds", True),
            ("elapsed_seconds", 299), ("completed_work", "not a list"),
            ("verification_evidence", [42]), ("remaining_work", {}),
            ("status", "unknown"), ("next_action", ""),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    self.checkpoints.save(PROJECT, {**update, key: value})
                self.assertEqual(path.read_bytes(), original_bytes)
                self.assertEqual(self.reopen().get(PROJECT), previous)

    def test_changed_spec_requires_explicit_reset_bound_to_current_spec_and_revision(self):
        previous = self.seed_checkpoint()
        new_spec = dict(self.project["spec"], seed=801)
        self.projects.save_spec(PROJECT, new_spec)
        stale = self.reopen().get(PROJECT)
        self.assertEqual((stale["state"], stale["revision"]), ("stale", previous["revision"]))
        self.assertEqual(stale["spec_sha256"], spec_digest(new_spec))
        self.assertEqual(stale["checkpoint"], previous["checkpoint"])

        reset = dict(checkpoint_update(stale, 0, "Validate the changed city"), reset_for_spec_change=True)
        for invalid in (
            checkpoint_update(stale, 360, "Continue old work"),
            dict(reset, spec_sha256=previous["spec_sha256"]),
            dict(reset, expected_revision=0),
        ):
            with self.subTest(update=invalid):
                with self.assertRaises(FileExistsError):
                    self.checkpoints.save(PROJECT, invalid)
                self.assertEqual(self.reopen().get(PROJECT), stale)

        self.checkpoints.save(PROJECT, reset)
        current = self.reopen().get(PROJECT)
        self.assertEqual((current["state"], current["revision"]), ("current", stale["revision"] + 1))
        self.assertEqual(current["remaining_seconds"], 18000)
        self.assertEqual(current["checkpoint"]["spec_sha256"], spec_digest(new_spec))

    def test_project_lock_serializes_spec_and_checkpoint_writers(self):
        previous = self.seed_checkpoint()
        new_spec = dict(self.project["spec"], seed=901)
        update = checkpoint_update(previous, 360, "Validate the old city")
        spec_started = threading.Event()
        checkpoint_started = threading.Event()

        def save_spec():
            projects = ProjectStore(ROOT, self.workspace)
            spec_started.set()
            return projects.save_spec(PROJECT, new_spec)

        def save_checkpoint():
            checkpoints = self.reopen()
            checkpoint_started.set()
            try:
                checkpoints.save(PROJECT, update)
            except FileExistsError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            lock = os.open(self.projects.directory(PROJECT), os.O_RDONLY)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
                spec_writer = pool.submit(save_spec)
                checkpoint_writer = pool.submit(save_checkpoint)
                self.assertTrue(spec_started.wait(5) and checkpoint_started.wait(5))
                finished, _ = wait([spec_writer, checkpoint_writer], timeout=0.25, return_when=FIRST_COMPLETED)
                self.assertFalse(finished, "A writer published while the project lock was held")
            finally:
                os.close(lock)
            self.assertEqual(spec_writer.result(timeout=5)["spec"], new_spec)
            checkpoint_won_lock = checkpoint_writer.result(timeout=5)

        final = self.reopen().get(PROJECT)
        self.assertEqual(final["state"], "stale")
        self.assertEqual(final["spec_sha256"], spec_digest(new_spec))
        self.assertEqual(final["checkpoint"]["spec_sha256"], previous["spec_sha256"])
        self.assertEqual(final["revision"], previous["revision"] + int(checkpoint_won_lock))
        expected = update if checkpoint_won_lock else previous["checkpoint"]
        self.assertEqual(final["checkpoint"]["next_action"], expected["next_action"])

    def test_linked_checkpoint_cannot_be_read_or_replaced(self):
        previous = self.seed_checkpoint()
        checkpoint = self.projects.directory(PROJECT) / "checkpoint.json"
        external = self.workspace.parent / "external.json"
        checkpoint.rename(external)
        original = external.read_bytes()
        try:
            checkpoint.symlink_to(external)
        except (NotImplementedError, PermissionError) as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")
        with self.assertRaises(ValueError):
            self.reopen().get(PROJECT)
        with self.assertRaises(ValueError):
            self.reopen().save(PROJECT, checkpoint_update(previous, 360, "Inspect route 17"))
        self.assertTrue(checkpoint.is_symlink())
        self.assertEqual(external.read_bytes(), original)

    def test_waiting_writer_rechecks_digest_after_spec_publication(self):
        previous = self.seed_checkpoint()
        project_dir = self.projects.directory(PROJECT)
        changed = dict(self.project["spec"], seed=801)
        staged = self.workspace / "edited-spec.json"
        staged.write_text(json.dumps(changed), encoding="utf-8")
        started = threading.Event()
        update = checkpoint_update(previous, 360, "Validate the old routes")

        def save_waiting_checkpoint():
            store = self.reopen()
            started.set()
            store.save(PROJECT, update)

        with ThreadPoolExecutor(max_workers=1) as pool:
            # Act as a spec writer already holding the lock. The new digest must
            # be observed when the queued checkpoint writer acquires it.
            lock = os.open(project_dir, os.O_RDONLY)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
                writer = pool.submit(save_waiting_checkpoint)
                self.assertTrue(started.wait(5))
                finished, _ = wait([writer], timeout=0.25)
                self.assertFalse(finished)
                staged.replace(project_dir / "spec.json")
            finally:
                os.close(lock)
            with self.assertRaises(FileExistsError):
                writer.result(timeout=5)

        final = self.reopen().get(PROJECT)
        self.assertEqual((final["state"], final["revision"]), ("stale", previous["revision"]))
        self.assertEqual(final["spec_sha256"], spec_digest(changed))
        self.assertEqual(final["checkpoint"], previous["checkpoint"])


if __name__ == "__main__":
    unittest.main()
