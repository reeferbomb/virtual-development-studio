extends Node3D

const WALL := 0.24
const DOOR_WIDTH := 2.2
const DOOR_HEIGHT := 2.45
const CEILING := 3.35
const PLAYER_RADIUS := 0.35
const COLORS := {"downtown": Color("#8197aa"), "residential": Color("#ab8e78"), "industrial": Color("#6b857a")}
const ROOM_NAMES := {"downtown": ["Reception", "Records office"], "residential": ["Entry hall", "Reading room"], "industrial": ["Dispatch", "Workroom"]}

var _seed: int
var _id := ""
var _district := ""
var _style := ""
var _layout_key := ""
var _size := Vector3.ZERO
var _shell: Node3D
var _door: StaticBody3D
var _door_open := false
var _front: float
var _partition: float
var _rooms: Array
var _obstacles: Array[AABB] = []
var _materials := {}


func _number(value: Variant) -> bool:
	return (typeof(value) == TYPE_INT or typeof(value) == TYPE_FLOAT) and is_finite(float(value))


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
	var size_m := Vector3(building.size[0], building.size[1], building.size[2])
	var center := Vector3(building.center[0], building.center[1], building.center[2])
	if not center.is_finite() or not size_m.is_finite() or size_m.x < 9 or size_m.z < 9 or size_m.y < 5 or size_m.x > 128 or size_m.z > 128 or size_m.y > 128:
		return false
	if is_instance_valid(_shell):
		_shell.free()
	_obstacles.clear()
	_seed = city_seed
	_id = building.id
	_district = building.district
	_style = building.style
	_size = size_m
	_rooms = ROOM_NAMES.get(_district, ["Lobby", "Office"])
	_front = -_size.z * 0.5 + WALL * 0.5
	_layout_key = JSON.stringify([center.x, center.y, center.z, size_m.x, size_m.y, size_m.z, _district, _style])
	var rng := RandomNumberGenerator.new()
	rng.seed = city_seed ^ _id.hash()
	_partition = rng.randf_range(-0.09, 0.09) * _size.z
	_shell = Node3D.new()
	_shell.name = "GroundFloor"
	_shell.position = center
	add_child(_shell)
	_build_shell()
	_furnish(-1.0 if rng.randi_range(0, 1) == 0 else 1.0)
	_set_open(false)
	return true


func _visual(parent: Node3D, label: String, at: Vector3, dimensions: Vector3, color: Color) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = dimensions
	if not _materials.has(color):
		var surface := StandardMaterial3D.new()
		surface.albedo_color = color
		surface.roughness = 0.83
		_materials[color] = surface
	mesh.material = _materials[color]
	var node := MeshInstance3D.new()
	node.name = label
	node.mesh = mesh
	node.position = at
	parent.add_child(node)
	return node


func _solid(label: String, at: Vector3, dimensions: Vector3, color: Color, obstacle: bool = false) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	body.position = at
	body.collision_layer = 1
	body.collision_mask = 0
	var box := BoxShape3D.new()
	box.size = dimensions
	var collider := CollisionShape3D.new()
	collider.shape = box
	body.add_child(collider)
	_visual(body, "Surface", Vector3.ZERO, dimensions, color)
	_shell.add_child(body)
	if obstacle:
		_obstacles.append(AABB(at - dimensions * 0.5, dimensions))
	return body


# Leave a two-metre passage around x=0 through both rooms.
func _wall_with_opening(label: String, z: float, width: float, height: float, color: Color, obstacle: bool) -> void:
	var wing := (width - DOOR_WIDTH) * 0.5
	var offset := (wing + DOOR_WIDTH) * 0.5
	_solid(label + "Left", Vector3(-offset, height * 0.5, z), Vector3(wing, height, WALL), color, obstacle)
	_solid(label + "Right", Vector3(offset, height * 0.5, z), Vector3(wing, height, WALL), color, obstacle)
	_solid(label + "Lintel", Vector3(0, (height + DOOR_HEIGHT) * 0.5, z), Vector3(DOOR_WIDTH, height - DOOR_HEIGHT, WALL), color)


func _build_shell() -> void:
	var facade: Color = COLORS.get(_district, Color("#829292"))
	var hx := _size.x * 0.5
	var hz := _size.z * 0.5
	# The finished floor is flush with the street. Its inset finish sits just above the city ground mesh.
	_solid("Floor", Vector3(0, -0.10, 0), Vector3(_size.x, 0.2, _size.z), Color("#506568"))
	_visual(_shell, "LobbyTile", Vector3(0, 0.013, (_partition-hz)*0.5), Vector3(_size.x-WALL*2, 0.01, hz+_partition-WALL*0.5), Color("#a3afa8"))
	_visual(_shell, "RearFloor", Vector3(0, 0.012, (_partition+hz)*0.5), Vector3(_size.x-WALL*2, 0.01, hz-_partition-WALL*0.5), Color("#707c7a"))
	_solid("WestWall", Vector3(-hx+WALL*0.5, CEILING*0.5, 0), Vector3(WALL, CEILING, _size.z), facade)
	_solid("EastWall", Vector3(hx-WALL*0.5, CEILING*0.5, 0), Vector3(WALL, CEILING, _size.z), facade)
	_solid("BackWall", Vector3(0, CEILING*0.5, hz-WALL*0.5), Vector3(_size.x-WALL*2, CEILING, WALL), facade)
	_wall_with_opening("Front", _front, _size.x-WALL*2, CEILING, facade, false)
	_wall_with_opening("Partition", _partition, _size.x-WALL*2, CEILING, Color("#c5c1ae"), true)
	_solid("UpperStoreys", Vector3(0, (_size.y+CEILING)*0.5, 0), Vector3(_size.x, _size.y-CEILING, _size.z), facade)
	_visual(_shell, "RoofParapet", Vector3(0, _size.y-0.08, 0), Vector3(_size.x+0.2, 0.22, _size.z+0.2), facade.darkened(0.22))
	_visual(_shell, "DoorCanopy", Vector3(0, 2.75, _front-0.45), Vector3(3.2, 0.12, 1.05), Color("#475c60"))
	for y in range(5, int(_size.y)-1, 3):
		for x in range(2, int(_size.x)-1, 4):
			_visual(_shell, "UpperWindow", Vector3(-hx+x, y, -hz-0.015), Vector3(1.5, 1.3, 0.04), Color("#354f63"))
	_door = _solid("SlidingDoor", Vector3(0, DOOR_HEIGHT*0.5, _front), Vector3(DOOR_WIDTH, DOOR_HEIGHT, 0.10), Color("#3a595f"))
	_visual(_door, "Glazing", Vector3(0, 0.27, -0.058), Vector3(1.78, 1.22, 0.015), Color("#7ea4aa"))
	_visual(_door, "Handle", Vector3(0.76, -0.12, -0.09), Vector3(0.055, 0.40, 0.07), Color("#deb974"))


func _furnish(side: float) -> void:
	var lobby_z := (_front + _partition) * 0.5
	var work_z := (_size.z * 0.5 + _partition) * 0.5
	var x := side * (_size.x * 0.5 - 1.45)
	var bench := _solid("BenchBase", Vector3(x, 0.22, lobby_z), Vector3(0.73, 0.44, 2.20), Color("#895e45"), true)
	_visual(bench, "Cushion", Vector3(0, 0.24, 0), Vector3(0.76, 0.13, 2.23), Color("#ad8660"))
	_visual(bench, "Backrest", Vector3(side*0.32, 0.47, 0), Vector3(0.11, 0.53, 2.20), Color("#937556"))
	var desk := _solid("WorkCounter", Vector3(-x, 0.45, work_z), Vector3(1.25, 0.9, 2.2), Color("#967256"), true)
	_visual(desk, "Worktop", Vector3(0, 0.48, 0), Vector3(1.31, 0.08, 2.26), Color("#d3c1a5"))
	_visual(desk, "Terminal", Vector3(-side*0.18, 0.75, 0.35), Vector3(0.10, 0.42, 0.55), Color("#3c5460"))
	for z: float in [lobby_z, work_z]:
		_visual(_shell, "CeilingFixture", Vector3(0, CEILING-0.07, z), Vector3(1.45, 0.10, 0.45), Color("#ffedc3"))
		var light := OmniLight3D.new()
		light.name = "RoomLight"
		light.position = Vector3(0, CEILING-0.24, z)
		light.light_color = Color("#ffecd1")
		light.light_energy = 1.25
		light.omni_range = maxf(6.0, maxf(_size.x * 0.60, _size.z * 0.37))
		_shell.add_child(light)
	_sign("%s  /  %s" % [_district.capitalize(), _rooms[0]], Vector3(0, 3.03, _front-WALL*0.56))
	_sign(_rooms[1], Vector3(0, 2.82, _partition-WALL*0.56))


func _sign(title: String, at: Vector3) -> void:
	var label := Label3D.new()
	label.name = "RoomSign"
	label.text = title
	label.position = at
	label.rotation.y = PI
	label.font_size = 32
	label.pixel_size = 0.007
	label.outline_size = 5
	_shell.add_child(label)


func _shell_transform() -> Transform3D:
	return _shell.global_transform if _shell.is_inside_tree() else transform * _shell.transform


func entrance_position() -> Vector3:
	return _shell_transform() * Vector3(0, 0, _front-1.4) if _shell else Vector3.ZERO


func room_target() -> Vector3:
	return _shell_transform() * Vector3(0, 0, (_size.z*0.5+_partition)*0.5) if _shell else Vector3.ZERO


func _set_open(opened: bool) -> void:
	_door_open = opened
	# The panel retracts into the west wall pocket, taking its collider with it.
	_door.position.x = -DOOR_WIDTH-0.02 if opened else 0.0
	_door.visible = not opened


func _threshold_occupied() -> bool:
	if not _shell.is_inside_tree():
		return false
	var box := BoxShape3D.new()
	box.size = Vector3(DOOR_WIDTH-0.02, DOOR_HEIGHT-0.05, 0.12)
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = box
	query.transform = _shell_transform() * Transform3D(Basis.IDENTITY, Vector3(0, DOOR_HEIGHT*0.5, _front))
	for hit in get_world_3d().direct_space_state.intersect_shape(query, 32):
		if not hit.collider is StaticBody3D:
			return true
	return false


func interact(player_pos: Vector3) -> bool:
	if not _shell or not player_pos.is_finite():
		return false
	var local := _shell_transform().affine_inverse() * player_pos
	var offset := Vector2(local.x, local.z - _front)
	if local.y < -0.25 or local.y > 2.4 or offset.length() > 2.50:
		return false
	if _door_open:
		if absf(offset.x) <= DOOR_WIDTH*0.5+PLAYER_RADIUS and absf(offset.y) <= PLAYER_RADIUS+0.10:
			return false
		if _threshold_occupied():
			return false
	_set_open(not _door_open)
	return true


# A grounded standing capsule must clear the perimeter, partition and furnishings.
func contains_walkable_position(world_feet: Vector3) -> bool:
	if not _shell or not world_feet.is_finite():
		return false
	var p := _shell_transform().affine_inverse() * world_feet
	if p.y < -0.03 or p.y > 0.25 or absf(p.x) >= _size.x*0.5-WALL-PLAYER_RADIUS or absf(p.z) >= _size.z*0.5-WALL-PLAYER_RADIUS:
		return false
	for bounds in _obstacles:
		var dx := p.x - clampf(p.x, bounds.position.x, bounds.end.x)
		var dz := p.z - clampf(p.z, bounds.position.z, bounds.end.z)
		if dx*dx + dz*dz <= PLAYER_RADIUS*PLAYER_RADIUS:
			return false
	return true


func status() -> Dictionary:
	if not _shell:
		return {}
	return {"building_id": _id, "district": _district, "style": _style, "door_open": _door_open,
		"room_count": _rooms.size(), "rooms": _rooms.duplicate(), "entrance": entrance_position(), "room_target": room_target()}


func snapshot() -> Dictionary:
	if not _shell:
		return {}
	return {"version": 1, "seed": _seed, "building_id": _id, "layout": _layout_key, "door_open": _door_open}


func valid_snapshot(value: Variant) -> bool:
	if not _shell or not value is Dictionary or value.size() != 5 or not value.has_all(["version", "seed", "building_id", "layout", "door_open"]):
		return false
	return _number(value.version) and value.version == 1 and _number(value.seed) and value.seed == _seed and value.building_id is String and value.building_id == _id and value.layout is String and value.layout == _layout_key and typeof(value.door_open) == TYPE_BOOL


func restore(value: Variant) -> bool:
	if not valid_snapshot(value):
		return false
	if _door_open and not value.door_open and _threshold_occupied():
		return false
	_set_open(value.door_open)
	return true
