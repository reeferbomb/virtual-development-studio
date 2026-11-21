extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _finish(passed: bool, metrics: Dictionary) -> void:
	print("STUDIO_ROUTE_QA_JSON " + JSON.stringify({"pass": passed, "metrics": metrics}))
	quit(0 if passed else 1)

func _run() -> void:
	var routes = JSON.parse_string(FileAccess.get_file_as_string("res://route.json"))
	var packed := load("res://main.tscn") as PackedScene
	if not routes is Array or routes.size() < 2 or packed == null:
		_finish(false, {"error":"Missing route or scene"})
		return
	var main := packed.instantiate()
	root.add_child(main)
	for frame in 30:
		await physics_frame
	var actor := main.get("player") as CharacterBody3D
	if actor == null or not actor.is_on_floor():
		_finish(false, {"error":"Player did not settle on terrain"})
		return
	var index := 1
	var ticks := 0
	var travel := 0.0
	var contacts := 0
	var last := Vector2(actor.global_position.x, actor.global_position.z)
	var start_time := Time.get_ticks_usec()
	while index < routes.size() and ticks < 7200:
		var point: Array = routes[index]
		var position := Vector2(actor.global_position.x, actor.global_position.z)
		var delta := Vector2(point[0], point[2]) - position
		if delta.length() < 0.08:
			index += 1
			continue
		actor.set_test_drive(delta.limit_length(4.0 / Engine.physics_ticks_per_second) * Engine.physics_ticks_per_second / 4.0)
		await physics_frame
		ticks += 1
		var current := Vector2(actor.global_position.x, actor.global_position.z)
		travel += current.distance_to(last)
		last = current
		for collision_index in actor.get_slide_collision_count():
			if absf(actor.get_slide_collision(collision_index).get_normal().y) < 0.5:
				contacts += 1
	actor.clear_test_drive()
	var target: Array = routes[-1]
	var error := last.distance_to(Vector2(target[0],target[2]))
	var reached: bool = main.get("goal_reached") == true
	var elapsed := (Time.get_ticks_usec() - start_time) / 1000000.0
	_finish(index == routes.size() and reached and error < 0.1 and contacts == 0, {"waypoints_reached":index,"waypoints_total":routes.size(),"physics_ticks":ticks,"travel_m":travel,"horizontal_collision_contacts":contacts,"goal_error_m":error,"goal_triggered":reached,"simulation_seconds":float(ticks)/Engine.physics_ticks_per_second,"headless_wall_seconds":elapsed})
