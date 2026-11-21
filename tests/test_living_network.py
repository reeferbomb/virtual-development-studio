import copy
import json
import math
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from living import network


def join(world, **fields):
    return world.join({"type": "join", "version": network.VERSION, **fields})


def move(seq, dx=1, dz=0):
    return {"type": "input", "seq": seq, "dx": dx, "dz": dz}


class WorldRulesTest(unittest.TestCase):
    def setUp(self):
        self.world = network.ReplicatedWorld(tick_hz=10)
        self.welcome = join(self.world)
        self.pid = self.welcome["id"]

    def row(self):
        return self.world.snapshot(self.pid)["players"][0]

    def test_server_clock_coalesces_input_and_normalizes_diagonal(self):
        for seq in range(1, 21):
            self.world.input(self.pid, move(seq, -1, 0))
        self.world.input(self.pid, move(21, 1, 1))
        self.assertEqual(self.row(), {"id": self.pid, "x": 0, "z": 0, "applied": 0})
        self.world.step()
        row = self.row()
        self.assertEqual(row["applied"], 21)
        self.assertEqual(row["x"], row["z"])
        self.assertAlmostEqual(math.hypot(row["x"], row["z"]), network.SPEED / 10)
        self.world.step()
        self.assertEqual(self.row(), row)

    def test_schema_rejects_invalid_inputs_and_leaves_sequence_available(self):
        inputs = [move(True), move(0), move(1, True), move(1, 2), move(1, 0.0),
                  move(1, dz=None), move(1) | {"id": "p2"}, move(1) | {"x": 10},
                  {"type": "input", "seq": 1, "dx": 1}, move(network.MAX_SEQ + 1)]
        for request in inputs:
            with self.subTest(request=request), self.assertRaisesRegex(network.ProtocolError, "invalid_input"):
                self.world.input(self.pid, request)
        with self.assertRaisesRegex(network.ProtocolError, "sequence_gap"):
            self.world.input(self.pid, move(2))
        self.world.input(self.pid, move(1))
        with self.assertRaisesRegex(network.ProtocolError, "stale_sequence"):
            self.world.input(self.pid, move(1))

    def test_coordinates_clamp_at_both_world_edges(self):
        for seq in range(1, 1001):
            self.world.input(self.pid, move(seq, 1, -1))
            self.world.step()
        self.assertEqual((self.row()["x"], self.row()["z"]), (network.WORLD_LIMIT, -network.WORLD_LIMIT))

    def test_resume_restores_only_applied_input_and_invalidates_old_token(self):
        token = self.welcome["resume"]
        with self.assertRaisesRegex(network.ProtocolError, "invalid_resume"):
            join(self.world, resume=token)
        self.world.input(self.pid, move(1))
        self.world.step()
        self.world.input(self.pid, move(2))
        self.world.leave(self.pid)
        resumed = join(self.world, resume=token)
        self.assertEqual(resumed["id"], self.pid)
        self.assertEqual(resumed["applied"], 1)
        self.assertNotEqual(resumed["resume"], token)
        self.world.input(self.pid, move(2, -1))
        self.world.step()
        self.assertAlmostEqual(self.row()["x"], 0.0)
        self.world.leave(self.pid)
        with self.assertRaisesRegex(network.ProtocolError, "invalid_resume"):
            join(self.world, resume=token)
        with patch.object(network.time, "monotonic", return_value=float("inf")):
            with self.assertRaisesRegex(network.ProtocolError, "invalid_resume"):
                join(self.world, resume=resumed["resume"])

    def test_client_state_schema(self):
        state = self.world.snapshot(self.pid)
        self.assertIs(network.validate_snapshot(state, self.pid), state)
        for key, val in (("x", float("nan")), ("z", 129), ("id", []), ("applied", True)):
            candidate = copy.deepcopy(state)
            candidate["players"][0][key] = val
            with self.subTest(key=key), self.assertRaisesRegex(network.ProtocolError, "invalid_snapshot"):
                network.validate_snapshot(candidate)
        for bad in (state | {"version": True}, state | {"self": "p2"}, state | {"tick": -1},
                    state | {"players": state["players"] * 2}, state | {"players": []}):
            with self.subTest(bad=bad), self.assertRaisesRegex(network.ProtocolError, "invalid_snapshot"):
                network.validate_snapshot(bad)


class WireTest(unittest.TestCase):
    def test_framing_accepts_fragmented_and_consecutive_messages(self):
        sender, reader = socket.socketpair()
        with sender, reader:
            body = b'{"type":"snapshot"}'
            framed = struct.pack("!I", len(body)) + body
            for byte in framed:
                sender.sendall(bytes([byte]))
            network.send_frame(sender, {"type": "leave"})
            self.assertEqual(network.receive_frame(reader), {"type": "snapshot"})
            self.assertEqual(network.receive_frame(reader), {"type": "leave"})

    def test_invalid_frames_are_bounded_and_connection_is_released(self):
        with network.WorldServer() as server:
            for body, expected in ((b"", "invalid_frame_size"), (b"[]", "object_required"),
                                   (b'{"a":1,"a":2}', "duplicate_key"), (b'{"x":NaN}', "invalid_json"),
                                   (b"\xff", "invalid_json"), (b"[", "invalid_json"),
                                   (None, "invalid_frame_size")):
                with self.subTest(body=body), socket.create_connection(server.address, timeout=2) as stream:
                    frame = (struct.pack("!I", len(body)) + body if body is not None
                             else struct.pack("!I", network.MAX_FRAME + 1))
                    stream.sendall(frame)
                    self.assertEqual(network.receive_frame(stream), {"type": "error", "code": expected})
                    self.assertEqual(stream.recv(1), b"")
            with network.WorldClient(server.address[1]) as client:
                self.assertEqual(len(client.snapshot()["players"]), 1)

    def test_disconnect_frame_timeout_and_local_binding(self):
        sender, reader = socket.socketpair()
        with sender, reader:
            sender.sendall(struct.pack("!I", 3) + b"{")
            with self.assertRaises(TimeoutError):
                network.receive_frame(reader, timeout=0.02)
            sender.shutdown(socket.SHUT_WR)
            with self.assertRaises(EOFError):
                network.receive_frame(reader)
        with network.WorldServer() as server:
            self.assertEqual(server.address[0], "127.0.0.1")

    def test_socket_identity_and_abrupt_disconnect(self):
        with network.WorldServer() as server, network.WorldClient(server.address[1]) as observer:
            port = server.address[1]
            with socket.create_connection(server.address, timeout=2) as socket_client:
                network.send_frame(socket_client, {"type": "join", "version": 1})
                welcome = network.receive_frame(socket_client)
                self.assertEqual(len(observer.snapshot()["players"]), 2)
                network.send_frame(socket_client, move(1) | {"id": observer.player_id})
                self.assertEqual(network.receive_frame(socket_client)["code"], "invalid_input")
                network.send_frame(socket_client, {"type": "snapshot", "id": observer.player_id})
                self.assertEqual(network.receive_frame(socket_client)["code"], "invalid_request")
            network._observe(observer, lambda s: len(s["players"]) == 1)
            with network.WorldClient(port, welcome["resume"]) as resumed:
                self.assertEqual(resumed.player_id, welcome["id"])
                self.assertEqual(len(observer.snapshot()["players"]), 2)
                with self.assertRaisesRegex(network.ProtocolError, "invalid_resume"):
                    network.WorldClient(port, welcome["resume"])

    def test_smoke_cli_writes_observed_two_peer_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "nested" / "smoke.json"
            completed = subprocess.run([sys.executable, "-m", "living.network", "smoke",
                                        "--report", str(report)], cwd=ROOT, check=True,
                                       capture_output=True, text=True, timeout=10)
            evidence = json.loads(report.read_text())
            self.assertEqual(evidence, json.loads(completed.stdout))
            self.assertEqual(evidence["simultaneous_clients"], 2)
            self.assertEqual(evidence["observed_remote_state"]["applied"], 1)
            self.assertAlmostEqual(evidence["displacement_per_tick"], network.SPEED / evidence["tick_hz"])
            self.assertEqual(len(set(evidence["ticks_observed"])), 3)
            for field in ("ok", "interest_filtered", "resume_restored_position",
                          "resume_rotated_token", "duplicate_input_rejected", "leave_observed"):
                self.assertIs(evidence[field], True, field)


if __name__ == "__main__":
    unittest.main()
