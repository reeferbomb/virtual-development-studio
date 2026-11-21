extends SceneTree

var checks: Array[Dictionary] = []
var metrics := {}
var actor: CharacterBody3D
var main: Node

func _initialize() -> void:
	call_deferred("_run")

func _record(label: String, passed: bool, detail: String) -> void:
	checks.append({"name": label, "status": "passed" if passed else "failed", "detail": detail})

func _finish() -> void:
	var passed := not checks.is_empty()
	for check in checks:
		if check.status != "passed":
			passed = false
	print("STUDIO_WORLD_QA_JSON " + JSON.stringify({"pass": passed, "checks": checks, "metrics": metrics}))
	quit(0 if passed else 1)

func _frames(count: int) -> void:
	for frame in count:
		await physics_frame

func _reset_actor(position: Vector3) -> void:
	actor.clear_test_drive()
	actor.global_position = position + Vector3.UP * 0.1
	actor.velocity = Vector3.ZERO
	actor.reset_physics_interpolation()
	actor.set_test_drive(Vector2.ZERO)
	await _frames(12)

func _run() -> void:
	var packed := load("res://main.tscn") as PackedScene
	if packed == null:
		_record("Scene load", false, "Unable to load main.tscn.")
		_finish()
		return
	main = packed.instantiate()
	if main == null:
		_record("Scene load", false, "Unable to instantiate main.tscn.")
		_finish()
		return
	root.add_child(main)
	await _frames(3)
	var world := main.get("world") as Node3D
	actor = main.get("player") as CharacterBody3D
	if world == null or actor == null or not actor.has_method("set_test_drive") or not actor.has_method("clear_test_drive"):
		_record("Scene contract", false, "Missing world, physics player, or test drive methods.")
		_finish()
		return
	var spawn := world.get_node_or_null("Spawn") as Marker3D
	var goal := world.get_node_or_null("Goal") as Marker3D
	if spawn == null or goal == null:
		_record("Scene contract", false, "Missing Spawn or Goal marker.")
		_finish()
		return
	var spec = main.get("spec")
	if spec is Dictionary:
		var placements = spec.get("placements")
		var actual := 0
		var loaded_meshes := 0
		var colliders := 0
		var expected_colliders := 0
		for prop in get_nodes_in_group("studio_prop"):
			if world.is_ancestor_of(prop):
				actual += 1
				if not prop.find_children("*", "MeshInstance3D", true, false).is_empty():
					loaded_meshes += 1
				if not prop.find_children("*", "CollisionShape3D", true, false).is_empty():
					colliders += 1
		for placement in placements:
			if placement.has("collider_size"):
				expected_colliders += 1
		metrics["prop_count"] = actual
		_record("Placed props", placements is Array and actual == placements.size(),
			"Found %d prop instances under the world." % actual)
		_record("Imported meshes and colliders", loaded_meshes == actual and colliders == expected_colliders,
			"Mesh-bearing placements %d; collider-bearing placements %d/%d." % [loaded_meshes, colliders, expected_colliders])
	else:
		_record("Placed props", false, "Missing level specification.")

	var start := spawn.global_position
	var target := goal.global_position
	var rate := Engine.physics_ticks_per_second
	actor.set_test_drive(Vector2.ZERO)
	await _frames(rate)
	var spawn_offset := Vector2(actor.global_position.x - start.x, actor.global_position.z - start.z).length()
	metrics["spawn_offset_m"] = spawn_offset
	var feet_error := absf(actor.global_position.y - start.y)
	metrics["settled_feet_error_m"] = feet_error
	_record("Ground contact", actor.is_on_floor() and feet_error < 0.15 and spawn_offset < 0.15, "Feet offset %.3f m; horizontal spawn offset %.3f m." % [feet_error, spawn_offset])
	var state := world.get_world_3d().direct_space_state
	var edge := state.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(14, 5, 0), Vector3(14, -5, 0), 1))
	var barrel := state.intersect_ray(PhysicsRayQueryParameters3D.create(Vector3(4.3, 3, 2.6), Vector3(4.3, -2, 2.6), 1))
	var edge_y: float = edge.get("position", Vector3.ZERO).y
	var barrel_y: float = barrel.get("position", Vector3.ZERO).y
	metrics["terrain_edge_height_m"] = edge_y
	metrics["barrel_collision_height_m"] = barrel_y
	_record("Terrain height collision", not edge.is_empty() and absf(edge_y) > 0.02,
		"Terrain collider surface at x=14: %.3f m." % edge_y)
	_record("Prop physics collision", not barrel.is_empty() and absf(barrel_y - 0.94) < 0.08,
		"Barrel collider top at %.3f m." % barrel_y)

	var direction := Vector2(target.x - start.x, target.z - start.z).normalized()
	var motion_frames := maxi(1, roundi(rate * 0.5))
	var walk := await _distance(start, direction, false, motion_frames)
	var sprint := await _distance(start, direction, true, motion_frames)
	metrics["walk_m"] = walk
	metrics["sprint_m"] = sprint
	_record("Walking", walk > 0.5, "Forward travel %.3f m in %d ticks." % [walk, motion_frames])
	_record("Sprinting", sprint > walk * 1.12, "Forward travel %.3f m over the same interval." % sprint)

	await _reset_actor(start)
	var base := actor.global_position.y
	actor.set_test_drive(Vector2.ZERO, false, true)
	await _frames(1)
	actor.set_test_drive(Vector2.ZERO)
	var peak := actor.global_position.y
	var airborne := not actor.is_on_floor()
	for frame in rate * 2:
		await physics_frame
		peak = maxf(peak, actor.global_position.y)
		airborne = airborne or not actor.is_on_floor()
	metrics["jump_height_m"] = peak - base
	_record("Jump and landing", airborne and peak - base > 0.2 and actor.is_on_floor() and absf(actor.global_position.y - base) < 0.15,
		"Jump height %.3f m; grounded on return: %s." % [peak - base, actor.is_on_floor()])

	await _reset_actor(Vector3(0, 0, 1))
	actor.set_test_drive(Vector2(0, 1))
	var wall_contact := false
	var max_z := actor.global_position.z
	for frame in rate * 2:
		await physics_frame
		max_z = maxf(max_z, actor.global_position.z)
		for index in actor.get_slide_collision_count():
			if actor.get_slide_collision(index).get_normal().z < -0.8:
				wall_contact = true
	metrics["wall_max_z"] = max_z
	_record("Wall collision", wall_contact and max_z > 2.5 and max_z <= 3.82,
		"Forward extent %.3f m; opposing collision normal observed: %s." % [max_z, wall_contact])

	await _reset_actor(start)
	var initially_clear: bool = main.get("goal_reached") == false
	var route_length := Vector2(target.x - start.x, target.z - start.z).length()
	var closest := route_length
	actor.set_test_drive(direction)
	for frame in ceili((route_length / 2.0 + 1.0) * rate):
		await physics_frame
		closest = minf(closest, Vector2(actor.global_position.x - target.x, actor.global_position.z - target.z).length())
		if main.get("goal_reached") == true:
			break
	actor.clear_test_drive()
	metrics["goal_distance_m"] = closest
	_record("Spawn-to-goal traversal", initially_clear and main.get("goal_reached") == true and closest < 2.0,
		"Closest approach %.3f m; goal triggered: %s." % [closest, main.get("goal_reached")])
	_finish()

func _distance(start: Vector3, direction: Vector2, sprint: bool, frames: int) -> float:
	await _reset_actor(start)
	var origin := actor.global_position
	actor.set_test_drive(direction, sprint)
	await _frames(frames)
	var travel := actor.global_position - origin
	return Vector2(travel.x, travel.z).dot(direction)
