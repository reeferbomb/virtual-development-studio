extends Node3D
## The session host supplies trusted peer positions and input to request() and step().
## Clients display validated snapshots. These methods are never exposed as RPCs.

const TOP_SPEED := 16.0
const REVERSE_SPEED := 5.0
const ACCELERATION := 8.0
const DECELERATION := 11.0
const ENTRY_REACH := 3.15
const DOOR_DISTANCE := 1.75
const AVATAR_RADIUS := 0.35
# The entire chassis and bumpers fit this envelope at every steering angle.
const COLLISION_RADIUS := 2.12
const SKIN := 0.003
const MAX_PEER := 2147483647
const SEAT_OFFSET := Vector3(-0.36, 0.38, 0.10)

var _extent := 0.0
var _ground_y := 0.0
var _buildings: Array[Rect2] = []
var _cover: Node
var _driver := 0
var _speed := 0.0
var _yaw := 0.0
var _seated := false
var _exit_peer := 0
var _exit_point := Vector3.ZERO


func configure(origin: Vector3, extent: float, buildings: Array) -> bool:
	if _extent > 0.0 or not origin.is_finite() or not is_finite(extent) or extent <= 2.0 * COLLISION_RADIUS:
		return false
	var rectangles: Array[Rect2] = []
	for row: Variant in buildings:
		if not row is Dictionary or not _triplet(row.get("center")) or not _triplet(row.get("size")):
			return false
		var size_3d := Vector3(row.size[0], row.size[1], row.size[2])
		if size_3d.x <= 0.0 or size_3d.y <= 0.0 or size_3d.z <= 0.0:
			return false
		var size_xz := Vector2(size_3d.x, size_3d.z)
		var center := Vector2(row.center[0], row.center[2])
		var rect := Rect2(center - size_xz * 0.5, size_xz)
		if not rect.position.is_finite() or not rect.end.is_finite():
			return false
		rectangles.append(rect)
	if not _clear(origin, COLLISION_RADIUS, extent, rectangles):
		return false
	_extent = extent
	_buildings = rectangles
	_ground_y = origin.y
	position = origin
	_build_visual()
	return true


func set_cover(cover: Node) -> void:
	_cover = cover


func occupied(peer: int) -> bool:
	return peer > 0 and peer == _driver


func release_peer(peer: int) -> void:
	if occupied(peer):
		_driver = 0
		_speed = 0.0
		_seated = false
	if _exit_peer == peer:
		_exit_peer = 0


func _seat() -> Vector3:
	return position + SEAT_OFFSET.rotated(Vector3.UP, _yaw)


func request(peer: int, peer_position: Vector3) -> bool:
	if _extent == 0.0 or peer < 1 or peer > MAX_PEER or not peer_position.is_finite() or _exit_peer != 0:
		return false
	if _driver == 0:
		if peer_position.distance_to(position) > ENTRY_REACH or not _walk_clear(peer_position, position):
			return false
		_driver = peer
		_seated = false
		return true
	if _driver != peer or not _seated or peer_position.distance_to(_seat()) > 0.75:
		return false
	for side: float in [-1.0, 1.0]:
		var door := position + Vector3.RIGHT.rotated(Vector3.UP, _yaw) * side * DOOR_DISTANCE
		if _walk_clear(position, door):
			_exit_point = door
			_exit_peer = peer
			_driver = 0
			_speed = 0.0
			_seated = false
			return true
	return false


func step(delta: float, positions: Dictionary, directions: Dictionary) -> void:
	if _extent == 0.0 or not is_finite(delta) or delta <= 0.0:
		return
	if _exit_peer != 0:
		if positions.has(_exit_peer):
			positions[_exit_peer] = _exit_point
		_exit_peer = 0
	if _driver == 0:
		return
	if not positions.has(_driver):
		release_peer(_driver)
		return
	var input: Variant = directions.get(_driver, Vector2.ZERO)
	var direction := Vector2.ZERO
	if input is Vector2 and input.is_finite():
		direction = input.clamp(-Vector2.ONE, Vector2.ONE)
	var remaining := minf(delta, 0.25)
	while remaining > 0.000001:
		var dt := minf(remaining, 1.0 / 30.0)
		_advance(dt, direction)
		remaining -= dt
	positions[_driver] = _seat()
	_seated = true


func _advance(dt: float, direction: Vector2) -> void:
	var throttle := -direction.y
	var target := throttle * (TOP_SPEED if throttle >= 0.0 else REVERSE_SPEED)
	_speed = move_toward(_speed, target, (DECELERATION if is_zero_approx(throttle) else ACCELERATION) * dt)
	if is_zero_approx(_speed):
		return
	var yaw_rate := clampf(_speed * tan(direction.x * 0.48) / 2.36, -1.45, 1.45)
	_yaw = wrapf(_yaw - yaw_rate * dt, -PI, PI)
	rotation.y = _yaw
	var motion := Vector3.FORWARD.rotated(Vector3.UP, _yaw) * _speed * dt
	var fraction := _sweep(position, motion, COLLISION_RADIUS)
	var end := position + motion * fraction
	if not _cover_clear(position, end, COLLISION_RADIUS):
		# A cover solver can slide an avatar along a panel. A car stops on its own heading.
		var lo := 0.0
		var hi := fraction
		for i in 12:
			var mid := (lo + hi) * 0.5
			if _cover_clear(position, position + motion * mid, COLLISION_RADIUS):
				lo = mid
			else:
				hi = mid
		fraction = lo
	if fraction < 1.0:
		fraction = maxf(0.0, fraction - SKIN / motion.length())
		_speed = 0.0
	position += motion * fraction


func _walk_clear(from: Vector3, to: Vector3) -> bool:
	return _clear(from, AVATAR_RADIUS, _extent, _buildings) and _clear(to, AVATAR_RADIUS, _extent, _buildings) \
			and _sweep(from, to - from, AVATAR_RADIUS) >= 1.0 and _cover_clear(from, to, AVATAR_RADIUS)


func _cover_clear(from: Vector3, to: Vector3, radius: float) -> bool:
	if not is_instance_valid(_cover):
		return true
	var allowed: Vector3 = _cover.call("move", from, to, radius)
	# Cover works in the street plane; boarding may start at a different height.
	return Vector2(allowed.x - to.x, allowed.z - to.z).length_squared() <= 0.00000001


func _clear(at: Vector3, radius: float, limit: float, rectangles: Array[Rect2]) -> bool:
	if not at.is_finite() or at.x < radius or at.z < radius or at.x > limit - radius or at.z > limit - radius:
		return false
	var point := Vector2(at.x, at.z)
	for rect in rectangles:
		var expanded := rect.grow(radius)
		if point.x > expanded.position.x and point.x < expanded.end.x and point.y > expanded.position.y and point.y < expanded.end.y:
			return false
	return true


func _sweep(from: Vector3, motion: Vector3, radius: float) -> float:
	var start := Vector2(from.x, from.z)
	var delta := Vector2(motion.x, motion.z)
	var fraction := 1.0
	for axis in 2:
		if delta[axis] > 0.0:
			fraction = minf(fraction, (_extent - radius - start[axis]) / delta[axis])
		elif delta[axis] < 0.0:
			fraction = minf(fraction, (radius - start[axis]) / delta[axis])
	for rect in _buildings:
		fraction = minf(fraction, _entry_fraction(start, delta, rect.grow(radius)))
	return clampf(fraction, 0.0, 1.0)


# Slab intersection finds the first contacted face, including on diagonal approaches.
func _entry_fraction(start: Vector2, motion: Vector2, rect: Rect2) -> float:
	var enter := 0.0
	var leave := 1.0
	for axis in 2:
		if is_zero_approx(motion[axis]):
			if start[axis] <= rect.position[axis] or start[axis] >= rect.end[axis]:
				return 1.0
			continue
		var a := (rect.position[axis] - start[axis]) / motion[axis]
		var b := (rect.end[axis] - start[axis]) / motion[axis]
		enter = maxf(enter, minf(a, b))
		leave = minf(leave, maxf(a, b))
		if enter >= leave:
			return 1.0
	return enter


func snapshot() -> Dictionary:
	if _extent == 0.0:
		return {}
	return {"version": 1, "position": [position.x, position.y, position.z],
			"yaw": _yaw, "speed": _speed, "driver": _driver}


func status() -> Dictionary:
	var state := snapshot()
	if not state.is_empty():
		state.position = position
	return state


func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _triplet(value: Variant) -> bool:
	return value is Array and value.size() == 3 and _number(value[0]) and _number(value[1]) and _number(value[2])


func valid_snapshot(state: Variant) -> bool:
	if _extent == 0.0 or not state is Dictionary or state.size() != 5:
		return false
	if not _number(state.get("version")) or state.version != 1 or not _triplet(state.get("position")):
		return false
	if not _number(state.get("yaw")) or absf(state.yaw) > PI or not _number(state.get("speed")):
		return false
	if state.speed < -REVERSE_SPEED or state.speed > TOP_SPEED or not _number(state.get("driver")):
		return false
	if state.driver < 0 or state.driver > MAX_PEER or state.driver != floorf(state.driver) or (state.driver == 0 and state.speed != 0.0):
		return false
	var at := Vector3(state.position[0], state.position[1], state.position[2])
	return absf(at.y - _ground_y) <= 0.001 and _clear(at, COLLISION_RADIUS, _extent, _buildings)


func restore(state: Variant) -> bool:
	if not valid_snapshot(state):
		return false
	position = Vector3(state.position[0], _ground_y, state.position[2])
	_yaw = state.yaw
	rotation.y = _yaw
	_speed = state.speed
	_driver = int(state.driver)
	_seated = _driver != 0
	_exit_peer = 0
	return true


func _part(label: String, center: Vector3, mesh: PrimitiveMesh, color: Color) -> MeshInstance3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	mesh.material = material
	var part := MeshInstance3D.new()
	part.name = label
	part.position = center
	part.mesh = mesh
	add_child(part, true)
	return part


func _box(label: String, center: Vector3, size: Vector3, color: Color) -> void:
	var mesh := BoxMesh.new()
	mesh.size = size
	_part(label, center, mesh, color)


func _build_visual() -> void:
	var paint := Color("#329a93")
	var trim := Color("#203238")
	var glass := Color("#49677a")
	_box("Chassis", Vector3(0, 0.64, 0), Vector3(1.78, 0.52, 3.66), paint)
	_box("Cab", Vector3(0, 1.11, -0.36), Vector3(1.51, 0.52, 1.51), glass)
	_box("Roof", Vector3(0, 1.41, -0.36), Vector3(1.54, 0.09, 1.55), paint)
	_box("Bed", Vector3(0, 0.91, 1.04), Vector3(1.53, 0.06, 1.28), trim)
	for side: float in [-1.0, 1.0]:
		_box("BedRail", Vector3(side * 0.84, 0.99, 1.08), Vector3(0.10, 0.20, 1.42), paint)
		_box("Headlamp", Vector3(side * 0.65, 0.73, -1.84), Vector3(0.30, 0.14, 0.05), Color("#ffecb3"))
		_box("TailLamp", Vector3(side * 0.7, 0.73, 1.84), Vector3(0.23, 0.15, 0.05), Color("#e65042"))
		for axle: float in [-1.15, 1.15]:
			var tire := CylinderMesh.new()
			tire.top_radius = 0.35
			tire.bottom_radius = 0.35
			tire.height = 0.26
			tire.radial_segments = 12
			tire.rings = 1
			var wheel := _part("Wheel", Vector3(side * 0.82, 0.35, axle), tire, trim)
			wheel.rotation.z = PI * 0.5
