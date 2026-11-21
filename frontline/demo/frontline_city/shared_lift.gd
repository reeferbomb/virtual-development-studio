extends Node3D

## A single-passenger observation lift. The session supplies city-local positions
## on the host and restores snapshots on observers. There are no RPCs or timers.
const HEIGHT := 6.0
const SPEED := 2.0
const BOARD_RADIUS := 2.2
const MAX_PEER := 2147483647
const STEEL := Color("#354654")
const PLATFORM := Color("#9eb4bb")
const SAFETY := Color("#f4b54b")

var _cab: Node3D
var _cab_gate: MeshInstance3D
var _street_gate: MeshInstance3D
var _phase := "ground"
var _height := 0.0
var _rider := 0


func configure(origin: Vector3) -> bool:
	if not origin.is_finite():
		return false
	position = origin
	if _cab == null:
		_build()
	_phase = "ground"
	_height = 0.0
	_rider = 0
	_render()
	return true


func occupied(peer: int) -> bool:
	return peer > 0 and peer == _rider


func request(peer: int, at: Vector3) -> bool:
	if _cab == null or peer < 1 or peer > MAX_PEER or not at.is_finite():
		return false
	var offset := at - (position + Vector3.UP * _height)
	if absf(offset.y) > 0.75 or Vector2(offset.x, offset.z).length_squared() > BOARD_RADIUS * BOARD_RADIUS:
		return false
	if _rider == 0:
		if _phase != "ground":
			return false
		_rider = peer
	elif _rider != peer:
		return false
	else:
		match _phase:
			"ground":
				_phase = "ascending"
			"upper":
				_phase = "descending"
			"returned":
				_rider = 0
				_phase = "ground"
			_:
				return false
	_render()
	return true


func release_peer(peer: int) -> void:
	if not occupied(peer):
		return
	_rider = 0
	_phase = "descending" if _height > 0.0 else "ground"
	_render()


func step(delta: float, positions: Dictionary, _directions: Dictionary) -> void:
	if _cab == null or not is_finite(delta) or delta <= 0.0:
		return
	if _rider != 0 and not positions.has(_rider):
		release_peer(_rider)
	if _phase == "ascending":
		_height = move_toward(_height, HEIGHT, SPEED * delta)
		if is_equal_approx(_height, HEIGHT):
			_height = HEIGHT
			_phase = "upper"
	elif _phase == "descending":
		_height = move_toward(_height, 0.0, SPEED * delta)
		if is_zero_approx(_height):
			_height = 0.0
			_phase = "ground" if _rider == 0 else "returned"
	if _rider != 0:
		positions[_rider] = position + Vector3.UP * _height
	_render()


func snapshot() -> Dictionary:
	return {"version": 1, "phase": _phase, "height": _height, "rider": _rider}


func _number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


func valid_snapshot(state: Variant) -> bool:
	if not state is Dictionary or state.size() != 4 or not state.has_all(["version", "phase", "height", "rider"]):
		return false
	if not _number(state.version) or state.version != 1 or not state.phase is String:
		return false
	if not _number(state.rider) or state.rider < 0 or state.rider > MAX_PEER or floorf(state.rider) != state.rider:
		return false
	if not _number(state.height) or state.height < 0.0 or state.height > HEIGHT:
		return false
	match state.phase:
		"ground":
			return state.height == 0.0
		"ascending":
			return state.rider > 0 and state.height < HEIGHT
		"upper":
			return state.rider > 0 and state.height == HEIGHT
		"descending":
			return state.height > 0.0
		"returned":
			return state.rider > 0 and state.height == 0.0
	return false


func restore(state: Variant) -> bool:
	if _cab == null or not valid_snapshot(state):
		return false
	_phase = state.phase
	_height = float(state.height)
	_rider = int(state.rider)
	_render()
	return true


func _box(parent: Node3D, label: String, center: Vector3, size_m: Vector3, color: Color) -> MeshInstance3D:
	var mesh := BoxMesh.new()
	mesh.size = size_m
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	mesh.material = material
	var piece := MeshInstance3D.new()
	piece.name = label
	piece.mesh = mesh
	piece.position = center
	parent.add_child(piece)
	return piece


func _build() -> void:
	_cab = Node3D.new()
	_cab.name = "Cab"
	add_child(_cab)
	_box(_cab, "Deck", Vector3(0, -0.08, 0), Vector3(2.2, 0.16, 2.1), PLATFORM)
	for side: int in [-1, 1]:
		_box(self, "Guide%d" % side, Vector3(side * 1.2, 4.1, -0.92), Vector3(0.13, 8.2, 0.15), STEEL)
		_box(_cab, "SideRail%d" % side, Vector3(side, 1.0, 0), Vector3(0.09, 0.09, 2.0), SAFETY)
		for end: int in [-1, 1]:
			_box(_cab, "Post%d_%d" % [side, end], Vector3(side, 0.5, end * 0.94), Vector3(0.08, 1.0, 0.08), STEEL)
	_box(_cab, "RearRail", Vector3(0, 1, -0.94), Vector3(2.05, 0.1, 0.1), SAFETY)
	_cab_gate = _box(_cab, "CabGate", Vector3(0, 1, 0.94), Vector3(2.05, 0.14, 0.10), SAFETY)
	_box(self, "Crossbeam", Vector3(0, 8.1, -0.92), Vector3(2.55, 0.22, 0.24), STEEL)
	_box(self, "UpperLanding", Vector3(0, HEIGHT - 0.09, -1.64), Vector3(2.55, 0.18, 1.13), PLATFORM)
	_box(self, "UpperBarrier", Vector3(0, HEIGHT + 1.0, -1.12), Vector3(2.55, 0.15, 0.12), STEEL)
	_street_gate = _box(self, "StreetGate", Vector3(0, 1.0, 1.16), Vector3(2.25, 0.16, 0.12), SAFETY)
	var sign := Label3D.new()
	sign.name = "LiftSign"
	sign.position = Vector3(0, 7.95, -0.78)
	sign.text = "OBSERVATION LIFT"
	sign.font_size = 42
	sign.pixel_size = 0.004
	sign.outline_size = 7
	add_child(sign)


func _render() -> void:
	_cab.position.y = _height
	# The observation stop keeps its front gate closed. Players exit at street level.
	var street_open := _phase == "ground" or _phase == "returned"
	_cab_gate.visible = not street_open
	_street_gate.visible = not street_open
