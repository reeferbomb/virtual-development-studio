extends SceneTree

const Vehicle = preload("res://vehicle.gd")

var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	if not condition:
		printerr("FAIL vehicle: ", label)
		failures += 1

func ticks(count: int) -> void:
	for i in range(count):
		await physics_frame

func solid(parent: Node3D, dimensions: Vector3, center: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.position = center
	var shape := BoxShape3D.new()
	shape.size = dimensions
	var collider := CollisionShape3D.new()
	collider.shape = shape
	body.add_child(collider)
	parent.add_child(body)
	return body

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	solid(world, Vector3(120, 1, 120), Vector3.DOWN * 0.5)
	var car := Vehicle.new()
	world.add_child(car)
	await ticks(5)
	check(car.is_on_floor() and absf(car.position.y) < 0.03, "tires rest on the floor")
	check(car.collision_layer == 4 and car.collision_mask == 1, "vehicle and world layers")
	check(car.get_node("Chassis") is MeshInstance3D and car.get_node("RearLeft") is Node3D,
			"chassis and wheels attached")
	car.set_drive(4.0, 0.0)
	await ticks(60)
	check(car.speed > 6.6 and car.speed < 7.4, "accelerates progressively in physics ticks")
	check(car.position.z < -3.1 and absf(car.position.x) < 0.02, "local -Z is forward")
	var straight_z := car.position.z
	car.set_drive(1.0, 1.0)
	await ticks(45)
	check(car.rotation.y < -0.55 and car.position.x > 1.25 and car.position.z < straight_z,
			"right steering changes heading and trajectory")
	car.set_drive(1.0, 0.0, true)
	var braking_start := car.position
	var entry_speed := car.speed
	await ticks(12)
	check(absf((entry_speed - car.speed) - Vehicle.BRAKE_DECELERATION * 0.2) < 0.1, "brake progressively slows the moving car")
	await ticks(36)
	check(absf(car.speed) < 0.03 and car.position.distance_to(braking_start) < entry_speed * entry_speed / (2.0 * Vehicle.BRAKE_DECELERATION) + 0.1,
			"brake overrides held accelerator and brings car to rest")
	var stopped := car.position
	car.set_drive(0.0, 1.0)
	var parked_angle := car.rotation.y
	await ticks(25)
	check(car.position.distance_to(stopped) < 0.03 and absf(car.rotation.y - parked_angle) < 0.001,
			"steering alone cannot pivot a parked vehicle")
	car.set_drive(-2.0, 0.0)
	await ticks(65)
	check(absf(car.speed + Vehicle.REVERSE_SPEED) < 0.05 and car.position.distance_to(stopped) > 3.0,
			"reverse moves the vehicle and respects its speed limit")
	car.stop()
	check(is_zero_approx(car.speed) and car.velocity.is_zero_approx(), "stop resets speed and velocity")
	var reset_at := car.position
	await ticks(10)
	check(car.position.distance_to(reset_at) < 0.02, "stop clears latched throttle")

	var wall := solid(world, Vector3(12, 3, 1), Vector3(26, 1.5, -10))
	var probe := Vehicle.new()
	probe.position.x = 26.0
	world.add_child(probe)
	await ticks(3)
	probe.set_drive(1.0, 0.0)
	var touched := false
	for i in range(170):
		await physics_frame
		for j in range(probe.get_slide_collision_count()):
			if probe.get_slide_collision(j).get_collider() == wall:
				touched = true
	check(touched, "Godot solver reported a vehicle/wall contact")
	check(probe.position.z < -7.65 and probe.position.z > -7.80, "wall stops front of car on near face")
	check(absf(probe.speed) < 0.2, "pressing into the wall does not accumulate speed")
	probe.set_drive(-1.0, 0.0)
	await ticks(40)
	check(probe.position.z > -6.4 and probe.speed < -3.5, "car can reverse clear of the wall")
	world.free()
	if failures == 0:
		print("PASS vehicle acceleration, steering, braking, reverse and solid-wall collision")
	quit(int(failures > 0))
