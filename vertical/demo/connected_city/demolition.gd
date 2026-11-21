extends Node3D

## The city drives step() and shoots from its physics tick. Layer 1 contains
## both solid architecture and the workshop panels. The player uses layer 2.
const WORLD_LAYER := 1
const REACH := 55.0
const COOLDOWN := 0.24
const MAX_HEALTH := 3
const PANEL_COUNT := 3
const SPACING := 3.4
const SIZE := Vector3(2.6, 2.3, 0.5)
const MAX_JSON_INTEGER := 9007199254740991
const CONCRETE := [Color("#a1a99f"), Color("#a3aaa8"), Color("#aca99d")]
const SAFETY_ORANGE := Color("#f1a442")
const CHARCOAL := Color("#3e4847")

var _seed := 0
var _origin := Vector3.ZERO
var _cooldown := 0.0
var _assembly: Node3D
var _panels: Array[StaticBody3D] = []
var _rubble: Array[Node3D] = []
var _health: Array[int] = []
var _materials := {}


func configure(world_seed: int, origin: Vector3) -> bool:
	if not origin.is_finite() or world_seed < -MAX_JSON_INTEGER or world_seed > MAX_JSON_INTEGER:
		return false
	if _assembly != null:
		_assembly.free()
	_panels.clear()
	_rubble.clear()
	_health.clear()
	_seed = world_seed
	_origin = origin
	_cooldown = 0.0
	_assembly = Node3D.new()
	_assembly.name = "WorkshopPanels"
	add_child(_assembly)
	if is_inside_tree():
		_assembly.global_position = origin
	else:
		_assembly.position = origin
	var rng := RandomNumberGenerator.new()
	rng.seed = world_seed
	for id in PANEL_COUNT:
		var base := Vector3((id - 1) * SPACING, 0, 0)
		var finish: Color = CONCRETE[rng.randi_range(0, CONCRETE.size() - 1)]
		_make_panel(id, base, finish)
		_make_rubble(id, base, finish, rng)
		_health.append(MAX_HEALTH)
	return true


func _box(parent: Node3D, center: Vector3, size: Vector3, color: Color) -> MeshInstance3D:
	if not _materials.has(color):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.94
		_materials[color] = material
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = _materials[color]
	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	parent.add_child(instance)
	instance.position = center
	return instance


func _make_panel(id: int, base: Vector3, color: Color) -> void:
	var panel := StaticBody3D.new()
	panel.name = "Panel%d" % id
	panel.collision_layer = WORLD_LAYER
	panel.collision_mask = 0
	_assembly.add_child(panel)
	panel.position = base + Vector3.UP * SIZE.y * 0.5
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = SIZE
	collider.shape = shape
	panel.add_child(collider)
	_box(panel, Vector3.ZERO, SIZE, color)
	var first_crack := Node3D.new()
	first_crack.name = "FirstCrack"
	var second_crack := Node3D.new()
	second_crack.name = "SecondCrack"
	panel.add_child(first_crack)
	panel.add_child(second_crack)
	for face: float in [-1.0, 1.0]:
		var z := face * (SIZE.z * 0.5 + 0.008)
		_box(panel, Vector3(0, 0.78, z), Vector3(2.46, 0.24, 0.016), CHARCOAL)
		for stripe in 6:
			var tab := _box(panel, Vector3(-1.0 + stripe * 0.40, 0.78, z + 0.014 * face),
					Vector3(0.19, 0.20, 0.016), SAFETY_ORANGE)
			tab.rotation.z = -0.40
		_box(first_crack, Vector3(-0.10, 0.12, z), Vector3(0.035, 0.46, 0.016), CHARCOAL).rotation.z = 0.42
		_box(first_crack, Vector3(-0.12, -0.25, z), Vector3(0.03, 0.37, 0.016), CHARCOAL).rotation.z = -0.38
		_box(second_crack, Vector3(0.09, 0.46, z), Vector3(0.04, 0.46, 0.016), CHARCOAL).rotation.z = -0.57
		_box(second_crack, Vector3(0.05, -0.54, z), Vector3(0.04, 0.43, 0.016), CHARCOAL).rotation.z = 0.60
	first_crack.hide()
	second_crack.hide()
	_panels.append(panel)


func _make_rubble(id: int, base: Vector3, color: Color, rng: RandomNumberGenerator) -> void:
	# Five decorative fragments per panel keep the opening traversable.
	var pieces := Node3D.new()
	pieces.name = "Rubble%d" % id
	_assembly.add_child(pieces)
	pieces.position = base
	for piece in 5:
		var width := rng.randf_range(0.30, 0.56)
		var height := rng.randf_range(0.12, 0.27)
		var center := Vector3((piece - 2) * 0.49, height * 0.5, rng.randf_range(-0.44, 0.44))
		var fragment := _box(pieces, center, Vector3(width, height, 0.36), color.darkened(0.08 * (piece % 3)))
		fragment.rotation.y = rng.randf_range(-0.55, 0.55)
	pieces.hide()
	_rubble.append(pieces)


func _set_health(id: int, value: int) -> void:
	_health[id] = value
	var panel := _panels[id]
	panel.collision_layer = WORLD_LAYER if value > 0 else 0
	panel.visible = value > 0
	panel.get_node("FirstCrack").visible = value < MAX_HEALTH
	panel.get_node("SecondCrack").visible = value == 1
	_rubble[id].visible = value == 0


func shoot(origin: Vector3, direction: Vector3) -> Dictionary:
	var result := {"fired": false, "hit": false, "destroyed": false, "id": -1}
	var length_squared := direction.length_squared()
	if _panels.is_empty() or _cooldown > 0.0 or not is_inside_tree() or not origin.is_finite():
		return result
	if not is_finite(length_squared) or length_squared < 0.000001:
		return result
	result.fired = true
	_cooldown = COOLDOWN
	var query := PhysicsRayQueryParameters3D.create(origin, origin + direction.normalized() * REACH, WORLD_LAYER)
	query.hit_from_inside = true
	var contact := get_world_3d().direct_space_state.intersect_ray(query)
	if contact.is_empty():
		return result
	var id := _panels.find(contact.collider)
	if id < 0 or _health[id] == 0:
		return result
	_set_health(id, _health[id] - 1)
	result.hit = true
	result.id = id
	result.destroyed = _health[id] == 0
	return result


func step(delta: float) -> void:
	if is_finite(delta) and delta > 0.0:
		_cooldown = maxf(0.0, _cooldown - delta)


func status() -> Dictionary:
	var targets: Array = []
	var destroyed := 0
	for id in _panels.size():
		var panel := _panels[id]
		var center := panel.global_position if is_inside_tree() else _origin + panel.position
		targets.append({"id": id, "position": [center.x, center.y, center.z], "health": _health[id],
				"max_health": MAX_HEALTH, "destroyed": _health[id] == 0})
		if _health[id] == 0:
			destroyed += 1
	return {"targets": targets, "destroyed": destroyed, "total": targets.size(), "cooldown": _cooldown}


func snapshot() -> Dictionary:
	return {"version": 1, "seed": _seed, "origin": [_origin.x, _origin.y, _origin.z],
			"health": _health.duplicate(), "cooldown": _cooldown}


func _number_in(value: Variant, low: float, high: float) -> bool:
	return (value is int or value is float) and is_finite(value) and value >= low and value <= high


func valid_snapshot(data: Variant) -> bool:
	if _panels.is_empty() or not data is Dictionary or data.size() != 5:
		return false
	if not data.has_all(["version", "seed", "origin", "health", "cooldown"]):
		return false
	if not _number_in(data.version, 1, 1) or not _number_in(data.seed, _seed, _seed):
		return false
	if not data.origin is Array or data.origin.size() != 3 or not data.health is Array or data.health.size() != PANEL_COUNT:
		return false
	for axis in 3:
		if not _number_in(data.origin[axis], _origin[axis], _origin[axis]):
			return false
	for value in data.health:
		if not _number_in(value, 0.0, MAX_HEALTH) or floorf(value) != value:
			return false
	return _number_in(data.cooldown, 0.0, COOLDOWN)


func restore(data: Variant) -> bool:
	if not valid_snapshot(data):
		return false
	for id in _panels.size():
		_set_health(id, int(data.health[id]))
	_cooldown = float(data.cooldown)
	return true
