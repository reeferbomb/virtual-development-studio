extends RefCounted


class Keeper extends CharacterBody2D:
	enum Mode { PATROL, CHASE, SEARCH, RETURN }
	const SIGHT_RADIUS := 40.0
	const STEP_DISTANCE := 2.0
	const MEMORY_TICKS := 4

	var route := PackedVector2Array([Vector2.ZERO, Vector2(-8, 0)])
	var waypoint := 1
	var mode := Mode.PATROL
	var last_seen := Vector2.ZERO
	var memory_left := 0
	var patrol_arrivals := 0

	func sees(subject: Area2D) -> bool:
		if not is_instance_valid(subject) or global_position.distance_to(subject.global_position) > SIGHT_RADIUS:
			return false
		# The first physics collider on the segment must be the observed subject.
		var query := PhysicsRayQueryParameters2D.create(global_position, subject.global_position, 3)
		query.collide_with_areas = true
		query.hit_from_inside = true
		var hit := get_world_2d().direct_space_state.intersect_ray(query)
		return hit.get("collider") == subject

	func approach(destination: Vector2) -> bool:
		var motion := (destination - global_position).limit_length(STEP_DISTANCE)
		if not motion.is_zero_approx():
			move_and_collide(motion)
		return global_position.is_equal_approx(destination)

	func tick(subject: Area2D) -> void:
		if sees(subject):
			last_seen = subject.global_position
			memory_left = MEMORY_TICKS
			mode = Mode.CHASE
			approach(last_seen)
			return
		if memory_left > 0:
			memory_left -= 1
			if memory_left > 0:
				mode = Mode.SEARCH
				approach(last_seen)
				return
			last_seen = Vector2.ZERO
			mode = Mode.RETURN
		if approach(route[waypoint]):
			patrol_arrivals += 1
			waypoint = (waypoint + 1) % route.size()
			mode = Mode.PATROL


func _attach_shape(body: CollisionObject2D, shape: Shape2D) -> void:
	var collider := CollisionShape2D.new()
	collider.shape = shape
	body.add_child(collider)


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var stage := SubViewport.new()
	stage.world_2d = World2D.new()
	tree.root.add_child(stage)

	var keeper := Keeper.new()
	keeper.collision_layer = 0
	keeper.collision_mask = 1
	var hull := CircleShape2D.new()
	hull.radius = 0.75
	_attach_shape(keeper, hull)
	stage.add_child(keeper)

	var wall := StaticBody2D.new()
	wall.position = Vector2(8, 0)
	wall.collision_layer = 1
	var panel := RectangleShape2D.new()
	panel.size = Vector2(2, 20)
	_attach_shape(wall, panel)
	stage.add_child(wall)

	var subject := Area2D.new()
	subject.collision_layer = 2
	subject.collision_mask = 0
	subject.position = Vector2(-100, -25)
	var marker := CircleShape2D.new()
	marker.radius = 0.75
	_attach_shape(subject, marker)
	stage.add_child(subject)

	var checks: Array[Dictionary] = []
	await tree.physics_frame
	var far_hidden := not keeper.sees(subject)
	for i in range(4):
		await tree.physics_frame
		keeper.tick(subject)
	checks.append(_check("patrol-motion",
		keeper.mode == Keeper.Mode.PATROL and keeper.patrol_arrivals == 1 and keeper.waypoint == 0
		and keeper.position.is_equal_approx(Vector2(-8, 0)),
		"Four physics steps ended at %s with %d patrol arrivals." % [keeper.position, keeper.patrol_arrivals]))

	subject.position = Vector2(18, 0)
	await tree.physics_frame
	var near_hidden := keeper.position.distance_to(subject.position) <= Keeper.SIGHT_RADIUS and not keeper.sees(subject)
	keeper.tick(subject)
	checks.append(_check("sight-gates",
		far_hidden and near_hidden and keeper.mode == Keeper.Mode.PATROL and keeper.memory_left == 0,
		"Out-of-range subject hidden: %s. In-range subject behind the panel hidden: %s." % [far_hidden, near_hidden]))

	subject.position = Vector2(-6, 10)
	await tree.physics_frame
	var first_fix := subject.position
	var start := keeper.position
	keeper.tick(subject)
	var chase_distance := start.distance_to(keeper.position)
	checks.append(_check("chase-acquisition",
		keeper.mode == Keeper.Mode.CHASE and keeper.last_seen == first_fix and keeper.memory_left == Keeper.MEMORY_TICKS
		and is_equal_approx(chase_distance, Keeper.STEP_DISTANCE)
		and keeper.position.distance_to(first_fix) < start.distance_to(first_fix),
		"Keeper moved %.2f pixels toward the visible subject and retained %d ticks." % [chase_distance, keeper.memory_left]))

	subject.position = Vector2(18, 0)
	await tree.physics_frame
	start = keeper.position
	keeper.tick(subject)
	checks.append(_check("search-memory",
		keeper.mode == Keeper.Mode.SEARCH and keeper.last_seen == first_fix and keeper.memory_left == Keeper.MEMORY_TICKS - 1
		and keeper.position.distance_to(first_fix) < start.distance_to(first_fix)
		and is_equal_approx(start.x, keeper.position.x),
		"One hidden tick left %d ticks and movement toward the previous fix at %s." % [keeper.memory_left, keeper.last_seen]))

	subject.position = Vector2(-15, 8)
	await tree.physics_frame
	start = keeper.position
	keeper.tick(subject)
	var new_fix := keeper.last_seen
	checks.append(_check("reacquisition",
		keeper.mode == Keeper.Mode.CHASE and new_fix == subject.position and new_fix != first_fix
		and keeper.memory_left == Keeper.MEMORY_TICKS and keeper.position.distance_to(new_fix) < start.distance_to(new_fix),
		"Reappearance interrupted search with a new fix at %s and %d ticks." % [new_fix, keeper.memory_left]))

	var interrupted_waypoint := keeper.waypoint
	subject.position = Vector2(-125, -30)
	var search_ticks := 0
	for missed in range(1, Keeper.MEMORY_TICKS + 1):
		await tree.physics_frame
		keeper.tick(subject)
		if keeper.mode == Keeper.Mode.SEARCH and keeper.last_seen == new_fix and keeper.memory_left == Keeper.MEMORY_TICKS - missed:
			search_ticks += 1
	checks.append(_check("memory-expiry",
		search_ticks == Keeper.MEMORY_TICKS - 1 and keeper.mode == Keeper.Mode.RETURN
		and keeper.memory_left == 0 and keeper.last_seen == Vector2.ZERO and keeper.waypoint == interrupted_waypoint,
		"Observed %d search ticks before the fix expired on missed tick %d." % [search_ticks, Keeper.MEMORY_TICKS]))

	var return_ticks := 0
	while keeper.mode == Keeper.Mode.RETURN and return_ticks < 24:
		await tree.physics_frame
		keeper.tick(subject)
		return_ticks += 1
	var returned := keeper.position.is_equal_approx(keeper.route[interrupted_waypoint])
	await tree.physics_frame
	keeper.tick(subject)
	checks.append(_check("patrol-recovery",
		returned and return_ticks > 0 and keeper.mode == Keeper.Mode.PATROL and keeper.patrol_arrivals == 2
		and keeper.waypoint == 1 and keeper.position.is_equal_approx(Vector2(-2, 0)),
		"Reached the interrupted waypoint in %d additional ticks and continued to %s." % [return_ticks, keeper.position]))

	var metrics := {"patrol_arrivals": keeper.patrol_arrivals, "chase_distance_px": chase_distance,
		"memory_limit_ticks": Keeper.MEMORY_TICKS, "search_ticks_before_expiry": search_ticks, "return_ticks": return_ticks}
	stage.free()
	return {"id": "npc", "checks": checks, "metrics": metrics}
