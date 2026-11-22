extends RefCounted
## An original clockwork glassworks district. Each resident traverses actual AStar2D edges.


class Resident extends Node2D:
	var home: int
	var late_post: int
	var anchor: int
	var next_stop := -1
	var destination := -1
	var last_service_day := -1
	var service_ticks := 0

	func _draw() -> void:
		draw_circle(Vector2.ZERO, 4.0, Color("#f3cb83") if home == 0 else Color("#89dacc"))


class District extends Node2D:
	signal tick_finished

	enum Place {NORTH_HOME, SOUTH_HOME, WEST, PUMP, EAST, HATCH, RACK, CANOPY, LAMP, BACK}
	const POSITIONS := [
		Vector2(40,64), Vector2(40,160), Vector2(40,112), Vector2(88,112), Vector2(136,112),
		Vector2(184,112), Vector2(136,160), Vector2(88,64), Vector2(184,64), Vector2(88,160)
	]
	const ROADS := [[0,2], [1,2], [2,3], [3,4], [4,5], [4,6], [3,7], [5,8], [3,9], [9,6]]
	const SHIFT := 96
	const SPEED := 16.0
	const MAX_CATCH_UP := 4
	const SERVICE_TIME := 3

	var paths := AStar2D.new()
	var staff: Array[Resident] = []
	var weather_events: Dictionary = {}
	var clock := 0  # The next tick to execute.
	var raining := false
	var night := true
	var reservation: Resident
	var shipments := 0
	var detour_entries := 0
	var closed_lane_entries := 0
	var shutter: Polygon2D
	var street_lamp: Polygon2D
	var shipment_marks: Array[Polygon2D] = []
	var hatch_sign: Label

	func _marker(title: String, at: Vector2, tint: Color, size: Vector2) -> Polygon2D:
		var marker := Polygon2D.new()
		marker.name = title
		marker.color = tint
		marker.polygon = PackedVector2Array([
			Vector2(-size.x, -size.y), Vector2(size.x, -size.y), size, Vector2(-size.x, size.y)
		])
		marker.position = at
		add_child(marker)
		return marker

	func _draw() -> void:
		for pair in ROADS:
			var tint := Color("#54727b")
			if raining and pair == [Place.PUMP, Place.EAST]:
				tint = Color("#9e6661")
			draw_line(POSITIONS[pair[0]], POSITIONS[pair[1]], tint, 4.0)
		for point in POSITIONS:
			draw_circle(point, 6.0, Color("#475860"))

	func _ready() -> void:
		for id in POSITIONS.size():
			paths.add_point(id, POSITIONS[id])
		for pair in ROADS:
			paths.connect_points(pair[0], pair[1])
		shutter = _marker("RainShutter", POSITIONS[Place.HATCH] - Vector2(0, 8), Color("#c58766"), Vector2(9, 3))
		street_lamp = _marker("NightLamp", POSITIONS[Place.LAMP] - Vector2(0, 8), Color("#ffe3a8"), Vector2(4, 4))
		for i in 2:
			shipment_marks.append(_marker("Crate%d" % i, POSITIONS[Place.HATCH] + Vector2(13 + 7 * i, 8),
				Color("#ace2cb"), Vector2(3, 3)))
		hatch_sign = Label.new()
		hatch_sign.name = "KilnLedger"
		hatch_sign.position = Vector2(217, 82)
		hatch_sign.add_theme_font_size_override("font_size", 13)
		add_child(hatch_sign)
		_add_resident("Glasskeeper", Place.NORTH_HOME, Place.LAMP)
		_add_resident("KilnRunner", Place.SOUTH_HOME, Place.RACK)
		_update_signs()

	func _add_resident(title: String, home: int, late_post: int) -> void:
		var person := Resident.new()
		person.name = title
		person.home = home
		person.late_post = late_post
		person.anchor = home
		person.destination = home
		person.position = paths.get_point_position(home)
		add_child(person)
		staff.append(person)

	func schedule_rain(at_tick: int, wet: bool) -> void:
		if at_tick >= clock:
			weather_events[at_tick] = wet

	func _set_rain(wet: bool) -> void:
		if raining == wet:
			return
		raining = wet
		if wet:
			paths.disconnect_points(Place.PUMP, Place.EAST)
			reservation = null
			for person in staff:
				person.service_ticks = 0
		else:
			paths.connect_points(Place.PUMP, Place.EAST)
		queue_redraw()

	func _advance_person(person: Resident, goal: int) -> void:
		person.destination = goal
		# A resident midway along an edge completes that short segment. Replan at the
		# next junction so a closure or shift change cannot teleport a moving actor.
		if person.next_stop < 0 and person.anchor != goal:
			var route := paths.get_id_path(person.anchor, goal)
			if route.size() > 1:
				person.next_stop = route[1]
				if raining:
					if (person.anchor == Place.RACK and person.next_stop == Place.BACK
							or person.anchor == Place.BACK and person.next_stop == Place.RACK):
						detour_entries += 1
					if (person.anchor == Place.PUMP and person.next_stop == Place.EAST
							or person.anchor == Place.EAST and person.next_stop == Place.PUMP):
						closed_lane_entries += 1
		if person.next_stop >= 0:
			var end := paths.get_point_position(person.next_stop)
			person.position = person.position.move_toward(end, SPEED)
			if person.position.is_equal_approx(end):
				person.anchor = person.next_stop
				person.next_stop = -1

	func _step() -> void:
		var phase := clock % SHIFT
		@warning_ignore("integer_division")
		var day := clock / SHIFT
		if weather_events.has(clock):
			_set_rain(weather_events[clock])
			weather_events.erase(clock)
		var work := phase >= 8 and phase < 70
		night = phase < 8 or phase >= 78
		if not work or raining:
			reservation = null
		elif not is_instance_valid(reservation):
			# The work order grants one hatch reservation, the other craftsperson
			# waits on the drying rack. Each can fill one crate per day.
			for person in staff:
				if person.last_service_day != day:
					reservation = person
					break
		for person in staff:
			var goal := person.home
			if raining and not night:
				goal = Place.CANOPY
			elif work:
				goal = Place.HATCH if person == reservation else Place.RACK
			elif not night:
				goal = person.late_post
			_advance_person(person, goal)
			if person == reservation and person.next_stop < 0 and person.anchor == Place.HATCH:
				person.service_ticks += 1
				if person.service_ticks == SERVICE_TIME:
					person.last_service_day = day
					person.service_ticks = 0
					shipments += 1
					reservation = null
			else:
				person.service_ticks = 0
		_update_signs()
		clock += 1
		tick_finished.emit()

	func _update_signs() -> void:
		var off_shift := night or clock % SHIFT >= 70
		shutter.visible = raining or off_shift
		street_lamp.visible = night
		var heading := "Kiln hatch open"
		if raining:
			heading = "Rain: hatch closed"
		elif off_shift:
			heading = "Off shift: hatch closed"
		hatch_sign.text = heading + "\nCrates sent: %d" % shipments
		for i in shipment_marks.size():
			shipment_marks[i].visible = i < shipments

	func advance_to(target_tick: int, step_budget: int = MAX_CATCH_UP) -> int:
		if target_tick <= clock:
			return 0
		var count := clampi(target_tick - clock, 0, clampi(step_budget, 0, MAX_CATCH_UP))
		for i in count:
			_step()
		return count

	func snapshot() -> Dictionary:
		var positions: Array[Vector2] = []
		var destinations: Array[int] = []
		var anchors: Array[int] = []
		var legs: Array[int] = []
		var completed: Array[int] = []
		var service_progress: Array[int] = []
		var at_hatch := 0
		for person in staff:
			positions.append(person.position)
			destinations.append(person.destination)
			anchors.append(person.anchor)
			legs.append(person.next_stop)
			completed.append(person.last_service_day)
			service_progress.append(person.service_ticks)
			if person.position.is_equal_approx(paths.get_point_position(Place.HATCH)):
				at_hatch += 1
		return {"clock": clock, "positions": positions, "goals": destinations, "anchors": anchors,
			"legs": legs, "served_day": completed, "service_progress": service_progress, "reserved_for": staff.find(reservation),
			"at_hatch": at_hatch, "rain": raining, "night": street_lamp.visible,
			"shutter": shutter.visible, "sign": hatch_sign.text, "marks": int(shipment_marks[0].visible) + int(shipment_marks[1].visible),
			"shipments": shipments, "lane_open": paths.are_points_connected(Place.PUMP, Place.EAST),
			"detours": detour_entries, "closed_lane_entries": closed_lane_entries}


func _check(key: String, passed: bool, detail: String) -> Dictionary:
	return {"id": key, "passed": passed, "detail": detail}


func _observe(tree: SceneTree, log: Array) -> District:
	var district := District.new()
	tree.root.add_child(district)
	if not district.is_node_ready():
		await district.ready
	district.schedule_rain(16, true)
	district.schedule_rain(33, false)
	district.tick_finished.connect(func() -> void: log.append(district.snapshot()))
	return district


func run(tree: SceneTree) -> Dictionary:
	const UNTIL := 106
	var frames: Array = []
	var district: District = await _observe(tree, frames)
	var start := district.snapshot()
	while district.clock < UNTIL:
		district.advance_to(UNTIL, 1)
	var p := District.Place
	var points := District.POSITIONS
	var day_goals := [p.HATCH, p.RACK]
	var homes := [points[p.NORTH_HOME], points[p.SOUTH_HOME]]
	var scheduled: bool = (start.positions == homes and frames[7].night and not frames[8].night
		and frames[8].goals == day_goals and frames[70].goals == [p.LAMP, p.RACK]
		and frames[78].night and frames[95].positions == homes and frames[104].goals == day_goals)
	var max_step := 0.0
	var on_road := true
	var midway := false
	var max_service := 0
	var last_positions: Array = start.positions
	for frame in frames:
		for i in frame.positions.size():
			var pos: Vector2 = frame.positions[i]
			max_step = maxf(max_step, pos.distance_to(last_positions[i]))
			var anchor: Vector2 = points[frame.anchors[i]]
			var leg: int = frame.legs[i]
			if leg < 0:
				on_road = on_road and pos.is_equal_approx(anchor)
			else:
				var end: Vector2 = points[leg]
				var projected := Geometry2D.get_closest_point_to_segment(pos, anchor, end)
				on_road = on_road and pos.is_equal_approx(projected)
				midway = midway or (not pos.is_equal_approx(anchor) and not pos.is_equal_approx(end))
		max_service = maxi(max_service, frame.at_hatch)
		last_positions = frame.positions
	var commutes: bool = (on_road and midway and is_equal_approx(max_step, District.SPEED)
		and frames[79].positions != frames[95].positions)
	var service: bool = (frames[8].goals == day_goals and max_service == 1
		and frames[69].shipments == 2 and frames[69].served_day == [0, 0])

	var disruption: bool = (frames[15].lane_open and not frames[16].lane_open and frames[16].shutter
		and frames[16].goals == [p.CANOPY, p.CANOPY] and frames[32].positions == [points[p.CANOPY], points[p.CANOPY]]
		and frames[32].shipments == 0 and frames[32].detours > 0 and frames[32].closed_lane_entries == 0
		and frames[33].lane_open and not frames[33].shutter and frames[33].goals == day_goals)
	var consequences: bool = (frames[16].sign.contains("hatch closed") and frames[32].marks == 0
		and frames[69].sign.contains("Crates sent: 2") and frames[69].marks == 2 and not frames[69].night
		and frames[95].night and frames[95].shutter and frames[95].sign.contains("Off shift"))

	var replay: Array = []
	var delayed: District = await _observe(tree, replay)
	while delayed.clock < 14:
		delayed.advance_to(14)
	var before_clock := delayed.clock
	var idle_steps := delayed.advance_to(UNTIL, 0) + delayed.advance_to(0)
	var catch_up_steps := delayed.advance_to(UNTIL, 100)
	var after_clock := delayed.clock
	var caught_gradually := (idle_steps == 0 and catch_up_steps == District.MAX_CATCH_UP
		and after_clock == before_clock + District.MAX_CATCH_UP and delayed.raining)
	var chunks := 1
	while delayed.clock < UNTIL:
		delayed.advance_to(UNTIL, 3)
		chunks += 1
	var same: bool = replay == frames and delayed.clock == district.clock
	var checks := [
		_check("day-night-schedule", scheduled, "Two homes, morning posts, later posts, night return and next shift match=%s." % scheduled),
		_check("routed-commutes", commutes, "Observed intermediate Node2D positions=%s, on waypoint segments=%s, largest step=%.1f." % [midway, on_road, max_step]),
		_check("service-capacity", service, "Peak simultaneous arrivals at the kiln hatch=%d. First-shift crates=%d." % [max_service, frames[69].shipments]),
		_check("weather-disruption", disruption, "Both sheltered=%s. Detour entries=%d, newly entered closed edges=%d." % [
			frames[32].positions == [points[p.CANOPY], points[p.CANOPY]], frames[32].detours, frames[32].closed_lane_entries]),
		_check("gradual-catch-up", caught_gradually and same, "From tick %d one bounded call advanced %d ticks. Recovery used %d batches." % [before_clock, catch_up_steps, chunks]),
		_check("district-consequences", consequences, "Shutter, kiln ledger, visible crate marks and night lamp match the district timeline=%s." % consequences),
		_check("deterministic-replay", same, "Compared every resident position, route, service record and visible state over %d ticks." % frames.size())
	]
	var metrics := {"ticks": frames.size(), "inhabitants": district.staff.size(), "first_shift_shipments": frames[69].shipments,
		"peak_hatch_occupancy": max_service, "weather_detours": frames[32].detours, "maximum_step_units": max_step,
		"catch_up_step_limit": catch_up_steps}
	district.free()
	delayed.free()
	return {"id": "citizens", "checks": checks, "metrics": metrics}
