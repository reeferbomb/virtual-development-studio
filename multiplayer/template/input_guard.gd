extends RefCounted

const MAX_PEERS := 16
const MAX_COMMANDS := 40
const WINDOW_MS := 1000
const MAX_SEQUENCE := 2147483647

class PeerState:
	var sequence := -1
	var times: Array[int] = []

var accepted := 0
var rejected := 0
var _peers: Dictionary[int, PeerState] = {}

# The server supplies now_ms from its monotonic clock. Buttons are typed booleans.
func accept(peer: int, seq: int, movement: Vector2, yaw: float, _fire: bool, _reload: bool, now_ms: int) -> bool:
	if peer < 1 or seq < 0 or seq > MAX_SEQUENCE or now_ms < 0:
		return _reject()
	if not movement.is_finite() or movement.length() > 1.001:
		return _reject()
	if not is_finite(yaw) or absf(yaw) > TAU:
		return _reject()

	var state: PeerState = _peers.get(peer)
	if state == null:
		if _peers.size() >= MAX_PEERS:
			return _reject()
		state = PeerState.new()
		_peers[peer] = state
	if seq <= state.sequence or (not state.times.is_empty() and now_ms < state.times.back()):
		return _reject()
	while not state.times.is_empty() and now_ms - state.times.front() >= WINDOW_MS:
		state.times.pop_front()
	if state.times.size() >= MAX_COMMANDS:
		return _reject()

	state.sequence = seq
	state.times.append(now_ms)
	accepted += 1
	return true

func forget(peer: int) -> void:
	_peers.erase(peer)

func _reject() -> bool:
	rejected += 1
	return false
