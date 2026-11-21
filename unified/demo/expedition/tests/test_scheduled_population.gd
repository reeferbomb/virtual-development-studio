extends SceneTree

const Population := preload("res://scheduled_population.gd")
const SEED := 241
const SIZE := 32.0
const WEST := Vector3(-0.01, 0.0, -32.01)
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, message: String) -> void:
	if not ok:
		printerr("FAIL ", message)
		failures += 1

func point(row: Dictionary) -> Vector3:
	return Vector3(row.position[0], row.position[1], row.position[2])

func verify_nodes(population: Node3D, expected_phase: String) -> Dictionary:
	var state: Dictionary = population.snapshot()
	check(not state.is_empty() and state.size() == population.loaded_count(), "stream has residents")
	for group in population.get_children():
		for npc in group.get_children():
			var row: Dictionary = state[npc.get_meta("npc_id")]
			var p: Vector3 = npc.global_position
			check(point(row).is_equal_approx(p), "snapshot tracks rendered node")
			check(npc.get_node("Coat").mesh is CapsuleMesh and npc.get_node("Head").is_visible_in_tree(), "base humanoid visible")
			check([floori(p.x / SIZE), floori(p.z / SIZE)] == row.chunk, "route stays inside home chunk")
			check(row.chunk == [-1, -2], "negative world coordinates use the correct chunk")
			var near: Dictionary = population.nearest(p)
			check(near.id == npc.name and near.phase == row.phase and is_zero_approx(near.distance), "nearest uses rendered position and activity")
			if not expected_phase.is_empty():
				check(row.phase == expected_phase, "expected " + expected_phase + ", got " + row.phase)
	return state

func run() -> void:
	var residents := Population.new()
	var partitioned := Population.new()
	root.add_child(residents)
	root.add_child(partitioned)
	check(residents.configure(SEED, SIZE, 0) and partitioned.configure(SEED, SIZE, 0), "initial setup")
	residents.update_center(WEST)
	partitioned.update_center(WEST)
	check(residents.clock_snapshot() == {"day": 1, "hour": 0.0, "phase": "home"}, "clock starts at midnight")
	var home := verify_nodes(residents, "home")
	residents.step(35.0)
	verify_nodes(residents, "to_work")
	residents.step(25.0)
	check(residents.clock_snapshot() == {"day": 1, "hour": 12.0, "phase": "work"}, "midday clock")
	var work := verify_nodes(residents, "work")
	residents.step(22.5)
	verify_nodes(residents, "to_leisure")
	residents.step(10.0)
	var leisure := verify_nodes(residents, "leisure")
	for id in home:
		check(point(home[id]).distance_to(point(work[id])) > SIZE / 4.0, "workplace differs from home")
		check(point(leisure[id]).distance_to(point(work[id])) > SIZE / 4.0, "leisure differs from workplace")
		check(point(leisure[id]).distance_to(point(home[id])) > SIZE / 4.0, "leisure differs from home")
	residents.step(12.5)
	verify_nodes(residents, "to_home")
	residents.step(15.0)
	check(residents.clock_snapshot().day == 2 and residents.clock_snapshot().hour == 0.0, "day advances at midnight")
	check(verify_nodes(residents, "home") == home, "positions repeat on the next day")

	# Observe successive real poses across a full day, including every commute
	# boundary and midnight. Instantaneous jumps would exceed the speed bound.
	var previous := home
	for i in 1200:
		partitioned.step(0.1)
		var now := partitioned.snapshot()
		for id in now:
			var p := point(now[id])
			check(p.distance_to(point(previous[id])) < 0.4, "no jump at a route transition")
			check([floori(p.x / SIZE), floori(p.z / SIZE)] == now[id].chunk, "commute stays in negative home chunk")
		previous = now
	check(partitioned.snapshot() == residents.snapshot() and partitioned.clock_snapshot() == residents.clock_snapshot(), "time partitions agree through rollover")

	residents.update_center(Vector3(400.0, 0.0, 160.0))
	for id in home:
		check(not residents.snapshot().has(id), "resident unloaded")
	residents.step(34.125)
	partitioned.step(34.125)
	residents.update_center(WEST)
	check(verify_nodes(residents, "") == partitioned.snapshot(), "unloaded resident rejoins a commute in progress")
	var restored := Population.new()
	root.add_child(restored)
	check(restored.configure(SEED, SIZE, 0), "fresh setup for checkpoint time")
	restored.step(154.125)
	restored.update_center(WEST)
	check(restored.snapshot() == residents.snapshot() and restored.clock_snapshot() == residents.clock_snapshot(), "fresh population restores from elapsed time alone")
	var saved := residents.snapshot()
	residents.step(NAN)
	residents.step(-1.0)
	check(not residents.configure(SEED, 2.0, 0) and residents.snapshot() == saved, "invalid update preserves schedule")
	check(residents.configure(SEED, SIZE, 0), "reconfiguration")
	residents.update_center(WEST)
	check(residents.snapshot() == home and residents.clock_snapshot().day == 1, "reconfigure resets route and clock")
	residents.free()
	partitioned.free()
	restored.free()
	if failures == 0:
		print("SCHEDULED_POPULATION_TEST_PASS")
	quit(int(failures > 0))
