extends SceneTree

const Planner = preload("res://navigation.gd")

var failures := 0

func check(condition: bool, message: String) -> void:
	if not condition:
		printerr(message)
		failures += 1

func _initialize() -> void:
	var spec := {"terrain": {"width": 16, "depth": 12, "flat_radius": 5},
		"blocks": [], "placements": [{"position": [0, 0, 0],
		"collider_size": [4, 1, 1], "yaw_deg": 90}]}
	var planner := Planner.new()
	planner.configure(spec)
	var start := Vector3(-3.1, 0, 0)
	var goal := Vector3(3.1, 0, 0)
	check(planner.plan(start, start).is_empty(), "Already at target")
	var route := planner.plan(start, goal)
	check(not route.is_empty() and route[-1].is_equal_approx(goal), "Expected route to exact goal")
	var previous := start
	for waypoint in route:
		check(not waypoint.is_equal_approx(start), "Route includes start")
		for step in range(21):
			var p := previous.lerp(waypoint, float(step) / 20)
			check(absf(p.x) > 1 or absf(p.z) > 2.5, "Crossed inflated rotated collider")
		previous = waypoint
	check(planner.plan(start, Vector3(5,0,0)).is_empty(), "Outside flat core")
	check(planner.plan(Vector3(INF,0,0), goal).is_empty(), "Non-finite endpoint")
	check(planner.plan(Vector3.ZERO, goal).is_empty(), "Start in solid")
	spec.blocks = [{"position": [0,1,0], "size": [1,2,11]}]
	planner.configure(spec)
	check(planner.plan(start, goal).is_empty(), "Crossed impassable wall")
	if failures == 0:
		print("Navigation tests passed")
	quit(int(failures > 0))
