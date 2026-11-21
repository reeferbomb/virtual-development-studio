"""Run one Godot server and a group of independent loopback clients."""
import argparse
from contextlib import ExitStack
import json
import math
from pathlib import Path
import socket
import subprocess
import time

READY = "STUDIO_NET_HOST_READY"
SERVER = "STUDIO_NET_SERVER_JSON"
CLIENT = "STUDIO_NET_CLIENT_JSON"


def parse_summary(log, marker):
    rows = [line[len(marker) + 1:] for line in log.splitlines() if line.startswith(marker + " ")]
    if len(rows) != 1:
        raise ValueError(f"expected one {marker} record, found {len(rows)}")
    summary = json.loads(rows[0])
    if not isinstance(summary, dict):
        raise ValueError(f"{marker} must contain a JSON object")
    return summary


def validate(host, clients, expected):
    errors = []

    def count(record, label, field, minimum, maximum=None):
        value = record.get(field)
        if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
            errors.append(f"{label}.{field} has unexpected value {value!r}")

    def flag(record, label, field):
        if record.get(field) is not True:
            errors.append(f"{label}.{field} must be true")

    flag(host, "host", "pass")
    flag(host, "host", "started")
    count(host, "host", "joined", expected, expected)
    count(host, "host", "peak_members", expected + 1, expected + 1)
    for field in ("accepted", "damage_events", "npc_damage_events", "npc_attack_events", "pvp_damage_events"):
        count(host, "host", field, 1)
    count(host, "host", "rejected", expected)
    count(host, "host", "disconnected", expected, expected)
    movement = host.get("movement_m")
    if type(movement) not in (float, int) or not math.isfinite(movement) or movement <= 0:
        errors.append("host.movement_m must be positive and finite")
    if len(clients) != expected:
        errors.append(f"expected {expected} client summaries, found {len(clients)}")
    peers = set()
    for index, client in enumerate(clients, 1):
        label = f"client-{index}"
        flag(client, label, "pass")
        flag(client, label, "saw_started")
        flag(client, label, "saw_player_damage")
        count(client, label, "snapshots", 1)
        count(client, label, "max_members", expected + 1, expected + 1)
        count(client, label, "min_npc_health", 0, 149)
        displacement = client.get("own_movement_m")
        if type(displacement) not in (float, int) or not math.isfinite(displacement) or displacement <= .25:
            errors.append(f"{label}.own_movement_m must exceed .25m")
        count(client, label, "peer_id", 2)
        peer = client.get("peer_id")
        if type(peer) is int:
            if peer in peers:
                errors.append(f"{label} duplicated peer ID {peer}")
            peers.add(peer)
    return errors


def stop_children(processes):
    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 2
    for process in processes.values():
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def run(args):
    errors = []
    processes = {}
    summaries = {}
    port = None
    with ExitStack() as files:
        def launch(label, options):
            log = files.enter_context((args.output / f"{label}.log").open("wb"))
            command = [args.godot, "--headless", "--path", str(args.project), "--", *options,
                       f"--port={port}", "--auto", "--duration=8"]
            processes[label] = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            launch("host", ["--host", "--bind=127.0.0.1", f"--expect={args.clients}"])
            deadline = time.monotonic() + 15
            host_log = args.output / "host.log"
            while not any(line.split()[:1] == [READY] for line in host_log.read_text(errors="replace").splitlines()):
                if processes["host"].poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("host failed to announce readiness")
                time.sleep(0.05)
            for index in range(1, args.clients + 1):
                launch(f"client-{index}", ["--join=127.0.0.1", f"--name=Bot{index}"])
            deadline = time.monotonic() + 30
            for process in processes.values():
                process.wait(timeout=max(0, deadline - time.monotonic()))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append(str(exc))
        finally:
            stop_children(processes)
    for label, process in processes.items():
        log = (args.output / f"{label}.log").read_text(errors="replace")
        if process.returncode != 0:
            errors.append(f"{label} exited with {process.returncode}")
        if "SCRIPT ERROR" in log or "ERROR:" in log:
            errors.append(f"{label} logged an engine error")
        try:
            summaries[label] = parse_summary(log, SERVER if label == "host" else CLIENT)
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
    host = summaries.pop("host", {})
    errors.extend(validate(host, list(summaries.values()), args.clients))
    report = {"pass": not errors, "errors": errors, "port": port, "expected_clients": args.clients,
              "host": host, "clients": summaries,
              "exit_codes": {key: proc.returncode for key, proc in processes.items()}}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clients", type=int, required=True)
    parser.add_argument("--godot", default="godot")
    args = parser.parse_args()
    if not 1 <= args.clients <= 15:
        parser.error("--clients must be 1–15")
    if not (args.project / "project.godot").is_file():
        parser.error("--project must contain project.godot")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"output already exists: {args.output}")
    report = run(args)
    print(json.dumps({"pass": report["pass"], "report": str(args.output / "report.json")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
