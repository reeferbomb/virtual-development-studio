extends SceneTree

const Car = preload("res://vehicle.gd")
const START := Vector3(32.0, 0.08, 52.0)
const DT := 1.0 / 60.0
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(value: bool, description: String) -> void:
	if not value:
		failures += 1
		printerr("FAIL street vehicle: ", description)


func _solid(label: String, point: Vector3, size: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = label
	var collider := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	collider.shape = box
	body.add_child(collider)
	root.add_child(body)
	body.global_position = point
	return body


func _player() -> CharacterBody3D:
	var player := CharacterBody3D.new()
	player.collision_layer = 2
	player.collision_mask = 1
	var collider := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.35
	capsule.height = 1.8
	collider.position.y = 0.9
	collider.shape = capsule
	player.add_child(collider)
	root.add_child(player)
	player.set_physics_process(true)
	return player


func _run() -> void:
	var car := Car.new()
	root.add_child(car)
	var floor_body := _solid("Street", Vector3(40, -0.5, 40), Vector3(82, 1, 82))
	var wall := _solid("ConcreteBarrier", Vector3(32, 1, 26), Vector3(12, 2, 0.6))
	var player := _player()
	var cam := Camera3D.new()
	player.add_child(cam)
	cam.make_current()
	check(not car.configure(7, START, NAN) and not car.configure(7, Vector3.ZERO, 80), "invalid configuration is atomic")
	check(car.configure(7, START, 80) and not car.configure(7, START, 80), "creates one bounded, seeded car")
	var parked: Dictionary = car.snapshot()
	await physics_frame
	await physics_frame
	player.global_position = START + Vector3.RIGHT * 5.0
	check(not car.interact(player), "out-of-reach boarding")
	player.global_position = START + Vector3.LEFT * 2.4
	var shut := _solid("FencedDoor", START + Vector3(-1.5, 0.9, 0), Vector3(0.12, 2, 2))
	await physics_frame
	await physics_frame
	check(not car.interact(player), "cannot board through a street obstacle")
	shut.free()
	await physics_frame
	check(car.interact(player), "board from reachable driver's door")
	check(car.status().driving and player.collision_layer == 0 and player.collision_mask == 0 and not player.is_physics_processing(), "rider physics and collision suspended")
	check(root.get_camera_3d() != cam, "boarding switches to a chase camera")
	check(not car.interact(_other_player()), "a passenger cannot eject the driver")
	for i in 45:
		car.step(DT, player, Vector2(0, 1))
	check(car.status().speed > 4.8 and car.status().position.z < START.z - 1.5, "accelerates and translates")
	check(not car.interact(player), "moving car rejects exit")
	check(player.global_position.is_equal_approx(car.status().seat_position), "driver follows physically moved car")
	var moving: Dictionary = JSON.parse_string(JSON.stringify(car.snapshot(), "", false, true))
	check(car.valid_snapshot(moving) and car.valid_player_position(player.global_position, moving), "occupied checkpoint validates after JSON round trip")
	check(not car.valid_player_position(START, moving), "occupied checkpoint requires driver on seat")
	for i in 18:
		car.step(DT, player, Vector2(0.58, 1))
	var expected := car.snapshot()
	check(expected.yaw < -0.06 and expected.position[0] > START.x + 0.02, "right steering changes heading and travel")
	check(car.restore(moving, player), "restore moving checkpoint")
	for i in 18:
		car.step(DT, player, Vector2(0.58, 1))
	var replay := car.snapshot()
	check(is_equal_approx(replay.yaw, expected.yaw) and is_equal_approx(replay.speed, expected.speed)
		and car.global_position.distance_to(Vector3(expected.position[0], expected.position[1], expected.position[2])) < 0.002
		and absf(replay.distance - expected.distance) < 0.002, "same controls reproduce saved trajectory")
	for field in ["speed", "version", "seed", "steer", "position", "driving", "collisions"]:
		var bad: Dictionary = moving.duplicate(true)
		bad[field] = 9000.5
		check(not car.restore(bad, player) and car.snapshot() == replay, "malformed " + field + " cannot mutate live state")
	var embedded: Dictionary = moving.duplicate(true)
	embedded.position = [32.0, START.y, 26.0]
	check(not car.restore(embedded, player) and car.snapshot() == replay, "reject checkpoint inside barrier")
	check(car.restore(moving, player), "restore pre-turn drive for obstacle approach")
	var fastest := 0.0
	for i in 240:
		car.step(DT, player, Vector2(0, 1))
		fastest = maxf(fastest, car.status().speed)
	check(car.status().collisions == 1 and car.global_position.z > 28.20 and car.global_position.z < 28.30
		and car.status().speed < 0.25, "swept chassis hits a narrow solid wall without tunneling")
	check(fastest <= Car.TOP_SPEED and fastest > 14.0, "forward speed bounded under sustained throttle")
	check(car.valid_snapshot(car.snapshot()), "car touching a wall can be saved")
	for i in 70:
		car.step(DT, player, Vector2(0, -1))
	check(is_equal_approx(car.status().speed, -Car.REVERSE_SPEED) and car.global_position.z > 30.0, "reverse clears the obstacle and stops accelerating at its limit")
	for i in 30:
		car.step(DT, player, Vector2.ZERO, true)
	check(is_zero_approx(car.status().speed) and car.status().distance > 24.0, "brake reaches rest and the odometer includes reverse travel")
	var door := car.global_position
	var left := _solid("LeftDoorObstacle", door + Vector3(-Car.DOOR_DISTANCE, 0.9, 0), Vector3(0.5, 1.8, 1.2))
	var right := _solid("RightDoorObstacle", door + Vector3(Car.DOOR_DISTANCE, 0.9, 0), Vector3(0.5, 1.8, 1.2))
	await physics_frame
	await physics_frame
	check(not car.interact(player) and car.status().driving, "blocked doors keep the driver seated")
	right.free()
	await physics_frame
	check(car.interact(player) and not car.status().driving and player.global_position.x > car.global_position.x + 1.5, "checks opposite door for a clear landing")
	check(player.is_physics_processing() and player.collision_layer == 2 and player.collision_mask == 1
		and root.get_camera_3d() == cam, "exit restores the player's control, collision and camera")
	player.set_physics_process(false)
	car.step(DT, player, Vector2(0, 1))
	check(not player.is_physics_processing(), "parked vehicle leaves other passenger systems in control")
	player.set_physics_process(true)
	left.free()
	check(not car.restore(moving), "occupied state needs a driver")
	check(car.restore(moving, player) and car.status().driving, "occupied save can reboard a walking driver")
	check(car.restore(parked, player) and not car.status().driving and player.is_physics_processing(), "parked save safely releases a live driver")
	check(car.snapshot() == parked, "original parked state round trips exactly")
	wall.free()
	floor_body.free()
	check(not car.valid_player_position(START, parked), "on-foot checkpoint cannot overlap the vehicle")
	check(car.valid_player_position(START + Vector3(Car.BODY_SIZE.x * 0.5 + 0.26, 0,
		Car.BODY_SIZE.z * 0.5 + 0.26), parked), "capsule can stand just outside the bumper corner")
	car.free()
	player.free()
	if failures == 0:
		print("PASS street vehicle ", JSON.stringify({"swept_collision": true, "safe_doors": true,
			"speed_peak": fastest, "reverse_and_braking": true, "driver_sync": true, "checkpoint_replay": true}))
	quit(1 if failures else 0)


func _other_player() -> CharacterBody3D:
	var other := _player()
	other.queue_free()
	return other
