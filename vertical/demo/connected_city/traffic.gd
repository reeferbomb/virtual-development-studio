extends Node3D

const MAX_CARS := 24
const TICK := 0.05
const LANE := 2.7
const TURN_RADIUS := 1.8
const STOP_FROM_NODE := 8.2
const MIN_GAP := 6.8
const ACCELERATION := 3.0
const BRAKING := 6.0
const GREEN_TICKS := 120
const CLEARANCE_TICKS := 20
const CYCLE := 2 * (GREEN_TICKS + CLEARANCE_TICKS)
const PALETTE := [Color("#f6ac3d"), Color("#2579a3"), Color("#d55a41"),
		Color("#6eac9b"), Color("#e5e4d7"), Color("#8a65a6")]

var _configured := false
var _seed_value := 0
var _blocks := 0
var _size := 0.0
var _straight := 0.0
var _quarter := 0.0
var _tick_index := 0
var _remainder := 0.0
var _distance := 0.0
var _stops := 0
var _cars: Array[Dictionary] = []
var _signals: Array[Dictionary] = []
var _route_members: Array = []
var _lights: Array[StandardMaterial3D] = []


func configure(seed_value: int, blocks: int, block_size: float, count: int) -> bool:
	if _configured or blocks < 3 or blocks > 8 or not is_finite(block_size) \
			or block_size < 32.0 or block_size > 64.0 or count < 0 or count > MAX_CARS:
		return false
	_seed_value = seed_value
	_blocks = blocks
	_size = block_size
	_straight = _size - 2.0 * (LANE + TURN_RADIUS)
	_quarter = _straight + TURN_RADIUS * PI * 0.5
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	var routes: Array[int] = []
	for route in blocks * blocks:
		routes.append(route)
		_route_members.append([])
	for i in range(routes.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var previous := routes[i]
		routes[i] = routes[j]
		routes[j] = previous
	for i in count:
		var route := routes[i % routes.size()]
		_route_members[route].append(i)
		var model := _build_car(i, PALETTE[rng.randi_range(0, PALETTE.size() - 1)])
		_cars.append({"id": i, "route": route, "progress": 0.0, "speed": 0.0,
				"cruise": rng.randf_range(5.5, 8.5), "waiting": false, "model": model})
	for route in routes:
		var members: Array = _route_members[route]
		var start := rng.randf_range(0.0, _quarter * 4.0)
		for i in members.size():
			var car: Dictionary = _cars[members[i]]
			car.progress = fposmod(start + i * _quarter * 4.0 / members.size(), _quarter * 4.0)
	_lights.append(_material(Color("#ee463c"), true))
	_lights.append(_material(Color("#49d975"), true))
	var pole_mesh := _box(Vector3(0.22, 3.2, 0.22), _material(Color("#414c55")))
	var lamp_mesh := _box(Vector3(0.55, 0.42, 0.25), null)
	for z in _blocks + 1:
		for x in _blocks + 1:
			var center := Vector3(x * _size, 0.0, z * _size)
			var pole := _part(self, pole_mesh, center + Vector3(5.3, 1.6, 5.3))
			pole.name = "Signal_%d_%d" % [x, z]
			var ns := _part(pole, lamp_mesh, Vector3(0, 1.33, -0.19))
			var ew := _part(pole, lamp_mesh, Vector3(-0.19, 1.33, 0))
			ew.rotation.y = PI * 0.5
			_signals.append({"id": "n%d_%d" % [x, z], "center": center,
					"offset": rng.randi_range(0, CYCLE - 1), "phase": "", "ns": ns, "ew": ew})
	_configured = true
	_update_models()
	_update_lights()
	return true


func _material(color: Color, glow := false) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.75
	if glow:
		mat.emission_enabled = true
		mat.emission = color
	return mat


func _box(size_value: Vector3, mat: Material) -> BoxMesh:
	var mesh := BoxMesh.new()
	mesh.size = size_value
	mesh.material = mat
	return mesh


func _part(parent: Node3D, mesh: Mesh, offset: Vector3) -> MeshInstance3D:
	var part := MeshInstance3D.new()
	part.mesh = mesh
	part.position = offset
	parent.add_child(part)
	return part


func _build_car(id: int, color: Color) -> Node3D:
	var model := Node3D.new()
	model.name = "Car_%d" % id
	add_child(model)
	_part(model, _box(Vector3(1.74, 0.66, 3.65), _material(color)), Vector3(0, 0.57, 0))
	_part(model, _box(Vector3(1.46, 0.62, 1.92), _material(Color("#384d61"))), Vector3(0, 1.19, 0.12))
	var tire := _box(Vector3(0.24, 0.47, 0.66), _material(Color("#262931")))
	for x in [-0.85, 0.85]:
		for z in [-1.04, 1.04]:
			_part(model, tire, Vector3(x, 0.235, z))
	var lamp := _box(Vector3(0.39, 0.18, 0.06), _material(Color("#ffe8b1"), true))
	for x in [-0.54, 0.54]:
		_part(model, lamp, Vector3(x, 0.64, -1.83))
	return model


func _phase(signal_data: Dictionary) -> String:
	var stage: int = (_tick_index + int(signal_data.offset)) % CYCLE
	if stage < GREEN_TICKS:
		return "east_west"
	if stage >= GREEN_TICKS + CLEARANCE_TICKS and stage < CYCLE - CLEARANCE_TICKS:
		return "north_south"
	return "all_red"


func _update_lights() -> void:
	for signal_data in _signals:
		var phase := _phase(signal_data)
		if signal_data.phase != phase:
			signal_data.phase = phase
			signal_data.ns.material_override = _lights[int(phase == "north_south")]
			signal_data.ew.material_override = _lights[int(phase == "east_west")]


func _signal_index(route: int, side: int) -> int:
	var x := route % _blocks
	var z := floori(float(route) / _blocks)
	if side == 0 or side == 1:
		x += 1
	if side == 1 or side == 2:
		z += 1
	return z * (_blocks + 1) + x


func _free_distance(car: Dictionary) -> float:
	var available := _quarter * 4.0
	for id in _route_members[car.route]:
		if id != car.id:
			var gap := fposmod(float(_cars[id].progress) - float(car.progress), _quarter * 4.0)
			available = minf(available, maxf(0.0, gap - MIN_GAP))
	return available


func _advance_tick() -> void:
	# Plan every advance from the same positions, including across the loop seam.
	var advances := PackedFloat64Array()
	for car in _cars:
		var progress := float(car.progress)
		var side := mini(3, floori(progress / _quarter))
		var segment_distance := progress - side * _quarter
		var stop_distance := _straight - (STOP_FROM_NODE - LANE - TURN_RADIUS) - segment_distance
		var phase: String = _signals[_signal_index(car.route, side)].phase
		var allowed_phase := "east_west" if side % 2 == 0 else "north_south"
		var red := phase != allowed_phase and stop_distance >= -0.000001
		var available := _free_distance(car)
		if red:
			available = minf(available, maxf(0.0, stop_distance))
		var target := minf(float(car.cruise), sqrt(2.0 * BRAKING * available))
		var speed := move_toward(float(car.speed), target,
				(ACCELERATION if target >= float(car.speed) else BRAKING) * TICK)
		var advance := minf(speed * TICK, available)
		car.speed = advance / TICK
		var waiting := red and stop_distance <= 0.01 and float(car.speed) < 0.05
		if waiting and not car.waiting:
			_stops += 1
		car.waiting = waiting
		advances.append(advance)
	for i in _cars.size():
		var car := _cars[i]
		car.progress = fposmod(float(car.progress) + advances[i], _quarter * 4.0)
		_distance += advances[i]
	_tick_index += 1
	_update_lights()


func step(delta: float) -> void:
	if not _configured or not is_finite(delta) or delta <= 0.0 or delta > 300.0:
		return
	_remainder += delta
	var ticks := floori((_remainder + 0.000000001) / TICK)
	_remainder = maxf(0.0, _remainder - ticks * TICK)
	for i in ticks:
		_advance_tick()
	if ticks > 0:
		_update_models()


func _update_models() -> void:
	for car in _cars:
		var progress := float(car.progress)
		var side := mini(3, floori(progress / _quarter))
		var segment_distance := progress - side * _quarter
		var angle := side * PI * 0.5
		var local := Vector2(LANE + TURN_RADIUS + segment_distance, LANE)
		var turn := 0.0
		if segment_distance > _straight:
			turn = (segment_distance - _straight) / TURN_RADIUS
			var pivot := Vector2(_size - LANE - TURN_RADIUS, LANE + TURN_RADIUS)
			local = pivot + Vector2(0.0, -TURN_RADIUS).rotated(turn)
		var middle := Vector2.ONE * _size * 0.5
		local = middle + (local - middle).rotated(angle)
		var origin := Vector2(int(car.route) % _blocks, floori(float(car.route) / _blocks)) * _size
		var pos := origin + local
		car.model.position = Vector3(pos.x, 0.12, pos.y)
		car.model.rotation.y = -PI * 0.5 - angle - turn


func status() -> Dictionary:
	var cars: Array = []
	var signals: Array = []
	var stopped := 0
	for car in _cars:
		var p: Vector3 = car.model.position
		cars.append({"id": car.id, "position": [p.x, p.y, p.z], "speed": car.speed,
				"route": car.route, "waiting_at_signal": car.waiting})
		if float(car.speed) <= 0.05:
			stopped += 1
	for signal_data in _signals:
		var p: Vector3 = signal_data.center
		signals.append({"id": signal_data.id, "position": [p.x, p.y, p.z], "phase": signal_data.phase})
	return {"cars": cars, "signals": signals, "metrics": {"car_count": cars.size(),
			"signal_count": signals.size(), "stopped_count": stopped,
			"distance_m": _distance, "signal_stops": _stops}}


func snapshot() -> Dictionary:
	if not _configured:
		return {}
	var cars: Array = []
	for car in _cars:
		cars.append({"id": car.id, "progress": car.progress, "speed": car.speed, "waiting": car.waiting})
	return {"version": 1, "seed": str(_seed_value), "blocks": _blocks, "block_size": _size,
			"tick": _tick_index, "remainder": _remainder, "distance_m": _distance,
			"signal_stops": _stops, "cars": cars}


func _number(value: Variant) -> bool:
	return (typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT) and is_finite(float(value))


func _integer(value: Variant, maximum: int) -> bool:
	return _number(value) and float(value) >= 0 and float(value) <= maximum and floorf(float(value)) == float(value)


func valid_snapshot(state: Variant) -> bool:
	if not _configured or not state is Dictionary or state.size() != 9 or not state.has_all([
			"version", "seed", "blocks", "block_size", "tick", "remainder", "distance_m", "signal_stops", "cars"]):
		return false
	if not _integer(state.version, 1) or state.version != 1 or typeof(state.seed) != TYPE_STRING \
			or state.seed != str(_seed_value) or not _integer(state.blocks, 8) or state.blocks != _blocks \
			or not _number(state.block_size) or state.block_size != _size:
		return false
	if not _integer(state.tick, 4503599627370495) or not _integer(state.signal_stops, 4503599627370495) \
			or not _number(state.remainder) or state.remainder < 0.0 or state.remainder >= TICK \
			or not _number(state.distance_m) or state.distance_m < 0.0 \
			or not state.cars is Array or state.cars.size() != _cars.size():
		return false
	for i in _cars.size():
		var item: Variant = state.cars[i]
		if not item is Dictionary or item.size() != 4 or not item.has_all(["id", "progress", "speed", "waiting"]):
			return false
		if not _integer(item.id, MAX_CARS) or item.id != i or typeof(item.waiting) != TYPE_BOOL \
				or not _number(item.progress) or item.progress < 0 or item.progress >= _quarter * 4 \
				or not _number(item.speed) or item.speed < 0 or item.speed > float(_cars[i].cruise) + 0.000001:
			return false
	for members in _route_members:
		for i in members.size():
			for j in range(i):
				var gap := absf(float(state.cars[members[i]].progress) - float(state.cars[members[j]].progress))
				if minf(gap, _quarter * 4.0 - gap) + 0.000001 < MIN_GAP:
					return false
	return true


func restore(state: Variant) -> bool:
	if not valid_snapshot(state):
		return false
	_tick_index = int(state.tick)
	_remainder = float(state.remainder)
	_distance = float(state.distance_m)
	_stops = int(state.signal_stops)
	for i in _cars.size():
		_cars[i].progress = float(state.cars[i].progress)
		_cars[i].speed = float(state.cars[i].speed)
		_cars[i].waiting = state.cars[i].waiting
	_update_models()
	_update_lights()
	return true
