#!/usr/bin/env python3
"""Single-writer studio coordinator. No commands are executed without explicit run."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from command_center.strict_engine_log import inspect_log


def now():
    return datetime.now(timezone.utc).isoformat()


def slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("IDs must be lowercase letters, digits, hyphens or underscores.")
    return value


def required(value):
    value = value.strip()
    if not value:
        raise ValueError("Required values must not be blank.")
    return value


def load(path):
    if not path.exists():
        return {"version": 2, "projects": []}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("version") != 2 or not isinstance(state.get("projects"), list):
        raise ValueError("Unsupported studio state format.")
    return state


def write(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    temp.replace(path)


def find(rows, id):
    for row in rows:
        if row["id"] == id:
            return row
    raise ValueError(f"Unknown ID: {id}")


def hash_file(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def valid_evidence(task):
    if task["status"] != "passed" or not task["evidence"]:
        return False
    ev = task["evidence"][-1]
    try:
        if ev["exit_code"] != 0 or ev.get("policy_passed", True) is not True:
            return False
        if ev.get("policy") == "godot-clean":
            with Path(ev["log"]).open("rb") as stream:
                digest, counts = inspect_log(stream)
            return (ev.get("policy_passed") is True and ev.get("diagnostics") == counts
                    and not counts and digest == ev["sha256"])
        if ev.get("policy", "exit-code") != "exit-code" or ("diagnostics" in ev and "policy" not in ev):
            return False
        return hash_file(Path(ev["log"])) == ev["sha256"]
    except (OSError, KeyError, TypeError):
        return False


def accepted(task, tasks):
    return valid_evidence(task) and all(
        accepted(find(tasks, dep), tasks) for dep in task["depends_on"]
    )


def invalidate_dependents(tasks, task_id):
    affected = {task_id}
    # Dependencies must pre-exist at task creation, so the list is topological.
    for task in tasks:
        if affected.intersection(task["depends_on"]):
            affected.add(task["id"])
            task["status"] = "pending"
            task["detail"] = f"Upstream task {task_id} is being re-verified."


def run_verification(path, state, project, task, cmd, timeout, *, godot_clean=False):
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        raise ValueError("Supply an explicit verification command after --.")
    tasks = project["tasks"]
    for dep in task["depends_on"]:
        if not accepted(find(tasks, dep), tasks):
            raise ValueError(f"Dependency {dep} has no current passing evidence.")
    if not 1 <= timeout <= 3600:
        raise ValueError("Timeout must be 1–3600 seconds.")
    source = Path(project["source"])
    if not source.is_dir():
        raise ValueError(f"Registered source directory is unavailable: {source}")

    log_dir = path.parent / "evidence" / slug(project["id"]) / slug(task["id"])
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (uuid.uuid4().hex + ".log")
    invalidate_dependents(tasks, task["id"])
    task["status"] = "active"
    write(path, state)
    start = time.monotonic()
    started = now()
    exit_code = 1
    detail = ""
    with log_path.open("xb") as handle:
        try:
            completed = subprocess.run(cmd, cwd=source, stdout=handle,
                                       stderr=subprocess.STDOUT, timeout=timeout,
                                       check=False)
            exit_code = completed.returncode
            detail = f"Verification exit code {exit_code}"
        except subprocess.TimeoutExpired:
            exit_code = 124
            detail = f"Verification exceeded {timeout} seconds"
            handle.write(("\n" + detail + "\n").encode())
        except OSError as exc:
            exit_code = 127
            detail = f"Unable to execute verification: {exc}"
            handle.write((detail + "\n").encode())
    evidence = {
        "command": cmd, "cwd": str(source), "started": started, "finished": now(),
        "duration_seconds": round(time.monotonic() - start, 3), "exit_code": exit_code,
        "log": str(log_path),
    }
    passed = exit_code == 0
    if godot_clean:
        with log_path.open("rb") as stream:
            digest, counts = inspect_log(stream)
        passed = passed and not counts
        evidence.update(sha256=digest, policy="godot-clean", diagnostics=counts, policy_passed=passed)
        if counts:
            detail += ". Godot diagnostics: " + ", ".join(f"{name}={count}" for name, count in counts.items())
    else:
        evidence["sha256"] = hash_file(log_path)
    task["evidence"].append(evidence)
    task["status"] = "passed" if passed else "failed"
    task["detail"] = detail
    write(path, state)
    print(f"{task['status'].upper()}: {detail}; log: {log_path}")
    return 0 if passed else 1


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, default=Path("studio.json"))
    commands = p.add_subparsers(dest="action", required=True)
    reg = commands.add_parser("register", help="Register an existing project root.")
    reg.add_argument("project")
    reg.add_argument("--name", required=True)
    reg.add_argument("--source", required=True, type=Path)
    reg.add_argument("--objective", required=True)
    reg.add_argument("--engine", default="Unspecified")
    reg.add_argument("--platform", default="Unspecified")
    task = commands.add_parser("task", help="Add a bounded work order.")
    task.add_argument("project")
    task.add_argument("id")
    task.add_argument("--title", required=True)
    task.add_argument("--owner", required=True)
    task.add_argument("--acceptance", required=True)
    task.add_argument("--depends", action="append", default=[])
    task.add_argument("--scope", default="Confirm explicit file ownership before edits.")
    gate = commands.add_parser("gate", help="Register a quality gate linked to a verification task or pending human check.")
    gate.add_argument("project")
    gate.add_argument("name")
    gate.add_argument("--task")
    brief = commands.add_parser("brief", help="Generate an agent-ready brief.")
    brief.add_argument("project")
    brief.add_argument("id")
    run = commands.add_parser("run", help="Run a trusted, explicit verification.")
    run.add_argument("project")
    run.add_argument("id")
    run.add_argument("--timeout", type=int, default=120)
    run.add_argument("--godot-clean", action="store_true",
                     help="Require exit zero and a log free of Godot errors, warnings and test failures.")
    # main splits at -- before parsing so timeout/options remain unambiguous.
    commands.add_parser("report", help="Report evidence-backed task status.")
    dash = commands.add_parser("dashboard", help="Generate an offline HTML report.")
    dash.add_argument("destination", type=Path)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = []
    if "--" in argv:
        cut = argv.index("--")
        argv, cmd = argv[:cut], argv[cut + 1:]
    args = parser().parse_args(argv)
    if cmd and args.action != "run":
        raise ValueError("Only run accepts a verification command.")
    path = args.state.resolve()
    state = load(path)
    projects = state["projects"]
    if args.action == "register":
        id = slug(args.project)
        if any(p["id"] == id for p in projects):
            raise ValueError(f"Project already exists: {id}")
        source = args.source.resolve()
        if not source.is_dir():
            raise ValueError("The source directory must exist.")
        projects.append({"id": id, "name": required(args.name), "source": str(source),
                         "objective": required(args.objective), "engine": args.engine,
                         "platform": args.platform, "tasks": [], "checks": []})
        write(path, state)
        print(f"Registered {id}. No project files were modified.")
    elif args.action == "gate":
        project = find(projects, slug(args.project))
        name = required(args.name)
        if any(g["name"] == name for g in project["checks"]):
            raise ValueError(f"Gate already exists: {name}")
        if args.task:
            find(project["tasks"], slug(args.task))
        project["checks"].append({"name": name, "task": args.task, "status": "pending",
                                  "detail": "Verification not yet established."})
        write(path, state)
        print(f"Created gate {name}.")
    elif args.action in ("task", "brief", "run"):
        project = find(projects, slug(args.project))
        tasks = project["tasks"]
        task_id = slug(args.id)
        if args.action == "task":
            if any(t["id"] == task_id for t in tasks):
                raise ValueError(f"Task already exists: {task_id}")
            deps = list(dict.fromkeys(args.depends))
            for dep in deps:
                find(tasks, slug(dep))
            tasks.append({"id": task_id, "title": required(args.title),
                          "owner": required(args.owner), "status": "pending",
                          "depends_on": deps, "acceptance": required(args.acceptance),
                          "scope": required(args.scope), "evidence": []})
            write(path, state)
            print(f"Created work order {task_id}.")
        else:
            task = find(tasks, task_id)
            if args.action == "run":
                return run_verification(path, state, project, task, cmd, args.timeout, godot_clean=args.godot_clean)
            print(f"# Work order: {task['title']}\nProject: {project['name']}"
                  f"\nSource: {project['source']}\nObjective: {project['objective']}"
                  f"\nEngine/platform: {project['engine']} / {project['platform']}"
                  f"\nOwner: {task['owner']}\nScope: {task['scope']}"
                  f"\nDepends on: {', '.join(task['depends_on']) or 'none'}"
                  f"\nAcceptance: {task['acceptance']}"
                  "\nReturn changed paths, test output, limitations, and any blocked criteria."
                  "\nDo not modify unrelated files or treat a passing command as device acceptance.")
    else:
        # Reconcile status against the actual retained log evidence (and dependencies)
        # in the generated view, not the stored original history.
        for project in projects:
            tasks = project["tasks"]
            for task in tasks:
                if task["status"] == "passed" and not accepted(task, tasks):
                    task["status"] = "blocked"
                    task["detail"] = "Missing, changed or invalid upstream evidence."
            for gate in project["checks"]:
                if gate.get("task"):
                    linked = find(tasks, gate["task"])
                    gate["status"] = linked["status"]
                    gate["detail"] = linked.get("detail", "Verification not yet established.")
                else:
                    gate["status"] = "pending"
                    gate["detail"] = "Human/device acceptance not recorded."
            if args.action == "report":
                count = sum(t["status"] == "passed" for t in tasks)
                print(f"{project['name']}: {count}/{len(tasks)} verified work orders")
                for task in tasks:
                    print(f"  {task['id']}: {task['status']} — {task['title']}")
                for gate in project["checks"]:
                    print(f"  {gate['name']}: {gate['status']}")
        if args.action == "dashboard":
            from dashboard import render_dashboard
            render_dashboard(projects, args.destination.resolve())
            print(f"Dashboard: {args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"Studio: {exc}", file=sys.stderr)
        sys.exit(2)
