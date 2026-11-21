extends SceneTree

const Civilians = preload("res://civilians.gd")
var failures := 0


func check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL ", label)


func _initialize() -> void:
	call_deferred("_run")


func _position(row: Dictionary) -> Vector3:
	return Vector3(row.position[0], row.position[1], row.position[2])


func _test_day(npcs: Civilians, blocks: int, size: float) -> void:
	var legal := true
	var crossings := 0
	var saw_sidestep := false
	var phases := {}
	var starts: Array = npcs.status().civilians
	for i in 720:
		npcs.step(1.0)
		if not saw_sidestep and npcs.get_child_count() == 40:
			for resident in npcs.get_children():
				var rendered := Vector2(resident.position.x, resident.position.z)
				if rendered.distance_to(resident.nominal) > 0.15:
					saw_sidestep = true
					break
		for row in npcs.status().civilians:
			var p := _position(row)
			var x := absf(p.x - roundf(p.x / size) * size)
			var z := absf(p.z - roundf(p.z / size) * size)
			var on_sidewalk := absf(x - 7.5) <= 0.56 or absf(z - 7.5) <= 0.56
			legal = legal and p.is_finite() and p.x >= 0 and p.x <= blocks * size and p.z >= 0 and p.z <= blocks * size and on_sidewalk
			if minf(x, z) < 6.0:
				crossings += 1
				legal = legal and row.moving and maxf(x, z) >= 6.94 and maxf(x, z) <= 8.06
			if not phases.has(row.id):
				phases[row.id] = {}
			phases[row.id][row.activity] = true
	check(legal and crossings > 0, "every sidewalk and crossing stays inside walkable strips")
	if npcs.get_child_count() == 40:
		check(saw_sidestep, "pedestrians give one another space at high occupancy")
	var complete := not phases.is_empty()
	for id in phases:
		complete = complete and phases[id].has_all(["home", "work", "leisure", "to_work", "to_leisure", "to_home"])
	check(complete, "each resident reaches all three destinations and walks every commute")
	check(npcs.status().civilians == starts, "daily circuit repeats without drift")


func _run() -> void:
	var npcs := Civilians.new()
	var twin := Civilians.new()
	root.add_child(npcs)
	root.add_child(twin)
	check(npcs.snapshot().is_empty() and npcs.nearest(Vector3.ZERO).is_empty() and not npcs.restore({}), "safe before configure")
	check(npcs.configure(237, 4, 48, 20) and twin.configure(237, 4, 48, 20), "default city configuration")
	var initial := npcs.status()
	var initial_save := npcs.snapshot()
	check(npcs.get_child_count() == 20 and initial.count == 20 and initial == twin.status(), "seeded visible population matches configuration")
	check(npcs.find_children("*", "MeshInstance3D", true, false).size() == 7 * 20, "twenty articulated residents have visible geometry")
	var first := _position(initial.civilians[0])
	var near := npcs.nearest(first + Vector3.UP * 0.5)
	check(near.id == "civilian-01" and is_equal_approx(near.distance, 0.5) and near.activity == initial.civilians[0].activity, "nearest resident and interaction distance")
	npcs.position = Vector3(100, 5, -60)
	var translated := npcs.nearest(first + npcs.position)
	check(translated.id == near.id and translated.distance < 0.0001 and _position(translated).is_equal_approx(first + npcs.position), "proximity query follows world transforms")
	npcs.position = Vector3.ZERO
	var original_row := npcs.status().civilians[0] as Dictionary
	near.position[0] = -999
	check(npcs.status().civilians[0] == original_row and npcs.nearest(Vector3(NAN, 0, 0)).is_empty(), "public queries return safe copies")
	for delta in [-1.0, 0.0, INF, NAN]:
		npcs.step(delta)
	check(npcs.snapshot() == initial_save and npcs.status() == initial, "invalid time steps are inert")
	for config in [[-1, 4, 48, 20], [2_147_483_648, 4, 48, 20], [0, 2, 48, 20], [0, 9, 48, 20], [0, 4, 31, 20], [0, 4, 65, 20], [0, 4, NAN, 20], [0, 4, 48, -1], [0, 4, 48, 41]]:
		check(not npcs.configure(config[0], config[1], config[2], config[3]) and npcs.status() == initial, "invalid configuration is atomic")
	npcs.step(3.75)
	for i in 30:
		twin.step(0.125)
	check(npcs.status() == twin.status() and npcs.status() != initial, "visible commuting motion independent of frame subdivision")
	for i in 1037:
		npcs.step(1.0 / 60.0)
	var saved := npcs.snapshot()
	var saved_pose := npcs.status()
	var decoded: Variant = JSON.parse_string(JSON.stringify(saved, "", true, true))
	check(twin.valid_snapshot(decoded) and twin.restore(decoded) and twin.status() == saved_pose and twin.snapshot() == saved, "fresh JSON restoration reproduces clock, poses and activities")
	npcs.step(2.5)
	twin.step(2.5)
	check(npcs.status() == twin.status(), "restored simulation continues identically")
	var stable := npcs.snapshot()
	var broken: Array = [null, true, [], {}, {"clock": 1}]
	for override in [{"version": 1.5}, {"seed": 238}, {"seed": "237"}, {"count": false}, {"blocks": 8}, {"block_size": 64}, {"count": 2}, {"clock": -0.01}, {"clock": 720.0}, {"clock": NAN}, {"clock": INF}, {"clock": "25"}, {"extra": 1}]:
		var malformed := saved.duplicate(true)
		malformed.merge(override, true)
		broken.append(malformed)
	for malformed in broken:
		check(not npcs.valid_snapshot(malformed) and not npcs.restore(malformed) and npcs.snapshot() == stable, "malformed or mismatched saves are atomic")
	check(twin.configure(238, 4, 48, 20) and twin.status() != initial, "different seed changes residents")
	check(npcs.configure(0, 3, 32, 40), "smallest city supports forty residents")
	_test_day(npcs, 3, 32.0)
	check(npcs.configure(2_147_483_647, 8, 64, 3) and npcs.get_child_count() == 3, "largest city and reconfiguration release obsolete residents")
	_test_day(npcs, 8, 64.0)
	check(npcs.configure(0, 3, 32, 0) and npcs.status().civilians.is_empty() and npcs.nearest(Vector3.ZERO).is_empty(), "empty city support")
	npcs.step(1e100)
	check(npcs.valid_snapshot(npcs.snapshot()), "large time jumps keep state bounded")
	npcs.free()
	twin.free()
	if failures == 0:
		print("PASS city civilians")
	quit(1 if failures else 0)
