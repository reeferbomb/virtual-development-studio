extends SceneTree

var game
var checks: Array = []
var metrics := {}
var physics_ticks := 0
var walked_m := 0.0

func _initialize() -> void:
	call_deferred("run")

func check(label: String, ok: bool, detail: String) -> bool:
	checks.append({"name":label,"status":"passed" if ok else "failed","detail":detail})
	return ok

func same_state(a: Variant, b: Variant) -> bool:
	# JSON decimal parsing may round a binary floating-point value by a few ULPs.
	if (a is int or a is float) and (b is int or b is float):
		return absf(float(a)-float(b)) <= 0.0000001
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size():
			return false
		for key in a:
			if not b.has(key) or not same_state(a[key],b[key]):
				return false
		return true
	if a is Array and b is Array:
		if a.size() != b.size():
			return false
		for i in a.size():
			if not same_state(a[i],b[i]):
				return false
		return true
	return a == b

func ticks(n: int) -> void:
	for i in n:
		await physics_frame
		physics_ticks += 1

func walk(target: Vector3, tolerance: float = 0.33, limit: int = 1400) -> bool:
	for i in limit:
		var old: Vector3 = game.player.global_position
		var offset := Vector2(target.x-old.x,target.z-old.z)
		if offset.length() <= tolerance:
			game.player.set_test_drive(Vector2.ZERO)
			await ticks(1)
			return true
		game.player.set_test_drive(offset.normalized(),true)
		await ticks(1)
		walked_m += old.distance_to(game.player.global_position)
	game.player.set_test_drive(Vector2.ZERO)
	return false

func road_point(x: float,z: float) -> Vector3:
	var size := float(game.config.world_size)
	return Vector3(clampf(x,0.55,size-0.55),0,clampf(z,0.55,size-0.55))

func drive_grid(target: Vector3) -> bool:
	# Physical walking follows the connected road grid, not through building lots.
	var block := float(game.config.block_size)
	var p: Vector3 = game.player.global_position
	var grid_x := roundf(p.x/block)*block
	var grid_z := roundf(p.z/block)*block
	if absf(p.z-grid_z) <= absf(p.x-grid_x):
		if not await walk(road_point(grid_x,p.z)):
			return false
	else:
		if not await walk(road_point(p.x,grid_z)):
			return false
	if not await walk(road_point(grid_x,grid_z)):
		return false
	var target_z := roundf(target.z/block)*block
	if not await walk(road_point(grid_x,target_z)):
		return false
	if not await walk(road_point(target.x,target_z)):
		return false
	return await walk(road_point(target.x,target.z))

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	metrics.physics_ticks = physics_ticks
	metrics.walk_m = walked_m
	print("STUDIO_CITY_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://city.tscn")
	if not check("Import city scene",scene is PackedScene,"Actual generated project"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	if not check("Initialize physical city",game.ready_for_play and game.player.is_on_floor() and game.buildings.size() == game.config.buildings.size(),"All city modules ready; actual collision ground"):
		finish()
		return
	check("Default city scale and occupancy",game.config.world_size == 192 and game.config.blocks == 4 and game.buildings.size() >= 16,"Four-by-four generated blocks")
	var before_traffic: Dictionary = game.traffic.status()
	var before_civilians: Dictionary = game.civilians.status()
	check("Spawn traffic and population",before_traffic.cars.size() == 12 and before_civilians.count == 20,"Exact configured active simulation counts")
	await ticks(720)
	var after_traffic: Dictionary = game.traffic.status()
	var after_civilians: Dictionary = game.civilians.status()
	check("Traffic progresses on lanes",after_traffic.metrics.distance_m > before_traffic.metrics.distance_m and after_traffic.metrics.signal_stops > 0,"Measured distance and signal stops")
	var moved := false
	for i in after_civilians.civilians.size():
		if after_civilians.civilians[i].position != before_civilians.civilians[i].position:
			moved = true
	check("Civilian schedule advances",after_civilians.hour != before_civilians.hour and moved,"Clock and actual pedestrian positions advance")
	check("Traffic lights present",after_traffic.signals.size() == 25,"Each intersection has a controlled signal")
	var reached := true
	for i in game.landmarks.size():
		var landmark: Dictionary = game.landmarks[i]
		reached = (await drive_grid(landmark.position)) and reached
		await ticks(2)
		if game.tour_index != i+1:
			reached = false
	check("Walk complete district tour",reached and game.tour_index == game.landmarks.size() and game.landmarks.size() >= 3,"Traversed all district markers using connected roads")
	var first: Dictionary = game.config.buildings[0]
	var center: Vector3 = game._vec(first.center)
	var size: Vector3 = game._vec(first.size)
	var block := float(game.config.block_size)
	var street_z := floorf(center.z/block)*block
	check("Reach facade from street",await drive_grid(Vector3(center.x,0,street_z)),"Physical route approaches building")
	var from: Vector3 = game.player.global_position+Vector3.UP
	var target := Vector3(center.x,1,center.z)
	var ray := PhysicsRayQueryParameters3D.create(from,target,1)
	var impact: Dictionary = game.get_world_3d().direct_space_state.intersect_ray(ray)
	check("Collision-backed building",not impact.is_empty() and impact.collider is StaticBody3D and impact.collider.has_meta("building_id"),"Actual physics ray hits facade")
	var collided := not await walk(center,0.25,300)
	check("Player cannot walk through facade",collided and game.player.global_position.distance_to(center) > 0.9,"Character body stops at solid geometry")
	# Return to an accessible road before writing the checkpoint.
	check("Return to public street",await walk(road_point(center.x,street_z)),"Player can leave blocked route")
	var save_traffic: Dictionary = game.traffic.snapshot()
	var save_civilians: Dictionary = game.civilians.snapshot()
	var save_position: Vector3 = game.player.global_position
	var saved_tour: int = game.tour_index
	var path := "user://city_qa_%d.json" % Time.get_ticks_usec()
	check("Save city checkpoint",game.save_world(path),"Checksummed state includes traffic, population and tour")
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	var loaded: bool = game.load_world(path)
	var traffic_equal: bool = same_state(game.traffic.snapshot(),save_traffic)
	var civilians_equal: bool = game.civilians.snapshot() == save_civilians
	var position_equal: bool = game.player.global_position.distance_to(save_position) < 0.01
	check("Restore city simulation",loaded and traffic_equal and civilians_equal and game.tour_index == saved_tour and position_equal,"Fresh scene restore: loaded=%s traffic=%s civilians=%s position=%s" % [loaded,traffic_equal,civilians_equal,position_equal])
	var corrupted: Dictionary = game.persistence.read_checkpoint(path)
	corrupted.tour_index = 999
	var bad_path := path+".bad"
	check("Reject malformed city checkpoint",game.persistence.write_checkpoint(bad_path,corrupted) and not game.load_world(bad_path) and game.tour_index == saved_tour,"Invalid state leaves city unchanged")
	metrics.city_size_m = game.config.world_size
	metrics.buildings = game.buildings.size()
	metrics.traffic_distance_m = game.traffic.status().metrics.distance_m
	metrics.traffic_signal_stops = game.traffic.status().metrics.signal_stops
	metrics.civilian_count = game.civilians.status().count
	metrics.districts_visited = game.tour_index
	# Exercise actual scene connection, not just a fake/offline network model.
	if not check("Host city on loopback",game.start_network("host",0),"Real ENet host with ephemeral local port"):
		finish()
		return
	var peer = game.NETWORK.new()
	root.add_child(peer)
	peer.configure(float(game.config.world_size),game._vec(game.config.spawn))
	if peer.has_method("set_obstacles"):
		peer.set_obstacles(game.config.buildings)
	var port: int = game.network.status().port
	if not check("Join host with independent peer",port > 0 and peer.join(port),"Second ENet endpoint"):
		finish()
		return
	for i in 2400:
		peer.step(1.0/60.0,Vector2.ZERO)
		await ticks(1)
		if peer.status().connected and game.remote_meshes.size() >= 1:
			break
	if not check("Networked remote avatar visible",peer.status().connected and game.remote_meshes.size() >= 1,"Peer snapshot creates visual representation"):
		finish()
		return
	var initial: Vector3 = game.player.global_position
	game.set_network_test_input(Vector2(1,0))
	for i in 240:
		peer.step(1.0/60.0,Vector2(0,1))
		await ticks(1)
		if game.player.global_position.distance_to(initial) > 1.5 and peer.status().local_position.distance_to(game._vec(game.config.spawn)) > 1.5:
			break
	game.set_network_test_input(Vector2.ZERO)
	check("Authoritative online movement",game.player.global_position.distance_to(initial) > 1.5 and peer.status().local_position.distance_to(game._vec(game.config.spawn)) > 1.5,"Both local player and remote endpoint move through server state")
	check("Network mode blocks offline checkpoint",not game.save_world(path),"No unsynchronized local restore while connected")
	metrics.network_peer_count = game.remote_meshes.size()
	peer.stop()
	for i in 1200:
		await ticks(1)
		if game.remote_meshes.is_empty():
			break
	check("Remote leave removes avatar",game.remote_meshes.is_empty(),"Disconnect reconciles scene replicas")
	game.network.stop()
	peer.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(bad_path))
	finish()
