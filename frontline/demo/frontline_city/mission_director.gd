extends Node3D
## The host supplies the peer's authoritative world position to request().
## Replicas rebuild their own markers from validated, JSON-safe snapshots.

const STAGES := 3
const REACH := 2.8
const TIME_LIMIT := 240.0
const MAX_PEER := 2147483647
const MAX_ROUND := 2147483647
const DIRECTIONS := [Vector3.RIGHT, Vector3.FORWARD, Vector3.LEFT, Vector3.BACK]
const STREETS := ["East Gate", "North Arcade", "West Exchange", "South Depot"]
const TITLES := ["Relay repair", "Medical delivery", "Street survey"]
const TASKS := [
	["Collect a relay cell", "Install the relay cell", "Confirm the signal"],
	["Collect the medical kit", "Register the delivery", "Deliver the kit"],
	["Collect a survey meter", "Record a street reading", "File the survey"],
]
const FIELDS := ["version", "world", "round", "phase", "stage", "remaining_ms", "score", "contributors"]

var _world := ""
var _seed_value := 0
var _dispatch := Vector3.ZERO
var _junction := Vector3.ZERO
var _radius := 0.0
var _round := 1
var _phase := "active"
var _actors: Array[int] = []
var _remaining_ms := TIME_LIMIT * 1000.0
var _authoritative := true
var _marker: Node3D
var _sign: Label3D
var _material: StandardMaterial3D


func configure(world_seed: int, origin: Vector3, extent: float, block_size: float) -> bool:
	if not _world.is_empty() or not origin.is_finite() or not is_finite(extent) or not is_finite(block_size):
		return false
	# These are the supported city dimensions. All four spokes stay inside
	# the map, and their interaction spheres are disjoint even on a 32 m block.
	if block_size < 32.0 or block_size > 64.0 or extent < block_size * 3.0 or extent > block_size * 8.0:
		return false
	if not is_equal_approx(extent, roundf(extent / block_size) * block_size):
		return false
	if origin.x < 0.0 or origin.z < 0.0 or origin.x > extent or origin.z > extent:
		return false
	var grid_x := snappedf(origin.x, block_size)
	var grid_z := snappedf(origin.z, block_size)
	if minf(absf(origin.x - grid_x), absf(origin.z - grid_z)) > 6.0:
		return false
	_world = JSON.stringify([str(world_seed), origin.x, origin.y, origin.z, extent, block_size], "", false, true).sha256_text()
	_seed_value = world_seed
	_dispatch = origin
	_junction = Vector3(clampf(grid_x, block_size, extent - block_size), origin.y, clampf(grid_z, block_size, extent - block_size))
	_radius = block_size * 0.25
	_make_marker()
	_refresh_marker()
	return true


func set_authoritative(enabled: bool) -> void:
	_authoritative = enabled


func _kind() -> int:
	return posmod(posmod(_seed_value, TITLES.size()) + _round - 1, TITLES.size())


func _direction() -> int:
	var turn := 1 if posmod(_seed_value, 2) == 1 else -1
	return posmod(posmod(_seed_value, 4) + _round - 1 + turn * _actors.size(), 4)


func target_position() -> Vector3:
	if _phase == "active" and not _world.is_empty():
		return _junction + DIRECTIONS[_direction()] * _radius
	return _dispatch


func request(peer: int, point: Vector3) -> bool:
	if not _authoritative or _world.is_empty() or peer < 1 or peer > MAX_PEER or not point.is_finite():
		return false
	if point.distance_squared_to(target_position()) > REACH * REACH:
		return false
	if _phase != "active":
		return restart()
	_actors.append(peer)
	if _actors.size() == STAGES:
		_phase = "completed"
	_refresh_marker()
	return true


func restart() -> bool:
	if not _authoritative or _world.is_empty() or _phase == "active" or _round >= MAX_ROUND:
		return false
	_round += 1
	_phase = "active"
	_actors.clear()
	_remaining_ms = TIME_LIMIT * 1000.0
	_refresh_marker()
	return true


func step(delta: float) -> void:
	if not _authoritative or _world.is_empty() or _phase != "active" or not is_finite(delta) or delta <= 0.0:
		return
	_remaining_ms = maxf(0.0, _remaining_ms - delta * 1000.0)
	if _remaining_ms == 0.0:
		_phase = "failed"
		_refresh_marker()


func _score(actors: Array) -> int:
	# Every handoff counts once. Bringing in another teammate earns a bonus.
	var unique := {}
	for peer in actors:
		unique[int(peer)] = true
	var completion := 100 if actors.size() == STAGES else 0
	return 100 * actors.size() + 25 * maxi(0, unique.size() - 1) + completion


func snapshot() -> Dictionary:
	if _world.is_empty():
		return {}
	return {"version": 1, "world": _world, "round": _round, "phase": _phase,
		"stage": _actors.size(), "remaining_ms": ceili(_remaining_ms),
		"score": _score(_actors), "contributors": _actors.duplicate()}


func _whole(value: Variant, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) \
		and value >= low and value <= high and value == floorf(float(value))


func valid_snapshot(data: Variant) -> bool:
	if _world.is_empty() or not data is Dictionary or data.size() != FIELDS.size() or not data.has_all(FIELDS):
		return false
	if not _whole(data.version, 1, 1) or not data.world is String or data.world != _world:
		return false
	if not _whole(data.round, 1, MAX_ROUND) or not _whole(data.stage, 0, STAGES):
		return false
	if not _whole(data.remaining_ms, 0, int(TIME_LIMIT * 1000.0)) or not data.phase is String:
		return false
	match data.phase:
		"active":
			if data.stage >= STAGES or data.remaining_ms == 0:
				return false
		"completed":
			if data.stage != STAGES or data.remaining_ms == 0:
				return false
		"failed":
			if data.stage >= STAGES or data.remaining_ms != 0:
				return false
		_:
			return false
	if not data.contributors is Array or data.contributors.size() != int(data.stage):
		return false
	for peer in data.contributors:
		if not _whole(peer, 1, MAX_PEER):
			return false
	var expected := _score(data.contributors)
	return _whole(data.score, expected, expected)


func restore(data: Variant) -> bool:
	if not valid_snapshot(data):
		return false
	var update_marker: bool = _round != int(data.round) or _phase != data.phase or _actors.size() != int(data.stage)
	_round = int(data.round)
	_phase = data.phase
	_actors.clear()
	for actor in data.contributors:
		_actors.append(int(actor))
	_remaining_ms = float(data.remaining_ms)
	if update_marker:
		_refresh_marker()
	return true


func status() -> Dictionary:
	if _world.is_empty():
		return {}
	var objective := "Return to dispatch for the next contract"
	if _phase == "active":
		objective = "%s · %s" % [TASKS[_kind()][_actors.size()], STREETS[_direction()]]
	return {"phase": _phase, "stage": _actors.size(), "stage_count": STAGES, "round": _round,
		"title": TITLES[_kind()], "objective": objective, "target": target_position(),
		"score": _score(_actors), "time_left": _remaining_ms / 1000.0, "contributors": _actors.duplicate()}


func _make_marker() -> void:
	_marker = Node3D.new()
	_marker.name = "MissionBeacon"
	_marker.top_level = true
	add_child(_marker)
	_material = StandardMaterial3D.new()
	_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var ring := TorusMesh.new()
	ring.inner_radius = 1.20
	ring.outer_radius = 1.34
	ring.rings = 32
	ring.ring_segments = 8
	ring.material = _material
	var base := MeshInstance3D.new()
	base.mesh = ring
	base.position.y = 0.1
	base.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_marker.add_child(base)
	var tip := CylinderMesh.new()
	tip.top_radius = 0.36
	tip.bottom_radius = 0.0
	tip.height = 0.62
	tip.radial_segments = 4
	tip.material = _material
	var pointer := MeshInstance3D.new()
	pointer.mesh = tip
	pointer.position.y = 1.65
	pointer.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_marker.add_child(pointer)
	_sign = Label3D.new()
	_sign.pixel_size = 0.0045
	_sign.font_size = 42
	_sign.outline_size = 9
	_sign.position.y = 2.6
	_sign.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_marker.add_child(_sign)


func _refresh_marker() -> void:
	_marker.position = target_position()
	if _phase == "active":
		_material.albedo_color = Color("#64f2da")
		_sign.text = "%s · %d/%d\n%s" % [TITLES[_kind()].to_upper(), _actors.size() + 1, STAGES, TASKS[_kind()][_actors.size()]]
	else:
		_material.albedo_color = Color("#8ce6ac") if _phase == "completed" else Color("#ffbe78")
		_sign.text = "DISPATCH · %s\nStart next contract" % _phase.to_upper()
	_sign.modulate = _material.albedo_color
