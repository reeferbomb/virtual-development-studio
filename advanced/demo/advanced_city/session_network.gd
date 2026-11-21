extends "res://world_sync.gd"

## Shared one-shot objectives. Only the host can change completion flags.
## Channel 2 carries fixed-size, reliable packets independently of the city.
const CLAIM_PACKET := 4
const SESSION_PACKET := 5
const SESSION_VERSION := 1
const SESSION_CHANNEL := 2
const MAX_OBJECTIVES := 16
const CLAIM_RADIUS := 2.5
const CLAIM_BYTES := 35
const SESSION_BYTES := 38

var _objectives: Array[Vector3] = []
var _layout_hash := PackedByteArray()
var _claimed_mask := 0
var _replica_mask := 0
var _session_received := 0
var _session_rejected := 0
var _host_objectives_active := false
var _sent_session: Dictionary[int, int] = {}


func configure_objectives(points: Array[Vector3]) -> bool:
	if _mode != "offline" or points.is_empty() or points.size() > MAX_OBJECTIVES:
		return false
	var coordinates := PackedByteArray()
	coordinates.resize(24 * points.size())
	for i in points.size():
		var point := points[i]
		if not point.is_finite():
			return false
		coordinates.encode_double(24 * i, point.x)
		coordinates.encode_double(24 * i + 8, point.y)
		coordinates.encode_double(24 * i + 16, point.z)
	# Repeating setup for the same city preserves its offline checkpoint.
	if points != _objectives:
		_objectives = points.duplicate()
		_layout_hash = coordinates.hex_encode().sha256_buffer()
		_claimed_mask = 0
	return true


func request_objective(index: int) -> bool:
	if index < 0 or index >= _objectives.size():
		return false
	if _mode == "host":
		return _claim(1, index)
	if _mode != "client" or _session_received == 0 or (_replica_mask & (1 << index)) != 0:
		return false
	var packet := PackedByteArray([CLAIM_PACKET, SESSION_VERSION, index])
	packet.append_array(_layout_hash)
	return _api.send_bytes(packet, 1, MultiplayerPeer.TRANSFER_MODE_RELIABLE, SESSION_CHANNEL) == OK


func _claim(sender: int, index: int) -> bool:
	if not _positions.has(sender) or index < 0 or index >= _objectives.size():
		return false
	if (_claimed_mask & (1 << index)) != 0:
		return false
	if _positions[sender].distance_squared_to(_objectives[index]) > CLAIM_RADIUS * CLAIM_RADIUS:
		return false
	_claimed_mask |= 1 << index
	_host_objectives_active = true
	return true


func _count_flags(mask: int) -> int:
	var count := 0
	for i in _objectives.size():
		count += (mask >> i) & 1
	return count


func session_snapshot() -> Dictionary:
	if _objectives.is_empty() or (_mode == "client" and _session_received == 0):
		return {}
	var mask := _replica_mask if _mode == "client" else _claimed_mask
	var flags: Array[bool] = []
	for i in _objectives.size():
		flags.append((mask & (1 << i)) != 0)
	return {"version": SESSION_VERSION, "revision": _count_flags(mask), "claimed": flags}


func valid_session_snapshot(state: Variant) -> bool:
	if _objectives.is_empty() or not state is Dictionary or state.size() != 3:
		return false
	if not state.has_all(["version", "revision", "claimed"]):
		return false
	if not _finite_number(state.version) or state.version != SESSION_VERSION:
		return false
	if not state.claimed is Array or state.claimed.size() != _objectives.size():
		return false
	var completed := 0
	for flag: Variant in state.claimed:
		if not flag is bool:
			return false
		completed += int(flag)
	# Godot's JSON parser represents integral checkpoint numbers as floats.
	return _finite_number(state.revision) and state.revision == completed


func restore_session(state: Variant) -> bool:
	if _mode == "client" or _host_objectives_active or not valid_session_snapshot(state):
		return false
	var mask := 0
	for i in _objectives.size():
		if state.claimed[i]:
			mask |= 1 << i
	_claimed_mask = mask
	return true


func _add_member(id: int) -> void:
	super._add_member(id)
	if _mode == "host" and id > 1 and not _objectives.is_empty():
		_host_objectives_active = true
		_sent_session[id] = -1
		_send_session(id)


func _remove_member(id: int) -> void:
	super._remove_member(id)
	_sent_session.erase(id)


func step(delta: float, input: Vector2) -> void:
	super.step(delta, input)
	if _mode == "host" and is_finite(delta) and delta > 0.0:
		for id: int in _sent_session:
			_send_session(id)


func _send_session(id: int) -> void:
	if _sent_session[id] == _claimed_mask:
		return
	var packet := PackedByteArray([SESSION_PACKET, SESSION_VERSION, _objectives.size(),
			_count_flags(_claimed_mask), 0, 0])
	packet.encode_u16(4, _claimed_mask)
	packet.append_array(_layout_hash)
	if _api.send_bytes(packet, id, MultiplayerPeer.TRANSFER_MODE_RELIABLE, SESSION_CHANNEL) == OK:
		_sent_session[id] = _claimed_mask


func _receive(sender: int, packet: PackedByteArray) -> void:
	if packet.is_empty() or (packet[0] != CLAIM_PACKET and packet[0] != SESSION_PACKET):
		super._receive(sender, packet)
		return
	if packet[0] == CLAIM_PACKET:
		if _mode == "host" and sender > 1 and packet.size() == CLAIM_BYTES \
				and packet[1] == SESSION_VERSION and packet.slice(3) == _layout_hash \
				and _claim(sender, int(packet[2])):
			return
	elif _mode == "client" and sender == 1 and _accept_session(packet):
		return
	_session_rejected += 1


func _accept_session(packet: PackedByteArray) -> bool:
	if packet.size() != SESSION_BYTES or packet[1] != SESSION_VERSION or _objectives.is_empty():
		return false
	if packet[2] != _objectives.size() or packet.slice(6) != _layout_hash:
		return false
	var mask := packet.decode_u16(4)
	if mask >= (1 << _objectives.size()) or int(packet[3]) != _count_flags(mask):
		return false
	# Each publication must add work without undoing any previous claim.
	if _session_received > 0 and (mask == _replica_mask or (_replica_mask & mask) != _replica_mask):
		return false
	_replica_mask = mask
	_session_received += 1
	return true


func status() -> Dictionary:
	var state := super.status()
	var ready := not _objectives.is_empty() and (_mode != "client" or _session_received > 0)
	var mask := _replica_mask if _mode == "client" else _claimed_mask
	state.merge({"session_ready": ready, "session_revision": _count_flags(mask) if ready else -1,
			"session_received": _session_received, "session_rejected": _session_rejected})
	return state


func stop() -> void:
	super.stop()
	_sent_session.clear()
	_replica_mask = 0
	_session_received = 0
	_session_rejected = 0
	_host_objectives_active = false
