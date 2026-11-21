extends Node3D

const FLOORS := 3
const STOREY := 3.0
const SPEED := 1.5
const WALL := 0.20
const SLAB := 0.16
const HALF_SHAFT := 1.45
const SHAFT_DEPTH := 3.0
const DOOR_WIDTH := 2.10
const RADIUS := 0.35
const FLOOR_NAMES := ["Lobby", "Design studio", "Observation lounge"]
const ACCENTS := [Color("#70b3ad"), Color("#dba06f"), Color("#9aa9dc")]
const STONE := Color("#586874")
const METAL := Color("#354d60")
const LIFT := Color("#bccad0")
const TIMBER := Color("#967458")

var _shell: Node3D
var _car: AnimatableBody3D
var _car_gate: CollisionShape3D
var _street_gate: StaticBody3D
var _gates: Array[StaticBody3D] = []
var _materials := {}
var _fixtures: Array[AABB] = []
var _seed := 0
var _id := ""
var _layout := ""
var _size := Vector3.ZERO
var _shaft_front := 0.0
var _car_z := 0.0
var _street_open := false
var _floor := 0
var _target := 0
var _height := 0.0
var _trips := 0
var _rider: CharacterBody3D
var _resume_physics := false
var _offset := Vector2.ZERO


func _number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


func _triple(value: Variant) -> bool:
	return value is Array and value.size() == 3 and _number(value[0]) and _number(value[1]) and _number(value[2])


func configure(city_seed: int, building: Dictionary) -> bool:
	if city_seed < 0 or city_seed > 2147483647:
		return false
	for key in ["id", "district", "style"]:
		if not building.get(key) is String or building[key].strip_edges().is_empty():
			return false
	if not _triple(building.get("size")) or not _triple(building.get("center")):
		return false
	var dimensions := Vector3(building.size[0], building.size[1], building.size[2])
	var center := Vector3(building.center[0], building.center[1], building.center[2])
	if not dimensions.is_finite() or not center.is_finite():
		return false
	if dimensions.x < 9 or dimensions.z < 9 or dimensions.y < FLOORS * STOREY or dimensions[dimensions.max_axis_index()] > 128:
		return false
	_release()
	if is_instance_valid(_shell):
		_shell.free()
	_fixtures.clear()
	_gates.clear()
	_seed = city_seed
	_id = building.id
	_layout = JSON.stringify([center.x, center.y, center.z, dimensions.x, dimensions.y, dimensions.z, building.district, building.style])
	_size = dimensions
	_shaft_front = _size.z * 0.5 - WALL - SHAFT_DEPTH
	_car_z = _shaft_front + SHAFT_DEPTH * 0.5
	_floor = 0
	_target = 0
	_height = 0.0
	_trips = 0
	_street_open = false
	_shell = Node3D.new()
	_shell.name = "TowerShell"
	_shell.position = center
	add_child(_shell)
	var rng := RandomNumberGenerator.new()
	rng.seed = _seed ^ _id.hash()
	var fixture_side := 1.0 if rng.randi_range(0, 1) else -1.0
	_build_exterior()
	for level in FLOORS:
		_build_floor(level, fixture_side)
	_build_car()
	_update_gates()
	return true


func _surface(parent: Node3D, label: String, at: Vector3, size_m: Vector3, color: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.name = label
	node.position = at
	var mesh := BoxMesh.new()
	mesh.size = size_m
	node.mesh = mesh
	if not _materials.has(color):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.77
		_materials[color] = material
	node.material_override = _materials[color]
	parent.add_child(node)
	return node


func _shape(body: PhysicsBody3D, label: String, at: Vector3, size_m: Vector3, color: Color) -> CollisionShape3D:
	var node := CollisionShape3D.new()
	node.name = label
	node.position = at
	var box := BoxShape3D.new()
	box.size = size_m
	node.shape = box
	body.add_child(node)
	_surface(node, "Finish", Vector3.ZERO, size_m, color)
	return node


func _solid(label: String, at: Vector3, size_m: Vector3, color: Color) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	body.position = at
	body.collision_layer = 1
	body.collision_mask = 0
	_shape(body, "Collider", Vector3.ZERO, size_m, color)
	_shell.add_child(body)
	return body


func _label(parent: Node3D, title: String, at: Vector3, faces_street := true) -> void:
	var sign := Label3D.new()
	sign.name = "Sign"
	sign.text = title
	sign.position = at
	sign.rotation.y = PI if faces_street else 0.0
	sign.pixel_size = 0.004
	sign.font_size = 38
	sign.outline_size = 5
	parent.add_child(sign)


func _build_exterior() -> void:
	var hx := _size.x * 0.5
	var hz := _size.z * 0.5
	var height := _size.y
	for side: float in [-1.0, 1.0]:
		_solid("SideWall", Vector3(side * (hx - WALL * 0.5), height * 0.5, 0), Vector3(WALL, height, _size.z), STONE)
	var front_z := -hz + WALL * 0.5
	var wing := (_size.x - DOOR_WIDTH) * 0.5
	for side: float in [-1.0, 1.0]:
		_solid("FrontWing", Vector3(side * (wing + DOOR_WIDTH) * 0.5, height * 0.5, front_z), Vector3(wing, height, WALL), STONE)
	_solid("FrontLintel", Vector3(0, (height + 2.4) * 0.5, front_z), Vector3(DOOR_WIDTH, height - 2.4, WALL), STONE)
	_solid("RearWall", Vector3(0, height * 0.5, hz - WALL * 0.5), Vector3(_size.x, height, WALL), STONE)
	_solid("Roof", Vector3(0, FLOORS * STOREY - SLAB * 0.5, 0), Vector3(_size.x, SLAB, _size.z), STONE)
	_street_gate = _solid("StreetDoor", Vector3(0, 1.2, front_z), Vector3(DOOR_WIDTH, 2.4, 0.12), METAL)
	_surface(_street_gate, "Glass", Vector3(0, 0.2, -0.065), Vector3(1.7, 1.3, 0.02), Color("#89aeb1"))
	_surface(_shell, "Canopy", Vector3(0, 2.64, -hz - 0.45), Vector3(3.4, 0.12, 1.12), METAL)
	_label(_shell, "ATLAS TOWER", Vector3(0, 2.96, -hz - 0.04))
	for level in FLOORS:
		for x in range(2, int(_size.x) - 1, 3):
			var px := -hx + x
			if absf(px) < 1.9 and level == 0:
				continue
			_surface(_shell, "Window", Vector3(px, level * STOREY + 1.5, -hz - 0.018), Vector3(1.1, 1.15, 0.04), Color("#507388"))
	if height > FLOORS * STOREY + 0.01:
		_solid("RoofCap", Vector3(0, (height + FLOORS * STOREY) * 0.5, 0), Vector3(_size.x, height - FLOORS * STOREY, _size.z), STONE)


func _build_floor(level: int, side: float) -> void:
	var y := level * STOREY
	var hx := _size.x * 0.5
	var hz := _size.z * 0.5
	var strip_depth := _shaft_front + hz
	var floor_color := Color("#9ca9a5").lerp(ACCENTS[level], 0.2)
	_solid("Slab%d" % level, Vector3(0, y - SLAB * 0.5, -hz + strip_depth * 0.5), Vector3(_size.x, SLAB, strip_depth), floor_color)
	var side_width := hx - HALF_SHAFT
	for flank: float in [-1.0, 1.0]:
		_solid("SlabWing%d" % level, Vector3(flank * (hx - side_width * 0.5), y - SLAB * 0.5, (_shaft_front + hz) * 0.5), Vector3(side_width, SLAB, hz - _shaft_front), floor_color)
		_solid("ShaftSide%d" % level, Vector3(flank * (HALF_SHAFT + WALL * 0.5), y + STOREY * 0.5, _car_z), Vector3(WALL, STOREY, SHAFT_DEPTH), METAL)
	var gate := _solid("LandingDoor%d" % level, Vector3(0, y + 1.29, _shaft_front), Vector3(HALF_SHAFT * 2, 2.58, 0.10), METAL)
	_surface(gate, "DoorSeam", Vector3(0, 0, -0.055), Vector3(0.025, 2.5, 0.02), LIFT)
	_gates.append(gate)
	_solid("ShaftLintel%d" % level, Vector3(0, y + 2.79, _shaft_front), Vector3(HALF_SHAFT * 2, 0.42, WALL), METAL)
	_label(_shell, "L%d   /   %s" % [level + 1, FLOOR_NAMES[level]], Vector3(0, y + 2.79, _shaft_front - 0.12))
	_surface(_shell, "CallPanel", Vector3(HALF_SHAFT + 0.11, y + 1.18, _shaft_front - 0.12), Vector3(0.19, 0.31, 0.07), ACCENTS[level])
	var fixture_pos := Vector3(side * (hx - 1.05), y + 0.33, -hz * 0.23)
	var fixture_size := Vector3(0.85, 0.66, 2.10)
	_solid("Bench%d" % level, fixture_pos, fixture_size, TIMBER)
	_fixtures.append(AABB(fixture_pos - fixture_size * 0.5, fixture_size))
	if level > 0:
		_surface(_shell, "FloorBand", Vector3(0, y + 1.15, -hz + WALL + 0.02), Vector3(_size.x - WALL * 2, 0.12, 0.025), ACCENTS[level])
	var light := OmniLight3D.new()
	light.name = "CeilingLight%d" % level
	light.position = Vector3(0, y + STOREY - 0.4, (_shaft_front - hz) * 0.5)
	light.omni_range = maxf(7.0, _size.z * 0.72)
	light.light_energy = 1.3
	light.light_color = Color("#ffedcf")
	_shell.add_child(light)


func _build_car() -> void:
	_car = AnimatableBody3D.new()
	_car.name = "ElevatorCabin"
	_car.sync_to_physics = false
	_car.collision_layer = 1
	_car.collision_mask = 0
	_car.position = Vector3(0, 0, _car_z)
	_shell.add_child(_car)
	_shape(_car, "CarFloor", Vector3(0, -SLAB * 0.5, 0), Vector3(HALF_SHAFT * 2 - 0.02, SLAB, SHAFT_DEPTH - 0.02), LIFT)
	_shape(_car, "CarRear", Vector3(0, 1.26, SHAFT_DEPTH * 0.5 - 0.07), Vector3(HALF_SHAFT * 2 - 0.02, 2.52, 0.12), LIFT)
	_shape(_car, "CarCeiling", Vector3(0, 2.57, 0), Vector3(HALF_SHAFT * 2 - 0.02, 0.10, SHAFT_DEPTH - 0.02), LIFT)
	_car_gate = _shape(_car, "CarDoor", Vector3(0, 1.26, -SHAFT_DEPTH * 0.5 + 0.10), Vector3(HALF_SHAFT * 2 - 0.02, 2.52, 0.08), LIFT)
	_surface(_car, "ControlPanel", Vector3(0.79, 1.24, SHAFT_DEPTH * 0.5 - 0.15), Vector3(0.25, 0.44, 0.05), METAL)
	_label(_car, "E   /   NEXT FLOOR", Vector3(0, 1.7, SHAFT_DEPTH * 0.5 - 0.14))


func _world() -> Transform3D:
	return _shell.global_transform if _shell.is_inside_tree() else transform * _shell.transform


func entrance_position() -> Vector3:
	return _world() * Vector3(0, 0, -_size.z * 0.5 - 1.25) if _shell else Vector3.ZERO


func landing_position(level: int) -> Vector3:
	return _world() * Vector3(0, level * STOREY, _shaft_front - 1.15) if _shell and level >= 0 and level < FLOORS else Vector3.ZERO


func cabin_position() -> Vector3:
	return _world() * Vector3(0, _height, _car_z) if _shell else Vector3.ZERO


func _update_gates() -> void:
	_street_gate.visible = not _street_open
	_street_gate.collision_layer = 0 if _street_open else 1
	for level in FLOORS:
		var closed := _floor != _target or level != _floor
		_gates[level].visible = closed
		_gates[level].collision_layer = 1 if closed else 0
	var moving := _floor != _target
	_car_gate.disabled = not moving
	_car_gate.visible = moving


func _blocking_threshold(z: float, width: float, y: float, actor: Vector3) -> bool:
	if absf(actor.x) <= width * 0.5 + RADIUS and absf(actor.z - z) <= RADIUS + 0.13 and absf(actor.y - y) < 1.8:
		return true
	if not _shell.is_inside_tree():
		return false
	# Query the city's character layer to catch a second avatar straddling a closing door.
	var shape := BoxShape3D.new()
	shape.size = Vector3(width, 2.35, 0.26)
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = shape
	query.collision_mask = 2
	query.transform = _world() * Transform3D(Basis.IDENTITY, Vector3(0, y + 1.18, z))
	return not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func _inside_car(p: Vector3) -> bool:
	return absf(p.x) < HALF_SHAFT - RADIUS and p.z > _shaft_front + RADIUS + 0.19 and p.z < _shaft_front + SHAFT_DEPTH - RADIUS - 0.14


func _release() -> void:
	if is_instance_valid(_rider):
		_rider.set_physics_process(_resume_physics)
		_rider.velocity = Vector3.ZERO
	_rider = null
	_offset = Vector2.ZERO


func _attach(player: CharacterBody3D, offset: Vector2) -> void:
	_rider = player
	_offset = offset
	_resume_physics = player.is_physics_processing()
	player.set_physics_process(false)
	player.velocity = Vector3.ZERO


func _place_car() -> void:
	_car.position.y = _height
	if is_instance_valid(_rider):
		_rider.set_physics_process(false)
		_rider.velocity = Vector3.ZERO
		_rider.global_position = _world() * Vector3(_offset.x, _height + 0.025, _car_z + _offset.y)


func interact(player: CharacterBody3D) -> bool:
	if not _shell or not is_instance_valid(player) or not player.is_inside_tree() or not player.global_position.is_finite():
		return false
	var p := _world().affine_inverse() * player.global_position
	var front := -_size.z * 0.5 + WALL * 0.5
	if absf(p.y) < 0.5 and Vector2(p.x, p.z - front).length() < 2.05:
		if _street_open and _blocking_threshold(front, DOOR_WIDTH, 0.0, p):
			return false
		_street_open = not _street_open
		_update_gates()
		return true
	if _floor != _target:
		return false
	var level := roundi(p.y / STOREY)
	if level < 0 or level >= FLOORS or absf(p.y - level * STOREY) > 0.30:
		return false
	if level == _floor and _inside_car(p):
		if _blocking_threshold(_shaft_front + 0.05, HALF_SHAFT * 2, _height, p):
			return false
		_attach(player, Vector2(p.x, p.z - _car_z))
		_target = (_floor + 1) % FLOORS
	elif level != _floor and absf(p.x) < HALF_SHAFT + 0.5 and p.z < _shaft_front - RADIUS and p.z >= _shaft_front - 2.1:
		if _blocking_threshold(_shaft_front + 0.05, HALF_SHAFT * 2, _height, p) or _car_occupied():
			return false
		_target = level
	else:
		return false
	_update_gates()
	return true


func _car_occupied() -> bool:
	if not _shell.is_inside_tree():
		return false
	var box := BoxShape3D.new()
	box.size = Vector3(HALF_SHAFT * 2, 2.32, SHAFT_DEPTH - 0.12)
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = box
	query.collision_mask = 2
	query.transform = _world() * Transform3D(Basis.IDENTITY, Vector3(0, _height + 1.18, _car_z))
	return not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func step(delta: float, _player: CharacterBody3D = null) -> void:
	if not _shell or _floor == _target or not is_finite(delta) or delta <= 0.0:
		return
	var destination := _target * STOREY
	_height = move_toward(_height, destination, SPEED * delta)
	_place_car()
	if _height == destination:
		_floor = _target
		if is_instance_valid(_rider):
			_trips += 1
		_release()
		_update_gates()


func status() -> Dictionary:
	if not _shell:
		return {}
	return {"building_id": _id, "floor_count": FLOORS, "floor_names": FLOOR_NAMES.duplicate(), "floor": _floor,
		"target_floor": _target, "phase": "docked" if _floor == _target else "moving", "riding": is_instance_valid(_rider),
		"trips": _trips, "height": _height, "door_open": _street_open, "entrance": entrance_position(), "cabin": cabin_position()}


func snapshot() -> Dictionary:
	if not _shell:
		return {}
	return {"version": 1, "seed": _seed, "building_id": _id, "layout": _layout, "door_open": _street_open,
		"floor": _floor, "target_floor": _target, "height": _height, "riding": is_instance_valid(_rider),
		"offset": [_offset.x, _offset.y] if is_instance_valid(_rider) else [0.0, 0.0], "trips": _trips}


func _integer(value: Variant, low: int, high: int) -> bool:
	return _number(value) and value == floorf(float(value)) and value >= low and value <= high


func valid_snapshot(data: Variant) -> bool:
	if not _shell or not data is Dictionary or data.size() != 11 or not data.has_all(["version", "seed", "building_id", "layout", "door_open", "floor", "target_floor", "height", "riding", "offset", "trips"]):
		return false
	if not _integer(data.version, 1, 1) or not _integer(data.seed, _seed, _seed) or not data.building_id is String or data.building_id != _id or not data.layout is String or data.layout != _layout:
		return false
	if not data.door_open is bool or not data.riding is bool or not _integer(data.floor, 0, FLOORS - 1) or not _integer(data.target_floor, 0, FLOORS - 1) or not _integer(data.trips, 0, 2147483647):
		return false
	if not _number(data.height) or not data.offset is Array or data.offset.size() != 2 or not _number(data.offset[0]) or not _number(data.offset[1]):
		return false
	var source := int(data.floor) * STOREY
	var destination := int(data.target_floor) * STOREY
	if data.height < minf(source, destination) or data.height > maxf(source, destination):
		return false
	if source != destination and data.height == destination:
		return false
	if data.riding:
		return int(data.target_floor) == (int(data.floor) + 1) % FLOORS and _inside_car(Vector3(data.offset[0], 0, _car_z + float(data.offset[1])))
	return data.offset[0] == 0 and data.offset[1] == 0


func _walkable_at(world_feet: Vector3, floor_index: int, target_index: int) -> bool:
	if not _shell or not world_feet.is_finite():
		return false
	var p := _world().affine_inverse() * world_feet
	var level := roundi(p.y / STOREY)
	if level < 0 or level >= FLOORS or p.y < level * STOREY - 0.04 or p.y > level * STOREY + 0.28:
		return false
	if absf(p.x) >= _size.x * 0.5 - WALL - RADIUS or absf(p.z) >= _size.z * 0.5 - WALL - RADIUS:
		return false
	for box in _fixtures:
		if p.y < box.position.y - 0.05 or p.y > box.end.y:
			continue
		var near_x := clampf(p.x, box.position.x, box.end.x)
		var near_z := clampf(p.z, box.position.z, box.end.z)
		if Vector2(p.x - near_x, p.z - near_z).length_squared() <= RADIUS * RADIUS:
			return false
	if p.z > _shaft_front - RADIUS - 0.1 and absf(p.x) < HALF_SHAFT + WALL + RADIUS:
		if absf(p.x) >= HALF_SHAFT - RADIUS or floor_index != level or target_index != level:
			return false
		return p.z < _shaft_front + SHAFT_DEPTH - RADIUS - 0.14
	return true


func contains_walkable_position(world_feet: Vector3) -> bool:
	return _walkable_at(world_feet, _floor, _target)


func valid_player_position(world_feet: Vector3, data: Dictionary) -> bool:
	if not valid_snapshot(data) or not world_feet.is_finite():
		return false
	if data.riding:
		var expected := _world() * Vector3(data.offset[0], data.height + 0.025, _car_z + float(data.offset[1]))
		return world_feet.distance_to(expected) <= 0.12
	return _walkable_at(world_feet, int(data.floor), int(data.target_floor))


func restore(data: Variant, player: CharacterBody3D = null) -> bool:
	if not valid_snapshot(data):
		return false
	var passenger := player if is_instance_valid(player) else _rider
	if data.riding and (not is_instance_valid(passenger) or not passenger.is_inside_tree()):
		return false
	_release()
	_floor = int(data.floor)
	_target = int(data.target_floor)
	_height = float(data.height)
	_street_open = data.door_open
	_trips = int(data.trips)
	if data.riding:
		_attach(passenger, Vector2(data.offset[0], data.offset[1]))
	_place_car()
	_update_gates()
	return true


func _exit_tree() -> void:
	_release()
