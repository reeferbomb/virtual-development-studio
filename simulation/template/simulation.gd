extends Node3D

const PLAYER = preload("res://player.gd")
const VEHICLE = preload("res://vehicle.gd")
const WEATHER = preload("res://weather.gd")
const INTERACTIONS = preload("res://interactions.gd")
const OBJECTIVES = preload("res://objectives.gd")

var player: CharacterBody3D
var vehicle: CharacterBody3D
var world: Node3D
var weather = WEATHER.new()
var interactions = INTERACTIONS.new()
var objectives = OBJECTIVES.new()
var driving := false
var ready_for_play := false
var checkpoint: Vector3
var goal: Marker3D
var status: Label
var message := ""
var test_controls := false
var test_throttle := 0.0
var test_steer := 0.0
var test_brake := false

func vec(row: Array) -> Vector3:
	return Vector3(float(row[0]), float(row[1]), float(row[2]))

func _ready() -> void:
	var config = JSON.parse_string(FileAccess.get_file_as_string("res://simulation.json"))
	if not config is Dictionary:
		push_error("Invalid simulation configuration")
		return
	world = load("res://world.tscn").instantiate()
	add_child(world)
	player = PLAYER.new()
	add_child(player)
	player.global_position = world.get_node("Spawn").global_position + Vector3.UP * 0.08
	goal = world.get_node("Goal")
	vehicle = VEHICLE.new()
	add_child(vehicle)
	vehicle.global_position = vec(config.vehicle_spawn) + Vector3.UP * 0.08
	checkpoint = vec(config.checkpoint)
	add_child(weather)
	add_child(interactions)
	if not weather.configure(world, config) or not interactions.configure(world, config.interactables) or not objectives.configure(config.stages):
		push_error("Simulation component configuration failed")
		return
	var marker := MeshInstance3D.new()
	var ring := TorusMesh.new()
	ring.inner_radius = 1.7
	ring.outer_radius = 2.0
	marker.mesh = ring
	var paint := StandardMaterial3D.new()
	paint.albedo_color = Color(0.1, 0.8, 0.9)
	paint.emission_enabled = true
	paint.emission = paint.albedo_color
	marker.material_override = paint
	add_child(marker)
	marker.global_position = checkpoint + Vector3.UP * 0.13
	var canvas := CanvasLayer.new()
	add_child(canvas)
	status = Label.new()
	status.position = Vector2(20,20)
	status.add_theme_font_size_override("font_size",20)
	status.add_theme_color_override("font_outline_color", Color.BLACK)
	status.add_theme_constant_override("outline_size", 7)
	canvas.add_child(status)
	ready_for_play = true
	print("STUDIO_SIMULATION_READY")

func enter_vehicle() -> bool:
	if not ready_for_play or driving or player.global_position.distance_to(vehicle.global_position) > 3.0 or absf(vehicle.speed) > 0.8:
		return false
	driving = true
	player.set_physics_process(false)
	player.collision_layer = 0
	player.collision_mask = 0
	player.velocity = Vector3.ZERO
	player.clear_test_drive()
	player.rotation.y = vehicle.rotation.y
	message = "Vehicle entered"
	return true

func exit_vehicle() -> bool:
	if not ready_for_play or not driving or absf(vehicle.speed) > 0.8:
		return false
	# Only exit where the standing capsule fits and the ground is present.
	var shape := CapsuleShape3D.new()
	shape.radius = 0.35
	shape.height = 1.8
	var space := get_world_3d().direct_space_state
	for side in [1.0, -1.0]:
		var point: Vector3 = vehicle.global_position + vehicle.global_transform.basis.x * 2.2 * side
		var floor_query := PhysicsRayQueryParameters3D.create(point + Vector3.UP * 2.0, point - Vector3.UP * 2.0, 1)
		var floor_hit := space.intersect_ray(floor_query)
		if floor_hit.is_empty() or floor_hit.normal.y < 0.7:
			continue
		point.y = floor_hit.position.y + 0.08
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = shape
		query.transform = Transform3D(Basis.IDENTITY, point + Vector3.UP * 0.9)
		query.collision_mask = 5
		if not space.intersect_shape(query, 1).is_empty():
			continue
		vehicle.stop()
		driving = false
		clear_test_drive()
		player.global_position = point
		player.velocity = Vector3.ZERO
		player.collision_layer = 2
		player.collision_mask = 1
		player.set_physics_process(true)
		message = "Vehicle exited"
		return true
	message = "No clear exit; move to open ground"
	return false

func interact(id: String) -> bool:
	if not ready_for_play or driving:
		return false
	var stage: Dictionary = objectives.current()
	if stage.get("action") != "interact" or stage.get("target") != id:
		return false
	if not interactions.activate(id, player.global_position):
		return false
	message = "Activated " + id
	return objectives.record("interact", id)

func set_test_drive(throttle: float, steer: float, brake: bool = false) -> void:
	test_controls = true
	test_throttle = throttle
	test_steer = steer
	test_brake = brake

func clear_test_drive() -> void:
	test_controls = false
	test_throttle = 0.0
	test_steer = 0.0
	test_brake = false

func _unhandled_input(event: InputEvent) -> void:
	if not ready_for_play or not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.physical_keycode:
		KEY_E:
			if driving:
				if not exit_vehicle():
					message = "Stop the vehicle and ensure space to exit"
			elif not enter_vehicle():
				message = "Approach the vehicle to enter"
		KEY_F:
			if not interact(str(objectives.current().get("target", ""))):
				message = "Approach the current mission object"
		KEY_T:
			var modes := ["clear", "rain", "fog"]
			weather.set_weather(modes[(modes.find(weather.snapshot().weather) + 1) % modes.size()])

func _physics_process(delta: float) -> void:
	if not ready_for_play:
		return
	weather.step(delta)
	if driving:
		var throttle := test_throttle if test_controls else 0.0
		var steer := test_steer if test_controls else 0.0
		var brake := test_brake if test_controls else false
		if not test_controls and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			throttle = float(Input.is_physical_key_pressed(KEY_W)) - float(Input.is_physical_key_pressed(KEY_S))
			steer = float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
			brake = Input.is_physical_key_pressed(KEY_SPACE)
		vehicle.set_drive(throttle, steer, brake)
		player.global_position = vehicle.global_position + Vector3.UP * 0.65
		player.rotation.y = vehicle.rotation.y
		if vehicle.global_position.distance_to(checkpoint) <= 2.5:
			objectives.record("drive", "checkpoint")
	else:
		if player.global_position.distance_to(goal.global_position) <= 1.0:
			objectives.record("visit", "goal")
	var climate: Dictionary = weather.snapshot()
	var stage: Dictionary = objectives.current()
	var instruction := "EXPEDITION COMPLETE" if objectives.completed else "%s %s" % [str(stage.get("action", "")).to_upper(), stage.get("target", "")]
	status.text = "%s  |  %.1f m/s  |  %s  %04.1f h\n%s\nWASD move/drive  •  E enter/exit  •  F interact  •  Space brake/jump  •  T weather\n%s" % ["DRIVING" if driving else "ON FOOT", absf(vehicle.speed), climate.weather, climate.hour, instruction, message]
