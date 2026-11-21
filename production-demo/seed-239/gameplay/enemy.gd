extends CharacterBody3D

var health := 50
var state := "patrol"
var target: CharacterBody3D
var navigator: RefCounted
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
	else:
		state = "patrol"
	path.clear()
	replan = 0.0
	attack_cooldown = 0.0

func take_damage(value: int) -> void:
	if health <= 0 or value <= 0:
		return
	set_health(health - value)
	if health == 0:
		game.mission.eliminate(str(name))

func _can_see() -> bool:
	var a := global_position + Vector3.UP * 1.2
	var b := target.global_position + Vector3.UP * 1.2
	if a.distance_to(b) > 8.0:
		return false
	return get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(a,b,1)).is_empty()

func _physics_process(delta: float) -> void:
	if health <= 0 or target == null or game.combat.health <= 0 or game.mission.completed:
		return
	attack_cooldown = maxf(0.0, attack_cooldown - delta)
	replan -= delta
	var destination := global_position
	var speed := 1.8
	if _can_see():
		if global_position.distance_to(target.global_position) <= 3.0:
			state = "attack"
			if attack_cooldown <= 0:
				game.combat.damage(6)
				attack_cooldown = 1.2
		else:
			state = "chase"
			destination = target.global_position
			speed = 3.0
	else:
		state = "patrol"
		if patrol.size() > 0:
			if Vector2(global_position.x-patrol[patrol_index].x,global_position.z-patrol[patrol_index].z).length() < 0.45:
				patrol_index = (patrol_index + 1) % patrol.size()
			destination = patrol[patrol_index]
	velocity.x = 0
	velocity.z = 0
	if state != "attack":
		if replan <= 0:
			path = navigator.plan(global_position, destination)
			replan = 0.4
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
