import unittest

from command_center.provenance import spec_digest
from command_center.team import release_summary, team_plan


PROJECT = {"id": "demo", "name": "Demo", "kind": "gameplay"}


def build(job_id="build", **fields):
    job = {
        "id": job_id,
        "project_id": "demo",
        "kind": "build",
        "created_at": "2026-11-20T02:00:00+00:00",
        "status": "succeeded",
        "verified": True,
        "output": "/studio/demo/build",
    }
    return job | fields


class CommandTeamTests(unittest.TestCase):
    def test_work_orders_offer_six_complementary_roles_for_the_project_kind(self):
        game = team_plan(PROJECT, [])
        asset = team_plan(PROJECT | {"kind": "assets"}, [])
        self.assertCountEqual(
            [role["model"] for role in game["roles"]],
            ["GPT-6.2 Astra Ultra"] * 5 + ["GPT-6.2 Sol Max"],
        )
        self.assertEqual(
            len({role["name"] for role in game["roles"]}), 6
        )
        self.assertNotEqual(
            [role["task"] for role in game["roles"]],
            [role["task"] for role in asset["roles"]],
        )
        self.assertIn("work orders", game["brief"].lower())

    def test_new_spec_invalidates_old_build_evidence(self):
        import hashlib, json
        original={'seed':237}
        digest=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        job=build(spec_sha256=digest)
        self.assertEqual(len(release_summary(PROJECT|{'spec':original},[job])['release_candidates']),1)
        revised=release_summary(PROJECT|{'spec':{'seed':238}},[job])
        self.assertEqual(revised['verification_gate']['status'],'stale')
        self.assertEqual(revised['release_candidates'],[])
        self.assertEqual(release_summary(PROJECT|{'spec':original},[build()])['release_candidates'],[])

    def test_tactical_gate_requires_current_fixture_report(self):
        import hashlib, json
        spec={'tactical':True}
        digest=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        project=PROJECT|{'spec':spec}
        def gate(j):
            return next(g['status'] for g in team_plan(project,[j])['gates'] if g['name']=='Tactical scenario QA')
        self.assertEqual(gate(build(spec_sha256=digest)),'pending')
        self.assertEqual(gate(build(spec_sha256=digest,tactical_qa={'pass':True})),'passed')
        self.assertEqual(gate(build(spec_sha256='old',tactical_qa={'pass':True})),'stale')

    def test_verified_automated_build_keeps_human_gates_pending(self):
        plan = team_plan(PROJECT, [build()])
        gates = {gate["name"]: gate["status"] for gate in plan["gates"]}
        self.assertEqual(gates["Build"], "passed")
        self.assertEqual(gates["Verification"], "passed")
        self.assertEqual(gates["Human render review"], "pending")
        self.assertEqual(gates["Device review"], "pending")

    def test_simulation_gate_is_current_fixture_evidence_only(self):
        spec = {'weather': 'rain'}
        project = PROJECT | {'kind': 'simulation', 'spec': spec}
        def gate(job):
            return next(g['status'] for g in team_plan(project, [job])['gates'] if g['name'] == 'Simulation scenario QA')
        current = build(spec_sha256=spec_digest(spec))
        self.assertEqual(gate(current), 'pending')
        self.assertEqual(gate(current | {'simulation_qa': {'pass': True}}), 'passed')
        self.assertEqual(gate(current | {'spec_sha256': 'old', 'simulation_qa': {'pass': True}}), 'stale')

    def test_openworld_gate_requires_scenario_report_for_the_current_spec(self):
        project = PROJECT | {"kind": "openworld", "spec": {"seed": 42}}
        current = build(kind="openworld", spec_sha256=spec_digest(project["spec"]))

        def gate(job=None, active_project=project):
            plan = team_plan(active_project, [job] if job else [])
            return next(gate["status"] for gate in plan["gates"] if gate["name"] == "Open-world scenario QA")

        self.assertEqual(gate(), "pending")
        self.assertEqual(gate(current), "pending")
        self.assertEqual(gate(current | {"openworld_qa": {"pass": "true"}}), "pending")
        self.assertEqual(gate(current | {"openworld_qa": {"pass": False}}), "failed")
        self.assertEqual(gate(current | {"openworld_qa": {"pass": True}, "verified": False}), "pending")
        passed = current | {"openworld_qa": {"pass": True}}
        self.assertEqual(gate(passed), "passed")
        self.assertEqual(gate(passed | {"spec_sha256": None}), "stale")
        self.assertEqual(gate(passed, project | {"spec": {"seed": 43}}), "stale")
        self.assertEqual(gate(current | {
            "status": "failed", "verified": False, "openworld_qa": {"pass": False}, "spec_sha256": "old",
        }), "stale")

    def test_openworld_work_orders_cover_streaming_crafting_and_persistence(self):
        plan = team_plan(PROJECT | {"kind": "openworld", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("stream", "craft", "checkpoint"):
            self.assertIn(topic, tasks)

    def test_scenario_gates_follow_verified_evidence_and_spec_digest(self):
        for kind, title in (("unified", "Unified"), ("living", "Living World"), ("city", "City"),
                            ("vertical", "Vertical City"), ("advanced", "Advanced City"),
                            ("frontline", "Frontline City")):
            with self.subTest(kind=kind):
                project = PROJECT | {"kind": kind, "spec": {"seed": 237}}
                current = build(kind=kind, spec_sha256=spec_digest(project["spec"]))
                key = f"{kind}_qa"

                def gate(job, active_project=project):
                    return next(g["status"] for g in team_plan(active_project, [job])["gates"]
                                if g["name"] == f"{title} scenario QA")

                self.assertEqual(gate(current), "pending")
                self.assertEqual(gate(current | {key: {"pass": "true"}}), "pending")
                self.assertEqual(gate(current | {key: {"pass": False}}), "failed")
                report = current | {key: {"pass": True}}
                self.assertEqual(gate(report), "passed")
                self.assertEqual(gate(report | {"verified": False}), "pending")
                self.assertEqual(gate(report | {"spec_sha256": None}), "stale")
                self.assertEqual(gate(report, project | {"spec": {"seed": 238}}), "stale")

    def test_unified_work_orders_cover_integrated_world_systems(self):
        plan = team_plan(PROJECT | {"kind": "unified", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("stream", "vehicle", "training range", "npc", "quest", "trading", "checkpoint"):
            self.assertIn(topic, tasks)

    def test_living_work_orders_cover_living_world_systems(self):
        plan = team_plan(PROJECT | {"kind": "living", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("encounter", "diplomacy", "contract", "checkpoint", "multiplayer", "animation"):
            self.assertIn(topic, tasks)

    def test_city_work_orders_cover_metropolis_systems(self):
        plan = team_plan(PROJECT | {"kind": "city", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("street layouts", "traffic", "civilian", "vehicle", "network", "checkpoint"):
            self.assertIn(topic, tasks)

    def test_vertical_work_orders_cover_connected_city_systems(self):
        plan = team_plan(PROJECT | {"kind": "vertical", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("interior", "elevator", "metro", "demolition", "world state", "multiplayer", "checkpoint"):
            self.assertIn(topic, tasks)

    def test_advanced_work_orders_cover_city_and_session_systems(self):
        plan = team_plan(PROJECT | {"kind": "advanced", "spec": {}}, [])
        tasks = " ".join(role["task"] for role in plan["roles"]).lower()
        for topic in ("tower", "vehicle", "npc", "multiplayer session", "checkpoint", "late join", "reconnect"):
            self.assertIn(topic, tasks)

    def test_newer_failed_build_takes_priority_over_older_verified_build(self):
        newest = build(
            "new", created_at="2026-11-20T03:00:00+00:00", status="failed"
        )
        summary = release_summary(PROJECT, [newest, build("old")])
        self.assertEqual(summary["latest_job"], newest)
        self.assertEqual(summary["verification_gate"]["status"], "failed")
        self.assertEqual(summary["release_candidates"], [])

    def test_pending_or_unverified_build_never_qualifies_for_release(self):
        for fields in (
            {"status": "queued"},
            {"status": "running"},
            {"status": "completed"},
            {"verified": False},
            {"verified": "true"},
        ):
            with self.subTest(fields=fields):
                summary = release_summary(PROJECT, [build(**fields)])
                self.assertEqual(summary["verification_gate"]["status"], "pending")
                self.assertEqual(summary["release_candidates"], [])

    def test_verified_latest_build_only_exposes_its_own_candidate(self):
        latest = build("latest", status="passed")
        unrelated = build(
            "unrelated",
            project_id="other",
            created_at="2026-11-20T05:00:00+00:00",
        )
        summary = release_summary(PROJECT, [unrelated, latest])
        self.assertEqual(summary["latest_job"], latest)
        self.assertEqual(summary["verification_gate"]["status"], "passed")
        self.assertEqual(summary["release_candidates"], [
            {"job_id": "latest", "kind": "build", "output": "/studio/demo/build"},
        ])

    def test_jobs_from_another_project_leave_evidence_pending(self):
        summary = release_summary(PROJECT, [build(project_id="unrelated")])
        self.assertIsNone(summary["latest_job"])
        self.assertEqual(summary["verification_gate"]["status"], "pending")
        self.assertEqual(summary["release_candidates"], [])
