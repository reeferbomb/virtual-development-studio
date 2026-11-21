"""Create the default six-agent profile and a handoff for a compatible host."""

from .provenance import spec_digest


_ASTRA = ("GPT-6.2 Astra Ultra", "gpt-6.2-astra", "ultra")
_SOL = ("GPT-6.2 Sol Max", "gpt-6.2-sol", "max")
_ROLE_SPECS = (
    ("architecture", "Architecture", "Count Blueprint", "count_blueprint", _ASTRA),
    ("gameplay", "Gameplay", "Major Mayhem", "major_mayhem", _ASTRA),
    ("verification", "Verification", "Doctor Doomcheck", "doctor_doomcheck", _ASTRA),
    ("ui", "UI", "Madame Glitch", "madame_glitch", _ASTRA),
    ("content", "Content", "Grimbrush", "grimbrush", _ASTRA),
    ("build_operations", "Build operations", "Baron Buildgrave", "baron_buildgrave", _SOL),
)


def continuity_policy() -> dict:
    """Requested host behavior, not a commitment of host resources."""
    return {
        "mode": "sustained_work",
        "target_duration_seconds": 18000,
        "checkpoint_interval_seconds": 300,
        "checkpoint_on_milestone": True,
        "continue_within_scope": True,
        "pause_for_routine_confirmation": False,
        "resume_from_checkpoint": True,
        "respect_host_limits": True,
        "stop_conditions": ["user_stop", "host_limit", "authorization_blocker", "unsafe_action", "no_remaining_authorized_work"],
        "checkpoint_fields": ["project_id", "spec_sha256", "completed_work", "verification_evidence", "remaining_work", "next_action", "elapsed_seconds"],
        "host_instruction": (
            "Aim for 5 hours of active authorized work from activation. Keep taking the next safe, "
            "in-scope task without routine approval pauses. Checkpoint progress every 5 minutes "
            "when practical and at verified milestones, using durable storage when available. "
            "Resume from the latest valid checkpoint on an authorized restart, preserving the "
            "remaining time and rechecking project identity. Respect host limits, user stop "
            "requests, authorization and safety; never attempt to bypass shutdown or session controls. "
            "If interrupted or blocked, record the precise next action and remaining work."
        ),
    }


def default_profile() -> dict:
    """Return the model settings and requested host service tier."""
    return {
        "id": "studio-fast",
        "team_name": "The Midnight Shift",
        "mode": "fast",
        "service_tier": "priority",
        "max_parallel": len(_ROLE_SPECS),
        "continuity": continuity_policy(),
        "roles": [
            {"id": identifier, "name": f"{codename} · {name}", "role_name": name,
             "codename": codename, "agent_task_name": agent_name, "model": label,
             "model_id": model, "reasoning_effort": effort}
            for identifier, name, codename, agent_name, (label, model, effort) in _ROLE_SPECS
        ],
    }


def production_instruction(project_id: str) -> str:
    prefix = f"/api/projects/{project_id}"
    return (
        f"Inspect {prefix}/supervisor and {prefix}/acceptance for current evidence; "
        f"these are advisory, not proof of game quality or permission to publish. "
        f"The lead reviews proposed tasks at {prefix}/sprint and explicitly applies the matching preview "
        f"before claiming work. The lead captures milestone audit observations at {prefix}/evidence-history. "
        "Historical snapshots cannot establish current acceptance. Report evidence to the lead; "
        f"After the lead claims the task, obtain its exact work order from {prefix}/work-orders. "
        f"The lead records structured reports at {prefix}/handoffs and reviews them separately from task completion. "
        f"Use {prefix}/dossier for the readiness evidence dossier and {prefix}/recovery for records-only recovery export. "
        "An order is bound to the board revision; refresh it after any board change. "
        "do not silently apply plans, capture records, resolve defects or promote releases. "
    )


def build_dispatch_plan(project: dict, tasks: tuple[str, ...]) -> dict:
    """Return work orders for dispatch by an external host."""
    profile = default_profile()
    roles = [{**role, "task": task} for role, task in zip(profile["roles"], tasks, strict=True)]
    target = {
        "id": project["id"],
        "name": project.get("name") or project["id"],
        "kind": project.get("kind"),
        "spec_sha256": spec_digest(project["spec"]) if "spec" in project else None,
    }
    context = f"Studio project {target['name']} (ID {target['id']}, kind {target['kind']})."
    if target["spec_sha256"]:
        context += f" Use the saved specification with SHA-256 {target['spec_sha256']}."
    checkpoint_access = {
        "path": f"/api/projects/{target['id']}/checkpoint",
        "read_method": "GET",
        "write_method": "PUT",
        "requires_expected_revision": True,
        "writer": "lead",
    }
    task_board_access = {
        "path": f"/api/projects/{target['id']}/tasks",
        "read_method": "GET",
        "write_method": "PUT",
        "requires_expected_revision": True,
        "writer": "lead",
        "dispatch_policy": "ready_idle_roles_only",
    }
    return {
        "schema_version": 1,
        "execution_mode": "export_only",
        "host_tool": "collaboration.spawn_agent",
        "project": target,
        "profile": profile,
        "checkpoint_access": checkpoint_access,
        "task_board_access": task_board_access,
        "assignments": roles,
        # Service tier is a requested host setting. The spawn tool accepts model and effort overrides.
        "spawn_args": [
            {
                "task_name": role["agent_task_name"],
                "fork_turns": "none",
                "model": role["model_id"],
                "reasoning_effort": role["reasoning_effort"],
                "message": (
                    f"{context} Role {role['name']}. {role['task']} "
                    f"{profile['continuity']['host_instruction']} "
                    f"The local checkpoint endpoint is {checkpoint_access['path']}. "
                    "Consult current progress through the lead; only the lead should commit the "
                    "merged checkpoint using its latest revision and matching project digest. "
                    f"The local task board is {task_board_access['path']}. "
                    "The lead must inspect it before dispatch, create tasks if empty, and resolve any stale board "
                    "explicitly. Treat static default role work orders as templates; work only on claimed scheduled tasks. "
                    "Use only ready tasks for idle roles; the lead must claim each task with a start action "
                    "using the latest board revision and matching specification digest. "
                    "Only the lead updates the board; report completion evidence and any verified build job ID. "
                    f"{production_instruction(target['id'])}"
                    "Return the completed assignment and evidence to the lead for safe reassignment; "
                    "do not idle or expand scope merely to fill the target duration."
                ),
            }
            for role in roles
        ],
    }


def scheduled_dispatch_plan(project: dict, board: dict) -> dict:
    """Export only the next recommended assignments, without claiming or launching them."""
    plan = build_dispatch_plan(project, ("",) * len(_ROLE_SPECS))
    plan.update(board_revision=board["revision"], board_state=board["state"])
    templates = {role["id"]: (role, args) for role, args in
                 zip(plan["assignments"], plan["spawn_args"], strict=True)}
    plan["assignments"] = []
    plan["spawn_args"] = []
    digest = plan["project"]["spec_sha256"]
    if (board["state"] != "current" or board["project_id"] != project["id"]
            or board["spec_sha256"] != digest or board["board_spec_sha256"] != digest):
        return plan
    tasks = {task["id"]: task for task in board["tasks"]}
    ready = set(board["ready_task_ids"])
    claimed_roles = {task["role"] for task in board["tasks"] if task["status"] == "running"}
    for assignment in board["assignments"]:
        task = tasks[assignment["task_id"]]
        role_id = assignment["role"]
        if (task["id"] not in ready or task["role"] != role_id or task["status"] != "pending"
                or role_id in claimed_roles):
            continue
        role, args = templates[role_id]
        claimed_roles.add(role_id)
        plan["assignments"].append({**role, "task_id": task["id"], "task": task["title"]})
        message = (
            f"Scheduled task {task['id']}: {task['title']}. "
            "The lead must freshly read the board and claim this exact task before spawning this worker. "
            "If it is no longer eligible, refresh the scheduled dispatch export instead. "
            + args["message"]
        )
        plan["spawn_args"].append({**args, "message": message})
    return plan
