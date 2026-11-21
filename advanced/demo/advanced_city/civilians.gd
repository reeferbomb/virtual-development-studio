extends Node3D
## Seeded sidewalk circuits connect three everyday destinations per resident.

const DAY_SECONDS := 720.0
const HOUR_SECONDS := DAY_SECONDS / 24.0
const START_CLOCK := 7.1 * HOUR_SECONDS
const SIDEWALK_OFFSET := 7.5
const PERSONAL_SPACE := 1.05
const PLACES := ["home", "work", "leisure"]
const DEPARTURES := [6.5, 15.0, 20.0]
const OUTFITS := [Color("337e85"), Color("e1a04f"), Color("974f67"), Color("679758"), Color("436aa2"), Color("e37e65")]
const COMPLEXIONS := [Color("edbd98"), Color("bc8665"), Color("85573d"), Color("634432")]

class Resident extends Node3D:
	var id: String
	var origin: Vector2
	var vertical: bool
	var span: Vector2
	var circuit: float
	var stops: Array[float] = []
	var shift_seconds: float
	var speed: float
	var direction: int
	var nominal: Vector2
	var forward: Vector2
	var sidestep := 0.0
	var activity: String
	var destination: String
	var moving: bool
	var limbs: Array[Node3D] = []

	func sample(clock: float) -> void:
		var local_clock := fposmod(clock - shift_seconds, DAY_SECONDS)
		var trip := 2
		if local_clock >= DEPARTURES[0] * HOUR_SECONDS and local_clock < DEPARTURES[1] * HOUR_SECONDS:
			trip = 0
		elif local_clock >= DEPARTURES[1] * HOUR_SECONDS and local_clock < DEPARTURES[2] * HOUR_SECONDS:
			trip = 1
		var next := (trip + 1) % 3
		var elapsed := fposmod(local_clock - DEPARTURES[trip] * HOUR_SECONDS, DAY_SECONDS)
		var distance := fposmod(direction * (stops[next] - stops[trip]), circuit)
		var walked := minf(distance, elapsed * speed)
		moving = walked < distance
		destination = PLACES[next]
		activity = "to_" + destination if moving else destination
		var d := fposmod(stops[trip] + direction * walked, circuit)
		var point: Vector2
		var tangent: Vector2
		if d < span.x:
			point = Vector2(d, 0.0)
			tangent = Vector2.RIGHT
		elif d < span.x + span.y:
			point = Vector2(span.x, d - span.x)
			tangent = Vector2.DOWN
		elif d < 2.0 * span.x + span.y:
			point = Vector2(2.0 * span.x + span.y - d, span.y)
			tangent = Vector2.LEFT
		else:
			point = Vector2(0.0, circuit - d)
			tangent = Vector2.UP
		nominal = origin + (Vector2(point.y, point.x) if vertical else point)
		forward = (Vector2(tangent.y, tangent.x) if vertical else tangent) * direction
		sidestep = 0.0
		var stride := 0.35 * sin(walked * 4.2) if moving else 0.0
		for i in limbs.size():
			limbs[i].rotation.x = stride if i == 0 or i == 3 else -stride

var _seed := -1
var _blocks := 0
var _size := 0.0
var _clock := START_CLOCK
var _people: Array[Resident] = []
var _box: BoxMesh
var _round: SphereMesh
var _materials: Dictionary = {}


func configure(seed: int, blocks: int, block_size: float, count: int) -> bool:
	if seed < 0 or seed > 2_147_483_647 or blocks < 3 or blocks > 8 or count < 0 or count > 40:
		return false
	if not is_finite(block_size) or block_size < 32.0 or block_size > 64.0:
		return false
	for resident in _people:
		resident.free()
	_people.clear()
	_seed = seed
	_blocks = blocks
	_size = block_size
	_clock = START_CLOCK
	if _box == null:
		_box = BoxMesh.new()
		_round = SphereMesh.new()
		_round.radial_segments = 8
		_round.rings = 4
	# Each circuit borders two adjacent blocks. Its two road crossings both lie
	# beside intersections; its six potential stops lie halfway along block faces.
	var circuits: Array[Vector3i] = []
	for z in blocks:
		for x in blocks:
			if x + 1 < blocks:
				circuits.append(Vector3i(x, z, 0))
			if z + 1 < blocks:
				circuits.append(Vector3i(x, z, 1))
	var rng := RandomNumberGenerator.new()
	rng.seed = ("city/civilians/%d" % seed).hash()
	for i in range(circuits.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var item := circuits[i]
		circuits[i] = circuits[j]
		circuits[j] = item
	for i in count:
		var person := _make_resident(i, circuits[i % circuits.size()], rng)
		_people.append(person)
		add_child(person)
	_sample()
	return true


func _make_resident(index: int, route: Vector3i, rng: RandomNumberGenerator) -> Resident:
	var npc := Resident.new()
	npc.id = "civilian-%02d" % (index + 1)
	npc.name = npc.id
	npc.vertical = route.z == 1
	npc.origin = Vector2(route.x, route.y) * _size + Vector2.ONE * SIDEWALK_OFFSET
	npc.span = Vector2(2.0 * _size, _size) - Vector2.ONE * (2.0 * SIDEWALK_OFFSET)
	npc.circuit = 2.0 * (npc.span.x + npc.span.y)
	var mid := npc.span.y * 0.5
	var opposite := npc.span.x + npc.span.y
	var stations := [mid, mid + _size, npc.span.x + mid, opposite + mid, opposite + mid + _size, opposite + npc.span.x + mid]
	npc.direction = 1 if rng.randi_range(0, 1) == 0 else -1
	var home := rng.randi_range(0, 5)
	for i in 3:
		var station := posmod(home + npc.direction * i * 2, 6)
		npc.stops.append(stations[station] + rng.randf_range(-0.10, 0.10) * _size)
	npc.shift_seconds = rng.randf_range(-0.4, 0.4) * HOUR_SECONDS
	npc.speed = rng.randf_range(1.35, 1.75)
	var coat: Color = OUTFITS[rng.randi_range(0, OUTFITS.size() - 1)]
	var skin: Color = COMPLEXIONS[rng.randi_range(0, COMPLEXIONS.size() - 1)]
	var trousers := Color("344154")
	npc.scale = Vector3.ONE * rng.randf_range(0.93, 1.08)
	_part(npc, "Coat", _box, Vector3(0, 1.06, 0), Vector3(0.46, 0.58, 0.31), coat)
	_part(npc, "Head", _round, Vector3(0, 1.54, 0), Vector3(0.33, 0.39, 0.33), skin)
	_part(npc, "Hair", _round, Vector3(0, 1.68, -0.01), Vector3(0.33, 0.16, 0.34), Color("433933"))
	for side in [-1, 1]:
		_limb(npc, "Hip%d" % side, Vector3(side * 0.12, 0.78, 0), Vector3(0.16, 0.75, 0.20), trousers)
	for side in [-1, 1]:
		_limb(npc, "Shoulder%d" % side, Vector3(side * 0.29, 1.29, 0), Vector3(0.12, 0.53, 0.14), coat)
	return npc


func _limb(npc: Resident, label: String, joint: Vector3, dimensions: Vector3, color: Color) -> void:
	var pivot := Node3D.new()
	pivot.name = label
	pivot.position = joint
	npc.add_child(pivot)
	_part(pivot, "Limb", _box, Vector3.DOWN * dimensions.y * 0.5, dimensions, color)
	npc.limbs.append(pivot)


func _part(parent: Node3D, label: String, mesh: Mesh, position_: Vector3, dimensions: Vector3, color: Color) -> void:
	if not _materials.has(color):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.9
		_materials[color] = material
	var part := MeshInstance3D.new()
	part.name = label
	part.mesh = mesh
	part.material_override = _materials[color]
	part.position = position_
	part.scale = dimensions
	parent.add_child(part)


func step(delta: float) -> void:
	if _seed < 0 or not is_finite(delta) or delta <= 0:
		return
	_clock = fposmod(_clock + fposmod(delta, DAY_SECONDS), DAY_SECONDS)
	_sample()


func _sample() -> void:
	for npc in _people:
		npc.sample(_clock)
	# Nearby walkers each give a little on their own sidewalk. Use nominal
	# positions for both participants so frame rate and update order cannot drift.
	for i in _people.size():
		var a := _people[i]
		for j in range(i + 1, _people.size()):
			var b := _people[j]
			var gap := a.nominal - b.nominal
			var distance_sq := gap.length_squared()
			if distance_sq < PERSONAL_SPACE * PERSONAL_SPACE:
				var amount := (PERSONAL_SPACE - sqrt(distance_sq)) * 0.5
				_give_space(a, gap, amount, 1.0)
				_give_space(b, -gap, amount, -1.0)
	for npc in _people:
		var right := Vector2(-npc.forward.y, npc.forward.x)
		var pose := npc.nominal + right * clampf(npc.sidestep, -0.55, 0.55)
		npc.position = Vector3(pose.x, 0.01, pose.y)
		npc.rotation.y = atan2(npc.forward.x, npc.forward.y)


func _give_space(npc: Resident, gap: Vector2, amount: float, tie: float) -> void:
	var lateral := Vector2(-npc.forward.y, npc.forward.x)
	var side := signf(lateral.dot(gap))
	if side == 0.0:
		# Resolve collinear ties in world space, even for opposite headings.
		side = tie * (lateral.x + lateral.y)
	npc.sidestep += amount * side


func _world_position(npc: Resident) -> Vector3:
	return npc.global_position if npc.is_inside_tree() else npc.position


func _row(npc: Resident) -> Dictionary:
	var p := _world_position(npc)
	return {"id": npc.id, "position": [p.x, p.y, p.z], "activity": npc.activity, "destination": npc.destination, "moving": npc.moving}


func status() -> Dictionary:
	var rows: Array = []
	for npc in _people:
		rows.append(_row(npc))
	return {"count": rows.size(), "hour": _clock / HOUR_SECONDS, "civilians": rows}


func nearest(pos: Vector3) -> Dictionary:
	if not pos.is_finite():
		return {}
	var closest: Resident
	var best := INF
	for npc in _people:
		var d := pos.distance_squared_to(_world_position(npc))
		if d < best:
			best = d
			closest = npc
	if closest == null:
		return {}
	var row := _row(closest)
	row["distance"] = sqrt(best)
	return row


func snapshot() -> Dictionary:
	if _seed < 0:
		return {}
	return {"version": 1, "seed": _seed, "blocks": _blocks, "block_size": _size, "count": _people.size(), "clock": _clock}


func _numeric(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func valid_snapshot(state: Variant) -> bool:
	if _seed < 0 or state is not Dictionary or state.size() != 6:
		return false
	if not state.has_all(["version", "seed", "blocks", "block_size", "count", "clock"]):
		return false
	for value in state.values():
		if not _numeric(value):
			return false
	return (state.version == 1 and state.seed == _seed and state.blocks == _blocks
		and state.block_size == _size and state.count == _people.size() and state.clock >= 0.0 and state.clock < DAY_SECONDS)


func restore(state: Variant) -> bool:
	if not valid_snapshot(state):
		return false
	_clock = state.clock
	_sample()
	return true
