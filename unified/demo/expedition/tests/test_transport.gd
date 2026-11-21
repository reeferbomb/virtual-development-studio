extends SceneTree

const Transport = preload("res://transport.gd")
const Player = preload("res://player.gd")

class PhysicsWorld extends Node3D:
	var transport: Node3D

	func _physics_process(delta: float) -> void:
		if transport != null:
			transport.step(delta)

var failures := 0


func _initialize() -> void:
	call_deferred("run")


func check(condition: bool, description: String) -> void:
	if not condition:
		printerr("FAIL transport: ", description)
		failures += 1


func ticks(count: int) -> void:
	for i in count:
		await physics_frame


func solid(parent: Node3D, center: Vector3, size: Vector3) -> StaticBody3D:
	var box := BoxShape3D.new()
	box.size = size
	var shape := CollisionShape3D.new()
	shape.shape = box
	var body := StaticBody3D.new()
	body.add_child(shape)
	parent.add_child(body)
	body.global_position = center
	return body


func run() -> void:
	var world := PhysicsWorld.new()
	root.add_child(world)
	var ground := solid(world, Vector3.DOWN * 0.5, Vector3(100, 1, 100))
	var player := Player.new()
	world.add_child(player)
	player.position = Vector3(3.2, 0.08, 0)
	var transport := Transport.new()
	world.add_child(transport)
	check(transport.configure(player, Vector3.UP * 0.08), "configure vehicle")
	world.transport = transport
	var car := transport.vehicle
	check(not transport.configure(player, Vector3.ZERO), "repeat configuration preserves vehicle")
	await ticks(14)
	check(car.is_on_floor() and player.is_on_floor(), "both bodies contact real terrain")
	check(not transport.enter(), "reject entry outside three meters")
	player.global_position = car.global_position + Vector3.RIGHT * 3.0
	player.collision_layer = 10
	check(transport.enter() and transport.driving, "allow entry at three meters")
	check(not transport.enter() and transport.snapshot().is_empty(), "reject repeated boarding and occupied saves")
	check(not player.is_physics_processing() and player.collision_layer == 0 and player.collision_mask == 0,
			"passenger physics and collisions are disabled")
	check(not transport.restore({"position": [4, 0, 0], "yaw": 0.5}), "reject restore while driving")
	var start := car.global_position
	transport.set_drive(1.0, 0.0)
	await ticks(60)
	check(car.global_position.z < start.z - 3.0 and car.speed > 6.5, "shared vehicle physics accelerates and travels")
	transport.set_drive(1.0, 0.6)
	await ticks(25)
	check(car.global_rotation.y < -0.1 and car.global_position.x > start.x, "steering turns car")
	check(not transport.exit() and transport.driving, "reject exit in motion")
	check((player.global_position - car.global_position).is_equal_approx(Vector3.UP * Transport.SEAT_HEIGHT)
			and absf(player.global_rotation.y - car.global_rotation.y) < 0.001, "passenger and camera track car in the same tick")
	var camera: Camera3D = player.get_node("Camera3D")
	check(camera.current and camera.global_position.distance_to(car.global_position) < 2.4, "driver retains active camera")
	var peak: float = car.speed
	transport.clear_test_drive()
	await ticks(8)
	check(car.speed < peak and car.speed > peak - 0.6, "clearing drive overrides returns to coasting")
	transport.set_drive(1.0, 0.0, true)
	await ticks(10)
	check(car.speed < peak - 2.0 and car.speed > 0.5, "braking is progressive")
	await ticks(45)
	check(absf(car.speed) < 0.01, "braking overrides throttle and stops")

	var right := car.global_basis.x
	var door := car.global_position + right * Transport.DOOR_OFFSET
	var right_obstacle := solid(world, door + Vector3.UP * 1.5, Vector3(0.9, 0.25, 0.9))
	var left_obstacle := solid(world, car.global_position - right * Transport.DOOR_OFFSET + Vector3.UP * 1.5,
			Vector3(0.9, 0.25, 0.9))
	await ticks(3)
	check(not transport.exit() and transport.driving, "low overhead obstacles block both standing capsules")
	left_obstacle.free()
	await ticks(3)
	check(transport.exit() and not transport.driving, "exit uses the clear door")
	check((player.global_position - car.global_position).dot(right) < -1.8, "blocked right door selects left side")
	check(player.is_physics_processing() and player.collision_layer == 10 and player.collision_mask == 1,
			"restore original walking physics and collision bits")
	right_obstacle.free()
	var parked := transport.snapshot()
	check(Transport.valid_snapshot(parked), "parked state validates")
	for wrong in [null, {}, {"position": [1, 2], "yaw": 0}, {"position": [1, 0, 2], "yaw": INF},
			{"position": [NAN, 0, 0], "yaw": 0}, {"position": [100001, 0, 0], "yaw": 0},
			{"position": [0, -1, 0], "yaw": 0}, {"position": [1, 0, 2], "yaw": true},
			{"position": [1, 0, 2], "yaw": 0, "other": 0}]:
		check(not transport.restore(wrong) and transport.snapshot() == parked, "malformed snapshot is atomic")
	var remote := {"position": [3000, 0.08, -5000], "yaw": 2.25}
	check(transport.restore(remote), "restore parked vehicle to unloaded terrain")
	var remote_pose := car.global_transform
	await ticks(35)
	check(car.global_transform.is_equal_approx(remote_pose), "parked vehicle survives unloaded ground")
	check(transport.restore(parked) and car.global_position.distance_to(
			Vector3(parked.position[0], parked.position[1], parked.position[2])) < 0.001
			and absf(car.global_rotation.y - parked.yaw) < 0.001, "restore captured position and yaw")
	check(transport.enter(), "board restored car")
	# A platform just wide enough for the tires has no ground at either exit.
	ground.free()
	var platform := solid(world, car.global_position + Vector3.DOWN * 0.5, Vector3(2.1, 1.0, 4.0))
	platform.rotation.y = car.rotation.y
	await ticks(5)
	check(car.is_on_floor() and not transport.exit() and transport.driving, "reject doors above empty space")
	world.free()
	if failures == 0:
		print("PASS transport driving, camera tracking, braking, safe exits and parked checkpoint restoration")
	quit(int(failures > 0))
