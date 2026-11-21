"""Black-box scheduler acceptance and a compare-and-swap race between independent writers."""

import multiprocessing
import shutil
import tempfile
import unittest
from pathlib import Path

from command_center.projects import ProjectStore
from command_center.scheduler_smoke import check_build_gate, check_workflow
from command_center.server import ROOT
from command_center.task_store import TaskStore


def _competing_writer(workspace, project_id, task_id, barrier, outcomes):
    store = TaskStore(ProjectStore(ROOT, workspace))
    observed = store.get(project_id)
    task = {'id': task_id, 'title': 'Review the terrain', 'role': 'gameplay',
            'priority': 3, 'depends_on': [], 'gate': 'manual'}
    payload = {'expected_revision': observed['revision'], 'spec_sha256': observed['spec_sha256'],
               'action': {'op': 'add', 'task': task}}
    barrier.wait(timeout=15)
    try:
        store.apply(project_id, payload)
    except FileExistsError:
        result = 'conflict'
    else:
        result = 'saved'
    outcomes.put((result, task_id, observed['revision']))


class SchedulerIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)

    def test_http_dependencies_capacity_evidence_reassignment_restart_and_reset(self):
        result = check_workflow(self.workspace)
        self.assertEqual(result['completed_tasks'], 3)
        self.assertEqual(result['running_at_restart'], 2)
        self.assertNotEqual(result['reset_spec_sha256'], result['spec_sha256'])

    @unittest.skipUnless(shutil.which('godot'), 'Real world build requires the Godot executable')
    def test_http_build_gate_requires_verified_job_for_same_project_and_spec(self):
        result = check_build_gate(self.workspace)
        self.assertTrue(result['verified'])
        self.assertTrue(result['route_qa']['pass'])
        self.assertEqual(result['completed_task'], 'release')

    def test_independent_processes_cannot_both_commit_the_same_revision(self):
        projects = ProjectStore(ROOT, self.workspace)
        project_id = projects.create('Contended Board', 'world')['id']
        context = multiprocessing.get_context('spawn')
        barrier = context.Barrier(2)
        outcomes = context.Queue()
        self.addCleanup(outcomes.close)
        writers = []
        try:
            for task_id in ('east', 'west'):
                writer = context.Process(target=_competing_writer,
                                         args=(self.workspace, project_id, task_id, barrier, outcomes))
                writer.start()
                writers.append(writer)
            for writer in writers:
                writer.join(timeout=20)
                self.assertEqual(writer.exitcode, 0, 'Writer failed or timed out')
            records = [outcomes.get(timeout=2) for _ in writers]
        finally:
            for writer in writers:
                if writer.is_alive():
                    writer.terminate()
                writer.join()
                writer.close()

        self.assertCountEqual([result for result, _, _ in records], ['saved', 'conflict'])
        self.assertEqual([revision for _, _, revision in records], [0, 0])
        winner = next(task_id for result, task_id, _ in records if result == 'saved')
        persisted = TaskStore(ProjectStore(ROOT, self.workspace)).get(project_id)
        self.assertEqual(persisted['revision'], 1)
        self.assertEqual([task['id'] for task in persisted['tasks']], [winner])


if __name__ == '__main__':
    unittest.main()
