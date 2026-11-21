extends SceneTree

const Enemy = preload("res://enemy.gd")

class Encounter extends Node3D:
	var combat = preload("res://combat.gd").new()
	var mission = preload("res://mission.gd").new()

class ObservedSquad extends RefCounted:
	var role := "pursuer"
	var active := false
	var seen := Vector3.ZERO
	var reports := 0
	var forgotten: Array[String] = []

	func report(_id: String, point: Vector3) -> void:
		active = true
		seen = point
		reports += 1

	func intel(_id: String) -> Dictionary:
		return {"active": active, "target": seen, "role": role}

	func forget(id: String) -> void:
		forgotten.append(id)

class CountingPlanner extends "res://navigation.gd":
	var calls := 0

	func plan(start: Vector3, goal: Vector3) -> PackedVector3Array:
		calls += 1
		return super.plan(start, goal)

var failures := 0

func check(condition: bool, detail: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", detail)

func box(arena: Node3D, center: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var geometry := BoxShape3D.new()
	geometry.size = size
	shape.shape = geometry
	body.add_child(shape)
	body.position = center
	arena.add_child(body)

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var guard = Enemy.new()
	if not ("tactical" in guard and "squad" in guard):
		check(false, "Enemy accepts tactical configuration")
		guard.free()
		quit(1)
		return
	check(not guard.tactical, "Legacy mode is the default")
	var arena := Encounter.new()
	root.add_child(arena)
	var player := CharacterBody3D.new()
	arena.add_child(player)
	var planner := CountingPlanner.new()
	var squad := ObservedSquad.new()
	var blocks := [
		{"position": [0, 1.5, 0], "size": [0.6, 3, 4]},
		{"position": [8.5, 1.5, 0], "size": [1.5, 3, 1.5]},
		{"position": [6, 1.5, -2], "size": [1, 3, 0.6]},
	]
	planner.configure({"terrain": {"width": 26, "depth": 26, "flat_radius": 12}, "blocks": blocks})
	box(arena, Vector3.DOWN * 0.5, Vector3(36, 1, 36))
	for block: Dictionary in blocks:
		var p: Array = block.position
		var s: Array = block.size
		box(arena, Vector3(p[0], p[1], p[2]), Vector3(s[0], s[1], s[2]))
	guard.name = "guard_a"
	guard.game = arena
	guard.target = player
	guard.navigator = planner
	guard.squad = squad
	guard.patrol.append(Vector3(-5, 0, -3))
	arena.add_child(guard)
	guard.set_physics_process(false)
	guard.position = Vector3(-4, 0.02, 0)
	player.position = Vector3(-3, 0.02, 4)
	await physics_frame
	await physics_frame
	guard._physics_process(1.0 / 60)
	check(guard.state == "chase" and squad.reports == 0, "Legacy sighting uses independent chase")
	guard.tactical = true
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	var last_seen := player.position
	check(guard.state == "chase" and guard.tactical_role == "pursuer", "First visible role pursues")
	check(squad.reports == 1 and squad.seen == last_seen, "A real sighting reports the player position")

	player.position = Vector3(2, 0.02, 0)
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	check(guard.state == "investigate" and squad.reports == 1, "A solid wall prevents a new sighting")
	check(guard.tactical_goal.distance_to(last_seen) < 0.1, "Guard investigates the last reported point")
	player.position = Vector3(1, 0.02, 0.5)
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	check(squad.seen == last_seen and guard.tactical_goal.distance_to(last_seen) < 0.1, "Hidden movement does not update the route")
	squad.active = false
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	check(guard.state == "patrol" and guard.tactical_role == "", "Expired intel returns to patrol")
	check(guard.tactical_goal.distance_to(guard.patrol[0]) < 0.1, "Expired intel clears the old destination")

	guard.position = Vector3(6, 0.02, -5)
	player.position = Vector3(-11, 0.02, 10)
	squad.active = true
	squad.seen = Vector3(6, 0.02, 0)
	squad.role = "flanker"
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	var flank: Vector3 = guard.tactical_goal
	check(guard.state == "investigate" and guard.tactical_role == "flanker", "Occluded flanker responds to a teammate")
	check(flank.x < squad.seen.x - 1 and absf(flank.z) < 0.5 and not guard.path.is_empty(), "Flanker finds a reachable side when the other side is solid")
	var after_plan := planner.calls
	for step in 12:
		guard._physics_process(1.0 / 60)
	check(planner.calls == after_plan, "Guard reuses its path between planning intervals")

	guard.position = Vector3(6, 0.02, -5)
	squad.role = "support"
	guard.replan = 0.0
	guard._physics_process(1.0 / 60)
	var hold: Vector3 = guard.tactical_goal
	check(guard.tactical_role == "support" and hold.z < -2.5, "Support takes a rear position")
	var eyes := Vector3.UP * 1.2
	var sight := PhysicsRayQueryParameters3D.create(hold + eyes, squad.seen + eyes, 1)
	check(not arena.get_world_3d().direct_space_state.intersect_ray(sight).is_empty(), "Support selects reachable cover when available")

	guard.position = Vector3(-1.2, 0.02, 0)
	player.position = Vector3(1.2, 0.02, 0)
	var health_before: int = arena.combat.health
	guard._physics_process(1.0 / 60)
	check(arena.combat.health == health_before and squad.reports == 1, "A wall blocks close-range damage and reports")
	player.position = Vector3(-2.4, 0.02, 0)
	guard._physics_process(1.0 / 60)
	check(guard.state == "attack" and arena.combat.health < health_before, "A visible target inside attack range takes damage")
	var health_after: int = arena.combat.health
	guard._physics_process(1.0 / 60)
	check(arena.combat.health == health_after, "Tactical attacks respect their cooldown")
	guard.take_damage(50)
	check(guard.state == "dead" and squad.forgotten == ["guard_a"], "Defeated guard leaves the squad")
	arena.free()
	if failures == 0:
		print("PASS tactical enemy sensing, routes, cover and cooldown")
	quit(int(failures > 0))
