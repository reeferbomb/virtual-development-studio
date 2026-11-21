extends Node3D

const MAGAZINE_SIZE := 6
const RESERVE_CAPACITY := 18
const SHOT_INTERVAL := 0.25
const HITS_TO_DEFEAT := 2
const MAX_DISTANCE := 120.0
const WORLD_LAYER := 1
const TARGET_LAYER := 8

var ammo := MAGAZINE_SIZE
var reserve := RESERVE_CAPACITY
var cooldown := 0.0
var _bodies: Dictionary[String, StaticBody3D] = {}
var _hits_left: Dictionary[String, int] = {}

# Each position is the drone's center in this node's coordinate system.
func configure(targets: Array) -> bool:
	var positions: Dictionary[String, Vector3] = {}
	for row in targets:
		if not row is Dictionary or not row.has_all(["id", "position"]):
			return false
		if not row.id is String or row.id.strip_edges().is_empty() or positions.has(row.id):
			return false
		if not row.position is Array or row.position.size() != 3:
			return false
		for value in row.position:
			if not _finite_number(value):
				return false
		var center := Vector3(row.position[0], row.position[1], row.position[2])
		if not center.is_finite():
			return false
		positions[row.id] = center

	for body in _bodies.values():
		body.free()
	_bodies.clear()
	_hits_left.clear()
	for id in positions:
		var body := _make_drone(id, positions[id])
		add_child(body)
		_bodies[id] = body
		_hits_left[id] = HITS_TO_DEFEAT
	ammo = MAGAZINE_SIZE
	reserve = RESERVE_CAPACITY
	cooldown = 0.0
	return true

func target_alive(id: String) -> bool:
	return _hits_left.get(id, 0) > 0

func tick(delta: float) -> void:
	if is_finite(delta) and delta > 0.0:
		cooldown = maxf(0.0, cooldown - delta)

func reload() -> bool:
	var transfer := mini(MAGAZINE_SIZE - ammo, reserve)
	if transfer <= 0:
		return false
	ammo += transfer
	reserve -= transfer
	return true

# Use world-space coordinates. The first surface occludes everything behind it.
func shoot(origin: Vector3, direction: Vector3) -> Dictionary:
	var shot := {"fired": false, "hit": false, "defeated": false, "id": ""}
	if ammo <= 0 or cooldown > 0.0 or not is_inside_tree():
		return shot
	if not origin.is_finite() or not direction.is_finite():
		return shot
	var aim := direction.normalized()
	if not aim.is_finite() or aim.is_zero_approx():
		return shot
	var endpoint := origin + aim * MAX_DISTANCE
	if not endpoint.is_finite() or endpoint == origin:
		return shot
	var ray := PhysicsRayQueryParameters3D.create(origin, endpoint, WORLD_LAYER | TARGET_LAYER)
	ray.hit_from_inside = true
	var impact := get_world_3d().direct_space_state.intersect_ray(ray)
	ammo -= 1
	cooldown = SHOT_INTERVAL
	shot.fired = true
	if impact.is_empty() or not impact.collider is StaticBody3D:
		return shot
	var body: StaticBody3D = impact.collider
	if body.get_parent() != self:
		return shot
	var id: String = body.get_meta(&"range_target_id", "")
	if not target_alive(id) or _bodies.get(id) != body:
		return shot
	_set_hits_left(id, _hits_left[id] - 1)
	shot.hit = true
	shot.id = id
	shot.defeated = not target_alive(id)
	return shot

func snapshot() -> Dictionary:
	return {"ammo": ammo, "reserve": reserve, "cooldown": cooldown, "targets": _hits_left.duplicate()}

func valid_snapshot(data: Dictionary) -> bool:
	if data.size() != 4 or not data.has_all(["ammo", "reserve", "cooldown", "targets"]):
		return false
	if not _whole_in_range(data.ammo, MAGAZINE_SIZE) or not _whole_in_range(data.reserve, RESERVE_CAPACITY):
		return false
	if not _finite_number(data.cooldown) or data.cooldown < 0.0 or data.cooldown > SHOT_INTERVAL:
		return false
	if not data.targets is Dictionary or data.targets.size() != _bodies.size():
		return false
	for id in _bodies:
		if not data.targets.has(id) or not _whole_in_range(data.targets[id], HITS_TO_DEFEAT):
			return false
	return true

func restore(data: Dictionary) -> bool:
	if not valid_snapshot(data):
		return false
	ammo = int(data.ammo)
	reserve = int(data.reserve)
	cooldown = float(data.cooldown)
	for id in _bodies:
		_set_hits_left(id, int(data.targets[id]))
	return true

func _set_hits_left(id: String, hits: int) -> void:
	_hits_left[id] = hits
	var body := _bodies[id]
	body.visible = hits > 0
	body.collision_layer = TARGET_LAYER if hits > 0 else 0
	var lamp := body.get_node("StatusLamp") as MeshInstance3D
	var material := lamp.material_override as StandardMaterial3D
	var signal_color := Color("#55e7ef") if hits == HITS_TO_DEFEAT else Color("#ff833d")
	material.albedo_color = signal_color
	material.emission = signal_color

func _finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))

func _whole_in_range(value: Variant, limit: int) -> bool:
	return _finite_number(value) and value >= 0 and value <= limit and floorf(value) == value

func _make_drone(id: String, center: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = center
	body.collision_layer = TARGET_LAYER
	body.collision_mask = 0
	body.set_meta(&"range_target_id", id)

	var hull := _material(Color("#e8aa49"))
	var trim := _material(Color("#243340"))
	var lamp := _material(Color("#55e7ef"))
	lamp.emission_enabled = true
	lamp.emission = lamp.albedo_color
	_add_cylinder(body, "Armor", Vector3.ZERO, 0.49, 0.56, hull, true)
	_add_cylinder(body, "StatusLamp", Vector3.ZERO, 0.50, 0.09, lamp, false)
	for side: int in [-1, 1]:
		var pod := Vector3(0.58 * side, 0.04, 0.0)
		_add_cylinder(body, "FanHousing", pod, 0.23, 0.19, trim, true)
		_add_cylinder(body, "FanHub", pod + Vector3.UP * 0.10, 0.13, 0.04, hull, false)
	return body

func _material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.65
	return mat

func _add_cylinder(body: StaticBody3D, part: String, offset: Vector3, radius: float, height: float, material: Material, solid: bool) -> void:
	var cylinder := CylinderMesh.new()
	cylinder.radial_segments = 12
	cylinder.rings = 0
	cylinder.top_radius = radius
	cylinder.bottom_radius = radius
	cylinder.height = height
	var visual := MeshInstance3D.new()
	visual.name = part
	visual.position = offset
	visual.mesh = cylinder
	visual.material_override = material
	body.add_child(visual)
	if solid:
		var shape := CylinderShape3D.new()
		shape.radius = radius
		shape.height = height
		var collider := CollisionShape3D.new()
		collider.shape = shape
		collider.position = offset
		body.add_child(collider)
