extends SceneTree

const Workshop = preload("res://demolition.gd")
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(condition: bool, label: String) -> void:
	if not condition:
		printerr("FAIL demolition: ", label)
		failures += 1


func settle() -> void:
	await physics_frame
	await physics_frame


func box_body(center: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collider.shape = shape
	body.add_child(collider)
	root.add_child(body)
	body.position = center
	return body


func raw_ray(workshop: Node3D, start: Vector3, end: Vector3) -> Dictionary:
	return workshop.get_world_3d().direct_space_state.intersect_ray(
			PhysicsRayQueryParameters3D.create(start, end, 1))


func _run() -> void:
	var workshop := Workshop.new()
	root.add_child(workshop)
	var origin := Vector3(48, 0, 64)
	check(workshop.configure(2007, origin), "configure three street panels")
	var intact := workshop.snapshot()
	check(not workshop.configure(2008, Vector3(NAN, 0, 0)) and workshop.snapshot() == intact,
			"invalid configuration preserves the workshop")
	var state := workshop.status()
	check(state.targets.size() == 3 and state.total == 3 and state.destroyed == 0, "three independent intact segments")
	var coords: Array = state.targets[1].position
	var target := Vector3(coords[0], coords[1], coords[2])
	check(target.is_equal_approx(origin + Vector3.UP * 1.15), "status reports the center in world coordinates")
	var start := target + Vector3.BACK * 4.0
	var end := target + Vector3.FORWARD * 1.5
	var panel := workshop.get_node("WorkshopPanels/Panel1") as StaticBody3D
	await settle()
	check(raw_ray(workshop, start, end).get("collider") == panel and panel.is_visible_in_tree(),
			"intact mesh has a real physics body at its reported location")
	var body := CharacterBody3D.new()
	body.collision_layer = 2
	body.collision_mask = 1
	var collider := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.height = 1.70
	capsule.radius = 0.32
	collider.shape = capsule
	body.add_child(collider)
	root.add_child(body)
	body.position = start
	await settle()
	check(body.test_move(body.global_transform, end - start), "a character sweep stops at intact cover")

	check(not workshop.shoot(start, Vector3.ZERO).fired and not workshop.shoot(start, Vector3(INF, 0, 0)).fired
			and workshop.snapshot() == intact, "invalid ray consumes no action")
	var far_shot := workshop.shoot(start + Vector3.BACK * 70.0, Vector3.FORWARD)
	check(far_shot.fired and not far_shot.hit, "ray has bounded reach")
	workshop.step(0.25)
	var blocker := box_body(start.lerp(target, 0.5), Vector3(2, 2, 0.4))
	await settle()
	var blocked := workshop.shoot(start, Vector3.FORWARD)
	check(blocked.fired and not blocked.hit and blocked.id == -1 and workshop.status().targets[1].health == 3,
			"unrelated world geometry occludes the target")
	blocker.free()
	await settle()
	workshop.step(0.25)
	var hit := workshop.shoot(start, Vector3.FORWARD * 5.0)
	check(hit.fired and hit.hit and hit.id == 1 and not hit.destroyed and workshop.status().targets[1].health == 2
			and panel.get_node("FirstCrack").is_visible_in_tree(), "one shot changes the struck panel and exposes a crack")
	var damaged := workshop.snapshot()
	check(not workshop.shoot(start, Vector3.FORWARD).fired, "held input cannot bypass the cooldown")
	workshop.step(-1.0)
	workshop.step(NAN)
	check(workshop.snapshot() == damaged, "invalid time step preserves cooldown and damage")
	workshop.step(0.25)
	check(workshop.shoot(start, Vector3.FORWARD).hit and panel.get_node("SecondCrack").is_visible_in_tree(),
			"second damage stage is visible")
	workshop.step(0.25)
	check(workshop.shoot(start, Vector3.FORWARD).destroyed, "third hit destroys the selected segment")
	await settle()
	check(raw_ray(workshop, start, end).is_empty() and not body.test_move(body.global_transform, end - start),
			"ray and character sweep both pass through the destroyed panel")
	var rubble := workshop.get_node("WorkshopPanels/Rubble1") as Node3D
	check(not panel.is_visible_in_tree() and rubble.is_visible_in_tree() and rubble.get_child_count() == 5,
			"destroyed segment leaves bounded visible rubble")
	workshop.step(0.25)
	check(not workshop.shoot(start, Vector3.FORWARD).hit and workshop.status().destroyed == 1
			and workshop.status().targets[0].health == 3 and workshop.status().targets[2].health == 3,
			"repeat fire through the opening leaves neighboring panels intact")
	var destroyed: Variant = JSON.parse_string(JSON.stringify(workshop.snapshot(), "", true, true))
	check(workshop.restore(damaged), "restore a partially damaged panel")
	await settle()
	check(raw_ray(workshop, start, end).get("collider") == panel and body.test_move(body.global_transform, end - start)
			and panel.is_visible_in_tree() and not rubble.is_visible_in_tree() and workshop.status().targets[1].health == 2,
			"restoring rebuilds matching visuals, health and collision")
	check(workshop.restore(destroyed) and workshop.status().targets[1].destroyed
			and workshop.status().destroyed == 1, "destroyed state survives JSON round trip")
	await settle()
	check(raw_ray(workshop, start, end).is_empty() and rubble.is_visible_in_tree(), "loaded destruction reopens passage")
	var before := workshop.snapshot()
	for fields in [{"origin": [5, 0, 64]}, {"version": true}, {"seed": 2008}, {"health": [3, 1.5, 3]},
			{"health": [3, -1, 3]}, {"health": [3, 4, 3]}, {"health": []}, {"cooldown": INF}, {"extra": true}]:
		var bad := before.duplicate(true)
		bad.merge(fields, true)
		check(not workshop.valid_snapshot(bad) and not workshop.restore(bad) and workshop.snapshot() == before,
				"invalid edits leave checkpoint state untouched")
	var detached := workshop.snapshot()
	detached.health[0] = 0
	check(workshop.snapshot() == before, "callers cannot modify live health through a snapshot")
	check(workshop.configure(2007, origin) and workshop.snapshot() == intact, "reconfigure cleanly resets the workshop")
	await settle()
	check(body.test_move(body.global_transform, end - start), "reconfiguration recreates solid cover")
	var side_start := target + Vector3.LEFT * 10.0
	for id in Workshop.PANEL_COUNT:
		for hit_index in Workshop.MAX_HEALTH:
			workshop.step(0.25)
			var side_hit := workshop.shoot(side_start, Vector3.RIGHT)
			check(side_hit.hit and side_hit.id == id and side_hit.destroyed == (hit_index == Workshop.MAX_HEALTH - 1),
					"nearest surviving panel takes the shot and shields its neighbors")
		await settle()
	check(workshop.status().destroyed == 3 and raw_ray(workshop, side_start, target + Vector3.RIGHT * 10.0).is_empty(),
			"all three modules can be cleared independently")
	body.free()
	workshop.free()
	if failures == 0:
		print("PASS demolition: occluded rays, controlled hits, three cover segments, rubble, character passage and checkpoint restoration")
	quit(int(failures > 0))
