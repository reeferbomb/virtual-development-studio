extends SceneTree

const Squads = preload("res://squad_ai.gd")
const CENTER := Vector3(22.25, 4, -13.5)
const EXTENT := 10.0
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(passed: bool, label: String) -> void:
	if not passed:
		failures += 1
		printerr("FAIL squad AI: ", label)


func _configured(seed_value: int) -> Squads:
	var squads := Squads.new()
	root.add_child(squads)
	check(squads.configure(seed_value, CENTER, EXTENT), "configure")
	return squads


func _validation(squads: Squads) -> void:
	var valid := squads.snapshot()
	var malformed: Array = [null, [], {}, false]
	for edits in [{"seed": 271}, {"carry": -0.2}, {"tick": 0.3}, {"version": true},
			{"agents": [null]}, {"origin": [0, 0, 0]}, {"extent": INF}, {"carry": Squads.STEP_SECONDS}]:
		var top := valid.duplicate(true)
		top.merge(edits, true)
		malformed.append(top)
	for edits in [{"health": NAN}, {"health": 101}, {"x": 513}, {"z": false}, {"target": 1},
			{"target": 6}, {"health": 0, "target": 4}, {"cooldown": -1}, {"lock": 4}, {"shots": 2147483647}]:
		var row := valid.duplicate(true)
		row.agents[0].merge(edits, true)
		malformed.append(row)
	var dead_target := valid.duplicate(true)
	dead_target.agents[0].target = 4
	dead_target.agents[4].merge({"health": 0, "lock": 0, "target": -1, "cooldown": 0}, true)
	malformed.append(dead_target)
	for bad in malformed:
		check(not squads.valid_snapshot(bad) and not squads.restore(bad) and squads.snapshot() == valid,
			"invalid snapshot rejected atomically")
	var copy := squads.snapshot()
	copy.agents[0].health = 0
	check(squads.snapshot() == valid, "snapshot has no mutable aliases")
	for delta in [0.0, -1.0, INF, NAN]:
		squads.step(delta)
	check(not squads.configure(-1, CENTER, EXTENT) and not squads.configure(17, Vector3.INF, EXTENT)
		and not squads.configure(17, CENTER, 1.0) and squads.snapshot() == valid, "invalid input leaves match intact")


func _run() -> void:
	var arena := _configured(270)
	var baseline := arena.snapshot()
	var opening := arena.status()
	check(opening.alive == [3, 3] and opening.phase == "active" and opening.shots == 0, "two teams of three")
	check(arena.get_child_count() == 6 and arena.get_node("Drone1/Readout").text.contains("100"), "six visible drone models")
	arena.step(0.5)
	var moved := arena.status()
	check(moved.agents[0].position != opening.agents[0].position and moved.agents[0].mode == "formation",
		"drones approach the relay in formation")
	check(is_equal_approx(float(moved.agents[0].position[0]) - float(opening.agents[0].position[0]),
		float(moved.agents[1].position[0]) - float(opening.agents[1].position[0])),
		"formation slots share horizontal movement")
	var suppressed := false
	var engaged := false
	var pulse_visible := false
	for frame in 55:
		arena.step(Squads.STEP_SECONDS)
		for agent in arena.status().agents:
			suppressed = suppressed or (agent.mode == "suppressed" and agent.health < 100)
			engaged = engaged or (agent.mode == "engage" and agent.target >= 0)
			var pulse: MeshInstance3D = arena.get_node("Drone%d/Pulse" % (int(agent.id) + 1))
			pulse_visible = pulse_visible or (pulse.visible and pulse.scale.z > 0.0)
			var pos: Array = agent.position
			check(absf(pos[0] - CENTER.x) <= EXTENT and absf(pos[2] - CENTER.z) <= EXTENT,
				"bounded arena positions")
	check(suppressed and engaged and pulse_visible and arena.status().shots > 0,
		"visible shield tags reduce health and briefly suppress an opponent")
	arena.step(0.03125)
	var checkpoint: Dictionary = JSON.parse_string(JSON.stringify(arena.snapshot()))
	_validation(arena)
	var client := _configured(270)
	check(client.valid_snapshot(checkpoint) and client.restore(checkpoint) and client.status() == arena.status(),
		"JSON checkpoint restores the joined client's state")
	check(client.get_node("Drone1").position == arena.get_node("Drone1").position
		and client.get_node("Drone1/Readout").text == arena.get_node("Drone1/Readout").text,
		"replica meshes and health readouts follow an incoming snapshot")
	var checkpoint_tick: int = client.status().tick
	client.step(0.03125)
	arena.step(0.03125)
	check(client.status().tick == checkpoint_tick + 1, "restore preserves the partial tick")
	for unused in 32:
		client.step(0.125)
		arena.step(0.0625)
		arena.step(0.0625)
	check(client.snapshot() == arena.snapshot(), "regrouped time and restored simulation agree")
	arena.step(200.0)
	client.step(10000.0)
	var result := arena.status()
	check(result.phase == "finished" and result.winner in ["cyan", "amber", "draw"] and result.shots > 0,
		"round reaches a stable result")
	var end := arena.snapshot()
	arena.step(1.0)
	check(arena.snapshot() == end and client.snapshot() == end, "result and elapsed ticks freeze after the round")
	check(arena.configure(270, CENTER, EXTENT) and arena.snapshot() == baseline and arena.get_child_count() == 6,
		"reset reuses the six models")
	client.configure(270, CENTER, EXTENT)
	for unused in 60:
		client.step(1.0 / 60.0)
	arena.step(1.0)
	check(client.snapshot() == arena.snapshot(), "sixty display frames agree with a one-second host step")
	arena.step(100.0)
	check(arena.snapshot() == end, "fresh replay reproduces every final state field")
	check(arena.configure(271, CENTER, EXTENT) and arena.snapshot().agents != baseline.agents, "seed varies starting setup")
	arena.free()
	client.free()
	if failures == 0:
		print("PASS squad AI ", JSON.stringify({"ticks": result.tick, "shots": result.shots, "winner": result.winner}))
	quit(1 if failures else 0)
