extends Node3D
## Six hovering arcade drones play a shield-tag round. Only the host calls step().
## The simulation uses integer arena coordinates; meshes never feed back into play.

const STEP_SECONDS := 1.0 / 16.0
const MAX_TICKS := 640
const GRID := 512
const MEMBERS := 3
const COUNT := 6
const MAX_HEALTH := 100
const RANGE := 380
const COLORS := [Color("#53e8ff"), Color("#ffb752")]
const TEAMS := ["cyan", "amber"]

var _seed := -1
var _origin := Vector3.ZERO
var _extent := 0.0
var _tick := 0
var _carry := 0.0
var _agents: Array[Dictionary] = []
var _models: Array[Node3D] = []


func configure(seed_value: int, origin: Vector3, extent: float) -> bool:
	if seed_value < 0 or seed_value > 2_147_483_647 or not origin.is_finite():
		return false
	if not is_finite(extent) or extent < 2.0 or extent > 1_000_000.0:
		return false
	_seed = seed_value
	_origin = origin
	_extent = extent
	if is_inside_tree():
		global_transform = Transform3D(Basis.IDENTITY, origin)
	else:
		position = origin
	_tick = 0
	_carry = 0.0
	_agents.clear()
	for i in COUNT:
		var slot := i % MEMBERS
		var side := -1 if i < MEMBERS else 1
		_agents.append({
			"x": side * (400 + 24 * absi(slot - 1)), "z": (slot - 1) * 110 + (_seed % 41) - 20,
			"health": MAX_HEALTH, "cooldown": (_seed + 3 * i) % 9, "lock": 0,
			"target": -1, "shots": 0,
		})
		if _models.size() <= i:
			_models.append(_build_drone(i))
	_render()
	return true


func step(delta: float) -> void:
	if _agents.is_empty() or not is_finite(delta) or delta <= 0.0 or _finished():
		return
	# A round lasts at most MAX_TICKS. This also bounds catch-up after a pause.
	_carry += minf(delta, MAX_TICKS * STEP_SECONDS)
	var steps := floori((_carry + 0.0000000001) / STEP_SECONDS)
	if steps == 0:
		return
	_carry = maxf(0.0, _carry - steps * STEP_SECONDS)
	if _carry < 0.0000000001:
		_carry = 0.0
	for unused in steps:
		_advance()
		if _finished():
			_carry = 0.0
			break
	_render()


func _nearest(i: int) -> int:
	var nearest := -1
	var best := 2147483647
	var first := MEMBERS if i < MEMBERS else 0
	for j in range(first, first + MEMBERS):
		if _agents[j].health == 0:
			continue
		var distance := _separation(i, j)
		if distance < best:
			best = distance
			nearest = j
	return nearest


func _separation(i: int, j: int) -> int:
	var dx := int(_agents[i].x) - int(_agents[j].x)
	var dz := int(_agents[i].z) - int(_agents[j].z)
	return dx * dx + dz * dz


func _advance() -> void:
	_tick += 1
	# Each trio follows a common relay point and keeps its own formation slots.
	var relay_z: int = [0, 64, -32, -64][((_tick >> 5) + _seed) % 4]
	for i in COUNT:
		var agent := _agents[i]
		if agent.health == 0:
			continue
		agent.cooldown = maxi(0, int(agent.cooldown) - 1)
		agent.lock = maxi(0, int(agent.lock) - 1)
		var slot := i % MEMBERS
		var side := -1 if i < MEMBERS else 1
		var goal_x := side * (104 + absi(slot - 1) * 20)
		var goal_z := relay_z + (slot - 1) * 96
		var speed := 3 if agent.lock > 0 else 9
		agent.x += clampi(goal_x - int(agent.x), -speed, speed)
		agent.z += clampi(goal_z - int(agent.z), -speed, speed)

	# Resolve all pulses together so an earlier array slot has no first-hit privilege.
	var damage := [0, 0, 0, 0, 0, 0]
	for i in COUNT:
		var agent := _agents[i]
		if agent.health == 0:
			continue
		var target := _nearest(i)
		agent.target = target
		if target < 0 or agent.cooldown > 0 or agent.lock > 0 or _separation(i, target) > RANGE * RANGE:
			continue
		agent.shots += 1
		agent.cooldown = _pulse_interval(i, agent.shots)
		damage[target] += 11 + ((_seed + 11 * i + int(agent.shots) * 7) % 6)
	for i in COUNT:
		if damage[i] > 0:
			var agent := _agents[i]
			agent.health = maxi(0, int(agent.health) - int(damage[i]))
			agent.lock = 3 if agent.health > 0 else 0
			if agent.health == 0:
				agent.cooldown = 0
	for agent in _agents:
		if agent.health == 0 or (agent.target >= 0 and _agents[agent.target].health == 0):
			agent.target = -1


func _pulse_interval(i: int, shots: int) -> int:
	return 12 + ((_seed + 5 * i + shots * 3) % 7)


func _team_total(rows: Array, start: int, count_health: bool) -> int:
	var total := 0
	for i in range(start, start + MEMBERS):
		if rows[i].health > 0:
			total += int(rows[i].health) if count_health else 1
	return total


func _finished() -> bool:
	return _tick >= MAX_TICKS or _team_total(_agents, 0, false) == 0 or _team_total(_agents, MEMBERS, false) == 0


func _mode(i: int) -> String:
	var agent := _agents[i]
	if agent.health == 0:
		return "offline"
	if _finished():
		return "complete"
	if agent.lock > 0:
		return "suppressed"
	if agent.target >= 0 and _separation(i, agent.target) <= RANGE * RANGE:
		return "engage"
	return "formation"


func _local_position(i: int) -> Vector3:
	var span := minf(_extent, 16.0) / GRID
	return Vector3(float(_agents[i].x) * span, 0, float(_agents[i].z) * span)


func status() -> Dictionary:
	if _agents.is_empty():
		return {}
	var rows := []
	var shots := 0
	for i in COUNT:
		var world := _origin + _local_position(i)
		var agent := _agents[i]
		shots += int(agent.shots)
		rows.append({"id": i, "team": TEAMS[0 if i < MEMBERS else 1], "mode": _mode(i),
			"health": agent.health, "target": agent.target, "position": [world.x, world.y, world.z]})
	var winner := ""
	var finished := _finished()
	if finished:
		var cyan := _team_total(_agents, 0, true)
		var amber := _team_total(_agents, MEMBERS, true)
		winner = "draw" if cyan == amber else ("cyan" if cyan > amber else "amber")
	return {"tick": _tick, "phase": "finished" if finished else "active", "winner": winner,
		"alive": [_team_total(_agents, 0, false), _team_total(_agents, MEMBERS, false)],
		"shots": shots, "agents": rows}


func snapshot() -> Dictionary:
	if _agents.is_empty():
		return {}
	return {"version": 1, "seed": _seed, "origin": [_origin.x, _origin.y, _origin.z], "extent": _extent,
		"tick": _tick, "carry": _carry, "agents": _agents.duplicate(true)}


func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _integer_between(value: Variant, low: int, high: int) -> bool:
	return _number(value) and value >= low and value <= high and floorf(value) == value


func valid_snapshot(state: Variant) -> bool:
	if _agents.is_empty() or state is not Dictionary or state.size() != 7:
		return false
	if not state.has_all(["version", "seed", "origin", "extent", "tick", "carry", "agents"]):
		return false
	if not _integer_between(state.version, 1, 1) or not _integer_between(state.seed, _seed, _seed):
		return false
	if state.origin is not Array or state.origin.size() != 3 or not _number(state.extent) or state.extent != _extent:
		return false
	for axis in 3:
		if not _number(state.origin[axis]):
			return false
	if Vector3(state.origin[0], state.origin[1], state.origin[2]) != _origin:
		return false
	if not _integer_between(state.tick, 0, MAX_TICKS) or not _number(state.carry) or state.carry < 0 or state.carry >= STEP_SECONDS:
		return false
	if state.agents is not Array or state.agents.size() != COUNT:
		return false
	for i in COUNT:
		var agent: Variant = state.agents[i]
		if agent is not Dictionary or agent.size() != 7 or not agent.has_all(["x", "z", "health", "cooldown", "lock", "target", "shots"]):
			return false
		if not _integer_between(agent.x, -GRID, GRID) or not _integer_between(agent.z, -GRID, GRID):
			return false
		if not _integer_between(agent.health, 0, MAX_HEALTH) or not _integer_between(agent.cooldown, 0, 18):
			return false
		if not _integer_between(agent.lock, 0, 3) or not _integer_between(agent.shots, 0, int(state.tick)):
			return false
		if not _integer_between(agent.target, -1, COUNT - 1):
			return false
		if agent.health == 0 and (agent.target != -1 or agent.lock != 0 or agent.cooldown != 0):
			return false
	for i in COUNT:
		var target := int(state.agents[i].target)
		if target >= 0 and ((i < MEMBERS) == (target < MEMBERS) or state.agents[target].health == 0):
			return false
	var finished: bool = state.tick == MAX_TICKS or _team_total(state.agents, 0, false) == 0 or _team_total(state.agents, MEMBERS, false) == 0
	return not finished or state.carry == 0


func restore(state: Variant) -> bool:
	if not valid_snapshot(state):
		return false
	_tick = int(state.tick)
	_carry = float(state.carry)
	for i in COUNT:
		for key in _agents[i]:
			_agents[i][key] = int(state.agents[i][key])
	_render()
	return true


func _material(color: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.65
	return mat


func _part(parent: Node3D, part_name: String, mesh: Mesh, offset: Vector3, mat: Material) -> MeshInstance3D:
	var part := MeshInstance3D.new()
	part.name = part_name
	part.mesh = mesh
	part.material_override = mat
	part.position = offset
	parent.add_child(part)
	return part


func _build_drone(i: int) -> Node3D:
	var drone := Node3D.new()
	drone.name = "Drone%d" % (i + 1)
	add_child(drone)
	var squad := 0 if i < MEMBERS else 1
	var color := _material(COLORS[squad])
	var body := SphereMesh.new()
	body.radius = 0.46
	body.height = 0.44
	_part(drone, "Hull", body, Vector3.UP * 0.72, _material(Color("#243449")))
	var rim := TorusMesh.new()
	rim.inner_radius = 0.38
	rim.outer_radius = 0.48
	_part(drone, "TeamRing", rim, Vector3.UP * 0.72, color)
	var gem := PrismMesh.new()
	gem.size = Vector3(0.22, 0.18, 0.34)
	_part(drone, "Emitter", gem, Vector3(0, 0.77, -0.39), color)
	var pulse := BoxMesh.new()
	pulse.size = Vector3(0.045, 0.045, 1.0)
	_part(drone, "Pulse", pulse, Vector3.ZERO, color)
	var field := TorusMesh.new()
	field.inner_radius = 0.51
	field.outer_radius = 0.58
	_part(drone, "Shield", field, Vector3.UP * 0.63, _material(Color.WHITE))
	var caption := Label3D.new()
	caption.name = "Readout"
	caption.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	caption.position.y = 1.45
	caption.font_size = 24
	caption.pixel_size = 0.009
	caption.modulate = COLORS[squad]
	drone.add_child(caption)
	return drone


func _render() -> void:
	var model_scale := clampf(_extent / 12.0, 0.16, 1.0)
	for i in COUNT:
		var drone := _models[i]
		var agent := _agents[i]
		var mode := _mode(i)
		drone.position = _local_position(i)
		drone.scale = Vector3.ONE * model_scale
		var pulse: MeshInstance3D = drone.get_node("Pulse")
		pulse.visible = false
		if agent.target >= 0:
			var offset := _local_position(agent.target) - drone.position
			drone.rotation.y = atan2(-offset.x, -offset.z)
			if mode != "complete" and agent.shots > 0 and agent.cooldown >= _pulse_interval(i, agent.shots) - 1:
				var length := offset.length() / model_scale
				pulse.scale.z = length
				pulse.position = Vector3(0, 0.77, -length * 0.5)
				pulse.visible = true
		drone.get_node("Shield").visible = mode == "suppressed"
		drone.get_node("Emitter").visible = agent.health > 0
		drone.get_node("TeamRing").visible = agent.health > 0
		drone.get_node("Hull").position.y = 0.18 if agent.health == 0 else 0.72
		var caption: Label3D = drone.get_node("Readout")
		caption.text = "%s%d  %s" % ["C" if i < MEMBERS else "A", 1 + i % MEMBERS,
			"OFFLINE" if agent.health == 0 else "%d" % int(agent.health)]
