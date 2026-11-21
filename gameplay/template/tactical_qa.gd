extends SceneTree

const LANE_START := Vector3(0, 0, 6.5)
const LANE_END := Vector3(0, 0, 1.5)
const AIM_HEIGHT := Vector3.UP * 0.9
const EYE_HEIGHT := Vector3.UP * 1.2

var checks: Array[Dictionary] = []
var metrics := {"accepted_shots": 0, "fixture_actor_repositions": 0}
var game
var player
var observer
var partner
var wall: MeshInstance3D
var wall_body: StaticBody3D
var checkpoints: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(label: String, passed: bool, detail: String) -> void:
	checks.append({"name": label, "status": "passed" if passed else "failed", "detail": detail})

func frames(count: int) -> void:
	for i in count:
		await physics_frame

func place(actor: CharacterBody3D, at: Vector3) -> void:
	actor.global_position = at + Vector3.UP * 0.06
	actor.velocity = Vector3.ZERO
	metrics.fixture_actor_repositions += 1

func horizontal(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()

func ray(a: Vector3, b: Vector3, mask: int) -> CollisionObject3D:
	var query := PhysicsRayQueryParameters3D.create(a, b, mask)
	return game.get_world_3d().direct_space_state.intersect_ray(query).get("collider")

func sight_blocker(guard: CharacterBody3D) -> CollisionObject3D:
	return ray(guard.global_position + EYE_HEIGHT, player.global_position + EYE_HEIGHT, 1)

func impact(guard: CharacterBody3D) -> CollisionObject3D:
	return ray(player.get_node("Camera3D").global_position, guard.global_position + AIM_HEIGHT, 5)

func fire_at(guard: CharacterBody3D) -> bool:
	var camera: Vector3 = player.get_node("Camera3D").global_position
	var accepted: bool = game.shoot(camera.direction_to(guard.global_position + AIM_HEIGHT))
	if accepted:
		metrics.accepted_shots += 1
	return accepted

func cover_hp() -> int:
	return game.destruction.snapshot().get("qa_wall", -1)

func route_length() -> float:
	var points: PackedVector3Array = game.nav.plan(LANE_START, LANE_END)
	if points.is_empty() or not points[-1].is_equal_approx(LANE_END):
		return -1.0
	var previous := LANE_START
	var length := 0.0
	for point in points:
		length += horizontal(previous, point)
		previous = point
	return length

func run() -> void:
	metrics.physics_ticks_per_second = Engine.physics_ticks_per_second
	var scene := load("res://gameplay.tscn") as PackedScene
	if scene == null:
		check("Load training scene", false, "Missing gameplay.tscn")
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	player = game.player
	observer = game.enemies.get("guard_a")
	partner = game.enemies.get("guard_b")
	wall = game.world.get_node_or_null("Blocks/qa_wall")
	var valid_fixture: bool = game.spec.get("id") == "training_yard" and game.config.get("tactical") == true and observer != null and partner != null and wall != null and cover_hp() == 50
	check("Load tactical training fixture", valid_fixture, "Seed %s, cover health %d" % [game.config.get("seed"), cover_hp()])
	if not valid_fixture:
		finish()
		return
	wall_body = wall.get_node("Body")
	player.set_test_drive(Vector2.ZERO)
	observer.set_physics_process(false)
	partner.set_physics_process(false)
	place(player, game.goal.global_position)
	await frames(3)
	check("Extraction locked with live guards", not game.mission.completed and game.mission.remaining.size() == 2, "Player placed at the extraction beacon with both guards alive")
	await test_squad()
	await test_combat()
	await test_extraction()
	finish()

func test_squad() -> void:
	# All three positions are arranged while guard AI is paused. The guards then run normally.
	place(observer, Vector3(-3.5, 0, 1))
	place(partner, Vector3(1, 0, 1))
	place(player, Vector3(-3, 0, 6.5))
	await frames(4)
	var cold: bool = not game.squad.intel("guard_a").active and not game.squad.intel("guard_b").active
	var isolated := sight_blocker(observer) == null and sight_blocker(partner) == wall_body
	var before: Vector3 = partner.global_position
	observer.set_physics_process(true)
	partner.set_physics_process(true)
	await frames(12)
	var a: Dictionary = game.squad.intel("guard_a")
	var b: Dictionary = game.squad.intel("guard_b")
	var seen: Vector3 = a.target
	metrics.flanker_travel_m = horizontal(before, partner.global_position)
	check("Single observer shares real sighting", cold and isolated and a.active and b.active and a.role == "pursuer" and b.role == "flanker" and horizontal(seen, player.global_position) < 0.1 and seen.is_equal_approx(b.target), "Independent physics rays clear guard A and hit the wall for guard B")
	check("Occluded flanker investigates", sight_blocker(partner) == wall_body and partner.state == "investigate" and partner.tactical_role == "flanker" and metrics.flanker_travel_m > 0.1, "Autonomous guard B moved %.2f m in state %s" % [metrics.flanker_travel_m, partner.state])
	place(player, Vector3(1, 0, 6.5))
	await frames(4)
	var hidden: bool = sight_blocker(observer) == wall_body and sight_blocker(partner) == wall_body
	var memory: Dictionary = game.squad.intel("guard_b")
	check("Hidden movement preserves last sighting", hidden and memory.active and seen.is_equal_approx(memory.target) and horizontal(seen, player.global_position) > 3.5, "Both independent rays hit the wall after the player was repositioned")
	# Move the player beyond sensor range to prevent reacquisition while normal AI and time continue.
	place(player, Vector3(9, 0, -9))
	var lost_frames := 4
	var unchanged := true
	var continuously_unseen := true
	while lost_frames < 6 * Engine.physics_ticks_per_second:
		await physics_frame
		lost_frames += 1
		continuously_unseen = continuously_unseen and not observer._can_see() and not partner._can_see()
		memory = game.squad.intel("guard_b")
		if not memory.active:
			break
		unchanged = unchanged and seen.is_equal_approx(memory.target)
	await frames(2)
	metrics.memory_decay_frames = lost_frames
	var seconds := float(lost_frames) / Engine.physics_ticks_per_second
	check("Unrefreshed sighting expires", continuously_unseen and unchanged and absf(seconds - 5.0) < 0.2 and not game.squad.intel("guard_a").active and not game.squad.intel("guard_b").active and observer.state == "patrol" and partner.state == "patrol", "Both guards returned to patrol after %.2f simulated seconds" % seconds)

func test_combat() -> void:
	# Stationary targets isolate the real weapon, geometry, navigation and save/load behavior.
	observer.set_physics_process(false)
	partner.set_physics_process(false)
	place(player, LANE_START)
	place(observer, LANE_END)
	place(partner, Vector3(1.2, 0, 1))
	await frames(4)
	metrics.initial_cover_hp = cover_hp()
	metrics.blocked_route_m = route_length()
	var ammo: int = game.combat.ammo
	var before: int = observer.health
	var blocked := impact(observer) == wall_body
	var fired := fire_at(observer)
	metrics.cover_hp_after_first_shot = cover_hp()
	check("First shot damages only cover", blocked and fired and cover_hp() == 25 and observer.health == before and game.combat.ammo == ammo - 1 and wall.visible, "Real weapon ray spent one round; cover %d, guard %d" % [cover_hp(), observer.health])
	var prefix := "user://studio_tactical_qa_%s_%s" % [OS.get_process_id(), Time.get_ticks_usec()]
	checkpoints.assign([prefix + "_damaged.json", prefix + "_breached.json"])
	var saved_damaged: bool = game.save_game(checkpoints[0])
	await frames(20)
	blocked = impact(observer) == wall_body
	fired = fire_at(observer)
	await frames(3)
	metrics.cover_hp_after_second_shot = cover_hp()
	metrics.breached_route_m = route_length()
	check("Second shot opens the breach", blocked and fired and cover_hp() == 0 and observer.health == before and not wall.visible and impact(observer) == observer, "The next independent physics ray reaches the guard")
	check("Navigation takes the opened lane", metrics.blocked_route_m > metrics.breached_route_m + 2.0 and is_equal_approx(metrics.breached_route_m, LANE_START.distance_to(LANE_END)), "Route shortened from %.1f m to %.1f m" % [metrics.blocked_route_m, metrics.breached_route_m])
	await frames(20)
	fired = fire_at(observer)
	check("Third shot crosses the breach", fired and observer.health == before - 25 and cover_hp() == 0, "Guard health changed from %d to %d" % [before, observer.health])
	var saved_breached: bool = game.save_game(checkpoints[1])
	var loaded_damaged: bool = saved_damaged and game.load_game(checkpoints[0])
	await frames(3)
	check("Checkpoint restores damaged cover", loaded_damaged and cover_hp() == 25 and wall.visible and observer.health == before and impact(observer) == wall_body and is_equal_approx(route_length(), metrics.blocked_route_m), "Reloaded cover health, mesh, ray obstruction, detour and guard health")
	var loaded_breached: bool = saved_breached and game.load_game(checkpoints[1])
	await frames(3)
	check("Checkpoint restores open breach", loaded_breached and cover_hp() == 0 and not wall.visible and observer.health == before - 25 and impact(observer) == observer and is_equal_approx(route_length(), metrics.breached_route_m), "Reloaded breach visibility, ray access, direct route and guard health")
	await frames(20)
	var kill_a := fire_at(observer)
	await frames(20)
	var hit_b := fire_at(partner)
	await frames(20)
	var kill_b := fire_at(partner)
	check("Weapon eliminates both guards", kill_a and hit_b and kill_b and observer.health == 0 and partner.health == 0 and game.mission.remaining.is_empty() and not game.mission.completed, "Both mission targets removed before extraction; %d accepted shots" % metrics.accepted_shots)

func test_extraction() -> void:
	# No transform writes in this phase. The player controller integrates all movement.
	var previous: Vector3 = player.global_position
	var travel := 0.0
	var crossed := false
	var largest_step := 0.0
	var ticks := 0
	var poses: int = metrics.fixture_actor_repositions
	while ticks < 4 * Engine.physics_ticks_per_second and not game.mission.completed:
		var goal: Vector3 = game.goal.global_position if previous.z <= 1.5 else LANE_END
		var direction := Vector2(goal.x - previous.x, goal.z - previous.z).normalized()
		player.set_test_drive(direction, true)
		await physics_frame
		var current: Vector3 = player.global_position
		var step := horizontal(previous, current)
		travel += step
		largest_step = maxf(largest_step, step)
		if previous.z > wall.global_position.z and current.z <= wall.global_position.z and absf(current.x) < 1.6:
			crossed = true
		previous = current
		ticks += 1
	player.set_test_drive(Vector2.ZERO)
	metrics.extraction_travel_m = travel
	metrics.extraction_frames = ticks
	metrics.extraction_max_step_m = largest_step
	metrics.extraction_actor_repositions = metrics.fixture_actor_repositions - poses
	check("Physical traversal through breach to extraction", crossed and travel > 9.0 and largest_step <= player.sprint_speed / Engine.physics_ticks_per_second + 0.02 and game.mission.completed and horizontal(previous, game.goal.global_position) <= 1.0 and metrics.extraction_actor_repositions == 0, "Controller moved %.2f m across the former wall over %d physics frames" % [travel, ticks])

func finish() -> void:
	for path in checkpoints:
		if FileAccess.file_exists(path):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	var passed := not checks.is_empty()
	for row in checks:
		passed = passed and row.status == "passed"
	print("STUDIO_TACTICAL_QA_JSON " + JSON.stringify({"pass": passed, "checks": checks, "metrics": metrics}))
	quit(0 if passed else 1)
