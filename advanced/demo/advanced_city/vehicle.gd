extends CharacterBody3D
## Flat-street touring car. The city supplies physics ticks and local driving input.
## World-space origin is the tire contact point. Heading zero points toward -Z.

const TOP_SPEED := 16.0
const REVERSE_SPEED := 5.0
const ACCELERATION := 7.0
const BRAKING := 20.0
const COASTING := 3.0
const WHEELBASE := 2.36
const MAX_STEER := 0.48
const MAX_YAW_RATE := 1.45
const MAX_STEP := 1.0 / 30.0
const BODY_SIZE := Vector3(1.90, 1.35, 3.88)
const BODY_CENTER := Vector3(0, 0.83, 0)
const SEAT := Vector3(0, 0.38, -0.15)
const DOOR_DISTANCE := 1.85
const ENTRY_REACH := 3.0
const STOP_SPEED := 0.08

var _seed_value := 0
var _origin := Vector3.ZERO
var _extent := 0.0
var _speed := 0.0
var _steer := 0.0
var _distance := 0.0
var _collisions := 0
var _body_shape: BoxShape3D
var _driver: CharacterBody3D
var _walk_processing := false
var _walk_layer := 0
var _walk_mask := 0
var _walk_camera: Camera3D
var _chase: SpringArm3D
var _front_wheels: Array[Node3D] = []


func configure(seed_value: int, origin: Vector3, world_size: float) -> bool:
	if _body_shape != null or not is_inside_tree() or not origin.is_finite() or not is_finite(world_size):
		return false
	if world_size < 6.0 or not _in_bounds(origin, 0.0, world_size):
		return false
	_seed_value = seed_value
	_origin = origin
	_extent = world_size
	collision_layer = 1
	collision_mask = 1
	safe_margin = 0.002
	global_transform = Transform3D(Basis.IDENTITY, origin)
	var shape_node := CollisionShape3D.new()
	shape_node.name = "ChassisCollider"
	_body_shape = BoxShape3D.new()
	_body_shape.size = BODY_SIZE
	shape_node.shape = _body_shape
	shape_node.position = BODY_CENTER
	add_child(shape_node)
	_build_car()
	return true


func interact(player: CharacterBody3D) -> bool:
	if _body_shape == null or not _usable_driver(player) or absf(_speed) > STOP_SPEED:
		return false
	if is_instance_valid(_driver):
		if _driver != player:
			return false
		var landing: Variant = _door_landing()
		if landing == null:
			return false
		_release_driver()
		player.global_position = landing
		_speed = 0.0
		_steer = 0.0
		velocity = Vector3.ZERO
		_show_steering()
		return true
	if player.global_position.distance_to(global_position) > ENTRY_REACH:
		return false
	var ignored: Array[RID] = [get_rid(), player.get_rid()]
	var query := PhysicsRayQueryParameters3D.create(player.global_position + Vector3.UP * 0.8,
		global_position + Vector3.UP * 0.8, collision_mask, ignored)
	if not get_world_3d().direct_space_state.intersect_ray(query).is_empty():
		return false
	_board(player)
	return true


func _usable_driver(player: CharacterBody3D) -> bool:
	return is_instance_valid(player) and player != self and player.is_inside_tree() and player.get_world_3d() == get_world_3d()


func _board(player: CharacterBody3D) -> void:
	_driver = player
	_walk_processing = player.is_physics_processing()
	_walk_layer = player.collision_layer
	_walk_mask = player.collision_mask
	player.collision_layer = 0
	player.collision_mask = 0
	if player.has_method("clear_test_drive"):
		player.call("clear_test_drive")
	_sync_driver()
	var active := get_viewport().get_camera_3d()
	if active != null and player.is_ancestor_of(active):
		_walk_camera = active
		_chase = SpringArm3D.new()
		_chase.name = "ChaseArm"
		_chase.position.y = 1.55
		_chase.rotation.x = deg_to_rad(-15.0)
		_chase.spring_length = 5.8
		_chase.margin = 0.15
		_chase.collision_mask = collision_mask
		_chase.add_excluded_object(get_rid())
		_chase.add_excluded_object(player.get_rid())
		add_child(_chase)
		var camera := Camera3D.new()
		camera.fov = active.fov
		_chase.add_child(camera)
		camera.make_current()


func _sync_driver() -> void:
	_driver.set_physics_process(false)
	_driver.velocity = Vector3.ZERO
	_driver.global_transform = Transform3D(global_basis, to_global(SEAT))


func _release_driver() -> void:
	if is_instance_valid(_driver):
		_driver.collision_layer = _walk_layer
		_driver.collision_mask = _walk_mask
		_driver.velocity = Vector3.ZERO
		if _driver.has_method("clear_test_drive"):
			_driver.call("clear_test_drive")
		_driver.set_physics_process(_walk_processing)
	if is_instance_valid(_walk_camera) and _walk_camera.is_inside_tree():
		_walk_camera.make_current()
	if is_instance_valid(_chase):
		_chase.queue_free()
	_chase = null
	_walk_camera = null
	_driver = null


func _exit_tree() -> void:
	_release_driver()


func _door_landing() -> Variant:
	var space := get_world_3d().direct_space_state
	var ignored: Array[RID] = [get_rid(), _driver.get_rid()]
	var mask := _walk_mask | collision_mask
	for side in [-1.0, 1.0]:
		var door := to_global(Vector3(float(side) * DOOR_DISTANCE, 0, 0))
		if door.x < 0.4 or door.z < 0.4 or door.x > _extent - 0.4 or door.z > _extent - 0.4:
			continue
		var ground := PhysicsRayQueryParameters3D.create(door + Vector3.UP * 0.42, door + Vector3.DOWN * 0.8, mask, ignored)
		var hit := space.intersect_ray(ground)
		if hit.is_empty() or hit.normal.y < cos(_driver.floor_max_angle):
			continue
		var landing: Vector3 = hit.position + Vector3.UP * 0.06
		var path := PhysicsRayQueryParameters3D.create(global_position + Vector3.UP * 0.8, landing + Vector3.UP * 0.8, mask, ignored)
		if not space.intersect_ray(path).is_empty():
			continue
		if _standing_clear(landing, mask):
			return landing
	return null


func _standing_clear(landing: Vector3, mask: int) -> bool:
	var query := PhysicsShapeQueryParameters3D.new()
	query.collision_mask = mask
	query.exclude = [_driver.get_rid()]
	var standing := Transform3D(global_basis, landing)
	var checked_shape := false
	for owner in _driver.get_shape_owners():
		if _driver.is_shape_owner_disabled(owner):
			continue
		query.transform = standing * _driver.shape_owner_get_transform(owner)
		for index in _driver.shape_owner_get_shape_count(owner):
			query.shape = _driver.shape_owner_get_shape(owner, index)
			if not get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty():
				return false
			checked_shape = true
	# Some scripted passengers have no collider. Reserve the world player's standing envelope.
	if not checked_shape:
		var capsule := CapsuleShape3D.new()
		capsule.radius = 0.35
		capsule.height = 1.8
		query.shape = capsule
		query.transform = Transform3D(global_basis, landing + Vector3.UP * 0.9)
		return get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()
	return true


func step(delta: float, player: CharacterBody3D, input: Vector2, brake: bool = false) -> void:
	if not is_instance_valid(_driver) or player != _driver or not is_finite(delta) or delta <= 0.0 or not input.is_finite():
		return
	# Substeps bound corner rotation and keep steering predictable across physics rates.
	var remaining := minf(delta, 1.0)
	while remaining > 0.000001:
		var dt := minf(remaining, MAX_STEP)
		_advance(dt, input.clamp(Vector2(-1, -1), Vector2.ONE), brake)
		remaining -= dt
	_sync_driver()
	_show_steering()


func _advance(dt: float, input: Vector2, brake: bool) -> void:
	var target := input.y * (TOP_SPEED if input.y >= 0.0 else REVERSE_SPEED)
	var rate := ACCELERATION
	if brake:
		rate = BRAKING
		target = 0.0
	elif is_zero_approx(input.y):
		rate = COASTING
	_speed = move_toward(_speed, target, rate * dt)
	_steer = move_toward(_steer, input.x * MAX_STEER, 2.3 * dt)
	var turn := clampf(_speed * tan(_steer) / WHEELBASE, -MAX_YAW_RATE, MAX_YAW_RATE)
	var yaw := wrapf(global_rotation.y - turn * dt, -PI, PI)
	if not is_zero_approx(turn) and _in_bounds(global_position, yaw, _extent) and _body_clear(global_position, yaw):
		global_basis = Basis(Vector3.UP, yaw)
	var motion := -global_basis.z * _speed * dt
	if motion.is_zero_approx():
		velocity = Vector3.ZERO
		return
	var start := global_position
	var half_extent := _planar_half_extent(global_rotation.y)
	var end := start + motion
	end.x = clampf(end.x, half_extent.x, _extent - half_extent.x)
	end.z = clampf(end.z, half_extent.y, _extent - half_extent.y)
	var blocked := not end.is_equal_approx(start + motion)
	if not end.is_equal_approx(start):
		blocked = move_and_collide(end - start) != null or blocked
	_distance += start.distance_to(global_position)
	if blocked:
		if absf(_speed) >= 0.5:
			_collisions += 1
		_speed = 0.0
	velocity = -global_basis.z * _speed


func _planar_half_extent(yaw: float) -> Vector2:
	var s := absf(sin(yaw))
	var c := absf(cos(yaw))
	return Vector2(c * BODY_SIZE.x + s * BODY_SIZE.z, s * BODY_SIZE.x + c * BODY_SIZE.z) * 0.5


func _in_bounds(point: Vector3, yaw: float, extent: float) -> bool:
	var half_extent := _planar_half_extent(yaw)
	return point.x >= half_extent.x - 0.0001 and point.x <= extent - half_extent.x + 0.0001 \
		and point.z >= half_extent.y - 0.0001 and point.z <= extent - half_extent.y + 0.0001


func _body_clear(point: Vector3, yaw: float) -> bool:
	var ignored: Array[RID] = [get_rid()]
	if is_instance_valid(_driver):
		ignored.append(_driver.get_rid())
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = _body_shape
	query.transform = Transform3D(Basis(Vector3.UP, yaw), point + BODY_CENTER)
	query.collision_mask = collision_mask
	query.exclude = ignored
	return get_world_3d().direct_space_state.intersect_shape(query, 1).is_empty()


func status() -> Dictionary:
	return {"driving": is_instance_valid(_driver), "position": global_position, "yaw": global_rotation.y,
		"speed": _speed, "distance": _distance, "collisions": _collisions, "seat_position": to_global(SEAT)}


func snapshot() -> Dictionary:
	if _body_shape == null:
		return {}
	var p := global_position
	return {"version": 1, "seed": _seed_value, "world_size": _extent,
		"position": [p.x, p.y, p.z], "yaw": global_rotation.y, "speed": _speed, "steer": _steer,
		"distance": _distance, "collisions": _collisions, "driving": is_instance_valid(_driver)}


func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func valid_snapshot(state: Variant) -> bool:
	if _body_shape == null or not state is Dictionary or state.size() != 10:
		return false
	for name_key in ["version", "seed", "world_size", "yaw", "speed", "steer", "distance", "collisions"]:
		if not _number(state.get(name_key)):
			return false
	if state.version != 1 or state.seed != _seed_value or state.world_size != _extent or not state.get("driving") is bool:
		return false
	var p: Variant = state.get("position")
	if not p is Array or p.size() != 3 or not _number(p[0]) or not _number(p[1]) or not _number(p[2]):
		return false
	if absf(p[1] - _origin.y) > 0.001 or absf(state.yaw) > PI + 0.000001 or absf(state.steer) > MAX_STEER:
		return false
	if state.speed < -REVERSE_SPEED or state.speed > TOP_SPEED or (not state.driving and (state.speed != 0 or state.steer != 0)):
		return false
	if state.distance < 0 or state.collisions < 0 or state.collisions > 2147483647 or state.collisions != floorf(state.collisions):
		return false
	var point := Vector3(p[0], p[1], p[2])
	return _in_bounds(point, state.yaw, _extent) and _body_clear(point, state.yaw)


func valid_player_position(point: Vector3, state: Variant) -> bool:
	if not point.is_finite() or not valid_snapshot(state):
		return false
	var p: Array = state.position
	var saved := Transform3D(Basis(Vector3.UP, state.yaw), Vector3(p[0], p[1], p[2]))
	if state.driving:
		return point.distance_to(saved * SEAT) <= 0.025
	var local := saved.affine_inverse() * point
	# The walking capsule has a circular footprint, including at the four bumper corners.
	var outside := Vector2(maxf(0.0, absf(local.x) - BODY_SIZE.x * 0.5),
		maxf(0.0, absf(local.z) - BODY_SIZE.z * 0.5))
	return outside.length_squared() > 0.33 * 0.33 or local.y > BODY_CENTER.y + BODY_SIZE.y * 0.5 or local.y < -1.8


func restore(state: Variant, player: CharacterBody3D = null) -> bool:
	if not valid_snapshot(state):
		return false
	var rider := player if player != null else _driver
	if is_instance_valid(_driver) and rider != _driver:
		return false
	if state.driving and not _usable_driver(rider):
		return false
	var landing: Variant = null
	if not state.driving and is_instance_valid(_driver):
		if _driver.global_position.distance_to(to_global(SEAT)) < 0.025:
			landing = _door_landing()
			if landing == null:
				return false
		_release_driver()
		if landing != null:
			rider.global_position = landing
	var p: Array = state.position
	global_transform = Transform3D(Basis(Vector3.UP, state.yaw), Vector3(p[0], p[1], p[2]))
	_speed = state.speed
	_steer = state.steer
	_distance = state.distance
	_collisions = int(state.collisions)
	velocity = -global_basis.z * _speed
	if state.driving:
		if not is_instance_valid(_driver):
			_board(rider)
		else:
			_sync_driver()
	_show_steering()
	return true


func _show_steering() -> void:
	for pivot in _front_wheels:
		pivot.rotation.y = -_steer


func _material(color: Color, metallic := 0.0, luminous := false) -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.albedo_color = color
	result.metallic = metallic
	result.roughness = 0.56
	result.emission_enabled = luminous
	if luminous:
		result.emission = color
	return result


func _box(label: String, at: Vector3, size: Vector3, surface: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh.material = surface
	var part := MeshInstance3D.new()
	part.name = label
	part.mesh = mesh
	part.position = at
	add_child(part)


func _wheel(pivot: Node3D, radius: float, width: float, offset: float, surface: Material) -> void:
	var disc := CylinderMesh.new()
	disc.top_radius = radius
	disc.bottom_radius = radius
	disc.height = width
	disc.radial_segments = 16
	disc.rings = 1
	disc.material = surface
	var part := MeshInstance3D.new()
	part.mesh = disc
	part.rotation.z = PI * 0.5
	part.position.x = offset
	pivot.add_child(part)


func _build_car() -> void:
	var colors := [Color("#ec9d40"), Color("#439a89"), Color("#658abc")]
	var paint := _material(colors[posmod(_seed_value, colors.size())], 0.35)
	var trim := _material(Color("#22333b"))
	var glass := _material(Color("#334e62"), 0.4)
	var alloy := _material(Color("#bcc1bc"), 0.65)
	var lights := _material(Color("#fff0b4"), 0.0, true)
	var tail := _material(Color("#ef5245"), 0.0, true)
	_box("Chassis", Vector3(0, 0.62, 0), Vector3(1.8, 0.53, 3.72), paint)
	_box("Cabin", Vector3(0, 1.12, 0.10), Vector3(1.50, 0.52, 1.83), glass)
	_box("Roof", Vector3(0, 1.41, 0.12), Vector3(1.52, 0.1, 1.85), paint)
	_box("FrontBumper", Vector3(0, 0.48, -1.85), Vector3(1.81, 0.18, 0.10), trim)
	_box("RearBumper", Vector3(0, 0.48, 1.85), Vector3(1.81, 0.18, 0.10), trim)
	_box("Grille", Vector3(0, 0.73, -1.867), Vector3(0.78, 0.15, 0.035), trim)
	for side in [-1.0, 1.0]:
		var x := float(side)
		_box("Headlamp", Vector3(0.67 * x, 0.74, -1.87), Vector3(0.35, 0.14, 0.04), lights)
		_box("Taillamp", Vector3(0.67 * x, 0.74, 1.87), Vector3(0.35, 0.14, 0.04), tail)
		_box("Pillar", Vector3(0.753 * x, 1.13, 0.16), Vector3(0.04, 0.48, 0.1), trim)
		for z in [-1.0, 1.0]:
			var pivot := Node3D.new()
			pivot.name = ("Front" if z < 0 else "Rear") + ("Left" if x < 0 else "Right")
			pivot.position = Vector3(x * 0.82, 0.35, float(z) * WHEELBASE * 0.5)
			add_child(pivot)
			_wheel(pivot, 0.35, 0.26, 0.0, trim)
			_wheel(pivot, 0.20, 0.03, x * 0.133, alloy)
			if z < 0:
				_front_wheels.append(pivot)
