"""Standalone loopback world replication over TCP. Run python -m living.network --help.

Each frame is a four-byte unsigned network-order length and one UTF-8 JSON
object. Join first, then send input, snapshot or leave requests. Only the fixed
server clock moves actors. Multiple inputs in one tick replace one another.
Clients poll for full snapshots within their server-defined interest radius.
"""

import argparse
import contextlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import socketserver
import struct
import tempfile
import threading
import time
from dataclasses import dataclass


VERSION = 1
HOST = "127.0.0.1"
MAX_FRAME = 16_384
MAX_CLIENTS = 16
MAX_SEQ = 2**53 - 1
RESUME_SECONDS = 30.0
SPEED = 6.0
WORLD_LIMIT = 128.0


class ProtocolError(ValueError):
    """A frame or request violated the protocol. The message is a stable code."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate_key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ProtocolError("invalid_json")


def _read_exact(stream, size, deadline):
    data = bytearray()
    while len(data) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("frame_timeout")
        stream.settimeout(remaining)
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError("connection_closed")
        data.extend(chunk)
    return bytes(data)


def receive_frame(stream, timeout=5.0):
    deadline = time.monotonic() + timeout
    old_timeout = stream.gettimeout()
    try:
        length, = struct.unpack("!I", _read_exact(stream, 4, deadline))
        if not 0 < length <= MAX_FRAME:
            raise ProtocolError("invalid_frame_size")
        payload = _read_exact(stream, length, deadline)
    finally:
        stream.settimeout(old_timeout)
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
    except ProtocolError:
        raise
    except (ValueError, RecursionError) as error:
        raise ProtocolError("invalid_json") from error
    if type(value) is not dict:
        raise ProtocolError("object_required")
    return value


def send_frame(stream, value):
    payload = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(payload) <= MAX_FRAME:
        raise ProtocolError("invalid_frame_size")
    stream.sendall(struct.pack("!I", len(payload)) + payload)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, low, high):
    return type(value) in (int, float) and low <= value <= high


def _id_valid(value):
    return (isinstance(value, str) and len(value) <= 20 and value.startswith("p")
            and value[1:].isascii() and value[1:].isdigit())


def _token_valid(value):
    return (isinstance(value, str) and len(value) == 32
            and all(char in "0123456789abcdef" for char in value))


def validate_snapshot(value, player_id=None):
    """Validate the wire schema before applying a snapshot to a client world."""
    if (type(value) is not dict or set(value) != {"type", "version", "tick", "self", "players"}
            or value["type"] != "snapshot" or not _integer(value["version"], VERSION, VERSION)
            or not _integer(value["tick"], 0, MAX_SEQ) or not _id_valid(value["self"])
            or (player_id is not None and value["self"] != player_id)):
        raise ProtocolError("invalid_snapshot")
    players = value["players"]
    if type(players) is not list or not 1 <= len(players) <= MAX_CLIENTS:
        raise ProtocolError("invalid_snapshot")
    seen = set()
    for row in players:
        if (type(row) is not dict or set(row) != {"id", "x", "z", "applied"}
                or not _id_valid(row["id"]) or row["id"] in seen
                or not _number(row["x"], -WORLD_LIMIT, WORLD_LIMIT)
                or not _number(row["z"], -WORLD_LIMIT, WORLD_LIMIT)
                or not _integer(row["applied"], 0, MAX_SEQ)):
            raise ProtocolError("invalid_snapshot")
        seen.add(row["id"])
    if value["self"] not in seen:
        raise ProtocolError("invalid_snapshot")
    return value


@dataclass
class Actor:
    id: str
    x: float = 0.0
    z: float = 0.0
    applied: int = 0
    received: int = 0
    direction: tuple = (0, 0)
    token: str = ""

    def state(self):
        return {"id": self.id, "x": self.x, "z": self.z, "applied": self.applied}


class ReplicatedWorld:
    """Thread-safe authoritative world. step() also supports deterministic tests."""

    def __init__(self, tick_hz=20, interest_radius=32.0):
        if not _integer(tick_hz, 1, 120) or not _number(interest_radius, 0, 1024):
            raise ValueError("invalid world settings")
        self.tick_hz = tick_hz
        self.interest_radius = interest_radius
        self.tick = 0
        self._lock = threading.RLock()
        self._active = {}
        self._detached = {}
        self._next_id = 1

    def _prune(self):
        now = time.monotonic()
        for token, (expires, _) in list(self._detached.items()):
            if expires <= now:
                del self._detached[token]

    def join(self, message):
        if (set(message) not in ({"type", "version"}, {"type", "version", "resume"})
                or message.get("type") != "join"
                or not _integer(message.get("version"), VERSION, VERSION)):
            raise ProtocolError("invalid_join")
        with self._lock:
            self._prune()
            if len(self._active) >= MAX_CLIENTS:
                raise ProtocolError("world_full")
            if "resume" in message:
                token = message["resume"]
                if not _token_valid(token) or token not in self._detached:
                    raise ProtocolError("invalid_resume")
                _, actor = self._detached.pop(token)
            else:
                actor = Actor("p" + str(self._next_id))
                self._next_id += 1
            actor.token = secrets.token_hex(16)
            self._active[actor.id] = actor
            return {"type": "welcome", "version": VERSION, "id": actor.id, "resume": actor.token,
                    "applied": actor.applied, "tick_hz": self.tick_hz, "speed": SPEED,
                    "world_limit": WORLD_LIMIT, "interest_radius": self.interest_radius}

    def leave(self, player_id):
        with self._lock:
            actor = self._active.pop(player_id, None)
            if actor is None:
                return
            actor.direction = (0, 0)
            actor.received = actor.applied
            self._prune()
            if len(self._detached) >= MAX_CLIENTS * 4:
                del self._detached[next(iter(self._detached))]
            self._detached[actor.token] = (time.monotonic() + RESUME_SECONDS, actor)

    def input(self, player_id, message):
        if (set(message) != {"type", "seq", "dx", "dz"} or message["type"] != "input"
                or not _integer(message["seq"], 1, MAX_SEQ)
                or not _integer(message["dx"], -1, 1) or not _integer(message["dz"], -1, 1)):
            raise ProtocolError("invalid_input")
        with self._lock:
            actor = self._active[player_id]
            seq = message["seq"]
            if seq <= actor.received:
                raise ProtocolError("stale_sequence")
            if seq != actor.received + 1:
                raise ProtocolError("sequence_gap")
            actor.received = seq
            actor.direction = (message["dx"], message["dz"])
            return {"type": "accepted", "seq": seq}

    def step(self):
        with self._lock:
            self.tick += 1
            for actor in self._active.values():
                if actor.applied == actor.received:
                    continue
                dx, dz = actor.direction
                scale = SPEED / self.tick_hz / max(1.0, math.hypot(dx, dz))
                actor.x = max(-WORLD_LIMIT, min(WORLD_LIMIT, actor.x + dx * scale))
                actor.z = max(-WORLD_LIMIT, min(WORLD_LIMIT, actor.z + dz * scale))
                actor.applied = actor.received

    def snapshot(self, player_id):
        with self._lock:
            viewer = self._active[player_id]
            rows = [actor.state() for actor in self._active.values()
                    if math.hypot(actor.x - viewer.x, actor.z - viewer.z) <= self.interest_radius]
            return {"type": "snapshot", "version": VERSION, "tick": self.tick,
                    "self": player_id, "players": rows}


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        stream = self.request
        stream.settimeout(2)
        world = self.server.world
        player_id = None
        try:
            while True:
                try:
                    message = receive_frame(stream, timeout=30)
                except ProtocolError as error:
                    send_frame(stream, {"type": "error", "code": str(error)})
                    return
                try:
                    if player_id is None:
                        reply = world.join(message)
                        player_id = reply["id"]
                    elif message == {"type": "snapshot"}:
                        reply = world.snapshot(player_id)
                    elif message.get("type") == "input":
                        reply = world.input(player_id, message)
                    elif message == {"type": "leave"}:
                        world.leave(player_id)
                        player_id = None
                        send_frame(stream, {"type": "left"})
                        return
                    else:
                        raise ProtocolError("invalid_request")
                except ProtocolError as error:
                    reply = {"type": "error", "code": str(error)}
                send_frame(stream, reply)
        except (EOFError, OSError):
            pass
        finally:
            if player_id is not None:
                world.leave(player_id)


class _TCPWorld(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False

    def __init__(self, port, world):
        self.world = world
        self._peers = set()
        self._lock = threading.Lock()
        super().__init__((HOST, port), _Handler)

    def verify_request(self, request, address):
        with self._lock:
            if len(self._peers) >= MAX_CLIENTS:
                return False
            self._peers.add(request)
            return True

    def close_request(self, request):
        with self._lock:
            self._peers.discard(request)
        super().close_request(request)

    def interrupt_peers(self):
        with self._lock:
            for stream in self._peers:
                with contextlib.suppress(OSError):
                    stream.shutdown(socket.SHUT_RDWR)


class WorldServer:
    """Context manager for a fixed-tick server bound exclusively to IPv4 loopback."""

    def __init__(self, port=0, tick_hz=20, interest_radius=32.0):
        self.world = ReplicatedWorld(tick_hz, interest_radius)
        self._tcp = _TCPWorld(port, self.world)
        self.address = self._tcp.server_address
        self._stop = threading.Event()
        self._clock = threading.Thread(target=self._tick, name="world-clock")
        self._host = threading.Thread(target=self._tcp.serve_forever, args=(0.025,), name="world-host")

    def _tick(self):
        interval = 1 / self.world.tick_hz
        deadline = time.monotonic() + interval
        while not self._stop.wait(max(0.0, deadline - time.monotonic())):
            self.world.step()
            deadline += interval
            if deadline <= time.monotonic():
                deadline = time.monotonic() + interval

    def __enter__(self):
        self._host.start()
        self._clock.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._tcp.shutdown()
        self._tcp.interrupt_peers()
        self._tcp.server_close()
        self._host.join()
        self._clock.join()


class WorldClient:
    """A synchronous single-session client for locally running game simulations."""

    def __init__(self, port, resume=None):
        self._stream = socket.create_connection((HOST, port), timeout=3.0)
        self._tick = -1
        try:
            join = {"type": "join", "version": VERSION}
            if resume is not None:
                join["resume"] = resume
            reply = self.request(join)
            if (reply.get("type") != "welcome" or not _integer(reply.get("version"), VERSION, VERSION)
                    or not _id_valid(reply.get("id")) or not _token_valid(reply.get("resume"))
                    or not _integer(reply.get("applied"), 0, MAX_SEQ)):
                raise ProtocolError("invalid_welcome")
            self.player_id = reply["id"]
            self.resume_token = reply["resume"]
            self.sequence = reply["applied"]
        except BaseException:
            self._stream.close()
            raise

    def request(self, message):
        send_frame(self._stream, message)
        reply = receive_frame(self._stream)
        if reply.get("type") == "error":
            raise ProtocolError(reply.get("code", "remote_error"))
        return reply

    def move(self, dx, dz):
        seq = self.sequence + 1
        reply = self.request({"type": "input", "seq": seq, "dx": dx, "dz": dz})
        if reply != {"type": "accepted", "seq": seq} or type(reply["seq"]) is not int:
            raise ProtocolError("invalid_ack")
        self.sequence = seq
        return seq

    def snapshot(self):
        state = validate_snapshot(self.request({"type": "snapshot"}), self.player_id)
        if state["tick"] < self._tick:
            raise ProtocolError("stale_snapshot")
        self._tick = state["tick"]
        return state

    def close(self):
        if self._stream.fileno() >= 0:
            try:
                self.request({"type": "leave"})
            except (OSError, EOFError, ProtocolError):
                pass
            finally:
                self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _observe(client, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.snapshot()
        if predicate(snapshot):
            return snapshot
        time.sleep(0.005)
    raise RuntimeError("expected world state did not arrive")


def _players(snapshot):
    return {row["id"]: row for row in snapshot["players"]}


def _requires(condition, message):
    if not condition:
        raise RuntimeError(message)


def smoke():
    """Exercise two independent TCP clients and return measured smoke evidence."""
    with WorldServer(tick_hz=30, interest_radius=0.3) as server:
        port = server.address[1]
        with WorldClient(port) as first, WorldClient(port) as second:
            start = second.snapshot()
            _requires(set(_players(start)) == {first.player_id, second.player_id}, "join visibility")
            seq = first.move(1, 1)
            observed = _observe(second, lambda s: _players(s)[first.player_id]["applied"] == seq)
            position = _players(observed)[first.player_id]
            distance = math.hypot(position["x"], position["z"])
            _requires(math.isclose(distance, SPEED / 30), "movement speed")
            try:
                first.request({"type": "input", "seq": seq, "dx": 1, "dz": 0})
            except ProtocolError as error:
                _requires(str(error) == "stale_sequence", "unexpected rejection")
            else:
                raise RuntimeError("duplicate input accepted")
            original_token = first.resume_token
            original_id = first.player_id
            first.close()
            detached = second.snapshot()
            _requires(original_id not in _players(detached), "leave visibility")
            with WorldClient(port, original_token) as resumed:
                restored = _players(resumed.snapshot())[resumed.player_id]
                _requires(resumed.player_id == original_id and restored == position
                          and resumed.resume_token != original_token, "resume continuity")
                _requires(original_id in _players(second.snapshot()), "resume visibility")
                next_seq = resumed.move(1, 1)
                end = _observe(resumed, lambda s: _players(s)[original_id]["applied"] == next_seq)
                _requires(original_id not in _players(second.snapshot()), "interest filtering")
                _requires(end["tick"] > observed["tick"] > start["tick"], "clock order")
            return {"ok": True, "schema_version": VERSION, "transport": "loopback TCP",
                    "simultaneous_clients": 2, "tick_hz": 30, "ticks_observed": [start["tick"],
                    observed["tick"], end["tick"]], "displacement_per_tick": distance,
                    "observed_remote_state": position, "resume_restored_position": True,
                    "resume_rotated_token": True, "duplicate_input_rejected": True,
                    "leave_observed": True, "interest_filtered": True}


def _write_report(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as handle:
        temporary = handle.name
        try:
            handle.write(data + "\n")
            handle.close()
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("smoke", help="exercise real clients and a reconnect")
    check.add_argument("--report", type=Path)
    serve = commands.add_parser("serve", help="run the loopback world until interrupted")
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--tick-hz", type=int, default=20)
    serve.add_argument("--interest-radius", type=float, default=32.0)
    args = parser.parse_args()
    if args.command == "smoke":
        result = json.dumps(smoke(), indent=2, allow_nan=False)
        if args.report:
            _write_report(args.report, result)
        print(result)
    else:
        with WorldServer(args.port, args.tick_hz, args.interest_radius) as server:
            print(json.dumps({"host": HOST, "port": server.address[1], "version": VERSION}), flush=True)
            try:
                threading.Event().wait()
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
