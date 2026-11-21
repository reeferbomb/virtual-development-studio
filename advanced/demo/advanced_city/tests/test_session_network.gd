extends SceneTree

const Session = preload("res://session_network.gd")
const Traffic = preload("res://traffic.gd")
const Civilians = preload("res://civilians.gd")
const STEP := 1.0 / 60.0
const SPAWN := Vector3(4, 0, 4)
const WORLD_SIZE := 96.0
const POINTS: Array[Vector3] = [SPAWN, Vector3(12, 0, 4), Vector3(4, 0, 12), Vector3(4, 8, 4)]

var server := Session.new()
var first := Session.new()
var late := Session.new()
var late_input := Vector2.ZERO
var failures: Array[String] = []
var saved_path := "user://test_multiplayer_session_%d.json" % OS.get_process_id()


func _initialize() -> void:
	_run.call_deferred()


func _check(value: bool, message: String) -> bool:
	if not value:
		failures.append(message)
		printerr("FAIL session network: ", message)
	return value


func _configure(session: Node, points: Array[Vector3] = POINTS) -> bool:
	root.add_child(session)
	return session.configure(WORLD_SIZE, SPAWN) and session.configure_objectives(points)


func _pump(first_input := Vector2.ZERO) -> void:
	server.step(STEP, Vector2.ZERO)
	first.step(STEP, first_input)
	late.step(STEP, late_input)
	OS.delay_msec(2)


func _until(condition: Callable, input := Vector2.ZERO) -> bool:
	for frame in 600:
		_pump(input)
		if condition.call():
			return true
	return false


func _revision(peer: Node, expected: int) -> bool:
	var status: Dictionary = peer.status()
	return status.connected and status.session_ready and status.session_revision == expected


func _send(from: Node, target: int, packet: PackedByteArray) -> void:
	_check(from._api.send_bytes(packet, target, MultiplayerPeer.TRANSFER_MODE_RELIABLE,
			Session.SESSION_CHANNEL) == OK, "application packet queued on session channel")


func _claim_packet(index: int) -> PackedByteArray:
	var packet := PackedByteArray([Session.CLAIM_PACKET, 1, index])
	packet.append_array(server._layout_hash)
	return packet


func _state_packet(mask: int, revision: int) -> PackedByteArray:
	var packet := PackedByteArray([Session.SESSION_PACKET, 1, POINTS.size(), revision, 0, 0])
	packet.encode_u16(4, mask)
	packet.append_array(server._layout_hash)
	return packet


func _run() -> void:
	for s in [server, first, late]:
		_check(_configure(s), "configure world and objectives")
	var initial := server.session_snapshot()
	_check(initial == {"version": 1, "revision": 0, "claimed": [false, false, false, false]},
			"configured host exposes detached empty flags")
	var detached := server.session_snapshot()
	detached.claimed[0] = true
	_check(server.session_snapshot() == initial, "returned state cannot mutate authority")
	var invalid_points: Array[Vector3] = [Vector3(NAN, 0, 0)]
	_check(not server.configure_objectives(invalid_points) and server.session_snapshot() == initial,
			"invalid reconfiguration preserves previous map")
	var capacity: Array[Vector3] = []
	capacity.resize(Session.MAX_OBJECTIVES)
	for i in capacity.size():
		capacity[i] = Vector3(i + 1, 0, 4)
	_check(late.configure_objectives(capacity), "maximum objective count accepted")
	var full := late.session_snapshot()
	full.claimed.fill(true)
	full.revision = Session.MAX_OBJECTIVES
	_check(late.restore_session(full) and late.session_snapshot() == full, "all sixteen flags restore")
	capacity.append(Vector3.ONE)
	_check(not late.configure_objectives(capacity) and late.session_snapshot() == full,
			"excess objectives refused without mutation")
	_check(late.configure_objectives(POINTS), "new layout starts with fresh flags")
	for invalid in [null, [], {}, {"version": 1, "revision": 1, "claimed": [false, false, false, false]},
			{"version": 1, "revision": 1, "claimed": [1, false, false, false]},
			{"version": 1, "revision": 0.5, "claimed": [false, false, false, false]}]:
		_check(not server.valid_session_snapshot(invalid) and not server.restore_session(invalid),
				"malformed checkpoint rejected atomically")
	_check(not server.request_objective(0) and server.session_snapshot() == initial, "offline cannot claim")
	if not _check(server.host(0), "bind ephemeral loopback port"):
		_finish()
		return
	_check(server.restore_session(initial), "host may restore before activation")
	_check(not server.request_objective(-1) and not server.request_objective(99)
			and not server.request_objective(1) and not server.request_objective(3),
			"host enforces index and three-dimensional radius")
	var port := int(server.status().port)
	if not _check(first.join(port) and _until(func(): return _revision(first, 0)), "initial ENet sync"):
		_finish()
		return
	_check(not server.restore_session(initial) and not first.restore_session(initial),
			"active host and remote client cannot replace progress")
	_check(server.request_objective(0) and not server.request_objective(0), "host claim awards once")
	_check(_until(func(): return _revision(first, 1)), "host claim replicated")
	var before := int(server.status().session_rejected)
	_check(first.request_objective(1), "distant client sends index-only request")
	_check(_until(func(): return server.status().session_rejected == before + 1),
			"server independently denies remote claim outside radius")
	_check(first.session_snapshot() == server.session_snapshot(), "denial leaves all flags unchanged")
	var first_id := int(first.status().peer_id)
	var wrong_layout := _claim_packet(0)
	wrong_layout[3] ^= 1
	for packet in [_claim_packet(255), _claim_packet(0), _claim_packet(1).slice(0, 2),
			_claim_packet(1) + PackedByteArray([0]), wrong_layout, _state_packet(15, 4)]:
		_send(first, 1, packet)
	_check(_until(func(): return server.status().session_rejected == before + 7),
			"host rejects bounds, replay, sizes, layout and client-authored snapshot")
	var active := server.session_snapshot()
	var previously_received := int(first.status().session_rejected)
	var wrong_version := _state_packet(3, 2)
	wrong_version[1] += 1
	for packet in [_state_packet(1, 1), _state_packet(2, 1), _state_packet(17, 2),
			_state_packet(3, 3), wrong_version, _state_packet(3, 2).slice(0, 5)]:
		_send(server, first_id, packet)
	_check(_until(func(): return first.status().session_rejected == previously_received + 6)
			and first.session_snapshot() == active, "stale, nonmonotone and malformed state rejected")
	_check(_until(func(): return server.status().peers[first_id].x > 11, Vector2.RIGHT),
			"server advances player from movement input")
	_check(first.request_objective(1) and _until(func(): return _revision(first, 2)),
			"same remote objective succeeds after authoritative movement")
	_check(not first.request_objective(1) and server.session_snapshot().revision == 2,
			"repeated confirmation cannot award an extra completion")
	if not _check(late.join(port) and _until(func(): return _revision(late, 2)),
			"idle late join receives current flags"):
		_finish()
		return
	_check(first.session_snapshot() == late.session_snapshot(), "independent clients converge")
	var traffic := Traffic.new()
	var civilians := Civilians.new()
	_check(traffic.configure(2, 3, 32.0, 3) and civilians.configure(2, 3, 32.0, 4), "configure world")
	var world := {"tick": 17, "traffic": traffic.snapshot(), "civilians": civilians.snapshot()}
	var world_arrived := func(): return first.latest_world() == world and late.latest_world() == world
	_check(server.publish_world(world) and _until(world_arrived),
			"inherited world snapshots pass alongside objective packets")
	_check(server.status().accepted_inputs > 0 and first.status().snapshots > 0, "avatar updates remain live")
	traffic.free()
	civilians.free()

	var saved := server.session_snapshot()
	var file := FileAccess.open(saved_path, FileAccess.WRITE)
	if not _check(file != null, "create restart fixture"):
		_finish()
		return
	file.store_string(JSON.stringify(saved))
	file.close()
	first.stop()
	_check(first.session_snapshot() == initial, "disconnect discards remote authority")
	_check(first.join(port) and _until(func(): return _revision(first, 2)), "reconnect receives idle progress")
	server.stop()
	_check(server.session_snapshot() == saved, "stopped host retains authoritative checkpoint")
	_check(_until(func(): return first.status().mode == "offline" and late.status().mode == "offline"),
			"both clients observe server shutdown")
	server.free()
	server = Session.new()
	var disk_state: Variant = JSON.parse_string(FileAccess.get_file_as_string(saved_path))
	if not _check(_configure(server) and server.restore_session(disk_state) and server.host(0),
			"fresh host restores saved JSON and starts"):
		_finish()
		return
	port = int(server.status().port)
	_check(first.join(port) and _until(func(): return _revision(first, 2))
			and first.session_snapshot() == saved, "new host republishes exact checkpoint")
	_check(late.join(port) and _until(func(): return _revision(late, 2)), "second client rejoins fresh host")
	var a := int(first.status().peer_id)
	var b := int(late.status().peer_id)
	var reached := func(): return server.status().peers[a].z > 11 and server.status().peers[b].z > 11
	late_input = Vector2.DOWN
	_check(_until(reached, Vector2.DOWN), "two players independently reach the same objective")
	late_input = Vector2.ZERO
	_check(first.request_objective(2) and late.request_objective(2), "simultaneous requests queued")
	var converged := func(): return _revision(first, 3) and _revision(late, 3)
	_check(_until(converged) and server.session_snapshot().revision == 3
			and server.status().session_rejected == 1, "concurrent claims advance the objective exactly once")
	late.stop()
	var alternate: Array[Vector3] = POINTS.duplicate()
	alternate.reverse()
	_check(late.configure_objectives(alternate) and late.join(port)
			and _until(func(): return late.status().session_rejected > 0),
			"peer with reordered landmarks rejects incompatible snapshot")
	_check(not late.status().session_ready and late.session_snapshot().is_empty()
			and not late.request_objective(2), "incompatible replica cannot submit a normal claim")
	if failures.is_empty():
		print("PASS session network ", JSON.stringify({"transport": "ENet", "clients": 2,
				"shared_claims": 3, "concurrent_claim": true, "late_join": true, "reconnect": true, "disk_restart": true,
				"authority_position": true, "world_and_avatars": true,
				"request_bytes": Session.CLAIM_BYTES, "snapshot_bytes": Session.SESSION_BYTES}))
	_finish()


func _finish() -> void:
	if FileAccess.file_exists(saved_path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(saved_path))
	for s in [server, first, late]:
		s.stop()
		s.free()
	quit(0 if failures.is_empty() else 1)
