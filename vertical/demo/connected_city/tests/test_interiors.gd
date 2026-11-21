extends SceneTree

const Interiors = preload("res://interiors.gd")
var failures := 0


func check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL interiors: ", label)


func _initialize() -> void:
	call_deferred("_run")


func _sync() -> void:
	await physics_frame
	await physics_frame


func _hit(p: Vector3, q: Vector3) -> String:
	var query := PhysicsRayQueryParameters3D.create(p, q, 1)
	var hit := root.world_3d.direct_space_state.intersect_ray(query)
	return str(hit.collider.name) if not hit.is_empty() else ""


func _player(at: Vector3) -> CharacterBody3D:
	var body := CharacterBody3D.new()
	body.position = at
	body.collision_layer = 2
	body.collision_mask = 1
	var shape := CapsuleShape3D.new()
	shape.radius = 0.35
	shape.height = 1.8
	var collision := CollisionShape3D.new()
	collision.shape = shape
	collision.position.y = 0.9
	body.add_child(collision)
	root.add_child(body)
	return body


func _exercise(inside: Interiors, row: Dictionary) -> void:
	check(inside.configure(225, row), "layout builds")
	await _sync()
	var outside := inside.entrance_position()
	var target := inside.room_target()
	var threshold := outside + Vector3.BACK * 1.4
	var at_eye := Vector3.UP * 1.55
	var start := outside + Vector3.UP * 0.04
	var avatar := _player(start)
	var dx := Vector3.RIGHT * 2.3
	var saved_closed := inside.snapshot()
	var initial := inside.status()
	check(initial.rooms.size() == 2 and not initial.door_open, "two named rooms and closed street door")
	check(inside.find_children("*", "OmniLight3D", true, false).size() == 2 and inside.find_children("WorkCounter", "StaticBody3D", true, false).size() == 1, "room lighting and collidable furniture")
	check(not inside.interact(target+Vector3.UP*10) and not inside.interact(Vector3(INF, 0, 0)), "range and finite checks")
	check(_hit(outside+at_eye, target+at_eye) == "SlidingDoor", "closed panel blocks eye-level ray")
	check(_hit(outside+at_eye+dx, threshold+Vector3.BACK+at_eye+dx).begins_with("Front"), "facade blocks entry adjacent to door")
	check(_hit(threshold+Vector3.BACK+dx+at_eye, target+dx+at_eye).begins_with("Partition"), "partition wings have collision")
	check(_hit(target+Vector3.UP, target+Vector3.DOWN) == "Floor", "interior floor supports avatar")
	check(_hit(target+Vector3.UP, target+Vector3.UP*6) == "UpperStoreys", "ceiling covers room")
	check(inside.contains_walkable_position(target) and not inside.contains_walkable_position(outside) and not inside.contains_walkable_position(target+Vector3.UP*4), "checkpoint accepts clear floor in rear room")
	var solid_desk := inside.find_child("WorkCounter", true, false) as StaticBody3D
	check(not inside.contains_walkable_position(solid_desk.global_position-Vector3.UP*0.45), "checkpoint rejects placement in furniture")
	await _sync()
	var stopped := avatar.move_and_collide(target+Vector3.UP*0.04-start)
	check(stopped != null and stopped.get_collider().name == &"SlidingDoor", "closed panel stops real player capsule")
	check(inside.interact(avatar.global_position) and inside.status().door_open, "player approaching from street can open door")
	await _sync()
	check(_hit(outside+at_eye, target+at_eye).is_empty(), "open doorway aligns with interior passage")
	var midway := threshold + Vector3.UP*0.04
	var crossed := avatar.move_and_collide(midway-avatar.global_position)
	check(crossed == null and avatar.global_position.is_equal_approx(midway), "capsule occupies threshold")
	await _sync()
	check(not inside.interact(avatar.global_position), "door cannot close on operator")
	check(not inside.interact(outside) and not inside.restore(saved_closed) and inside.status().door_open, "other occupant prevents collision on interaction and restore")
	crossed = avatar.move_and_collide(target+Vector3.UP*0.04-avatar.global_position)
	check(crossed == null and avatar.global_position.distance_to(target) < 0.05, "capsule crosses both openings into second room")
	await _sync()
	var saved_open: Variant = JSON.parse_string(JSON.stringify(inside.snapshot()))
	check(inside.interact(threshold + Vector3.BACK*1.4) and not inside.status().door_open, "door closes from inside after threshold clears")
	check(inside.restore(saved_open) and inside.status().door_open, "JSON checkpoint restores the open door")
	for malformed in [null, [], {}, {"seed": 225}]:
		check(not inside.restore(malformed) and inside.status().door_open, "incomplete save rejected atomically")
	for edits: Dictionary in [{"version": 2}, {"seed": "225"}, {"building_id": "other"}, {"layout": "other"}, {"door_open": 1}, {"extra": 1}]:
		var broken: Dictionary = saved_open.duplicate()
		broken.merge(edits, true)
		check(not inside.valid_snapshot(broken) and not inside.restore(broken) and inside.status().door_open, "invalid snapshot rejected")
	check(inside.restore(saved_closed), "restore original closed state after avatar moves")
	await _sync()
	check(_hit(outside+at_eye, target+at_eye) == "SlidingDoor", "restored state updates actual collision")
	avatar.free()


func _run() -> void:
	var inside := Interiors.new()
	root.add_child(inside)
	check(inside.snapshot().is_empty() and not inside.valid_snapshot({}) and not inside.interact(Vector3.ZERO), "unconfigured interior is inert")
	var row := {"id": "b0_0", "district": "downtown", "style": "midrise", "center": [60, 0, 35], "size": [25, 14, 29]}
	await _exercise(inside, row)
	var typical := inside.snapshot()
	var small := {"id": "b1_2", "district": "industrial", "style": "workshop", "center": [-23, 0, 7], "size": [9, 5, 9]}
	await _exercise(inside, small)
	check(inside.get_child_count() == 1 and not inside.valid_snapshot(typical), "reconfiguring replaces old geometry and rejects another layout")
	var stable := inside.snapshot()
	for bad_edit: Dictionary in [{"id": ""}, {"district": null}, {"center": [NAN, 0, 0]}, {"size": [8, 5, 9]}, {"size": [10, INF, 10]}]:
		var bad := small.duplicate()
		bad.merge(bad_edit, true)
		check(not inside.configure(10, bad) and inside.snapshot() == stable, "invalid layout leaves existing room unchanged")
	inside.free()
	if failures == 0:
		print("PASS vertical interiors")
	quit(1 if failures else 0)
