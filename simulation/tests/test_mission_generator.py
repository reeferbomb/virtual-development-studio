import random
import unittest

from simulation.mission_generator import generate_mission


class MissionGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.pools = {
            "interact_ids": ["relay_b", "relay_a"],
            "drive_ids": ["checkpoint_2", "checkpoint_1"],
            "visit_ids": ["gate", "depot", "base"],
        }

    def test_replay_ignores_pool_order_and_global_rng(self):
        before = random.getstate()
        stages = generate_mission(237, **self.pools)
        reversed_pools = {key: ids[::-1] for key, ids in self.pools.items()}
        self.assertEqual(stages, generate_mission(237, **reversed_pools))
        self.assertEqual(before, random.getstate())

    def test_varies_only_within_available_targets(self):
        variants = set()
        for seed in [*range(32), 2**31 - 1]:
            stages = generate_mission(seed, **self.pools)
            self.assertEqual([stage["action"] for stage in stages], ["interact", "drive", "visit"])
            for stage in stages:
                self.assertEqual(set(stage), {"action", "target"})
                self.assertIn(stage["target"], self.pools[stage["action"] + "_ids"])
            variants.add(tuple(stage["target"] for stage in stages))
        self.assertGreater(len(variants), 1)

    def test_singleton_pools(self):
        stages = generate_mission(0, interact_ids=["relay"], drive_ids=["checkpoint"], visit_ids=["goal"])
        self.assertEqual([stage["target"] for stage in stages], ["relay", "checkpoint", "goal"])

    def test_rejects_invalid_seed_and_pools(self):
        for seed in (-1, 2**31, True, "42", 1.5):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                generate_mission(seed, **self.pools)
        for action in self.pools:
            for invalid in ([], "", "relay", [""], [" gate "], [2], ["gate", "gate"]):
                with self.subTest(action=action, invalid=invalid), self.assertRaises(ValueError):
                    generate_mission(42, **{**self.pools, action: invalid})


if __name__ == "__main__":
    unittest.main()
