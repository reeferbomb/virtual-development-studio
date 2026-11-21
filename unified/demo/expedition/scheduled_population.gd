extends "res://population.gd"

const DAY_SECONDS := 120.0
const SECONDS_PER_HOUR := DAY_SECONDS / 24.0
const COMMUTE_HOURS := 2.0

class DailyRoute:
	var stops: Array[Vector3] = []
	var shift: float
	var pace_radius: float
	var activity := "home"

	func _init(npc: Resident, size: float) -> void:
		var rng := RandomNumberGenerator.new()
		rng.seed = (npc.id + "/schedule").hash()
		shift = rng.randf_range(-0.5, 0.5)
		pace_radius = size * 0.018
		var center := Vector3(npc.chunk.x + 0.5, 0.0, npc.chunk.y + 0.5) * size
		center = center.lerp(npc.home, 0.3)
		var bearing := rng.randf_range(0.0, TAU)
		for index in 3:
			var angle := bearing + index * TAU / 3.0
			var radius := size * rng.randf_range(0.24, 0.30)
			stops.append(center + Vector3(cos(angle), 0.0, sin(angle)) * radius)
		npc.home = stops[0]

	func pose(npc: Resident, seconds_today: float) -> void:
		var hour := fposmod(seconds_today / SECONDS_PER_HOUR - shift, 24.0)
		var start := 0
		var finish := 0
		var departure := 0.0
		if hour < 6.0 or hour >= 22.0:
			activity = "home"
		elif hour < 8.0:
			activity = "to_work"
			finish = 1
			departure = 6.0
		elif hour < 15.5:
			activity = "work"
			start = 1
			finish = 1
		elif hour < 17.5:
			activity = "to_leisure"
			start = 1
			finish = 2
			departure = 15.5
		elif hour < 20.0:
			activity = "leisure"
			start = 2
			finish = 2
		else:
			activity = "to_home"
			start = 2
			departure = 20.0

		# An eased walk between stops joins the small local pacing loop smoothly.
		var t := clampf((hour - departure) / COMMUTE_HOURS, 0.0, 1.0)
		var progress := t * t * (3.0 - 2.0 * t)
		var progress_speed := 6.0 * t * (1.0 - t) / (COMMUTE_HOURS * SECONDS_PER_HOUR)
		var pace_speed := 12.0 * TAU / DAY_SECONDS
		var angle := npc.phase + seconds_today * pace_speed
		var pace := Vector3(cos(angle), 0.0, sin(angle)) * pace_radius
		var velocity := (stops[finish] - stops[start]) * progress_speed
		velocity += Vector3(-sin(angle), 0.0, cos(angle)) * pace_radius * pace_speed
		npc.position = stops[start].lerp(stops[finish], progress) + pace
		npc.rotation.y = atan2(velocity.x, velocity.z)
		var stride := sin(npc.phase + seconds_today * TAU) * minf(0.35, velocity.length() * 0.25)
		npc.left_leg.rotation.x = stride
		npc.right_leg.rotation.x = -stride

# Quantize only the sampled instant. Sub-frame deltas still accumulate on the
# same full-precision clock as the checkpoint's world_seconds.
func _sample_seconds() -> float:
	return snappedf(_time, 0.000001)

func clock_snapshot() -> Dictionary:
	var seconds := _sample_seconds()
	var hour := fposmod(seconds, DAY_SECONDS) / SECONDS_PER_HOUR
	var phase := "home"
	if hour >= 7.0 and hour < 16.0:
		phase = "work"
	elif hour >= 16.0 and hour < 21.0:
		phase = "leisure"
	return {"day": floori(seconds / DAY_SECONDS) + 1, "hour": hour, "phase": phase}

func _load_chunk(key: Vector2i) -> void:
	super._load_chunk(key)
	var seconds := fposmod(_sample_seconds(), DAY_SECONDS)
	for npc: Resident in _chunks[key].get_children():
		var route := DailyRoute.new(npc, _size)
		npc.set_meta("daily_route", route)
		route.pose(npc, seconds)

func step(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0 or not is_finite(_time + delta):
		return
	_time += delta
	var seconds := fposmod(_sample_seconds(), DAY_SECONDS)
	for npc in _residents.values():
		var route: DailyRoute = npc.get_meta("daily_route")
		route.pose(npc, seconds)

func snapshot() -> Dictionary:
	var state := super.snapshot()
	for id in state:
		var route: DailyRoute = _residents[id].get_meta("daily_route")
		state[id].phase = route.activity
	return state

func nearest(position: Vector3) -> Dictionary:
	var result := super.nearest(position)
	if not result.is_empty():
		var route: DailyRoute = _residents[result.id].get_meta("daily_route")
		result.phase = route.activity
	return result
