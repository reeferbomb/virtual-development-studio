extends SceneTree

const Traffic = preload("res://traffic.gd")
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(condition: bool, label: String) -> void:
	if not condition:
		printerr("FAIL traffic: ", label)
		failures += 1


func as_vector(coords: Array) -> Vector3:
	return Vector3(coords[0], coords[1], coords[2])


func check_stop_line() -> void:
	var single := Traffic.new()
	root.add_child(single)
	single.configure(9, 3, 32.0, 1)
	var route := int(single.status().cars[0].route)
	var x := route % 3
	var z := floori(float(route) / 3.0)
	var junction := z * 4 + x + 1
	var previous: String = single.status().signals[junction].phase
	var saw_red_start := false
	for i in Traffic.CYCLE + 1:
		single.step(Traffic.TICK)
		var phase: String = single.status().signals[junction].phase
		if phase == "north_south" and previous != phase:
			saw_red_start = true
			break
		previous = phase
	var fixture := single.snapshot()
	fixture.cars[0].progress = 32.0 - Traffic.LANE - Traffic.TURN_RADIUS - Traffic.STOP_FROM_NODE - 1.0
	fixture.cars[0].speed = 0.0
	fixture.cars[0].waiting = false
	check(saw_red_start and single.restore(fixture), "place an eastbound car one meter before a red light")
	single.step(2.0)
	var stop := Vector3((x + 1) * 32.0 - Traffic.STOP_FROM_NODE, 0.12, z * 32.0 + Traffic.LANE)
	var car: Dictionary = single.status().cars[0]
	check(car.waiting_at_signal and car.speed == 0.0 and as_vector(car.position).distance_to(stop) < 0.001,
			"vehicle nose stays behind the intersection at the stop line")
	single.step(3.0)
	check(as_vector(single.status().cars[0].position).distance_to(stop) < 0.001,
			"vehicle holds the stop line throughout the red interval")
	single.step(3.0)
	check(single.status().signals[junction].phase == "east_west"
			and as_vector(single.status().cars[0].position).x > stop.x + 1.0,
			"vehicle crosses the line on its own directional green")
	single.free()


func _run() -> void:
	check_stop_line()
	var traffic := Traffic.new()
	root.add_child(traffic)
	check(not traffic.configure(8, 3, 32.0, 25), "enforce car cap")
	check(not traffic.configure(8, 3, NAN, 1), "reject invalid geometry")
	check(traffic.configure(319, 3, 32.0, 24), "configure maximum traffic")
	var initial := traffic.status()
	check(initial.cars.size() == 24 and initial.signals.size() == 16, "grid signals and traffic budget")
	var twin := Traffic.new()
	root.add_child(twin)
	check(twin.configure(319, 3, 32.0, 24) and twin.snapshot() == traffic.snapshot(),
			"identical seed reproduces every car")
	var other := Traffic.new()
	root.add_child(other)
	check(other.configure(320, 3, 32.0, 24) and other.status().cars != initial.cars, "seed changes placements")
	other.free()
	var zero := Traffic.new()
	root.add_child(zero)
	check(zero.configure(319, 8, 64.0, 0), "empty fleet on maximum grid")
	zero.step(2.0)
	check(zero.status().cars.is_empty() and zero.status().signals.size() == 81
			and zero.valid_snapshot(zero.snapshot()), "signals operate without cars")
	zero.free()
	var same := traffic.snapshot()
	traffic.step(-1.0)
	traffic.step(INF)
	check(traffic.snapshot() == same, "invalid step leaves state intact")
	traffic.step(1.037)
	for i in 20:
		twin.step(0.05)
	twin.step(0.037)
	check(traffic.status() == twin.status(), "irregular frame sizes reproduce a fixed-tick simulation")
	twin.free()
	var capture := traffic.snapshot()
	check(traffic.valid_snapshot(capture), "validate current checkpoint")
	var wire_snapshot: Variant = JSON.parse_string(JSON.stringify(capture, "", false, true))
	check(traffic.restore(wire_snapshot), "restore JSON checkpoint")
	var restored := traffic.snapshot()
	traffic.step(4.41)
	var expected := traffic.status()
	check(traffic.restore(restored), "rewind")
	traffic.step(4.41)
	check(traffic.status() == expected, "checkpoint resumes identical motion and signal phases")
	var before := traffic.snapshot()
	for bad in [null, {}, [], {"cars": []}]:
		check(not traffic.restore(bad) and traffic.snapshot() == before, "invalid structure handled atomically")
	for edits in [{"tick": -1}, {"remainder": 0.05}, {"seed": "901"}, {"distance_m": INF},
			{"signal_stops": 1.5}, {"cars": []}, {"extra": true}]:
		var bad := before.duplicate(true)
		bad.merge(edits, true)
		check(not traffic.restore(bad) and traffic.snapshot() == before, "invalid checkpoint field is atomic")
	for edits in [{"id": 2}, {"progress": NAN}, {"speed": 255}, {"waiting": 1}]:
		var bad := before.duplicate(true)
		bad.cars[0].merge(edits, true)
		check(not traffic.restore(bad) and traffic.snapshot() == before, "invalid vehicle state is atomic")
	var overlap := before.duplicate(true)
	overlap.cars[9].progress = overlap.cars[0].progress
	check(not traffic.restore(overlap) and traffic.snapshot() == before, "reject overlapping same-lane positions")
	var stayed_on_road := true
	var stayed_apart := true
	var real_meshes := true
	var waited := false
	var moved_after_green := false
	var observed_wait: Dictionary = {}
	var phases: Dictionary = {}
	for frame in 500:
		traffic.step(0.15)
		var info := traffic.status()
		phases[info.signals[0].phase] = true
		for car in info.cars:
			var p := as_vector(car.position)
			var model := traffic.get_node("Car_%d" % car.id) as Node3D
			real_meshes = real_meshes and model.position.is_equal_approx(p) and model.get_child(0) is MeshInstance3D
			var road_distance := minf(absf(p.x - roundf(p.x / 32.0) * 32.0),
					absf(p.z - roundf(p.z / 32.0) * 32.0))
			stayed_on_road = stayed_on_road and road_distance <= 6.0
			for j in int(car.id):
				if p.distance_to(as_vector(info.cars[j].position)) < 3.85:
					stayed_apart = false
			if car.waiting_at_signal and car.speed < 0.05:
				if observed_wait.has(car.id) and p.distance_to(observed_wait[car.id]) < 0.001:
					waited = true
				observed_wait[car.id] = p
			elif observed_wait.has(car.id) and p.distance_to(observed_wait[car.id]) > 1:
				moved_after_green = true
				observed_wait.erase(car.id)
		if not traffic.valid_snapshot(traffic.snapshot()):
			check(false, "runtime never produces invalid state")
			break
	check(stayed_on_road, "rubber stays inside road envelopes through rounded turns")
	check(stayed_apart, "vehicles remain separated around junctions and following traffic")
	check(real_meshes and traffic.status().metrics.distance_m > 100, "meshes visibly travel along routes")
	check(waited and moved_after_green and traffic.status().metrics.signal_stops > 0,
			"cars wait at signals and proceed after a phase change")
	check(phases.has_all(["east_west", "north_south", "all_red"]), "signal cycles through both axes and clearance")
	traffic.free()
	if failures == 0:
		print("PASS traffic: seeded fleet, road lanes, visible motion, signal stops, spacing and checkpoint replay")
	quit(int(failures > 0))
