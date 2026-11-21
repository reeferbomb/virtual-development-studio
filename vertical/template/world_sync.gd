extends "res://city_network.gd"

## Full snapshots use a separate ENet channel from player input and avatars.
const TrafficModel = preload("res://traffic.gd")
const CivilianModel = preload("res://civilians.gd")
const WORLD_PACKET := 3
const WORLD_VERSION := 1
const WORLD_CHANNEL := 1
const WORLD_PERIOD := 0.1
const WORLD_HEADER_BYTES := 73
const CAR_BYTES := 17
const MAX_COUNTER := 4503599627370495

var _world: Dictionary = {}
var _world_sequence := 0
var _world_received := 0
var _world_rejected := 0
var _world_bytes := PackedByteArray()
var _sent_world: Dictionary[int, int] = {}
var _world_send_in := 0.0
var _traffic_validator := Callable()
var _civilian_validator := Callable()


func set_world_validators(traffic_validator: Callable, civilian_validator: Callable) -> bool:
	if _mode != "offline" or not traffic_validator.is_valid() or not civilian_validator.is_valid():
		return false
	_traffic_validator = traffic_validator
	_civilian_validator = civilian_validator
	return true


func latest_world() -> Dictionary:
	return _world.duplicate(true)


func publish_world(state: Dictionary) -> bool:
	if _mode != "host" or _world_sequence >= MAX_COUNTER or not _valid_world(state):
		return false
	if not _world.is_empty() and state.tick <= _world.tick:
		return false
	_world = state.duplicate(true)
	_world_sequence += 1
	_world_bytes = _encode_world(_world, _world_sequence)
	return true


func _add_member(id: int) -> void:
	super._add_member(id)
	if _mode == "host" and id > 1:
		_sent_world[id] = 0
		_send_world(id)


func _remove_member(id: int) -> void:
	super._remove_member(id)
	_sent_world.erase(id)


func step(delta: float, input: Vector2) -> void:
	super.step(delta, input)
	if _mode != "host" or not is_finite(delta) or delta <= 0.0:
		return
	_world_send_in -= minf(delta, 0.1)
	if _world_send_in <= 0.0:
		_world_send_in = WORLD_PERIOD
		for id: int in _sent_world:
			_send_world(id)


func _send_world(id: int) -> void:
	if _world_sequence > _sent_world[id]:
		if _api.send_bytes(_world_bytes, id, MultiplayerPeer.TRANSFER_MODE_RELIABLE, WORLD_CHANNEL) == OK:
			_sent_world[id] = _world_sequence


func _receive(sender: int, packet: PackedByteArray) -> void:
	if packet.is_empty() or packet[0] != WORLD_PACKET:
		super._receive(sender, packet)
		return
	if _mode != "client" or sender != 1 or not _accept_world(packet):
		_world_rejected += 1


func _accept_world(packet: PackedByteArray) -> bool:
	if packet.size() < WORLD_HEADER_BYTES or packet[1] != WORLD_VERSION:
		return false
	var count := int(packet[72])
	if count > TrafficModel.MAX_CARS or packet.size() != WORLD_HEADER_BYTES + CAR_BYTES * count:
		return false
	var sequence := packet.decode_u64(2)
	var tick := packet.decode_u64(10)
	if sequence <= _world_sequence or sequence > MAX_COUNTER or tick < 0 or tick > MAX_COUNTER:
		return false
	if not _world.is_empty() and tick <= _world.tick:
		return false
	var seed_value := packet.decode_u32(18)
	var blocks := int(packet[22])
	var block_size := packet.decode_double(23)
	var cars := []
	for i in count:
		var offset := WORLD_HEADER_BYTES + CAR_BYTES * i
		if packet[offset + 16] > 1:
			return false
		cars.append({"id": i, "progress": packet.decode_double(offset),
				"speed": packet.decode_double(offset + 8), "waiting": packet[offset + 16] == 1})
	var next := {"tick": tick, "traffic": {
			"version": 1, "seed": str(seed_value), "blocks": blocks, "block_size": block_size,
			"tick": packet.decode_u64(31), "remainder": packet.decode_double(39),
			"distance_m": packet.decode_double(47), "signal_stops": packet.decode_u64(55),
			"cars": cars}, "civilians": {
			"version": 1, "seed": seed_value, "blocks": blocks, "block_size": block_size,
			"count": int(packet[63]), "clock": packet.decode_double(64)}}
	if not _valid_world(next):
		return false
	_world = next
	_world_sequence = sequence
	_world_received += 1
	return true


func _uint(value: Variant, maximum: int) -> bool:
	return value is int and value >= 0 and value <= maximum


func _finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _valid_world(state: Dictionary) -> bool:
	if state.size() != 3 or not state.has_all(["tick", "traffic", "civilians"]):
		return false
	if not _uint(state.tick, MAX_COUNTER) or not state.traffic is Dictionary or not state.civilians is Dictionary:
		return false
	var traffic: Dictionary = state.traffic
	var civilians: Dictionary = state.civilians
	if civilians.size() != 6 or not civilians.has_all(["version", "seed", "blocks", "block_size", "count", "clock"]):
		return false
	if not _uint(civilians.version, 1) or civilians.version != 1 or not _uint(civilians.seed, 2147483647) \
			or not _uint(civilians.blocks, 8) or civilians.blocks < 3 or not _uint(civilians.count, 40):
		return false
	if not _finite_number(civilians.block_size) or civilians.block_size < 32 or civilians.block_size > 64 \
			or not _finite_number(civilians.clock) or civilians.clock < 0 or civilians.clock >= CivilianModel.DAY_SECONDS:
		return false
	if traffic.size() != 9 or not traffic.has_all(["version", "seed", "blocks", "block_size", "tick",
			"remainder", "distance_m", "signal_stops", "cars"]):
		return false
	if not _uint(traffic.version, 1) or traffic.version != 1 or not traffic.seed is String \
			or traffic.seed != str(civilians.seed) or not _uint(traffic.blocks, 8) or traffic.blocks != civilians.blocks \
			or not _finite_number(traffic.block_size) or traffic.block_size != civilians.block_size:
		return false
	if not _uint(traffic.tick, MAX_COUNTER) or not _uint(traffic.signal_stops, MAX_COUNTER) \
			or not _finite_number(traffic.distance_m) or traffic.distance_m < 0 or traffic.distance_m > MAX_COUNTER \
			or not _finite_number(traffic.remainder) or traffic.remainder < 0 or traffic.remainder >= TrafficModel.TICK:
		return false
	if not traffic.cars is Array or traffic.cars.size() > TrafficModel.MAX_CARS:
		return false
	var loop_length := 4.0 * (float(traffic.block_size) - 2.0 * (TrafficModel.LANE + TrafficModel.TURN_RADIUS)
			+ TrafficModel.TURN_RADIUS * PI * 0.5)
	for i: int in traffic.cars.size():
		var car: Variant = traffic.cars[i]
		if not car is Dictionary or car.size() != 4 or not car.has_all(["id", "progress", "speed", "waiting"]):
			return false
		if not _uint(car.id, TrafficModel.MAX_CARS) or car.id != i or not car.waiting is bool \
				or not _finite_number(car.progress) or car.progress < 0 or car.progress >= loop_length \
				or not _finite_number(car.speed) or car.speed < 0 or car.speed > 8.500001:
			return false
	if not _traffic_validator.is_null():
		return _traffic_validator.is_valid() and _civilian_validator.is_valid() \
				and _traffic_validator.call(traffic) and _civilian_validator.call(civilians)
	return true


# The wire format only represents the bounded numeric fields above. Stable car
# IDs are implicit in array order. Seed, blocks and block size are shared by
# both simulations. Doubles preserve the exact values used by restore().
func _encode_world(state: Dictionary, sequence: int) -> PackedByteArray:
	var traffic: Dictionary = state.traffic
	var civilians: Dictionary = state.civilians
	var packet := PackedByteArray()
	packet.resize(WORLD_HEADER_BYTES + CAR_BYTES * traffic.cars.size())
	packet[0] = WORLD_PACKET
	packet[1] = WORLD_VERSION
	packet.encode_u64(2, sequence)
	packet.encode_u64(10, state.tick)
	packet.encode_u32(18, civilians.seed)
	packet[22] = civilians.blocks
	packet.encode_double(23, civilians.block_size)
	packet.encode_u64(31, traffic.tick)
	packet.encode_double(39, traffic.remainder)
	packet.encode_double(47, traffic.distance_m)
	packet.encode_u64(55, traffic.signal_stops)
	packet[63] = civilians.count
	packet.encode_double(64, civilians.clock)
	packet[72] = traffic.cars.size()
	for i: int in traffic.cars.size():
		var car: Dictionary = traffic.cars[i]
		var offset := WORLD_HEADER_BYTES + CAR_BYTES * i
		packet.encode_double(offset, car.progress)
		packet.encode_double(offset + 8, car.speed)
		packet[offset + 16] = int(car.waiting)
	return packet


func status() -> Dictionary:
	var result := super.status()
	result.merge({"world_tick": _world.get("tick", -1), "world_sequence": _world_sequence,
			"world_received": _world_received, "world_rejected": _world_rejected})
	return result


func stop() -> void:
	super.stop()
	_world = {}
	_world_bytes = PackedByteArray()
	_world_sequence = 0
	_world_received = 0
	_world_rejected = 0
	_sent_world.clear()
	_world_send_in = 0.0
