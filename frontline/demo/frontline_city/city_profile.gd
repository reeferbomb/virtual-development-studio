extends SceneTree

const SAMPLE_COUNT := 600

func _initialize() -> void:
	call_deferred("run")

func percentile(samples: Array, fraction: float) -> float:
	return float(samples[clampi(ceili(samples.size()*fraction)-1,0,samples.size()-1)]) / 1000.0

func run() -> void:
	var scene = load("res://city.tscn")
	var game = scene.instantiate()
	root.add_child(game)
	for i in 45:
		await physics_frame
	if not game.ready_for_play:
		quit(1)
		return
	var samples: Array = []
	var total := 0.0
	var start := Time.get_ticks_usec()
	for i in SAMPLE_COUNT:
		await physics_frame
		samples.append(game.simulation_usec)
		total += game.simulation_usec
	var elapsed := Time.get_ticks_usec()-start
	samples.sort()
	var report := {
		"scope":"Headless CPU wall time of city simulation callback only; excludes rendering, GPU, and target hardware validation.",
		"spec":game._identity(),"samples":SAMPLE_COUNT,"mean_ms":total/SAMPLE_COUNT/1000.0,
		"p50_ms":percentile(samples,0.50),"p95_ms":percentile(samples,0.95),"p99_ms":percentile(samples,0.99),"max_ms":float(samples.back())/1000.0,
		"elapsed_ms":float(elapsed)/1000.0,"scene_nodes":get_node_count(),"buildings":game.buildings.size(),"window_instances":game._window_transforms.size(),"road_mark_instances":game._paint_transforms.size(),
		"traffic":game.traffic.status().cars.size(),"civilians":game.civilians.status().count
	}
	print("STUDIO_CITY_PROFILE_JSON " + JSON.stringify(report))
	quit(0)
