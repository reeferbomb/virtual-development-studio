"""Optional two-crew Midnight Shift dispatch export.

This adds a reversible planning/export view over the unchanged six-role profile.
It never invokes external agents, changes a task board, or accepts test results.
"""

import argparse
import copy
import json
from pathlib import Path


_CREWS = (
    {
        "id": "visual_realism", "name": "Visual Realism", "lead_role": "content",
        "roles": (
            ("content", "Lead art direction; improve terrain materials, vegetation, models, textures, and visual consistency."),
            ("ui", "Validate first-person visual presentation, on-screen proportions, readability, and accessibility."),
            ("build_operations", "Check draw calls, LODs, shader costs, native renders, platform budgets, and reproducible builds."),
        ),
        "workstream": ("terrain_and_soil_materials", "vegetation_and_bark", "daylight_shadows_and_weather", "first_person_art"),
        "acceptance": ("native_before_after_render", "handheld_readability_review", "no_physics_edits", "bounded_draw_calls"),
    },
    {
        "id": "real_world_physics", "name": "Real-World Physics", "lead_role": "gameplay",
        "roles": (
            ("architecture", "Define the gravity, collision, deformation, and vehicle-contact boundaries; protect save compatibility."),
            ("gameplay", "Improve grounded movement, shovel/terrain interaction, truck traction, collision and impacts."),
            ("verification", "Independently test collision, tunneling, gravity, excavated ground, truck rollover, regression and recovery."),
        ),
        "workstream": ("gravity_and_ground_contact", "excavation_support_and_collision", "vehicle_suspension_and_traction", "impact_and_ragdoll_behavior"),
        "acceptance": ("deterministic_physics_regressions", "no_tunneling_or_floating", "vehicle_contact_smoke", "save_and_resume_compatibility"),
    },
)
_EXPECTED_IDS = {"architecture", "gameplay", "verification", "ui", "content", "build_operations"}


def split_profile(profile: dict, *, project: str, source_sha256: str | None = None) -> dict:
    """Return two work-order crews for a compatible host. This does not spawn agents."""
    if not isinstance(project, str) or not project.strip():
        raise ValueError("project must be a non-empty name")
    if not isinstance(profile, dict) or not isinstance(profile.get("roles"), list):
        raise ValueError("expected a Graveforge profile with roles")
    roles = profile["roles"]
    identifiers = [role.get("id") for role in roles]
    if len(identifiers) != 6 or len(set(identifiers)) != 6 or set(identifiers) != _EXPECTED_IDS:
        raise ValueError("two-crew dispatch requires exactly the unchanged six Midnight Shift role ids")
    by_id = {role["id"]: role for role in roles}
    crews = []
    for definition in _CREWS:
        assignments = []
        for role_id, mission in definition["roles"]:
            role = copy.deepcopy(by_id[role_id])
            assignments.append({
                "role_id": role_id,
                "codename": role.get("codename", role.get("name", role_id)),
                "model_id": role.get("model_id"),
                "reasoning_effort": role.get("reasoning_effort"),
                "mission": mission,
                "status": "pending_authorized_host",
            })
        crews.append({
            "id": definition["id"], "name": definition["name"],
            "lead_role": definition["lead_role"], "assignments": assignments,
            "workstream": list(definition["workstream"]),
            "acceptance": list(definition["acceptance"]),
        })
    return {
        "schema_version": 1, "project": project.strip(),
        "source_sha256": source_sha256,
        "source_profile_id": profile.get("id"),
        "execution_mode": "export_only", "deployment_status": "not_dispatched",
        "crews": crews,
        "cross_review": {
            "visual_reviewer": "verification (Doctor Doomcheck) reviews visuals after physics critical tests",
            "physics_build_reviewer": "build_operations (Baron Buildgrave) reviews physics build/runtime budgets",
        },
        "merge_gates": ["source_hash_and_lineage", "real_runtime_tests", "performance", "save_compatibility", "rollback", "owner_visual_review"],
        "coordination": {
            "branch_policy": "separate visual and physics branches from identical verified baseline",
            "shared_files": "do not edit the same source path simultaneously; integration lead resolves conflicts",
            "no_unverified_claims": True,
            "no_background_execution_claim": True,
            "no_automatic_release": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the optional split Midnight Shift work orders")
    parser.add_argument("--project", required=True, help="Project display name")
    parser.add_argument("--output", required=True, type=Path, help="Private JSON path outside checkout")
    parser.add_argument("--source-sha256", help="SHA256 of the verified source manifest")
    args = parser.parse_args(argv)
    from .dispatch import default_profile
    payload = split_profile(default_profile(), project=args.project, source_sha256=args.source_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        parser.error("output already exists; use a new checkpoint path")
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Exported {len(payload['crews'])} crews / 6 pending roles to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
