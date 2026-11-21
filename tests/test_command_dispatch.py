import json
import unittest
from collections import Counter

from command_center.provenance import spec_digest
from command_center.dispatch import scheduled_dispatch_plan
from command_center.team import team_plan


class CommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.project = {
            "id": "relay-basin",
            "name": "Relay Basin",
            "kind": "openworld",
            "spec": {"seed": 42},
        }

    def test_default_profile_has_six_slots_with_exact_model_effort_pairs(self):
        plan = team_plan(self.project, [])
        dispatch = plan["dispatch_plan"]
        profile = dispatch["profile"]
        expected = {("gpt-6.2-astra", "ultra"): 5, ("gpt-6.2-sol", "max"): 1}
        self.assertEqual(profile["mode"], "fast")
        self.assertEqual(profile["service_tier"], "priority")
        self.assertEqual(profile["max_parallel"], 6)
        self.assertEqual(profile["team_name"], "The Midnight Shift")
        self.assertEqual([r["codename"] for r in profile["roles"]], [
            "Count Blueprint", "Major Mayhem", "Doctor Doomcheck", "Madame Glitch", "Grimbrush", "Baron Buildgrave",
        ])
        self.assertEqual(Counter(
            (role["model_id"], role["reasoning_effort"]) for role in profile["roles"]
        ), expected)
        self.assertEqual(Counter(
            (args["model"], args["reasoning_effort"]) for args in dispatch["spawn_args"]
        ), expected)

    def test_export_handoff_uses_exact_spawn_arguments_and_saved_spec_identity(self):
        plan = team_plan(self.project, [])
        dispatch = plan["dispatch_plan"]
        self.assertEqual(dispatch["execution_mode"], "export_only")
        self.assertEqual(dispatch["host_tool"], "collaboration.spawn_agent")
        self.assertEqual(dispatch["project"]["spec_sha256"], spec_digest(self.project["spec"]))
        self.assertEqual(json.loads(json.dumps(dispatch)), dispatch)
        self.assertEqual([args["task_name"] for args in dispatch["spawn_args"]], [
            "count_blueprint", "major_mayhem", "doctor_doomcheck", "madame_glitch", "grimbrush", "baron_buildgrave",
        ])
        for role, args in zip(plan["roles"], dispatch["spawn_args"], strict=True):
            self.assertEqual(set(args), {"task_name", "fork_turns", "model", "reasoning_effort", "message"})
            self.assertEqual(args["task_name"], role["agent_task_name"])
            self.assertIn(role["codename"], args["message"])
            self.assertEqual(args["fork_turns"], "none")
            self.assertIn(role["task"], args["message"])
            self.assertIn(self.project["id"], args["message"])
            self.assertIn(dispatch["project"]["spec_sha256"], args["message"])
            for endpoint in ('supervisor', 'sprint', 'acceptance', 'evidence-history', 'work-orders', 'handoffs', 'dossier', 'recovery',
                             'blueprint', 'forecast', 'dependency-impact', 'preflight',
                             'specialist-memory', 'priorities', 'recovery-advice'):
                self.assertIn(f'/api/projects/{self.project["id"]}/{endpoint}', args['message'])
            self.assertIn('/api/allocation', args['message'])
            self.assertIn('untrusted historical observations', args['message'])
            self.assertIn('advisory', args['message'])
            self.assertIn('lead', args['message'])

    def test_export_is_deterministic_and_independent_from_job_lifecycle(self):
        jobs = [{
            "id": "build",
            "project_id": self.project["id"],
            "created_at": "2026-11-20T02:00:00+00:00",
            "status": "running",
        }]
        dispatch = team_plan(self.project, [])["dispatch_plan"]
        self.assertEqual(dispatch, team_plan(self.project, jobs)["dispatch_plan"])
        self.assertTrue({"status", "agents", "agent_ids"}.isdisjoint(dispatch))
        revised = self.project | {"spec": {"seed": 43}}
        self.assertNotEqual(dispatch, team_plan(revised, [])["dispatch_plan"])

    def test_sustained_work_policy_is_exported_to_every_agent(self):
        dispatch = team_plan(self.project, [])["dispatch_plan"]
        policy = dispatch["profile"]["continuity"]
        self.assertEqual(policy["target_duration_seconds"], 18000)
        self.assertEqual(policy["checkpoint_interval_seconds"], 300)
        self.assertTrue(policy["continue_within_scope"])
        self.assertFalse(policy["pause_for_routine_confirmation"])
        self.assertTrue(policy["resume_from_checkpoint"])
        self.assertTrue(policy["respect_host_limits"])
        self.assertIn("user_stop", policy["stop_conditions"])
        self.assertIn("host_limit", policy["stop_conditions"])
        self.assertIn("authorization_blocker", policy["stop_conditions"])
        for args in dispatch["spawn_args"]:
            self.assertIn("5 hours", args["message"])
            self.assertIn("5 minutes", args["message"])
            self.assertIn("host limits", args["message"])
            self.assertIn("checkpoint", args["message"])

    def test_export_points_hosts_to_the_project_checkpoint(self):
        dispatch = team_plan(self.project, [])["dispatch_plan"]
        access = dispatch["checkpoint_access"]
        self.assertEqual(access["path"], "/api/projects/relay-basin/checkpoint")
        self.assertEqual(access["read_method"], "GET")
        self.assertEqual(access["write_method"], "PUT")
        self.assertTrue(access["requires_expected_revision"])
        self.assertEqual(access["writer"], "lead")
        for args in dispatch["spawn_args"]:
            self.assertIn(access["path"], args["message"])
            self.assertIn("lead", args["message"])

    def test_export_gate_requires_lead_to_claim_ready_tasks(self):
        dispatch = team_plan(self.project, [])["dispatch_plan"]
        access = dispatch["task_board_access"]
        self.assertEqual(access["path"], "/api/projects/relay-basin/tasks")
        self.assertEqual(access["read_method"], "GET")
        self.assertEqual(access["write_method"], "PUT")
        self.assertTrue(access["requires_expected_revision"])
        self.assertEqual(access["writer"], "lead")
        self.assertEqual(access["dispatch_policy"], "ready_idle_roles_only")
        for args in dispatch["spawn_args"]:
            self.assertIn(access["path"], args["message"])
            self.assertIn("ready", args["message"])
            self.assertIn("stale", args["message"])
            self.assertIn("claim", args["message"])

    def test_ready_dispatch_export_contains_only_scheduled_idle_roles(self):
        digest = spec_digest(self.project["spec"])
        board = {
            "project_id": self.project["id"], "spec_sha256": digest,
            "board_spec_sha256": digest, "revision": 4, "state": "current",
            "tasks": [{"id": "test-build", "title": "Verify the build", "role": "verification", "status": "pending"}],
            "ready_task_ids": ["test-build"],
            "assignments": [{"task_id": "test-build", "role": "verification", "model_id": "gpt-6.2-astra", "reasoning_effort": "ultra"}],
        }
        export = scheduled_dispatch_plan(self.project, board)
        self.assertEqual(export["board_revision"], 4)
        self.assertEqual(export["board_state"], "current")
        self.assertEqual(export["execution_mode"], "export_only")
        self.assertEqual(len(export["spawn_args"]), 1)
        args = export["spawn_args"][0]
        self.assertEqual(args["task_name"], "doctor_doomcheck")
        self.assertEqual(args["model"], "gpt-6.2-astra")
        self.assertEqual(args["reasoning_effort"], "ultra")
        self.assertIn("test-build", args["message"])
        self.assertIn("Verify the build", args["message"])
        self.assertIn("claim", args["message"])
        self.assertIn("curriculum", args["message"].lower())
        for invalid in (dict(board, state="stale"), dict(board, spec_sha256="wrong"), dict(board, project_id="wrong")):
            self.assertEqual(scheduled_dispatch_plan(self.project, invalid)["spawn_args"], [])
