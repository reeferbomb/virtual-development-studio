import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from multiplayer import stress


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.host = dict(joined=2, started=True, accepted=41, rejected=2,
                         damage_events=2, pvp_damage_events=1, npc_attack_events=1, npc_damage_events=1, movement_m=1.5,
                         peak_members=3, disconnected=2, **{"pass": True})
        self.clients = [dict(peer_id=i, snapshots=10, saw_started=True,
                             max_members=3, own_movement_m=1.5, min_npc_health=50, saw_player_damage=True, **{"pass": True}) for i in (2, 3)]

    def test_markers(self):
        marker = stress.CLIENT
        self.assertEqual(stress.parse_summary("Godot\n" + marker + ' {"pass": true}\n', marker), {"pass": True})
        for log in ["missing", "prefix " + marker + " {}", marker + " []", marker + " broken",
                    marker + " {}\n" + marker + " {}"]:
            with self.subTest(log=log), self.assertRaises(ValueError):
                stress.parse_summary(log, marker)

    def test_evidence(self):
        self.assertEqual(stress.validate(self.host, self.clients, 2), [])
        for field, value in dict(joined=1, peak_members=2, started=False,
                                 accepted=0, rejected=0, damage_events=0, pvp_damage_events=0, npc_attack_events=0, disconnected=1,
                                 npc_damage_events=0, movement_m=float('nan')).items():
            with self.subTest(field=field):
                self.assertTrue(stress.validate(dict(self.host, **{field: value}), self.clients, 2))
        for field, value in dict(peer_id=2, snapshots=0, saw_started=False,
                                 max_members=2, own_movement_m=0, min_npc_health=150, saw_player_damage=False, **{"pass": False}).items():
            with self.subTest(field=field):
                self.assertTrue(stress.validate(self.host, [self.clients[0], dict(self.clients[1], **{field: value})], 2))

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "project.godot").touch()
            result = subprocess.run([sys.executable, str(ROOT / "multiplayer/stress.py"),
                                     "--project", temp, "--output", temp, "--clients", "1"],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
            self.assertFalse((root / "report.json").exists())
