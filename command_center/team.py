"""Draft team work orders and summarize recorded build evidence."""

from datetime import datetime, timezone

from .dispatch import build_dispatch_plan
from .provenance import spec_digest


_SUCCESS = {"passed", "succeeded"}
_TASKS = {
    "assets": (
        "Define asset formats, reuse boundaries and size budgets.",
        "Check collision, scale and interaction needs for game-ready assets.",
        "Check manifest coverage, provenance and import evidence.",
        "Prepare the asset browsing and inspection workflow.",
        "Produce approved assets and record sources and attribution.",
        "Run the asset builder and archive the output inventory and audit.",
    ),
    "world": (
        "Define scene structure, dependencies and level boundaries.",
        "Validate traversal, spawn points and encounter placement.",
        "Check level load, collision and deterministic smoke-test evidence.",
        "Prepare the level editing workflow and in-world navigation cues.",
        "Assemble approved geometry, props and lighting.",
        "Run the world builder and archive the scene and verification logs.",
    ),
    "gameplay": (
        "Define gameplay system boundaries and scene integration.",
        "Implement the approved mechanics, progression and failure states.",
        "Run gameplay smoke tests and review the recorded results.",
        "Implement player controls, HUD and readable state feedback.",
        "Prepare encounters, player-facing copy and tuning data.",
        "Run the gameplay builder and archive the playable scene and logs.",
    ),
    "multiplayer": (
        "Define authority, session lifecycle and replication boundaries.",
        "Implement shared gameplay rules and reconnect behavior.",
        "Check loopback, state convergence and disconnect evidence.",
        "Prepare lobby, connection and reconnect feedback.",
        "Prepare shared match content and deterministic fixtures.",
        "Run the multiplayer builder and archive server and client logs.",
    ),
    "cinematic": (
        "Define how shots, camera tracks, dialogue and audio fit together.",
        "Check gameplay handoffs, triggers and interruption behavior.",
        "Check timeline, audio timing and render evidence.",
        "Prepare timeline editing and preview controls.",
        "Assemble shot framing, dialogue, captions and licensed audio.",
        "Run the cinematic builder and archive its output and logs.",
    ),
    "simulation": (
        "Define world, vehicle, weather and objective component boundaries.",
        "Tune vehicle physics and enforce safe entry and exit.",
        "Check actual traversal, ordered objectives and climate transitions.",
        "Prepare readable player controls, HUD and mission feedback.",
        "Generate deterministic mission stages and interactive landmarks.",
        "Build and verify the world simulation package and scenario report.",
    ),
    "openworld": (
        "Define terrain streaming, NPC population and checkpoint lifecycle boundaries.",
        "Implement world interactions, inventory, crafting and faction reputation.",
        "Verify physical chunk traversal, bounded population, and checkpoint recovery.",
        "Prepare readable interaction prompts, inventory and faction feedback.",
        "Prepare reproducible terrain, resource placement and NPC identities.",
        "Build and verify the open-world package and archive the scenario report.",
    ),
    "unified": (
        "Define how streamed terrain, vehicle transport and checkpoints share a world lifecycle.",
        "Integrate transport, the training range, quest progression and trading with the world.",
        "Verify streamed traversal, scheduled NPCs, quest rewards, trading and checkpoint recovery.",
        "Prepare controls, interaction prompts, quest progress and trade feedback.",
        "Prepare deterministic routes, target placement, NPC schedules and vendor stock.",
        "Build and verify the unified expedition package and archive the scenario report.",
    ),
    "living": (
        "Define how streamed encounters, diplomacy and contracts share a checkpoint lifecycle.",
        "Integrate encounter progress, faction standings and contract payouts with the world.",
        "Verify encounter persistence, contract progression and the local multiplayer test toolkit.",
        "Prepare interaction prompts, contract tracking and faction feedback.",
        "Prepare deterministic encounters and character animations for the frontier.",
        "Build and verify the Living World package and archive the scenario report.",
    ),
    "city": (
        "Define deterministic street layouts, districts and authoritative city networking.",
        "Integrate traffic vehicles, civilian routines and city checkpoints.",
        "Verify traffic signals, civilian schedules and multiplayer convergence.",
        "Prepare city project controls, street navigation and district tour feedback.",
        "Prepare city blocks, street details and distinct district styles.",
        "Build and verify the Metropolis package and archive the city scenario report.",
    ),
    "vertical": (
        "Define how interiors, transit and demolition share authoritative world state.",
        "Integrate building access, elevator movement, metro journeys and demolition.",
        "Verify physical traversal, checkpoint restoration and multiplayer convergence.",
        "Prepare controls and feedback for building access, transit and demolition.",
        "Prepare deterministic interiors, stations, trains and destructible structures.",
        "Build and verify the Vertical City package and archive the scenario report.",
    ),
    "advanced": (
        "Define authority, multiplayer session lifecycle and checkpoint persistence across city systems.",
        "Integrate tower traversal, vehicle controls and NPC interactions with shared world state.",
        "Verify physical traversal, vehicle and NPC interactions, late join, reconnect and checkpoint recovery.",
        "Prepare readable tower, driving, NPC dialogue and session controls.",
        "Prepare the tower interiors, drivable vehicle and NPC interaction content.",
        "Build and verify the Advanced City package and archive the scenario report.",
    ),
    "frontline": (
        "Define how shared vehicles, lifts, cover and mission state use host authority.",
        "Integrate co-op interactions, mission objectives and squad behavior with city traversal.",
        "Verify the mission route, shared state, late join, reconnect and checkpoint recovery.",
        "Prepare controls and feedback for shared interactions and mission objectives.",
        "Place the mission route, squad encounters and destructible cover in the city.",
        "Build and verify the Frontline City package and archive the scenario report.",
    ),
}
_DEFAULT_TASKS = (
    "Define component boundaries and integration dependencies.",
    "Implement and check the approved interactive behavior.",
    "Check verification evidence against project acceptance criteria.",
    "Prepare the project controls and status feedback.",
    "Prepare approved content and record its provenance.",
    "Run the configured builder and archive its output and logs.",
)


def _job_time(job: dict) -> datetime:
    try:
        created = datetime.fromisoformat(job.get("created_at", ""))
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created


def release_summary(project: dict, jobs: list) -> dict:
    """Report the newest project job and its eligibility as a release candidate."""
    project_jobs = [
        job for job in jobs if job.get("project_id") == project["id"]
    ]
    latest = max(reversed(project_jobs), key=_job_time, default=None)
    status = latest.get("status") if latest else None
    verified = status in _SUCCESS and latest.get("verified") is True
    stale = bool(verified and "spec" in project and latest.get("spec_sha256") != spec_digest(project["spec"]))
    verification_status = "pending"
    if stale:
        verification_status = "stale"
    elif verified:
        verification_status = "passed"
    elif status == "failed":
        verification_status = "failed"

    candidates = []
    if verified and not stale and latest.get("output"):
        candidates.append({
            "job_id": latest["id"],
            "kind": latest["kind"],
            "output": latest["output"],
        })

    return {
        "latest_job": latest,
        "verification_gate": {"name": "Verification", "status": verification_status},
        "release_candidates": candidates,
    }


def _scenario_gate(project: dict, release: dict, current_digest: str | None) -> dict | None:
    kind = project.get("kind")
    if kind == "gameplay":
        spec = project.get("spec", {})
        if not (spec.get("tactical") or spec.get("destructible_blocks")):
            return None
        title, report_key = "Tactical", "tactical_qa"
    elif kind == "simulation":
        title, report_key = "Simulation", "simulation_qa"
    elif kind == "openworld":
        title, report_key = "Open-world", "openworld_qa"
    elif kind == "unified":
        title, report_key = "Unified", "unified_qa"
    elif kind == "living":
        title, report_key = "Living World", "living_qa"
    elif kind == "city":
        title, report_key = "City", "city_qa"
    elif kind == "vertical":
        title, report_key = "Vertical City", "vertical_qa"
    elif kind == "advanced":
        title, report_key = "Advanced City", "advanced_qa"
    elif kind == "frontline":
        title, report_key = "Frontline City", "frontline_qa"
    else:
        return None

    verification = release["verification_gate"]["status"]
    latest = release["latest_job"] or {}
    report = latest.get(report_key)
    result = report.get("pass") if isinstance(report, dict) else None
    mismatched = (kind in ("openworld", "unified", "living", "city", "vertical", "advanced", "frontline")
                  and isinstance(result, bool)
                  and (not current_digest or latest.get("spec_sha256") != current_digest))
    status = "pending"
    if verification == "stale" or mismatched:
        status = "stale"
    elif verification == "passed" and result is True:
        status = "passed"
    elif result is False:
        status = "failed"
    return {"name": f"{title} scenario QA", "status": status}


def team_plan(project: dict, jobs: list) -> dict:
    """Draft assignments and reflect recorded build and verification status."""
    tasks = _TASKS.get(project.get("kind"), _DEFAULT_TASKS)
    dispatch = build_dispatch_plan(project, tasks)
    roles = dispatch["assignments"]
    release = release_summary(project, jobs)
    latest = release["latest_job"]
    status = latest.get("status") if latest else None
    build_status = "pending"
    if status in _SUCCESS:
        build_status = "stale" if release["verification_gate"]["status"] == "stale" else "passed"
    elif status == "failed":
        build_status = "failed"
    gates = [
        {"name": "Build", "status": build_status},
        release["verification_gate"],
        {"name": "Human render review", "status": "pending"},
        {"name": "Device review", "status": "pending"},
    ]
    scenario = _scenario_gate(project, release, dispatch["project"]["spec_sha256"])
    if scenario:
        gates.insert(2, scenario)
    heading = f"Draft work orders for {project.get('name') or project['id']}."
    assignments = [
        f"- {role['name']} ({role['model']}) · {role['task']}"
        for role in roles
    ]
    return {
        "roles": roles,
        "gates": gates,
        "brief": "\n".join([heading, *assignments]),
        "dispatch_plan": dispatch,
    }
