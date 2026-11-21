extends CharacterBody3D

@export var walk_speed := 4.0
@export var sprint_speed := 7.0
@export var jump_speed := 5.2
@export var mouse_sensitivity := 0.002
var _camera: Camera3D
var _testing := false
var _test_direction := Vector2.ZERO
var _test_sprint := false
var _pending_jump := false
var _test_jump_held := false
var _pitch := 0.0

func _ready() -> void:
	collision_layer = 2
	collision_mask = 1
	var shape := CapsuleShape3D.new()
	shape.radius = 0.35
	shape.height = 1.8
	var collider := CollisionShape3D.new()
	collider.name = "PlayerCollider"
	collider.shape = shape
	collider.position.y = shape.height * 0.5
	add_child(collider)
	_camera = Camera3D.new()
	_camera.name = "Camera3D"
	_camera.position.y = 1.6
	add_child(_camera)
	_camera.current = true
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if _testing or DisplayServer.get_name() == "headless":
		return
	if event is InputEventKey and event.pressed and not event.echo:
		if event.physical_keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			_pending_jump = false
		elif event.physical_keycode == KEY_SPACE and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			_pending_jump = true
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.screen_relative.x * mouse_sensitivity)
		_pitch = clampf(_pitch - event.screen_relative.y * mouse_sensitivity, -1.5, 1.5)
		_camera.rotation.x = _pitch

func set_test_drive(direction: Vector2, sprint: bool = false, jump: bool = false) -> void:
	if not _testing:
		_pending_jump = false
	_testing = true
	_test_direction = direction.limit_length(1.0)
	_test_sprint = sprint
	if jump and not _test_jump_held:
		_pending_jump = true
	_test_jump_held = jump

func clear_test_drive() -> void:
	_testing = false
	_test_direction = Vector2.ZERO
	_test_sprint = false
	_test_jump_held = false
	_pending_jump = false

func _physics_process(delta: float) -> void:
	var movement := Vector3.ZERO
	var sprint := false
	if _testing:
		movement = Vector3(_test_direction.x, 0.0, _test_direction.y)
		sprint = _test_sprint
	elif Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		var x := int(Input.is_physical_key_pressed(KEY_D)) - int(Input.is_physical_key_pressed(KEY_A))
		var z := int(Input.is_physical_key_pressed(KEY_S)) - int(Input.is_physical_key_pressed(KEY_W))
		movement = global_transform.basis * Vector3(x, 0, z).normalized()
		sprint = Input.is_physical_key_pressed(KEY_SHIFT)
	var speed := sprint_speed if sprint else walk_speed
	velocity.x = movement.x * speed
	velocity.z = movement.z * speed
	if not is_on_floor():
		velocity += get_gravity() * delta
	elif _pending_jump:
		velocity.y = jump_speed
	_pending_jump = false
	move_and_slide()
