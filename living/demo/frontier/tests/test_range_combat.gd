extends SceneTree

const RangeCombat = preload("res://range_combat.gd")
var failures := 0

func check(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", label)

func _initialize() -> void:
	call_deferred("_run")

func _blocker(center: Vector3, layer: int) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = layer
	body.position = center
	var shape := BoxShape3D.new()
	shape.size = Vector3(2.0, 2.0, 0.4)
	var collider := CollisionShape3D.new()
	collider.shape = shape
	body.add_child(collider)
	root.add_child(body)
	return body

func _run() -> void:
	var combat := RangeCombat.new()
	root.add_child(combat)
	# Keeping the range offset also exercises world-space ray coordinates.
	combat.position = Vector3(2.0, 1.5, 0.0)
	var rows := [
		{"id": "front", "position": [0, 0, -5]},
		{"id": "rear", "position": [0, 0, -9]},
		{"id": "covered", "position": [4, 0, -5]},
	]
	check(combat.configure(rows), "configure range")
	var fresh := combat.snapshot()
	check(combat.target_alive("front") and not combat.target_alive("unknown"), "stable target IDs")
	check(not combat.reload(), "full magazine")
	for invalid in [[rows[0], rows[0]], [{"id": "", "position": [1, 2, 3]}], [{"id": "bad", "position": [NAN, 0, 0]}], [{"id": "short", "position": [1, 2]}]]:
		check(not combat.configure(invalid) and combat.snapshot() == fresh, "invalid configure is atomic")
	var wall := _blocker(combat.position + Vector3(4.0, 0.0, -3.0), 1)
	var bystander := _blocker(combat.position + Vector3(0.0, 0.0, -2.0), 2)
	# Even an unrelated collider carrying a copied ID must not count as a target.
	wall.set_meta(&"range_target_id", "covered")
	await physics_frame
	await physics_frame

	var origin := combat.global_position
	for direction: Vector3 in [Vector3.ZERO, Vector3(INF, 0, 1)]:
		check(not combat.shoot(origin, direction).fired and combat.snapshot() == fresh, "invalid aim")
	var blocked := combat.shoot(origin + Vector3.RIGHT * 4, Vector3.FORWARD)
	check(blocked == {"fired": true, "hit": false, "defeated": false, "id": ""}, "solid wall occludes target")
	check(combat.ammo == 5 and combat.snapshot().targets.covered == 2, "blocked shot consumes one round")
	combat.tick(NAN)
	combat.tick(-1.0)
	combat.tick(0.125)
	check(not combat.shoot(origin, Vector3.FORWARD).fired and combat.ammo == 5, "cooldown rejects early fire")
	combat.tick(0.125)
	var hit := combat.shoot(origin, Vector3.FORWARD * 4)
	check(hit == {"fired": true, "hit": true, "defeated": false, "id": "front"}, "nearest drone hit through ignored layer")
	var wounded := combat.snapshot()
	check(wounded.targets.front == 1 and wounded.targets.rear == 2, "first hit changes only front target")
	combat.tick(1.0)
	hit = combat.shoot(origin, Vector3.FORWARD)
	check(hit.hit and hit.defeated and hit.id == "front" and not combat.target_alive("front"), "second hit defeats front drone")
	var defeated := combat.snapshot()
	var front := combat.get_child(0) as StaticBody3D
	check(not front.visible and front.collision_layer == 0, "defeated drone hidden and removed from ray mask")
	await physics_frame
	combat.tick(1.0)
	hit = combat.shoot(origin, Vector3.FORWARD)
	check(hit.id == "rear" and hit.hit and not hit.defeated, "shot passes defeated drone")
	check(combat.reload() and combat.ammo == 6 and combat.reserve == 14, "reload transfers spent rounds")
	check(not combat.shoot(origin, Vector3.FORWARD).fired, "reload preserves fire interval")

	var saved := combat.snapshot()
	check(combat.valid_snapshot(wounded) and combat.snapshot() == saved, "successful preflight is read-only")
	for change in [{"ammo": 7}, {"ammo": 1.5}, {"ammo": true}, {"reserve": 19}, {"reserve": -1}, {"cooldown": INF}, {"cooldown": 0.26}, {"targets": []}, {"unexpected": 1}]:
		var invalid := saved.merged(change, true)
		check(not combat.valid_snapshot(invalid) and not combat.restore(invalid) and combat.snapshot() == saved, "invalid checkpoint field " + str(change))
	for counts in [{"front": 1, "rear": 2}, {"front": 1, "rear": 2, "different": 1}, {"front": 1, "rear": 2, "covered": -1}, {"front": 1, "rear": 2, "covered": 2.5}]:
		var invalid := fresh.merged({"targets": counts}, true)
		check(not combat.restore(invalid) and combat.snapshot() == saved, "invalid target state rolls back all changes")
	check(combat.restore(JSON.parse_string(JSON.stringify(wounded))) and combat.snapshot() == wounded, "JSON restores all ammunition, cooldown, and partial damage")
	check(front.visible and front.collision_layer == 8, "restore reactivates target's mesh and collider")
	await physics_frame
	combat.tick(1.0)
	check(combat.shoot(origin, Vector3.FORWARD).defeated, "restored damaged drone takes one further hit")
	check(combat.restore(defeated) and not front.visible, "checkpoint keeps defeated drone down")

	check(combat.restore(fresh.merged({"ammo": 1, "reserve": 1}, true)), "partial supply checkpoint")
	check(combat.reload() and combat.ammo == 2 and combat.reserve == 0 and not combat.reload(), "partial reload uses only remaining reserve")
	for i in range(2):
		var miss := combat.shoot(origin, Vector3.UP)
		check(miss.fired and not miss.hit, "clear-sky miss")
		combat.tick(1.0)
	check(not combat.shoot(origin, Vector3.UP).fired and not combat.reload(), "empty magazine and reserve")
	check(combat.configure(rows) and combat.snapshot() == fresh and combat.get_child_count() == rows.size(), "fresh configuration replaces old bodies")
	wall.free()
	bystander.free()
	combat.free()
	if failures == 0:
		print("PASS unified range combat")
	quit(1 if failures else 0)
