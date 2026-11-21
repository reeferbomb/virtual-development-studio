extends CharacterBody3D
## Arcade road vehicle. Root Y=0 is the tire contact plane; local -Z is forward.

const TOP_SPEED := 16.0
const REVERSE_SPEED := 5.5
const ACCELERATION := 7.0
const BRAKE_DECELERATION := 18.0
const ROLLING_DECELERATION := 2.5
const MAX_STEER_ANGLE := 0.47
const WHEELBASE := 2.1
const WHEEL_RADIUS := 0.36

## Signed longitudinal speed in meters per second.
var speed := 0.0
var _throttle := 0.0
var _steer := 0.0
var _brake := false
var _steer_angle := 0.0
var _front_wheels: Array[Node3D] = []
var _wheel_axles: Array[Node3D] = []

func set_drive(throttle: float, steer: float, brake: bool = false) -> void:
	_throttle = clampf(throttle, -1.0, 1.0)
	_steer = clampf(steer, -1.0, 1.0)
	_brake = brake

func stop() -> void:
	set_drive(0.0, 0.0)
	speed = 0.0
	velocity = Vector3.ZERO
	_steer_angle = 0.0

func _ready() -> void:
	collision_layer = 4
	collision_mask = 1
	floor_snap_length = 0.18
	var collider := CollisionShape3D.new()
	collider.name = "Collider"
	var bounds := BoxShape3D.new()
	bounds.size = Vector3(1.96, 1.48, 3.55)
	collider.shape = bounds
	collider.position.y = bounds.size.y * 0.5
	add_child(collider)
	_build_bodywork()

func _physics_process(delta: float) -> void:
	var target_speed := _throttle * (TOP_SPEED if _throttle >= 0.0 else REVERSE_SPEED)
	var acceleration := ACCELERATION
	if _brake:
		target_speed = 0.0
		acceleration = BRAKE_DECELERATION
	elif is_zero_approx(_throttle):
		acceleration = ROLLING_DECELERATION
	speed = move_toward(speed, target_speed, acceleration * delta)
	_steer_angle = move_toward(_steer_angle, _steer * MAX_STEER_ANGLE, 2.0 * delta)
	# Bicycle steering reverses naturally when backing up. Positive input turns right.
	var yaw_rate := clampf(speed * tan(_steer_angle) / WHEELBASE, -1.35, 1.35)
	rotate_y(-yaw_rate * delta)
	var forward := -global_transform.basis.z.normalized()
	velocity.x = forward.x * speed
	velocity.z = forward.z * speed
	velocity.y += get_gravity().y * delta
	move_and_slide()
	# Retain only motion the collision solver allowed along the car's heading.
	speed = velocity.dot(Vector3(forward.x, 0.0, forward.z))
	for pivot in _front_wheels:
		pivot.rotation.y = -_steer_angle
	for axle in _wheel_axles:
		axle.rotate_x(-speed * delta / WHEEL_RADIUS)

func _build_bodywork() -> void:
	var paint := _material(Color("#dc8e40"), 0.2)
	var charcoal := _material(Color("#223138"))
	var tires := _material(Color("#202325"))
	var glass := _material(Color("#254655"), 0.35)
	var alloy := _material(Color("#97a8a4"), 0.6)
	var lamp := _material(Color("#fff3be"), 0.0, true)
	var tail_lamp := _material(Color("#e84a3d"), 0.0, true)
	_box(self, "Sill", Vector3(1.68, 0.25, 3.33), Vector3(0, 0.43, 0), charcoal)
	_box(self, "Chassis", Vector3(1.80, 0.41, 3.45), Vector3(0, 0.72, 0), paint)
	_box(self, "Cabin", Vector3(1.48, 0.53, 1.65), Vector3(0, 1.16, 0.19), glass)
	_box(self, "Roof", Vector3(1.53, 0.10, 1.68), Vector3(0, 1.47, 0.19), paint)
	_box(self, "FrontBumper", Vector3(1.75, 0.13, 0.15), Vector3(0, 0.51, -1.69), charcoal)
	_box(self, "Grille", Vector3(0.78, 0.13, 0.06), Vector3(0, 0.68, -1.72), charcoal)
	for side in [-1.0, 1.0]:
		var x: float = side
		_box(self, "Headlight", Vector3(0.31, 0.13, 0.06), Vector3(x * 0.66, 0.77, -1.72), lamp)
		_box(self, "TailLight", Vector3(0.27, 0.17, 0.06), Vector3(x * 0.67, 0.75, 1.72), tail_lamp)
		_box(self, "DoorPillar", Vector3(0.05, 0.54, 0.10), Vector3(x * 0.74, 1.16, 0.23), charcoal)
		for z in [-WHEELBASE * 0.5, WHEELBASE * 0.5]:
			var wheel := Node3D.new()
			wheel.name = ("Front" if z < 0 else "Rear") + ("Left" if x < 0 else "Right")
			wheel.position = Vector3(x * 0.86, WHEEL_RADIUS, z)
			add_child(wheel)
			if z < 0:
				_front_wheels.append(wheel)
			var axle := Node3D.new()
			wheel.add_child(axle)
			_wheel_axles.append(axle)
			_disc(axle, WHEEL_RADIUS, 0.26, 0, tires)
			_disc(axle, WHEEL_RADIUS * 0.57, 0.038, x * 0.132, alloy)
			_box(axle, "Hub", Vector3(0.04, 0.07, 0.27), Vector3(x * 0.152, 0, 0), charcoal)

func _material(color: Color, metal: float = 0.0, luminous: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metal
	if luminous:
		material.emission_enabled = true
		material.emission = color
	return material

func _box(parent: Node3D, part_name: String, dimensions: Vector3, center: Vector3, surface: Material) -> void:
	var mesh := BoxMesh.new()
	mesh.size = dimensions
	var part := MeshInstance3D.new()
	part.name = part_name
	part.mesh = mesh
	part.material_override = surface
	part.position = center
	parent.add_child(part)

func _disc(parent: Node3D, radius: float, width: float, x: float, surface: Material) -> void:
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = width
	mesh.radial_segments = 16
	mesh.rings = 1
	var disc := MeshInstance3D.new()
	disc.mesh = mesh
	disc.material_override = surface
	disc.rotation.z = PI / 2.0
	disc.position.x = x
	parent.add_child(disc)
