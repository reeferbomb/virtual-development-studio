extends SceneTree
## Run the expedition through the same controllers and physics steps as a player.

var game
var player: CharacterBody3D
var vehicle: CharacterBody3D
var checks: Array[Dictionary] = []
var metrics := {}
var foot_distance := 0.0
var longest_foot_step := 0.0
var physics_start := 0

func _initialize() -> void:
	call_deferred("run")

func check(label: String, passed: bool, detail: String) -> bool:
	checks.append({"name": label, "status": "passed" if passed else "failed", "detail": detail})
	return passed

func frames(count: int) -> void:
	for tick in count:
		await physics_frame

func flat(position: Vector3) -> Vector2:
	return Vector2(position.x, position.z)

func run() -> void:
	physics_start = Engine.get_physics_frames()
	var scene := load("res://simulation.tscn") as PackedScene
	if not check("Load simulation scene", scene != null, "res://simulation.tscn"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	if not check("Initialize simulation", game.get("ready_for_play") == true, "World, player, vehicle and simulation components"):
		finish()
		return
	player = game.player
	vehicle = game.vehicle
	await frames(20)
	if not check("Settle on terrain", player.is_on_floor() and vehicle.is_on_floor(), "Player and vehicle have physics floor contacts"):
		finish()
		return

	var config: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://simulation.json"))
	await test_climate(config)
	if await prepare_mission(config):
		if await drive_checkpoint():
			await complete_mission()
	finish()

func test_climate(config: Dictionary) -> void:
	var env: Environment = game.world.get_node("Environment").environment
	var rain := game.world.get_node("Rain") as MultiMeshInstance3D
	var sun := game.world.get_node("Sun") as DirectionalLight3D
	var initial: Dictionary = game.weather.snapshot()
	var initial_sun: Vector3 = sun.rotation_degrees
	var ticks := Engine.physics_ticks_per_second
	await frames(ticks)
	var hour_now := float(game.weather.snapshot().hour)
	var expected := fposmod(float(initial.hour) + 24.0 / float(config.cycle_seconds), 24.0)
	metrics.clock_start_hour = initial.hour
	metrics.clock_after_one_second = hour_now
	check("Advance clock and sun", is_equal_approx(hour_now, expected) and not initial_sun.is_equal_approx(sun.rotation_degrees),
		"%.4f to %.4f in %d physics ticks (expected %.4f)" % [initial.hour, hour_now, ticks, expected])

	var clear_set: bool = game.weather.set_weather("clear")
	var clear: Dictionary = game.weather.snapshot()
	var before_rain := not rain.visible and not env.fog_enabled
	var rain_set: bool = game.weather.set_weather("rain")
	var wet: Dictionary = game.weather.snapshot()
	var raining := rain.visible and rain.multimesh != null and rain.multimesh.instance_count > 0 and env.fog_enabled
	var rain_density := env.fog_density
	var fog_set: bool = game.weather.set_weather("fog")
	var fog: Dictionary = game.weather.snapshot()
	var foggier := env.fog_enabled and env.fog_density > rain_density and not rain.visible
	var cleared: bool = game.weather.set_weather("clear")
	metrics.weather_visibility = {"clear": clear.visibility, "rain": wet.visibility, "fog": fog.visibility}
	metrics.rain_fog_density = rain_density
	metrics.fog_density = fog.fog_density
	check("Switch clear, rain and fog in the world", clear_set and rain_set and fog_set and cleared and before_rain
		and raining and foggier and not rain.visible and not env.fog_enabled and clear.weather == "clear"
		and wet.weather == "rain" and fog.weather == "fog" and fog.visibility < wet.visibility and wet.visibility < clear.visibility,
		"Rain mesh, environment fog and visibility respond to all three modes")

# Every on-foot leg advances the normal character controller and measures displacement.
func walk_to(target: Vector3) -> bool:
	var destination := flat(target)
	for tick in 1200:
		var position := flat(player.global_position)
		var offset := destination - position
		if offset.length() < 0.09:
			player.set_test_drive(Vector2.ZERO)
			await frames(2)
			return true
		player.set_test_drive(offset.normalized())
		await physics_frame
		var step := position.distance_to(flat(player.global_position))
		foot_distance += step
		longest_foot_step = maxf(longest_foot_step, step)
	player.set_test_drive(Vector2.ZERO)
	return false

func awaiting_stage(index: int, action: String, target: String) -> bool:
	return (not game.objectives.completed and game.objectives.index == index
		and game.objectives.current() == {"action": action, "target": target})

func prepare_mission(config: Dictionary) -> bool:
	var first_stage: Dictionary = game.objectives.current()
	var relay_id := str(first_stage.get("target", ""))
	var relay: Vector3
	var found_relay := false
	for item in config.interactables:
		if item.id == relay_id:
			relay = game.vec(item.position)
			found_relay = true
	if not check("Start ordered mission", found_relay and awaiting_stage(0, "interact", relay_id),
			"Starting objective is to activate %s" % relay_id):
		return false

	var entry_distance := player.global_position.distance_to(vehicle.global_position)
	metrics.initial_vehicle_distance_m = entry_distance
	if not check("Reject distant vehicle entry", entry_distance > 3.0 and not game.enter_vehicle() and not game.driving,
			"Vehicle is %.2f m away" % entry_distance):
		return false

	var approach: Vector3 = vehicle.global_position + vehicle.global_position.direction_to(relay) * 1.35
	var arrived := await walk_to(approach)
	var relay_distance := player.global_position.distance_to(relay)
	metrics.remote_interaction_distance_m = relay_distance
	if not check("Reject distant relay activation", arrived and relay_distance > 2.0 and not game.interact(relay_id)
			and game.interactions.snapshot().get(relay_id) == false and awaiting_stage(0, "interact", relay_id),
			"Attempted activation from %.2f m" % relay_distance):
		return false

	arrived = await walk_to(relay)
	if not check("Activate nearby relay once", arrived and game.interact(relay_id)
			and game.interactions.snapshot().get(relay_id) == true and not game.interact(relay_id)
			and awaiting_stage(1, "drive", "checkpoint"), "Relay activation advances exactly one stage"):
		return false

	arrived = await walk_to(game.goal.global_position)
	if not check("Reject early goal arrival", arrived and awaiting_stage(1, "drive", "checkpoint"),
			"Player reached the goal before delivering the vehicle"):
		return false
	arrived = await walk_to(game.checkpoint)
	if not check("Require vehicle at checkpoint", arrived and not game.driving and awaiting_stage(1, "drive", "checkpoint"),
			"Player crossed the checkpoint on foot"):
		return false

	arrived = await walk_to(approach)
	metrics.boarding_distance_m = player.global_position.distance_to(vehicle.global_position)
	return check("Enter nearby vehicle", arrived and game.enter_vehicle() and game.driving and not player.is_physics_processing(),
		"Player boarded from %.2f m" % metrics.boarding_distance_m)

func drive_checkpoint() -> bool:
	var checkpoint := flat(game.checkpoint)
	var start := flat(vehicle.global_position)
	var last := start
	var route_length := start.distance_to(checkpoint)
	var travel := 0.0
	var max_step := 0.0
	var peak_speed := 0.0
	var checked_moving_exit := false
	var elapsed := 0
	for tick in 900:
		var offset := checkpoint - last
		if offset.length() <= 0.7:
			break
		var direction := offset.normalized()
		var heading := flat(-vehicle.global_transform.basis.z).normalized()
		var right := flat(vehicle.global_transform.basis.x).normalized()
		var steer := clampf(atan2(direction.dot(right), direction.dot(heading)), -1.0, 1.0)
		game.set_test_drive(0.4, steer)
		await physics_frame
		var current := flat(vehicle.global_position)
		var step := current.distance_to(last)
		travel += step
		max_step = maxf(max_step, step)
		last = current
		peak_speed = maxf(peak_speed, game.vehicle.speed)
		elapsed += 1
		if not checked_moving_exit and game.vehicle.speed > 2.0:
			checked_moving_exit = true
			if not check("Reject exit while moving", not game.exit_vehicle() and game.driving,
					"Attempted to exit at %.2f m/s" % game.vehicle.speed):
				return false

	var error := last.distance_to(checkpoint)
	metrics.drive_distance_m = travel
	metrics.drive_ticks = elapsed
	metrics.drive_max_step_m = max_step
	metrics.drive_peak_mps = peak_speed
	metrics.drive_checkpoint_error_m = error
	if not check("Drive to checkpoint under physics", checked_moving_exit and error <= 0.7 and elapsed > 1
			and travel >= route_length - 0.71 and max_step <= peak_speed / Engine.physics_ticks_per_second + 0.03
			and awaiting_stage(2, "visit", "goal"), "Drove %.2f m over %d ticks, %.2f m from checkpoint" % [travel, elapsed, error]):
		return false

	var coast_start: float = absf(game.vehicle.speed)
	game.set_test_drive(0.0, 0.0)
	var coast_ticks := 6
	await frames(coast_ticks)
	var before: float = absf(game.vehicle.speed)
	var coast_deceleration := (coast_start - before) * Engine.physics_ticks_per_second / coast_ticks
	game.set_test_drive(0.0, 0.0, true)
	var brake_ticks := 0
	while brake_ticks < 240 and absf(game.vehicle.speed) > 0.05:
		await physics_frame
		brake_ticks += 1
	metrics.brake_ticks = brake_ticks
	metrics.brake_initial_mps = before
	metrics.brake_final_mps = absf(game.vehicle.speed)
	var brake_deceleration := (before - absf(game.vehicle.speed)) * Engine.physics_ticks_per_second / maxi(brake_ticks, 1)
	metrics.coast_deceleration_mps2 = coast_deceleration
	metrics.brake_deceleration_mps2 = brake_deceleration
	if not check("Brake to a stop", before > 1.0 and brake_ticks > 1 and absf(game.vehicle.speed) <= 0.05
			and brake_deceleration > maxf(0.0, coast_deceleration) + 0.5,
			"%.2f to %.2f m/s in %d ticks, %.2f m/s² braking vs %.2f coasting" % [before, game.vehicle.speed, brake_ticks, brake_deceleration, coast_deceleration]):
		return false
	var exited: bool = game.exit_vehicle()
	metrics.exit_separation_m = flat(player.global_position).distance_to(flat(vehicle.global_position))
	game.clear_test_drive()
	return check("Exit stopped vehicle", exited and not game.driving and player.is_physics_processing()
		and metrics.exit_separation_m > 1.0, "On-foot controller restored beside the vehicle")

func complete_mission() -> void:
	var before := foot_distance
	var start := flat(player.global_position)
	var destination := flat(game.goal.global_position)
	var arrived := await walk_to(game.goal.global_position)
	var error := destination.distance_to(flat(player.global_position))
	metrics.final_walk_m = foot_distance - before
	metrics.goal_error_m = error
	check("Walk to goal and complete mission", arrived and not game.driving and game.objectives.completed
		and game.objectives.index == 3 and game.objectives.current().is_empty()
		and metrics.final_walk_m > 0.5 and metrics.final_walk_m >= start.distance_to(destination) - 0.10
		and longest_foot_step <= player.walk_speed / Engine.physics_ticks_per_second + 0.02,
		"Walked the final %.2f m, finishing %.2f m from the goal" % [metrics.final_walk_m, error])
	player.clear_test_drive()

func finish() -> void:
	metrics.physics_ticks = Engine.get_physics_frames() - physics_start
	metrics.physics_ticks_per_second = Engine.physics_ticks_per_second
	metrics.walk_distance_m = foot_distance
	metrics.walk_max_step_m = longest_foot_step
	var passed := not checks.is_empty()
	for row in checks:
		if row.status != "passed":
			passed = false
	print("STUDIO_SIMULATION_QA_JSON " + JSON.stringify({"pass": passed, "checks": checks, "metrics": metrics}))
	quit(0 if passed else 1)
