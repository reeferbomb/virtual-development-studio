extends Node3D

## Independent ENet session. The city calls step() once each physics tick.
## Positions use the city's local coordinates, with +X and +Z as the input axes.
const LOOPBACK := "127.0.0.1"
const MAX_CLIENTS := 8
const SPEED := 6.0
const RADIUS := 0.35
const INPUT_PERIOD := 1.0 / 30.0
const SNAPSHOT_PERIOD := 1.0 / 20.0
const INPUT_TIMEOUT := 0.35
const INPUT := 1
const SNAPSHOT := 2

var _world_limit := 0.0
var _spawn := Vector3.ZERO
var _obstacles: Array[Rect2] = []
var _mode := "offline"
var _api: SceneMultiplayer
var _peer: ENetMultiplayerPeer
var _local_id := 0
var _port := 0
var _positions: Dictionary[int, Vector3] = {}
var _directions: Dictionary[int, Vector2] = {}
var _last_input: Dictionary[int, int] = {}
var _input_age: Dictionary[int, float] = {}
var _avatars: Dictionary[int, MeshInstance3D] = {}
var _until_send := 0.0
var _sequence := 0
var _snapshot_sequence := 0
var _received_snapshots := 0
var _accepted := 0
var _rejected := 0
var _lost_connection := false

func configure(world_size: float, spawn: Vector3) -> bool:
	if _mode != "offline" or not is_finite(world_size) or world_size <= RADIUS * 2.0 or not spawn.is_finite():
		return false
	var limit := world_size - RADIUS
	if spawn.x < RADIUS or spawn.x > limit or spawn.z < RADIUS or spawn.z > limit:
		return false
	_world_limit = limit
	_spawn = spawn
	_obstacles.clear()
	return true

func set_obstacles(buildings: Array) -> bool:
	if _mode != "offline" or _world_limit <= 0.0:
		return false
	var rectangles: Array[Rect2] = []
	for building in buildings:
		if not building is Dictionary or not building.has_all(["center", "size"]):
			return false
		var center = building.center
		var size = building.size
		if not _is_triplet(center) or not _is_triplet(size):
			return false
		if size[0] <= 0 or size[1] <= 0 or size[2] <= 0:
			return false
		var footprint := Vector2(size[0], size[2])
		var rectangle := Rect2(Vector2(center[0], center[2]) - footprint * 0.5, footprint).grow(RADIUS)
		if rectangle.has_point(Vector2(_spawn.x, _spawn.z)):
			return false
		rectangles.append(rectangle)
	_obstacles = rectangles
	return true

func _is_triplet(value: Variant) -> bool:
	if not value is Array or value.size() != 3:
		return false
	for n in value:
		if not (n is float or n is int) or not is_finite(float(n)):
			return false
	return true

func host(port: int) -> bool:
	if not _can_start(port, 0):
		return false
	var peer := ENetMultiplayerPeer.new()
	peer.set_bind_ip(LOOPBACK)
	if peer.create_server(port, MAX_CLIENTS) != OK:
		return false
	_start(peer, "host", peer.host.get_local_port())
	_add_member(1)
	return true

func join(port: int) -> bool:
	if not _can_start(port, 1):
		return false
	var peer := ENetMultiplayerPeer.new()
	if peer.create_client(LOOPBACK, port) != OK:
		return false
	_start(peer, "client", port)
	return true

func _can_start(port: int, minimum_port: int) -> bool:
	return is_inside_tree() and _mode == "offline" and _world_limit > 0.0 and port >= minimum_port and port <= 65535

func _start(peer: ENetMultiplayerPeer, mode: String, port: int) -> void:
	_peer = peer
	_mode = mode
	_port = port
	_api = SceneMultiplayer.new()
	_api.root_path = get_path()
	_api.server_relay = false
	_api.peer_packet.connect(_receive)
	_api.peer_connected.connect(_add_member)
	_api.peer_disconnected.connect(_remove_member)
	_api.server_disconnected.connect(_server_lost)
	_api.connection_failed.connect(_server_lost)
	_api.multiplayer_peer = peer
	_local_id = peer.get_unique_id()

func _server_lost() -> void:
	_lost_connection = true

func _add_member(id: int) -> void:
	if _mode == "host":
		_positions[id] = _spawn
		_directions[id] = Vector2.ZERO
		_last_input[id] = 0
		_input_age[id] = 0.0
		_until_send = 0.0

func _remove_member(id: int) -> void:
	if _mode == "host":
		_positions.erase(id)
		_directions.erase(id)
		_last_input.erase(id)
		_input_age.erase(id)
		_until_send = 0.0

func step(delta: float, input: Vector2) -> void:
	if _api == null or not is_finite(delta) or delta <= 0.0:
		return
	_api.poll()
	if _lost_connection:
		stop()
		return
	var dt := minf(delta, 0.1)
	var direction := input.limit_length(1.0) if input.is_finite() else Vector2.ZERO
	_until_send -= dt
	if _mode == "host":
		_directions[1] = direction
		for id: int in _positions:
			_input_age[id] += dt
			if id != 1 and _input_age[id] > INPUT_TIMEOUT:
				_directions[id] = Vector2.ZERO
			_positions[id] = _member_move(id,dt)
		_after_members_moved(dt)
		if _positions.size() > 1 and _until_send <= 0.0:
			_until_send = SNAPSHOT_PERIOD
			_snapshot_sequence += 1
			_api.send_bytes(_snapshot(), 0, MultiplayerPeer.TRANSFER_MODE_UNRELIABLE_ORDERED)
	elif _until_send <= 0.0 and _peer.get_connection_status() == MultiplayerPeer.CONNECTION_CONNECTED:
		_until_send = INPUT_PERIOD
		_sequence += 1
		_api.send_bytes(_input_packet(_sequence, direction), 1, MultiplayerPeer.TRANSFER_MODE_UNRELIABLE_ORDERED)
	_update_avatars()

func _member_move(id: int,dt: float) -> Vector3:
	return _move(_positions[id], _directions[id] * SPEED * dt)

func _after_members_moved(_dt: float) -> void:
	pass

func _move(from: Vector3, distance: Vector2) -> Vector3:
	var x := clampf(from.x + distance.x, RADIUS, _world_limit)
	for r in _obstacles:
		if from.z > r.position.y and from.z < r.end.y:
			if from.x <= r.position.x and x >= r.position.x:
				x = r.position.x
			elif from.x >= r.end.x and x <= r.end.x:
				x = r.end.x
	var z := clampf(from.z + distance.y, RADIUS, _world_limit)
	for r in _obstacles:
		if x > r.position.x and x < r.end.x:
			if from.z <= r.position.y and z >= r.position.y:
				z = r.position.y
			elif from.z >= r.end.y and z <= r.end.y:
				z = r.end.y
	return Vector3(x, from.y, z)

# Fixed-size numeric packets. Only server code constructs positions.
func _input_packet(sequence: int, direction: Vector2) -> PackedByteArray:
	var packet := PackedByteArray()
	packet.resize(13)
	packet[0] = INPUT
	packet.encode_u32(1, sequence)
	packet.encode_float(5, direction.x)
	packet.encode_float(9, direction.y)
	return packet

func _snapshot() -> PackedByteArray:
	var packet := PackedByteArray()
	packet.resize(6 + 16 * _positions.size())
	packet[0] = SNAPSHOT
	packet.encode_u32(1, _snapshot_sequence)
	packet[5] = _positions.size()
	var offset := 6
	for id: int in _positions:
		var position_value := _positions[id]
		packet.encode_u32(offset, id)
		packet.encode_float(offset + 4, position_value.x)
		packet.encode_float(offset + 8, position_value.y)
		packet.encode_float(offset + 12, position_value.z)
		offset += 16
	return packet

func _receive(sender: int, packet: PackedByteArray) -> void:
	if _mode == "host":
		if not _positions.has(sender) or sender <= 1 or packet.size() != 13 or packet[0] != INPUT:
			_rejected += 1
			return
		var sequence := packet.decode_u32(1)
		var direction := Vector2(packet.decode_float(5), packet.decode_float(9))
		if sequence <= _last_input[sender] or not direction.is_finite() or direction.length_squared() > 1.00001:
			_rejected += 1
			return
		_last_input[sender] = sequence
		_directions[sender] = direction.limit_length(1.0)
		_input_age[sender] = 0.0
		_accepted += 1
	elif sender == 1:
		_receive_snapshot(packet)

func _receive_snapshot(packet: PackedByteArray) -> void:
	if packet.size() < 6 or packet[0] != SNAPSHOT:
		return
	var sequence := packet.decode_u32(1)
	var count := int(packet[5])
	if sequence <= _snapshot_sequence or count < 1 or count > MAX_CLIENTS + 1 or packet.size() != 6 + count * 16:
		return
	var next: Dictionary[int, Vector3] = {}
	for i in count:
		var offset := 6 + i * 16
		var id := packet.decode_u32(offset)
		var pos := Vector3(packet.decode_float(offset + 4), packet.decode_float(offset + 8), packet.decode_float(offset + 12))
		if id < 1 or next.has(id) or not pos.is_finite():
			return
		if pos.x < RADIUS - 0.001 or pos.z < RADIUS - 0.001 or maxf(pos.x, pos.z) > _world_limit + 0.001:
			return
		next[id] = pos
	if not next.has(1) or not next.has(_local_id):
		return
	_positions = next
	_snapshot_sequence = sequence
	_received_snapshots += 1

func _update_avatars() -> void:
	for id: int in _avatars.keys():
		if not _positions.has(id):
			_avatars[id].queue_free()
			_avatars.erase(id)
	for id: int in _positions:
		if id == _local_id:
			continue
		if not _avatars.has(id):
			var avatar := MeshInstance3D.new()
			avatar.name = "Peer_%d" % id
			var mesh := CapsuleMesh.new()
			mesh.radius = RADIUS
			mesh.height = 1.8
			avatar.mesh = mesh
			var material := StandardMaterial3D.new()
			material.albedo_color = Color.from_hsv(fmod(id * 0.61803, 1.0), 0.72, 0.95)
			avatar.material_override = material
			add_child(avatar)
			_avatars[id] = avatar
		_avatars[id].position = _positions[id] + Vector3.UP * 0.9

func status() -> Dictionary:
	return {"mode": _mode, "connected": _positions.has(_local_id), "peer_id": _local_id,
		"port": _port, "local_position": _positions.get(_local_id, _spawn), "peers": _positions.duplicate(),
		"accepted_inputs": _accepted, "rejected_inputs": _rejected,
		"snapshots": _snapshot_sequence if _mode == "host" else _received_snapshots}

func stop() -> void:
	if _peer != null:
		_peer.close()
		_api.multiplayer_peer = null
	_peer = null
	_api = null
	_mode = "offline"
	_local_id = 0
	_port = 0
	_sequence = 0
	_snapshot_sequence = 0
	_received_snapshots = 0
	_until_send = 0.0
	_accepted = 0
	_rejected = 0
	_lost_connection = false
	_positions.clear()
	_directions.clear()
	_last_input.clear()
	_input_age.clear()
	_update_avatars()

func _exit_tree() -> void:
	stop()
