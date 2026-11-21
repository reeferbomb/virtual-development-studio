extends SceneTree

const Session = preload("res://city_network.gd")
const SPAWN := Vector3(4.0, 0.05, 4.0)
const BUILDINGS := [{"center": [7.0, 0.0, 4.0], "size": [2.0, 4.0, 3.0]}]
var server := Session.new()
var first := Session.new()
var second := Session.new()
var failures: Array[String] = []

func _initialize() -> void:
	_run.call_deferred()

func _check(ok: bool, reason: String) -> void:
	if not ok:
		failures.append(reason)
		printerr("FAIL city network: ", reason)

func _ticks(count: int, host_input := Vector2.ZERO, first_input := Vector2.ZERO, second_input := Vector2.ZERO) -> void:
	for _i in count:
		server.step(1.0 / 60.0, host_input)
		first.step(1.0 / 60.0, first_input)
		second.step(1.0 / 60.0, second_input)
		OS.delay_msec(3)

func _run() -> void:
	for session in [server, first, second]:
		root.add_child(session)
		_check(not session.configure(20.0, Vector3(-1, 0, 0)), "spawn outside city rejected")
		_check(session.configure(20.0, SPAWN), "positive-coordinate city configured")
		_check(not session.set_obstacles([{"center": [4, 0, 4], "size": [2, 4, 2]}]), "blocked spawn rejected")
		_check(session.set_obstacles(BUILDINGS), "building footprints configured")
	_check(not server.host(-1) and not first.join(0), "invalid ports rejected")
	_check(server.host(0), "ENet host bound on loopback")
	var port: int = server.status().port
	_check(port > 0, "ephemeral port assigned")
	_check(first.join(port) and second.join(port), "two ENet clients started")
	for _i in 400:
		_ticks(1)
		if first.status().peers.size() == 3 and second.status().peers.size() == 3:
			break
	if first.status().peers.size() != 3 or second.status().peers.size() != 3:
		_check(false, "three authoritative members did not appear on both clients")
		_finish()
		return
	var one: int = first.status().peer_id
	var two: int = second.status().peer_id
	_check(one != two and one > 1 and two > 1, "clients have distinct ENet identities")
	_check(server.get_child_count() == 2 and first.get_child_count() == 2 and second.get_child_count() == 2, "each scene renders two remote avatars")
	_ticks(100, Vector2.UP, Vector2.RIGHT, Vector2.DOWN)
	_ticks(20)
	var authority: Dictionary = server.status()
	_check(is_equal_approx(authority.local_position.z, Session.RADIUS), "host stops at lower city boundary")
	_check(is_equal_approx(authority.peers[one].x, 6.0 - Session.RADIUS), "server stops first client at building wall")
	_check(authority.peers[two].z > SPAWN.z + 5.0, "second client moves independently")
	_check(first.status().local_position.is_equal_approx(authority.peers[one]), "first client matches authority")
	_check(second.status().peers[one].is_equal_approx(authority.peers[one]), "observer sees same building collision")
	_check(first.status().peers[two].is_equal_approx(authority.peers[two]), "first client sees second client's position")
	_ticks(120, Vector2.ZERO, Vector2(1, 1).normalized(), Vector2.DOWN)
	_ticks(20)
	_check(first.status().local_position.z > 6.0 and first.status().local_position.x > 7.0, "diagonal movement slides past wall")
	_check(is_equal_approx(second.status().local_position.z, 20.0 - Session.RADIUS), "server enforces upper city boundary")

	var before: int = server.status().rejected_inputs
	var accepted_before: int = server.status().accepted_inputs
	var position_before: Vector3 = first.status().local_position
	# Exercise invalid input over the same socket as player traffic.
	first._api.send_bytes(first._input_packet(0, Vector2.RIGHT), 1)
	first._api.send_bytes(first._input_packet(first._sequence + 1, Vector2(9, 0)), 1)
	first._api.send_bytes(first._input_packet(first._sequence + 2, Vector2(NAN, 0)), 1)
	_ticks(40)
	_check(server.status().rejected_inputs == before + 3, "server rejects replay, excessive input and nonfinite values")
	_check(server.status().accepted_inputs > accepted_before, "valid input continues after rejected packets")
	_check(first.status().local_position.is_equal_approx(position_before), "invalid commands do not move player")
	var snapshots_one: int = first.status().snapshots
	var snapshots_two: int = second.status().snapshots
	var accepted: int = server.status().accepted_inputs
	var rejected: int = server.status().rejected_inputs
	second.stop()
	for _i in 400:
		_ticks(1)
		if first.status().peers.size() == 2:
			break
	_check(not server.status().peers.has(two) and not first.status().peers.has(two), "disconnect removed from authority and surviving client")
	server.stop()
	for _i in 400:
		_ticks(1)
		if first.status().mode == "offline":
			break
	_check(first.status().mode == "offline", "client clears session after server shutdown")
	_check(server.host(0), "stopped session can host again")
	if failures.is_empty():
		print("PASS city network ", JSON.stringify({"transport":"ENet", "address":"127.0.0.1",
			"clients":2, "client_snapshots":[snapshots_one,snapshots_two], "accepted_inputs":accepted,
			"rejected_inputs":rejected, "building_collision":true, "bounds":true, "disconnect":true}))
	_finish()

func _finish() -> void:
	for session in [server, first, second]:
		session.stop()
		session.free()
	quit(0 if failures.is_empty() else 1)
