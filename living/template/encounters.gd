extends Node3D
## Seeded sentry posts on flat ground. Call step() from the world's physics tick.
## All public positions are world-space feet positions. Layer 1 contains solid scenery.

signal player_damaged(amount: int, enemy_id: int)

const POST_COUNT := 6
const MAX_ACTIVE := 3
const MAX_HEALTH := 100
const ENEMY_HP := 2
const ENEMY_LAYER := 16
const WORLD_LAYER := 1
const WAKE_RANGE := 28.0
const SIGHT_RANGE := 11.0
const LEASH := 17.0
const REACH := 1.45
const ATTACK_DAMAGE := 8
const ATTACK_INTERVAL := 1.25
const SHOT_INTERVAL := 0.3
const SEARCH_TIME := 5.0
const GRID_RADIUS := 6
const CELL := 1.0
const MAX_ROUTE := (GRID_RADIUS * 2 + 1) * (GRID_RADIUS * 2 + 1)
const NAV_RADIUS := LEASH + GRID_RADIUS * CELL * 2.0
const EYE := Vector3(0, 1.12, 0)
const STATES := ["patrol", "pursuit", "investigate", "return", "defeated"]

var health := MAX_HEALTH
var _seed: int
var _origin := Vector3.ZERO
var _posts: Array[Dictionary] = []
var _agents: Array[Dictionary] = []
var _bodies: Dictionary[int, StaticBody3D] = {}
var _shot_cooldown := 0.0
var _shape := CapsuleShape3D.new()

func configure(world_seed: int, origin: Vector3) -> bool:
	if not is_inside_tree() or not origin.is_finite():
		return false
	if origin.abs()[origin.abs().max_axis_index()] > 100000.0:
		return false
	for body in _bodies.values():
		body.free()
	_bodies.clear()
	_posts.clear()
	_agents.clear()
	_seed = world_seed
	_origin = origin
	health = MAX_HEALTH
	_shot_cooldown = 0.0
	_shape.radius = 0.43
	_shape.height = 1.5
	var rng := RandomNumberGenerator.new()
	rng.seed = world_seed
	var bearing := rng.randf_range(0.0, TAU)
	for id in POST_COUNT:
		var angle := bearing + TAU * id / POST_COUNT + rng.randf_range(-0.1, 0.1)
		var radial := Vector3(cos(angle), 0, sin(angle))
		var radius := rng.randf_range(1.5, 2.5) if id == 0 else rng.randf_range(9.0, 15.0)
		var home := origin + radial * radius
		var tangent := radial.cross(Vector3.UP)
		var patrol := [home + tangent * 3.0, home + radial * 2.0, home - tangent * 3.0, home]
		_posts.append({"home": home, "patrol": patrol})
		_agents.append({"position": home, "state": "patrol", "hp": ENEMY_HP,
			"waypoint": 0, "last_seen": home, "search": 0.0, "cooldown": 0.0,
			"route": [], "replan": 0.0})
	_activate_near(origin)
	return true

func _activate_near(player: Vector3) -> void:
	var ranked: Array = []
	for id in _agents.size():
		var distance: float = _posts[id].home.distance_to(player)
		if _agents[id].hp > 0 and distance <= WAKE_RANGE:
			# A small preference for existing actors avoids swapping at post boundaries.
			ranked.append([distance - (2.0 if _bodies.has(id) else 0.0), id])
	ranked.sort_custom(func(a: Array, b: Array) -> bool:
		return a[1] < b[1] if a[0] == b[0] else a[0] < b[0])
	var wanted: Array[int] = []
	for i in mini(MAX_ACTIVE, ranked.size()):
		wanted.append(int(ranked[i][1]))
	for id: int in _bodies.keys():
		if not wanted.has(id):
			_remove_body(id)
	for id in wanted:
		if not _bodies.has(id):
			_spawn_body(id)

func _remove_body(id: int) -> void:
	_bodies[id].free()
	_bodies.erase(id)

func _spawn_body(id: int) -> void:
	var body := StaticBody3D.new()
	body.name = "Sentry%d" % id
	body.collision_layer = ENEMY_LAYER
	body.collision_mask = 0
	body.set_meta(&"sentry_id", id)
	var collider := CollisionShape3D.new()
	collider.name = "HullCollider"
	collider.position.y = 0.8
	collider.shape = _shape
	body.add_child(collider)
	# The dark head and luminous eye ring make the sentry readable from every side.
	_mesh_part(body, "Hull", 0.28, 0.40, 0.83, 0.64, Color("#b66a42"))
	_mesh_part(body, "Head", 0.35, 0.38, 0.39, 1.21, Color("#2d3442"))
	_mesh_part(body, "EyeRing", 0.386, 0.386, 0.10, 1.23, Color("#ff694a"))
	add_child(body)
	body.global_position = _agents[id].position
	_bodies[id] = body

func _mesh_part(body: Node3D, part_name: String, top: float, bottom: float, height: float, y: float, color: Color) -> void:
	var mesh := CylinderMesh.new()
	mesh.radial_segments = 8
	mesh.rings = 0
	mesh.top_radius = top
	mesh.bottom_radius = bottom
	mesh.height = height
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	if part_name == "EyeRing":
		material.emission_enabled = true
		material.emission = color
	mesh.material = material
	var part := MeshInstance3D.new()
	part.name = part_name
	part.mesh = mesh
	part.position.y = y
	body.add_child(part)

func step(delta: float, player_position: Vector3) -> void:
	if _agents.is_empty() or not is_inside_tree() or not player_position.is_finite() or not is_finite(delta) or delta <= 0:
		return
	_shot_cooldown = maxf(0.0, _shot_cooldown - delta)
	_activate_near(player_position)
	for id in _agents.size():
		if _bodies.has(id):
			_step_agent(id, delta, player_position)

func _step_agent(id: int, delta: float, player: Vector3) -> void:
	var actor := _agents[id]
	var home: Vector3 = _posts[id].home
	var p: Vector3 = actor.position
	var gap := p.distance_to(player)
	actor.cooldown = maxf(0.0, float(actor.cooldown) - delta)
	actor.replan = maxf(0.0, float(actor.replan) - delta)
	var visible := health > 0 and gap <= SIGHT_RANGE and home.distance_to(player) <= LEASH and _visible_from(p, player)
	var target: Vector3
	var speed := 1.15
	if visible:
		actor.state = "pursuit"
		actor.last_seen = Vector3(player.x, home.y, player.z)
		actor.search = SEARCH_TIME
		if gap <= REACH:
			if actor.cooldown <= 0.0:
				actor.cooldown = ATTACK_INTERVAL
				var damage := mini(ATTACK_DAMAGE, health)
				health -= damage
				player_damaged.emit(damage, id)
			return
		target = actor.last_seen
		speed = 2.8
	else:
		if actor.state == "pursuit":
			actor.state = "investigate"
		if actor.state == "investigate":
			actor.search = maxf(0.0, float(actor.search) - delta)
			if actor.search <= 0.0:
				actor.state = "return"
				actor.route.clear()
				actor.replan = 0.0
		match actor.state:
			"investigate":
				target = actor.last_seen
				speed = 2.1
			"return":
				target = home
				speed = 1.8
				if p.distance_to(home) <= 0.15:
					actor.state = "patrol"
			_:
				var patrol: Array = _posts[id].patrol
				target = patrol[actor.waypoint]
				if p.distance_to(target) <= 0.15:
					actor.waypoint = (int(actor.waypoint) + 1) % patrol.size()
					target = patrol[actor.waypoint]
	_move(id, target, speed * delta)

func _visible_from(p: Vector3, player: Vector3) -> bool:
	if (p + EYE).is_equal_approx(player + EYE):
		return true
	var ray := PhysicsRayQueryParameters3D.create(p + EYE, player + EYE, WORLD_LAYER)
	ray.hit_from_inside = true
	return get_world_3d().direct_space_state.intersect_ray(ray).is_empty()

# Sweep the entire hull, including its radius, before accepting any movement segment.
func _clear(p: Vector3, to: Vector3) -> bool:
	if p.is_equal_approx(to):
		return true
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = _shape
	query.transform.origin = p + Vector3.UP * 0.8
	query.collision_mask = WORLD_LAYER
	query.margin = 0.012
	query.motion = to - p
	var fractions := get_world_3d().direct_space_state.cast_motion(query)
	return fractions.size() == 2 and fractions[0] >= 1.0

func _move(id: int, target: Vector3, distance: float) -> void:
	var actor := _agents[id]
	var p: Vector3 = actor.position
	if p.distance_to(target) < 0.03:
		return
	var next := target
	if _clear(p, target):
		actor.route.clear()
		actor.replan = 0.0
	else:
		if not actor.route.is_empty() and not _clear(p, actor.route[0]):
			actor.route.clear()
		if actor.route.is_empty() and actor.replan <= 0.0:
			actor.route = _detour(p, target, _posts[id].home)
			actor.replan = 0.5
		if actor.route.is_empty():
			return
		next = actor.route[0]
	var destination := p.move_toward(next, distance)
	if not _clear(p, destination):
		return
	actor.position = destination
	_bodies[id].global_position = destination
	if not actor.route.is_empty() and destination.distance_to(next) < 0.02:
		actor.route.pop_front()

# Breadth-first search on a bounded local grid. Check each edge with the same hull
# sweep used by movement. Stop when a visited cell has a clear segment to the goal.
func _detour(start: Vector3, goal: Vector3, home: Vector3) -> Array:
	var queue: Array[Vector2i] = [Vector2i.ZERO]
	var previous := {Vector2i.ZERO: Vector2i.ZERO}
	var best := Vector2i.ZERO
	var closest := start.distance_squared_to(goal)
	var cursor := 0
	while cursor < queue.size():
		var cell := queue[cursor]
		cursor += 1
		var p := start + Vector3(cell.x * CELL, 0.0, cell.y * CELL)
		if cell != Vector2i.ZERO and _clear(p, goal):
			best = cell
			break
		for direction: Vector2i in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
			var neighbor := cell + direction
			if absi(neighbor.x) > GRID_RADIUS or absi(neighbor.y) > GRID_RADIUS or previous.has(neighbor):
				continue
			var destination := start + Vector3(neighbor.x * CELL, 0.0, neighbor.y * CELL)
			if destination.distance_to(home) > NAV_RADIUS or not _clear(p, destination):
				continue
			previous[neighbor] = cell
			queue.append(neighbor)
			var remaining := destination.distance_squared_to(goal)
			if remaining < closest:
				closest = remaining
				best = neighbor
	var route: Array = []
	while best != Vector2i.ZERO:
		route.push_front(start + Vector3(best.x * CELL, 0.0, best.y * CELL))
		best = previous[best]
	return route

func shoot(origin: Vector3, direction: Vector3) -> Dictionary:
	var result := {"fired": false, "hit": false, "defeated": false, "id": -1}
	if _agents.is_empty() or not is_inside_tree() or _shot_cooldown > 0.0 or not origin.is_finite() or not direction.is_finite():
		return result
	var aim := direction.normalized()
	if aim.is_zero_approx() or not aim.is_finite():
		return result
	result.fired = true
	_shot_cooldown = SHOT_INTERVAL
	var ray := PhysicsRayQueryParameters3D.create(origin, origin + aim * 55.0, WORLD_LAYER | ENEMY_LAYER)
	ray.hit_from_inside = true
	var impact := get_world_3d().direct_space_state.intersect_ray(ray)
	if impact.is_empty() or not impact.collider is StaticBody3D:
		return result
	var id: int = impact.collider.get_meta(&"sentry_id", -1)
	if not _bodies.has(id) or _bodies[id] != impact.collider:
		return result
	var actor := _agents[id]
	actor.hp -= 1
	result.hit = true
	result.id = id
	if actor.hp == 0:
		result.defeated = true
		actor.state = "defeated"
		actor.route.clear()
		_remove_body(id)
	return result

func heal(amount: int) -> bool:
	if _agents.is_empty() or amount <= 0 or health >= MAX_HEALTH:
		return false
	health += mini(amount, MAX_HEALTH - health)
	return true

func _pack(p: Vector3) -> Array:
	return [p.x, p.y, p.z]

func _unpack(v: Array) -> Vector3:
	return Vector3(v[0], v[1], v[2])

func status() -> Dictionary:
	var enemies: Array = []
	var alive := 0
	for id in _agents.size():
		var a := _agents[id]
		if a.hp > 0:
			alive += 1
		enemies.append({"id": id, "state": a.state, "hp": a.hp, "active": _bodies.has(id),
			"position": _pack(a.position), "home": _pack(_posts[id].home)})
	return {"health": health, "active_count": _bodies.size(), "alive_count": alive, "enemies": enemies}

func snapshot() -> Dictionary:
	var enemies: Array = []
	for id in _agents.size():
		var a := _agents[id]
		var path: Array = []
		for p: Vector3 in a.route:
			path.append(_pack(p))
		enemies.append({"id": id, "position": _pack(a.position), "state": a.state, "hp": a.hp,
			"waypoint": a.waypoint, "last_seen": _pack(a.last_seen), "search": a.search,
			"cooldown": a.cooldown, "replan": a.replan, "route": path, "active": _bodies.has(id)})
	# A string preserves all 64 seed bits through a JSON numeric round trip.
	return {"seed": str(_seed), "origin": _pack(_origin), "health": health, "shot_cooldown": _shot_cooldown, "enemies": enemies}

func _number(v: Variant, minimum: float, maximum: float) -> bool:
	return (v is int or v is float) and is_finite(float(v)) and v >= minimum and v <= maximum

func _whole(v: Variant, minimum: int, maximum: int) -> bool:
	return _number(v, minimum, maximum) and float(v) == floorf(float(v))

func _point(v: Variant) -> bool:
	if not v is Array or v.size() != 3:
		return false
	for axis in v:
		if not _number(axis, -101000.0, 101000.0):
			return false
	return true

func _near_post(v: Variant, home: Vector3) -> bool:
	if not _point(v):
		return false
	var p := _unpack(v)
	return p.y == home.y and p.distance_to(home) <= NAV_RADIUS

func valid_snapshot(data: Dictionary) -> bool:
	if _posts.size() != POST_COUNT or data.size() != 5 or not data.has_all(["seed", "origin", "health", "shot_cooldown", "enemies"]):
		return false
	if not data.seed is String or data.seed != str(_seed) or not _point(data.origin) or _unpack(data.origin) != _origin:
		return false
	if not _whole(data.health, 0, MAX_HEALTH) or not _number(data.shot_cooldown, 0.0, SHOT_INTERVAL):
		return false
	if not data.enemies is Array or data.enemies.size() != POST_COUNT:
		return false
	var active := 0
	for id in POST_COUNT:
		var row: Variant = data.enemies[id]
		if not row is Dictionary or row.size() != 11 or not row.has_all(["id", "position", "state", "hp", "waypoint", "last_seen", "search", "cooldown", "replan", "route", "active"]):
			return false
		if not _whole(row.id, id, id) or not _whole(row.hp, 0, ENEMY_HP) or not _whole(row.waypoint, 0, 3):
			return false
		if not row.state is String or not STATES.has(row.state) or not row.active is bool:
			return false
		if (row.hp == 0) != (row.state == "defeated") or (row.active and row.hp == 0):
			return false
		if not _number(row.search, 0.0, SEARCH_TIME) or not _number(row.cooldown, 0.0, ATTACK_INTERVAL) or not _number(row.replan, 0.0, 0.5):
			return false
		var home: Vector3 = _posts[id].home
		if not _near_post(row.position, home) or not _near_post(row.last_seen, home) or not row.route is Array or row.route.size() > MAX_ROUTE:
			return false
		for p in row.route:
			if not _near_post(p, home):
				return false
		if row.active:
			active += 1
	return active <= MAX_ACTIVE

func restore(data: Dictionary) -> bool:
	if not valid_snapshot(data):
		return false
	health = int(data.health)
	_shot_cooldown = float(data.shot_cooldown)
	# Discard retired bodies before creating replacements to preserve the live cap.
	for id: int in _bodies.keys():
		if not data.enemies[id].active:
			_remove_body(id)
	for id in POST_COUNT:
		var row: Dictionary = data.enemies[id]
		var path: Array = []
		for v in row.route:
			path.append(_unpack(v))
		_agents[id] = {"position": _unpack(row.position), "state": row.state, "hp": int(row.hp),
			"waypoint": int(row.waypoint), "last_seen": _unpack(row.last_seen),
			"search": float(row.search), "cooldown": float(row.cooldown),
			"replan": float(row.replan), "route": path}
		if row.active:
			if not _bodies.has(id):
				_spawn_body(id)
			_bodies[id].global_position = _agents[id].position
	return true
