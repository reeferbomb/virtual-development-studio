extends Node3D

const LEVEL := -7.0
const DWELL := 7.0
const PLATFORM_HALF := 8.0
const PLATFORM_EDGE := 1.58
const PLATFORM_BACK := 7.1
const REACH := 1.65
const STATION_NAMES := ["West Exchange", "East Market"]
const WALL := Color("#324451")
const STEEL := Color("#829499")
const LIGHT := Color("#e4f7eb")
const AMBER := Color("#f1ac40")
const TEAL := Color("#147b77")

var _seed_value := 0
var _extent := 0.0
var _block := 0.0
var _line_z := 0.0
var _trip := 0.0
var _clock := 0.0
var _stations: Array[Dictionary] = []
var _train: Node3D
var _doors: Array[MeshInstance3D] = []
var _materials := {}
var _riding := false
var _rider: CharacterBody3D
var _resume_movement := true


func configure(seed_value: int, world_size: float, block_size: float) -> bool:
	if _train != null or not is_finite(world_size) or not is_finite(block_size):
		return false
	if block_size < 32.0 or block_size > 64.0 or world_size < 3.0 * block_size or world_size > 8.0 * block_size:
		return false
	var blocks := roundi(world_size / block_size)
	if not is_equal_approx(world_size, blocks * block_size):
		return false
	_seed_value = seed_value
	_extent = world_size
	_block = block_size
	_line_z = (1 + posmod(seed_value, blocks - 1)) * block_size
	_trip = maxf(6.0, (world_size - 2.0 * block_size) / 16.0)
	for i in 2:
		var x := block_size if i == 0 else world_size - block_size
		_stations.append({"id": i, "name": STATION_NAMES[i],
			"entrance": Vector3(x - 4.5, 0.08, _line_z + 6.35),
			"portal": Vector3(x - 4.5, LEVEL + 0.04, _line_z + 5.75),
			"platform": Vector3(x, LEVEL + 0.04, _line_z + 2.52)})
	_build_tunnel()
	for i in 2:
		_build_station(i)
	_build_train()
	_update_train()
	return true


func _material(color: Color, glow: bool = false) -> StandardMaterial3D:
	var key := color.to_html() + ("+" if glow else "")
	if not _materials.has(key):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.78
		material.emission_enabled = glow
		if glow:
			material.emission = color
		_materials[key] = material
	return _materials[key]


func _box(parent: Node3D, label: String, at: Vector3, size: Vector3, color: Color, glow: bool = false) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = _material(color, glow)
	var part := MeshInstance3D.new()
	part.name = label
	part.mesh = mesh
	parent.add_child(part)
	part.position = at
	return part


func _collider(parent: Node3D, label: String, at: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	body.collision_mask = 0
	var shape := BoxShape3D.new()
	shape.size = size
	var hit := CollisionShape3D.new()
	hit.shape = shape
	body.add_child(hit)
	parent.add_child(body)
	body.position = at
	return body


func _solid(parent: Node3D, label: String, at: Vector3, size: Vector3, color: Color) -> void:
	var body := _collider(parent, label, at, size)
	_box(body, "Mesh", Vector3.ZERO, size, color)


func _sign(parent: Node3D, at: Vector3, words: String, tint := LIGHT) -> void:
	var label := Label3D.new()
	label.text = words
	label.modulate = tint
	label.font_size = 64
	label.pixel_size = 0.007
	label.outline_size = 8
	label.double_sided = true
	label.shaded = false
	parent.add_child(label)
	label.position = at


func _build_tunnel() -> void:
	var tunnel := Node3D.new()
	tunnel.name = "Tunnel"
	add_child(tunnel)
	tunnel.position = Vector3(_extent * 0.5, LEVEL, _line_z)
	var length := _extent - 2.0 * _block + 2.0 * (PLATFORM_HALF + 1.0)
	_box(tunnel, "TrackBed", Vector3(0, -1.28, 0), Vector3(length, 0.35, 5.2), Color("#343c42"))
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		_box(tunnel, "Rail%d" % i, Vector3(0, -0.89, side * 0.80), Vector3(length, 0.16, 0.13), STEEL)
		_box(tunnel, "Buffer%d" % i, Vector3(side * (length * 0.5 - 0.15), 0.98, 0), Vector3(0.30, 4.5, 5.2), WALL)
	var count := floori(length / 1.15)
	var sleepers := MultiMesh.new()
	sleepers.transform_format = MultiMesh.TRANSFORM_3D
	var sleeper_mesh := BoxMesh.new()
	sleeper_mesh.size = Vector3(0.24, 0.16, 2.4)
	sleeper_mesh.material = _material(Color("#5b5550"))
	sleepers.mesh = sleeper_mesh
	sleepers.instance_count = count
	for i in count:
		sleepers.set_instance_transform(i, Transform3D(Basis.IDENTITY, Vector3(-length * 0.5 + (i + 0.5) * length / count, -1.04, 0)))
	var ties := MultiMeshInstance3D.new()
	ties.name = "Sleepers"
	ties.multimesh = sleepers
	tunnel.add_child(ties)
	_box(tunnel, "NorthWall", Vector3(0, 1.0, -2.7), Vector3(length, 4.6, 0.3), WALL)
	_box(tunnel, "Ceiling", Vector3(0, 3.24, 0), Vector3(length, 0.22, 5.5), WALL)
	var enclosed := _extent - 2.0 * _block - 2.0 * PLATFORM_HALF
	_box(tunnel, "SouthWall", Vector3(0, 1.0, 2.7), Vector3(enclosed, 4.6, 0.3), WALL)
	for i in ceili(length / 9.0):
		var x := -length * 0.5 + (i + 0.5) * length / ceili(length / 9.0)
		_box(tunnel, "TunnelLamp%d" % i, Vector3(x, 1.9, -2.51), Vector3(1.25, 0.13, 0.10), LIGHT, true)


func _build_station(index: int) -> void:
	var station := Node3D.new()
	station.name = "Station%d" % index
	add_child(station)
	var where: Vector3 = _stations[index].platform
	station.position = Vector3(where.x, LEVEL, _line_z)
	var width := PLATFORM_BACK - PLATFORM_EDGE
	var mid := (PLATFORM_EDGE + PLATFORM_BACK) * 0.5
	var span := PLATFORM_HALF * 2.0
	_solid(station, "Platform", Vector3(0, -0.5, mid), Vector3(span, 1.0, width), Color("#99a5a3"))
	_solid(station, "BackWall", Vector3(0, 1.5, PLATFORM_BACK + 0.1), Vector3(span, 3.4, 0.2), WALL)
	_solid(station, "Canopy", Vector3(0, 3.24, mid), Vector3(span, 0.22, width), WALL)
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		_solid(station, "EndWall%d" % i, Vector3(side * PLATFORM_HALF, 1.5, mid), Vector3(0.2, 3.4, width), WALL)
	_box(station, "EdgeStripe", Vector3(0, 0.012, PLATFORM_EDGE + 0.28), Vector3(span, 0.024, 0.32), AMBER)
	# The glass-free platform guard leaves a sightline into the carriage. Its
	# collision spans the central gate, where interact() authorizes boarding.
	_collider(station, "PlatformGuard", Vector3(0, 1.5, PLATFORM_EDGE), Vector3(span, 3.4, 0.10))
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		_box(station, "Rail%d" % i, Vector3(side * 4.55, 1.0, PLATFORM_EDGE + 0.06), Vector3(6.7, 0.10, 0.09), STEEL)
		for j in 2:
			_box(station, "Post%d%d" % [i,j], Vector3(side * (1.23 + j * 6.5), 0.5, PLATFORM_EDGE + 0.06), Vector3(0.11, 1.0, 0.11), TEAL)
	_box(station, "BackStripe", Vector3(0, 1.8, PLATFORM_BACK - 0.06), Vector3(span, 0.53, 0.12), TEAL)
	_sign(station, Vector3(1, 1.81, PLATFORM_BACK - 0.15), STATION_NAMES[index].to_upper())
	_sign(station, Vector3(-4.5, 1.0, PLATFORM_BACK - 0.16), "LIFT  /  STREET", AMBER)
	_box(station, "LiftLanding", Vector3(-4.5, 0.017, 5.75), Vector3(2.6, 0.034, 1.8), Color("#567b79"))
	_box(station, "StripLight", Vector3(0, 3.07, 4.1), Vector3(13.8, 0.09, 0.32), LIGHT, true)
	var lift := Node3D.new()
	lift.name = "StreetLift"
	station.add_child(lift)
	lift.position = Vector3(-4.5, -LEVEL, 6.35)
	_box(lift, "Mat", Vector3(0, 0.06, 0), Vector3(2.3, 0.075, 1.7), TEAL)
	for i in 2:
		_box(lift, "Pillar%d" % i, Vector3(-1.13 + i * 2.26, 1.4, 0.67), Vector3(0.14, 2.8, 0.14), TEAL)
	_box(lift, "Marquee", Vector3(0, 2.8, 0), Vector3(3.2, 0.66, 1.7), TEAL)
	_sign(lift, Vector3(0, 2.8, 0.86), "M  /  METRO")
	_sign(lift, Vector3(0, 2.8, -0.86), "M  /  METRO")


func _build_train() -> void:
	_train = Node3D.new()
	_train.name = "Train"
	add_child(_train)
	_box(_train, "Floor", Vector3(0, -0.18, 0), Vector3(9.6, 0.36, 2.73), Color("#66726f"))
	_box(_train, "Roof", Vector3(0, 2.48, 0), Vector3(9.6, 0.18, 2.78), STEEL)
	_box(_train, "FarSill", Vector3(0, 0.42, -1.31), Vector3(9.5, 0.84, 0.14), TEAL)
	_box(_train, "FarLintel", Vector3(0, 2.17, -1.31), Vector3(9.5, 0.49, 0.14), Color("#e4e3d8"))
	for i in 5:
		_box(_train, "WindowPillar%d" % i, Vector3(-4.66 + i * 2.33, 1.38, -1.31), Vector3(0.16, 1.13, 0.14), STEEL)
	for i in 2:
		var side := -1.0 if i == 0 else 1.0
		_box(_train, "EndPanel%d" % i, Vector3(side * 4.73, 0.56, 0), Vector3(0.16, 1.16, 2.72), TEAL)
		_box(_train, "NearSill%d" % i, Vector3(side * 2.92, 0.45, 1.31), Vector3(3.64, 0.90, 0.14), TEAL)
		_box(_train, "NearLintel%d" % i, Vector3(side * 2.92, 2.14, 1.31), Vector3(3.64, 0.56, 0.14), Color("#e4e3d8"))
		_box(_train, "Bogie%d" % i, Vector3(side * 2.95, -0.60, 0), Vector3(1.5, 0.42, 1.83), WALL)
		_box(_train, "Seat%d" % i, Vector3(side * 2.65, 0.38, -0.88), Vector3(2.7, 0.35, 0.61), Color("#cf8640"))
		var door := _box(_train, "Door%d" % i, Vector3(0, 1.12, 1.39), Vector3(1.1, 2.24, 0.08), Color("#e2b444"))
		_box(door, "Window", Vector3(0, 0.36, 0.055), Vector3(0.73, 0.78, 0.035), Color("#34545b"))
		_doors.append(door)
	_box(_train, "CabinLight", Vector3(0, 2.35, 0.15), Vector3(8.2, 0.09, 0.17), LIGHT, true)


func _half_trip() -> float:
	return DWELL + _trip


func _origin(at: float) -> int:
	return 0 if at < _half_trip() else 1


func _at_station(at: float) -> int:
	return _origin(at) if fmod(at, _half_trip()) < DWELL else -1


func _train_at(at: float) -> Vector3:
	var t := clampf((fmod(at, _half_trip()) - DWELL) / _trip, 0.0, 1.0)
	# Ease off the platform and brake into the opposite stop.
	t = t * t * (3.0 - 2.0 * t)
	if _origin(at) == 1:
		t = 1.0 - t
	return Vector3(lerpf(_block, _extent - _block, t), LEVEL, _line_z)


func _update_train() -> void:
	_train.position = _train_at(_clock)
	var spread := 1.59 if _at_station(_clock) >= 0 else 0.55
	_doors[0].position.x = -spread
	_doors[1].position.x = spread


func _carry(player: CharacterBody3D) -> void:
	if not is_instance_valid(player):
		return
	if _rider == null:
		_rider = player
		_resume_movement = player.is_physics_processing()
	if player != _rider:
		return
	player.set_physics_process(false)
	player.velocity = Vector3.ZERO
	player.global_position = to_global(_train.position + Vector3.UP * 0.04)


func _release_rider() -> void:
	if is_instance_valid(_rider):
		_rider.set_physics_process(_resume_movement)
	_rider = null
	_riding = false


func step(delta: float, player: CharacterBody3D = null) -> void:
	if _train == null or not is_finite(delta) or delta < 0.0:
		return
	var period := 2.0 * _half_trip()
	_clock = fposmod(_clock + fmod(delta, period), period)
	_update_train()
	if _riding:
		_carry(player if player != null else _rider)


func _action_at(player: CharacterBody3D) -> Dictionary:
	if _train == null or not is_instance_valid(player):
		return {}
	var stop := _at_station(_clock)
	if _riding:
		if stop >= 0 and (_rider == null or _rider == player):
			return {"action": "disembark", "station": stop}
		return {}
	var here := to_local(player.global_position)
	for row in _stations:
		if here.distance_to(row.entrance) <= REACH:
			return {"action": "descend", "station": row.id}
		if here.distance_to(row.portal) <= REACH:
			return {"action": "ascend", "station": row.id}
		if stop == row.id and here.z >= _line_z + PLATFORM_EDGE and here.distance_to(row.platform) <= REACH:
			return {"action": "board", "station": row.id}
	return {}


func interaction_hint(player: CharacterBody3D) -> String:
	var action := _action_at(player)
	if action.is_empty():
		return ""
	var row: Dictionary = _stations[action.station]
	match action.action:
		"ascend": return "Take lift to street"
		"descend": return "Take lift to " + str(row.name)
		"board": return "Board train to " + str(_stations[1 - int(row.id)].name)
	return "Leave train at " + str(row.name)


func interact(player: CharacterBody3D) -> bool:
	var action := _action_at(player)
	if action.is_empty():
		return false
	var row: Dictionary = _stations[action.station]
	player.velocity = Vector3.ZERO
	match action.action:
		"ascend": player.global_position = to_global(row.entrance)
		"descend": player.global_position = to_global(row.portal)
		"board":
			_riding = true
			_carry(player)
		"disembark":
			_release_rider()
			player.global_position = to_global(row.platform)
	return true


func status() -> Dictionary:
	if _train == null:
		return {"stations": [], "phase": "unconfigured", "riding": false, "doors_open": false, "station": -1}
	var stop := _at_station(_clock)
	return {"stations": _stations.duplicate(true), "phase": "dwell" if stop >= 0 else "travel",
		"station": stop, "next_station": 1 - _origin(_clock), "doors_open": stop >= 0, "riding": _riding,
		"seconds_remaining": (DWELL if stop >= 0 else _half_trip()) - fmod(_clock, _half_trip()),
		"train_position": _train.position}


func snapshot() -> Dictionary:
	return {"version": 1, "seed": _seed_value, "world_size": _extent, "block_size": _block,
		"clock": _clock, "riding": _riding}


func valid_snapshot(data: Variant) -> bool:
	if _train == null or not data is Dictionary or data.size() != 6:
		return false
	var identity := {"version": 1, "seed": _seed_value, "world_size": _extent, "block_size": _block}
	for field in identity:
		var value: Variant = data.get(field)
		if not (value is int or value is float) or value != identity[field]:
			return false
	var at: Variant = data.get("clock")
	return (at is int or at is float) and is_finite(at) and at >= 0 and at < 2.0 * _half_trip() and data.get("riding") is bool


func valid_player_position(world_position: Vector3, state: Dictionary) -> bool:
	if not valid_snapshot(state) or not world_position.is_finite():
		return false
	var here := to_local(world_position)
	if state.riding:
		return here.distance_to(_train_at(state.clock) + Vector3.UP * 0.04) <= 0.15
	for row in _stations:
		var platform: Vector3 = row.platform
		if absf(here.x - platform.x) <= PLATFORM_HALF and here.z > _line_z + PLATFORM_EDGE and here.z < _line_z + PLATFORM_BACK and here.y >= LEVEL - 0.10 and here.y <= LEVEL + 1.8:
			return true
	return false


func restore(data: Variant, player: CharacterBody3D = null) -> bool:
	if not valid_snapshot(data):
		return false
	var passenger := player if player != null else _rider
	_release_rider()
	_clock = data.clock
	_riding = data.riding
	_update_train()
	if _riding:
		_carry(passenger)
	return true
