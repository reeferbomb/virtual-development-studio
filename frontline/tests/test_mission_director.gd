extends SceneTree

const Director = preload("res://mission_director.gd")
const SEED := 237
const SPAWN := Vector3(96, 0, 96)
var failures := 0


func check(ok: bool, description: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL mission director: ", description)


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var host := Director.new()
	var client := Director.new()
	root.add_child(host)
	root.add_child(client)
	check(host.snapshot().is_empty() and not host.request(1, SPAWN), "inert before configuration")
	check(not host.configure(SEED, SPAWN, NAN, 48) and not host.configure(SEED, Vector3(72, 0, 72), 192, 48), "bad geometry and dispatch inside city lot rejected")
	check(host.configure(SEED, SPAWN, 192, 48) and client.configure(SEED, SPAWN, 192, 48), "configure matching worlds")
	check(not host.configure(SEED, SPAWN, 192, 48), "no duplicate marker on repeat configuration")
	client.set_authoritative(false)
	var plan := [SPAWN + Vector3.FORWARD * 12, SPAWN + Vector3.LEFT * 12, SPAWN + Vector3.BACK * 12]
	var peers := [1, 8, 8]
	var fresh := host.snapshot()
	var title: String = host.status().title
	var beacon := host.get_node("MissionBeacon") as Node3D
	check(beacon.is_visible_in_tree() and beacon.get_child_count() == 3, "visible objective ring, pointer, and sign")
	check(not host.restart(), "active contracts cannot be reset")
	for invalid_delta in [-0.25, NAN, INF, 0.0]:
		host.step(invalid_delta)
	check(host.snapshot() == fresh, "invalid clock input has no effect")
	for i in plan.size():
		var point: Vector3 = plan[i]
		check(host.target_position().is_equal_approx(point) and beacon.global_position.is_equal_approx(point), "seeded marker at road landmark %d" % i)
		check(client.target_position().is_equal_approx(point), "replica marker matches host")
		check(not host.request(0, point) and not host.request(1, Vector3(NAN, 0, 0)), "peer ID and position validated")
		check(not host.request(1, point + Vector3.UP * 4) and not host.request(1, SPAWN), "enforce world-space proximity")
		var replica_before := client.snapshot()
		client.step(999)
		check(not client.request(1, point) and client.snapshot() == replica_before, "replica cannot advance or expire a stage")
		host.step(1.2345)
		check(host.request(peers[i], point), "one nearby teammate advances stage %d" % i)
		check(not host.request(peers[i], point) and host.status().stage == i + 1, "same position cannot advance twice")
		var encoded: Variant = JSON.parse_string(JSON.stringify(host.snapshot()))
		check(client.valid_snapshot(encoded) and client.restore(encoded), "replicate stage %d through JSON" % i)
		check(client.snapshot() == host.snapshot(), "same canonical state after transport")
	var done := host.snapshot()
	check(host.status().phase == "completed" and done.score == 425 and done.contributors == peers, "co-op credit, completion bonus and attribution")
	check(host.target_position() == SPAWN and not client.restart(), "terminal marker points to dispatch and replica cannot restart")
	host.step(999)
	check(host.snapshot() == done, "completed timer and score freeze")
	check(not host.request(1, plan[2]) and host.request(8, SPAWN), "only nearby dispatch interaction starts next contract")
	check(host.status().round == 2 and host.status().phase == "active" and host.status().score == 0, "new round resets progress")
	check(host.status().title != title and host.target_position() != plan[0], "next round changes contract and route")
	check(host.request(8, host.target_position()), "record first handoff before timeout")
	host.step(Director.TIME_LIMIT)
	var expired := host.snapshot()
	check(expired.phase == "failed" and expired.stage == 1 and expired.score == 100 and expired.remaining_ms == 0, "timeout preserves only earned points")
	check(client.restore(JSON.parse_string(JSON.stringify(expired))) and client.target_position() == SPAWN, "timeout replicates to dispatch")
	for changes in [{"version": true}, {"world": "elsewhere"}, {"round": 1.5}, {"phase": "completed"},
			{"stage": 3}, {"score": 999}, {"remaining_ms": 1}, {"contributors": [0]},
			{"contributors": [1, 2]}, {"contributors": ["8"]}, {"extra": true}]:
		var invalid := expired.duplicate(true)
		invalid.merge(changes, true)
		check(not client.valid_snapshot(invalid) and not client.restore(invalid) and client.snapshot() == expired, "reject invalid snapshot atomically: %s" % [changes])
	var incomplete := expired.duplicate(true)
	incomplete.erase("score")
	check(not client.restore(incomplete) and not client.restore(null) and not client.restore([]), "reject missing fields and wrong root type")
	check(host.restart() and host.status().round == 3 and host.status().time_left == Director.TIME_LIMIT, "restart after timeout")
	var other := Director.new()
	root.add_child(other)
	check(other.configure(SEED + 1, SPAWN, 192, 48) and not other.restore(fresh) and other.target_position() != plan[0], "world identity and route vary by seed")
	other.free()
	client.free()
	host.free()
	if failures == 0:
		print("PASS mission director: 3 stages, 2 contributors, 425 points, timeout/restart and replicated markers")
	quit(int(failures != 0))
