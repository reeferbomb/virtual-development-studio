"""The two-crew option must preserve the six original roles and honest deployment state."""
import copy
import unittest

from command_center.crew_split import split_profile


ROLE_IDS = ("architecture", "gameplay", "verification", "ui", "content", "build_operations")


def studio_profile():
    return {
        "id": "studio-fast", "team_name": "The Midnight Shift", "max_parallel": 6,
        "roles": [
            {"id": i, "codename": n, "model_id": "unchanged-test-identifier"}
            for i, n in zip(ROLE_IDS, (
                "Count Blueprint", "Major Mayhem", "Doctor Doomcheck",
                "Madame Glitch", "Grimbrush", "Baron Buildgrave",
            ))
        ],
    }


class CrewSplitTests(unittest.TestCase):
    def test_exactly_two_disjoint_three_member_crews(self):
        result = split_profile(studio_profile(), project="Dig It")
        self.assertEqual([c["id"] for c in result["crews"]],
                         ["visual_realism", "real_world_physics"])
        self.assertEqual([len(c["assignments"]) for c in result["crews"]], [3, 3])
        ids = [a["role_id"] for c in result["crews"] for a in c["assignments"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(ROLE_IDS))

    def test_preexisting_dispatch_profile_is_not_mutated(self):
        profile = studio_profile()
        before = copy.deepcopy(profile)
        result = split_profile(profile, project="Dig It")
        self.assertEqual(profile, before)
        self.assertEqual(result["source_profile_id"], profile["id"])
        self.assertTrue(all(a["model_id"] == "unchanged-test-identifier"
                            for c in result["crews"] for a in c["assignments"]))

    def test_no_worker_can_be_claimed_spawned(self):
        result = split_profile(studio_profile(), project="Dig It")
        self.assertEqual(result["execution_mode"], "export_only")
        self.assertEqual(result["deployment_status"], "not_dispatched")
        self.assertTrue(all(a["status"] == "pending_authorized_host"
                            for c in result["crews"] for a in c["assignments"]))
        self.assertIn("real_runtime_tests", result["merge_gates"])
        self.assertIn("performance", result["merge_gates"])
        self.assertIn("rollback", result["merge_gates"])

    def test_rejects_missing_duplicate_and_unknown_roles(self):
        missing = studio_profile()
        missing["roles"].pop()
        with self.assertRaises(ValueError):
            split_profile(missing, project="Dig It")
        duplicate = studio_profile()
        duplicate["roles"][-1]["id"] = "content"
        with self.assertRaises(ValueError):
            split_profile(duplicate, project="Dig It")
        changed = studio_profile()
        changed["roles"][-1]["id"] = "other"
        with self.assertRaises(ValueError):
            split_profile(changed, project="Dig It")

    def test_no_empty_project(self):
        with self.assertRaises(ValueError):
            split_profile(studio_profile(), project=" ")

    def test_crew_assignments_are_exclusive_and_cross_reviewed(self):
        result = split_profile(studio_profile(), project="Dig It")
        visual, physics = result["crews"]
        self.assertEqual(visual["lead_role"], "content")
        self.assertEqual(physics["lead_role"], "gameplay")
        self.assertEqual(set(a["role_id"] for a in visual["assignments"]),
                         {"content", "ui", "build_operations"})
        self.assertEqual(set(a["role_id"] for a in physics["assignments"]),
                         {"architecture", "gameplay", "verification"})
        self.assertIn("verification", result["cross_review"]["visual_reviewer"])
        self.assertIn("build_operations", result["cross_review"]["physics_build_reviewer"])


if __name__ == "__main__":
    unittest.main()
