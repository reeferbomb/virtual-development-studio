extends SceneTree

const Session = preload("res://world_sync.gd")
const Traffic = preload("res://traffic.gd")
const Civilians = preload("res://civilians.gd")
const SEED := 2026
const BLOCKS := 3
const BLOCK_SIZE := 32.0
const DT := 1.0 / 60.0
var server := Session.new()
var client := Session.new()
var late := Session.new()
var traffic := Traffic.new()
var civilians := Civilians.new()
var replica_traffic := Traffic.new()
var replica_civilians := Civilians.new()
var failures: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _check(condition: bool, message: String) -> void:
	if not condition:
		printerr("FAIL world sync: ", message)
		failures.append(message)


func _poll() -> void:
	server.step(DT, Vector2.ZERO)
	client.step(DT, Vector2.ZERO)
	late.step(DT, Vector2.ZERO)
	OS.delay_msec(2)


func _wait_for_tick(session: Node, tick: int) -> bool:
	for frame in 450:
		_poll()
		if session.status().world_tick == tick and session.status().connected:
			return true
	return false


func _world(tick: int) -> Dictionary:
	return {"tick": tick, "traffic": traffic.snapshot(), "civilians": civilians.snapshot()}


func _run() -> void:
	for model in [traffic, replica_traffic]:
		root.add_child(model)
		_check(model.configure(SEED, BLOCKS, BLOCK_SIZE, 24), "maximum traffic model configured")
	for model in [civilians, replica_civilians]:
		root.add_child(model)
		_check(model.configure(SEED, BLOCKS, BLOCK_SIZE, 40), "maximum civilian model configured")
	for session in [server, client, late]:
		root.add_child(session)
		_check(session.configure(BLOCKS * BLOCK_SIZE, Vector3(4, 0, 4)), "session configured")
	_check(server.set_world_validators(traffic.valid_snapshot, civilians.valid_snapshot), "authority validators bound")
	for session in [client, late]:
		_check(session.set_world_validators(replica_traffic.valid_snapshot, replica_civilians.valid_snapshot), "replica validators bound")
	var initial := _world(0)
	_check(not server.publish_world(initial), "offline publication refused")
	_check(server.host(0) and server.publish_world(initial), "host retains tick zero before any client joins")
	if not failures.is_empty():
		_finish()
		return
	var port := int(server.status().port)
	_check(client.join(port) and _wait_for_tick(client, 0), "first client receives full starting state")
	if not failures.is_empty():
		_finish()
		return
	_check(client.latest_world() == initial and client.status().world_sequence == 1, "starting snapshot matches exactly")
	var detached := client.latest_world()
	detached.traffic.cars[0].speed = -1
	_check(client.latest_world() == initial, "latest_world returns a detached copy")
	_check(not client.publish_world(_world(1)), "client cannot publish")

	traffic.step(10.75)
	civilians.step(10.75)
	var active := _world(645)
	_check(server.publish_world(active), "authority publishes moving traffic and walkers")
	active.traffic.cars.clear()
	_check(not server.publish_world(_world(645)) and not server.publish_world(initial), "repeated or backward ticks refused")
	var wrong_config := _world(650)
	wrong_config.traffic.seed = str(SEED + 1)
	wrong_config.civilians.seed += 1
	_check(not server.publish_world(wrong_config), "configuration mismatch rejected atomically")
	var oversized := _world(651)
	oversized.traffic.cars.append(oversized.traffic.cars[0])
	_check(not server.publish_world(oversized), "oversized traffic list refused")
	_check(_wait_for_tick(client, 645), "new snapshot arrives through ENet")
	var expected := _world(645)
	var replica := client.latest_world()
	_check(replica == expected, "maximum population decoded without float precision loss")
	if replica == expected:
		replica_traffic.step(2.0)
		replica_civilians.step(12.0)
		_check(replica_traffic.restore(replica.traffic) and replica_civilians.restore(replica.civilians), "remote simulation restored")
		_check(replica_traffic.status() == traffic.status(), "traffic positions and signal phases match")
		_check(replica_civilians.status() == civilians.status(), "resident positions and activities match")
	_check(late.join(port) and _wait_for_tick(late, 645), "late join receives last full world while host is idle")
	_check(late.latest_world() == expected, "late client converges without a new publication")

	var sequence := int(server.status().world_sequence)
	var packet := server._encode_world(_world(646), sequence + 1)
	_check(packet.size() == 481, "24 cars fit a single bounded world packet")
	var sender := int(client.status().peer_id)
	var rejected := int(client.status().world_rejected)
	# Send ordinary application packets over the live connection to exercise the
	# same authority, size, sequence and restore guards as the running scene.
	var replay := server._encode_world(initial, 1)
	var stale_tick := server._encode_world(initial, sequence + 1)
	var bad_value := packet.duplicate()
	bad_value.encode_double(64, NAN)
	for invalid in [replay, stale_tick, packet.slice(0, 70), bad_value]:
		server._api.send_bytes(invalid, sender, MultiplayerPeer.TRANSFER_MODE_RELIABLE, Session.WORLD_CHANNEL)
	client._api.send_bytes(packet, 1, MultiplayerPeer.TRANSFER_MODE_RELIABLE, Session.WORLD_CHANNEL)
	for frame in 450:
		_poll()
		if client.status().world_rejected == rejected + 4 and server.status().world_rejected == 1:
			break
	_check(client.status().world_rejected == rejected + 4 and client.latest_world() == expected, "stale and invalid snapshots leave last full state intact")
	_check(server.status().world_rejected == 1 and server.latest_world() == expected, "host retains exclusive world authority")
	_check(server.publish_world(_world(646)) and _wait_for_tick(client, 646) and _wait_for_tick(late, 646), "healthy updates resume on both clients")
	_check(client.status().snapshots > 0 and server.status().accepted_inputs > 0, "avatar channel remains live")
	var received := int(client.status().world_received)
	server.stop()
	for frame in 450:
		_poll()
		if client.status().mode == "offline" and late.status().mode == "offline":
			break
	_check(client.latest_world().is_empty() and late.latest_world().is_empty(), "disconnect discards previous authority")
	_check(server.host(0) and server.publish_world(initial), "new session starts at tick zero")
	_check(client.join(int(server.status().port)) and _wait_for_tick(client, 0), "reconnect accepts new session sequence")
	if failures.is_empty():
		print("PASS world sync ", JSON.stringify({"transport":"ENet", "clients":2, "late_join":true,
				"cars":24, "civilians":40, "packet_bytes":packet.size(), "received":received, "rejected":5,
				"traffic_restored":true, "civilians_restored":true, "reconnect":true}))
	_finish()


func _finish() -> void:
	for session in [server, client, late]:
		session.stop()
		session.free()
	for model in [traffic, civilians, replica_traffic, replica_civilians]:
		model.free()
	quit(0 if failures.is_empty() else 1)
