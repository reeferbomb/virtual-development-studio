extends CharacterBody3D

const TACTICAL_PLAN_INTERVAL := 0.6
const FLANK_DISTANCE := 2.5
const SUPPORT_DISTANCE := 4.0

var health := 50
var state := "patrol"
var target: CharacterBody3D
var navigator: RefCounted
var tactical := false
var squad: RefCounted
var tactical_role := ""
var tactical_goal := Vector3.ZERO
var _approach_axis := Vector3.BACK
var patrol: Array[Vector3] = []
var patrol_index := 0
var game: Node
var path := PackedVector3Array()
var replan := 0.0
var attack_cooldown := 0.0
var body_mesh: MeshInstance3D

func _ready() -> void:
	collision_layer = 4
	collision_mask = 1
	var shape := CapsuleShape3D.new()
	shape.radius = 0.38
	shape.height = 1.8
	var collider := CollisionShape3D.new()
	collider.shape = shape
	collider.position.y = 0.9
	add_child(collider)
	body_mesh = MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = 0.38
	mesh.height = 1.8
	body_mesh.mesh = mesh
	body_mesh.position.y = 0.9
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.82, 0.24, 0.16)
	body_mesh.material_override = mat
	add_child(body_mesh)

func set_health(value: int) -> void:
	health = clampi(value, 0, 50)
	visible = health > 0
	collision_layer = 4 if health > 0 else 0
	if health == 0:
		state = "dead"
		velocity = Vector3.ZERO
		if tactical and squad != null:
			squad.forget(str(name))
	else:
		state = "patrol"
	if tactical:
		tactical_role = ""
		tactical_goal = position
	path.clear()
	replan = 0.0
	attack_cooldown = 0.0

func take_damage(value: int) -> void:
	if health <= 0 or value <= 0:
		return
	if tactical and value < health:
		health -= value
		return
	set_health(health - value)
	if health == 0:
		game.mission.eliminate(str(name))

func _can_see() -> bool:
	var a := global_position + Vector3.UP * 1.2
	var b := target.global_position + Vector3.UP * 1.2
	if a.distance_to(b) > 8.0:
		return false
	return _clear_sight(a, b)

func _clear_sight(from_eye: Vector3, to_eye: Vector3) -> bool:
	var ray := PhysicsRayQueryParameters3D.create(from_eye, to_eye, 1)
	return get_world_3d().direct_space_state.intersect_ray(ray).is_empty()

func _attack() -> void:
	state = "attack"
	if attack_cooldown <= 0:
		game.combat.damage(6)
		attack_cooldown = 1.2

func _patrol_destination() -> Vector3:
	if patrol.is_empty():
		return global_position
	if Vector2(global_position.x-patrol[patrol_index].x,global_position.z-patrol[patrol_index].z).length() < 0.45:
		patrol_index = (patrol_index + 1) % patrol.size()
	return patrol[patrol_index]

func _physics_process(delta: float) -> void:
	if health <= 0 or target == null or game.combat.health <= 0 or game.mission.completed:
		return
	attack_cooldown = maxf(0.0, attack_cooldown - delta)
	replan -= delta
	if tactical and squad != null:
		var speed := _tactical_decision()
		_move_along_path(delta, speed)
		return
	var destination := global_position
	var speed := 1.8
	if _can_see():
		if global_position.distance_to(target.global_position) <= 3.0:
			_attack()
		else:
			state = "chase"
			destination = target.global_position
			speed = 3.0
	else:
		state = "patrol"
		destination = _patrol_destination()
	if state != "attack" and replan <= 0:
		path = navigator.plan(global_position, destination)
		replan = 0.4
	_move_along_path(delta, speed)

func _tactical_decision() -> float:
	var sees_player := _can_see()
	var id := str(name)
	if sees_player:
		squad.report(id, target.global_position)
	var intel: Dictionary = squad.intel(id)
	if not intel.active:
		if not tactical_role.is_empty():
			tactical_role = ""
			tactical_goal = global_position
			path.clear()
		state = "patrol"
		var waypoint := _patrol_destination()
		if replan <= 0:
			_plan_direct(waypoint)
			replan = TACTICAL_PLAN_INTERVAL
		return 1.8

	var focus: Vector3 = intel.target
	if tactical_role != intel.role:
		tactical_role = intel.role
		# Keep the approach direction for this assignment so a flanker can reach its post.
		_approach_axis = global_position - focus
		_approach_axis.y = 0.0
		_approach_axis = Vector3.BACK if _approach_axis.is_zero_approx() else _approach_axis.normalized()
		path.clear()
		tactical_goal = global_position
	if sees_player and global_position.distance_to(target.global_position) <= 3.0:
		_attack()
		path.clear()
		tactical_goal = global_position
		return 0.0

	state = "investigate"
	if sees_player:
		match tactical_role:
			"flanker": state = "flank"
			"support": state = "support"
			_: state = "chase"
	if replan <= 0:
		if tactical_role == "pursuer":
			_plan_direct(focus)
		else:
			_plan_formation(focus)
		replan = TACTICAL_PLAN_INTERVAL
	return 2.2 if tactical_role == "support" else 3.0

func _plan_direct(destination: Vector3) -> void:
	path = navigator.plan(global_position, destination)
	tactical_goal = destination if not path.is_empty() or _at_post(destination) else global_position

func _at_post(point: Vector3) -> bool:
	return Vector2(point.x - global_position.x, point.z - global_position.z).length() <= 0.2

func _plan_formation(focus: Vector3) -> void:
	var side := Vector3(-_approach_axis.z, 0, _approach_axis.x)
	var wants_cover := tactical_role == "support"
	var candidates: Array[Vector3]
	if wants_cover:
		var rear := focus + _approach_axis * SUPPORT_DISTANCE
		candidates = [rear, rear + side * 2.0, rear - side * 2.0]
	else:
		candidates = [focus + side * FLANK_DISTANCE, focus - side * FLANK_DISTANCE]

	# The first reachable post is a fallback if none offers the role's preferred sightline.
	var has_fallback := false
	for candidate in candidates:
		var route: PackedVector3Array = navigator.plan(global_position, candidate)
		if route.is_empty() and not _at_post(candidate):
			continue
		var from_eye := Vector3(candidate.x, global_position.y + 1.2, candidate.z)
		var clear := _clear_sight(from_eye, focus + Vector3.UP * 1.2)
		if clear != wants_cover:
			path = route
			tactical_goal = candidate
			return
		if not has_fallback:
			path = route
			tactical_goal = candidate
			has_fallback = true
	if not has_fallback:
		_plan_direct(focus)

func _move_along_path(delta: float, speed: float) -> void:
	velocity.x = 0
	velocity.z = 0
	if state != "attack":
		while path.size() > 0:
			var offset: Vector3 = path[0] - global_position
			offset.y = 0
			if offset.length() > 0.2:
				var step := offset.normalized() * speed
				velocity.x = step.x
				velocity.z = step.z
				break
			path.remove_at(0)
	if not is_on_floor():
		velocity += get_gravity() * delta
	move_and_slide()
