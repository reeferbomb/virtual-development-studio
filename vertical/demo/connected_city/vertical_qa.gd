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

func same(a: Variant,b: Variant) -> bool:
	if (a is int or a is float) and (b is int or b is float):
		return absf(float(a)-float(b)) < 0.000001
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size(): return false
		for key in a:
			if not b.has(key) or not same(a[key],b[key]): return false
		return true
	if a is Array and b is Array:
		if a.size() != b.size(): return false
		for i in a.size():
			if not same(a[i],b[i]): return false
		return true
	return a == b

func ticks(n: int) -> void:
	for i in n:
		await physics_frame
		physics_ticks += 1

func walk(target: Vector3, tolerance: float = 0.35, limit: int = 1800) -> bool:
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

func road(x: float,z: float) -> Vector3:
	var extent := float(game.config.world_size)
	return Vector3(clampf(x,0.55,extent-0.55),0,clampf(z,0.55,extent-0.55))

func grid(target: Vector3) -> bool:
	var block := float(game.config.block_size)
	var p: Vector3 = game.player.global_position
	var gx := roundf(p.x/block)*block
	var gz := roundf(p.z/block)*block
	if absf(p.z-gz) <= absf(p.x-gx):
		if not await walk(road(p.x,gz)): return false
	else:
		if not await walk(road(gx,p.z)): return false
	if not await walk(road(gx,gz)): return false
	var tz := roundf(target.z/block)*block
	if not await walk(road(gx,tz)): return false
	if not await walk(road(target.x,tz)): return false
	return await walk(target)

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks: ok = ok and row.status == "passed"
	metrics.physics_ticks = physics_ticks
	metrics.walk_m = walked_m
	print("STUDIO_VERTICAL_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://vertical.tscn")
	if not check("Load vertical city",scene is PackedScene,"Generated project scene"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	if not check("Combined world initialized",game.vertical_ready and game.player.is_on_floor() and game.buildings.size() == game.config.buildings.size(),"City, interior, underground transit and destruction all constructed"):
		finish()
		return
	var entrance: Vector3 = game.interior.entrance_position()
	var room: Vector3 = game.interior.room_target()
	check("Approach building",await grid(entrance),"Walk the road grid to the entrance")
	check("Closed door stops player",not await walk(room,0.35,100),"Character collision with closed door")
	check("Open door by interaction",game.interact_world() and game.interior.status().door_open,"Actual door moves from threshold")
	await ticks(3)
	check("Walk into rear room",await walk(room),"Collision-backed entry through door and partition")
	check("Explore furnished interior",game.interior_visited and game.interior.status().room_count >= 2,"Physical interior discovery")
	var path := "user://vertical_qa_%d.json" % Time.get_ticks_usec()
	check("Interior checkpoint constrained",not game.save_world(path),"Save only from accessible exterior")
	check("Return outside",await walk(entrance),"Walk out of same entry")
	var demo_origin: Vector3 = game.demolition_origin
	var block := float(game.config.block_size)
	var lab_approach := Vector3(block,0,demo_origin.z-4)
	var reached_lab := await grid(lab_approach) and await walk(demo_origin+Vector3(0,0,-4))
	check("Reach cover lab",reached_lab,"Approach from road shoulder, not along the panel row: %s" % game.player.global_position)
	var panel: Vector3 = game._vec(game.demolition.status().targets[1].position)
	var aim: Vector3 = panel-game.player.get_node("Camera3D").global_position
	var shot: Dictionary = game.shoot_cover(aim.normalized())
	check("Shoot actual cover",shot.fired and shot.hit and shot.id == 1,"Camera ray damages center panel")
	check("Enforce fire cooldown",not game.shoot_cover(aim.normalized()).fired,"Immediate extra shot refused")
	await ticks(20)
	game.shoot_cover(aim.normalized())
	await ticks(20)
	shot = game.shoot_cover(aim.normalized())
	await ticks(4)
	check("Break panel",shot.destroyed and game.demolition.status().destroyed == 1,"Three accepted shots remove collision")
	check("Traverse destroyed cover",await walk(demo_origin+Vector3(0,0,4)),"Player crosses previously blocked segment")
	var stations: Array = game.transit.status().stations
	var west: Vector3 = stations[0].entrance
	var reached_metro := await walk(Vector3(block,0,demo_origin.z+4)) and await walk(Vector3(block,0,west.z)) and await walk(west)
	check("Reach west metro",reached_metro,"Walk around surviving cover to underground access: %s" % game.player.global_position)
	check("Descend below streets",game.interact_world() and game.player.global_position.y < -6,"Lift transition into physical station")
	await ticks(8)
	check("Walk underground platform",await walk(stations[0].platform),"Station floor supports moving player")
	for i in 2400:
		if game.transit.status().station == 0: break
		await ticks(1)
	check("Board west station train",game.interact_world() and game.transit.status().riding,"Board open carriage")
	await ticks(2)
	var aboard: Vector3 = game.player.global_position
	for i in 2400:
		if game.transit.status().phase == "travel": break
		await ticks(1)
	check("Moving train locks exit",game.transit.status().phase == "travel" and not game.interact_world(),"Cannot disembark in tunnel")
	for i in 2400:
		if game.transit.status().station == 1: break
		await ticks(1)
	check("Ride to east station",game.transit.status().station == 1 and game.player.global_position.distance_to(aboard) > 50,"Passenger carried through tunnel")
	check("Disembark at east station",game.interact_world() and not game.transit.status().riding,"Open doors permit exit")
	await ticks(3)
	check("Metro trip recorded",game.metro_trips == 1,"Completed one distinct station trip")
	check("Walk to east lift",await walk(stations[1].portal),"Walk underground to lift")
	check("Return to street",game.interact_world() and game.player.global_position.y >= 0,"Ascend to surface")
	await ticks(8)
	var stored := {"interior":game.interior.snapshot(),"transit":game.transit.snapshot(),"demolition":game.demolition.snapshot()}
	check("Save combined checkpoint",game.save_world(path),"Persist city plus interior, train and cover")
	metrics.interior_rooms = game.interior.status().room_count
	metrics.metro_trips = game.metro_trips
	metrics.cover_destroyed = game.demolition.status().destroyed
	metrics.stations = stations.size()
	metrics.buildings = game.buildings.size()
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	var loaded: bool = game.load_world(path)
	check("Restore combined checkpoint",loaded and game.metro_trips == 1 and game.interior_visited and same(game.interior.snapshot(),stored.interior) and same(game.transit.snapshot(),stored.transit) and same(game.demolition.snapshot(),stored.demolition),"Fresh scene restores exact feature state")
	var corrupted: Dictionary = game.persistence.read_checkpoint(path)
	corrupted.demolition = {}
	var bad_path := path+".bad"
	check("Reject malformed checkpoint",game.persistence.write_checkpoint(bad_path,corrupted) and not game.load_world(bad_path) and game.demolition.status().destroyed == 1,"Invalid state rejected before mutation")
	if not check("Host shared city",game.start_network("host",0),"Real loopback ENet server"):
		finish()
		return
	var viewport := SubViewport.new()
	viewport.own_world_3d = true
	root.add_child(viewport)
	var client = scene.instantiate()
	viewport.add_child(client)
	await ticks(10)
	var port: int = game.network.status().port
	check("Join second city scene",port > 0 and client.start_network("client",port),"Independent ENet client and simulation")
	for i in 2400:
		await ticks(1)
		if client._applied_world_tick >= 1 and game.remote_meshes.size() >= 1: break
	var shared: Dictionary = client.network.latest_world()
	check("Receive authoritative population",not shared.is_empty() and client._applied_world_tick >= 1 and same(client.traffic.snapshot(),shared.get("traffic",{})) and same(client.civilians.snapshot(),shared.get("civilians",{})),"Client applies exact host traffic and resident snapshots")
	var initial_tick: int = client._applied_world_tick
	await ticks(120)
	check("Live shared updates",client._applied_world_tick > initial_tick and game.remote_meshes.size() >= 1,"Subsequent server ticks and visible peer")
	check("Online local edits blocked",not game.interact_world() and not game.save_world(path) and not game.shoot_cover(Vector3.FORWARD).fired,"Offline-only special interactions cannot diverge online")
	metrics.shared_world_tick = client._applied_world_tick
	metrics.network_peers = game.remote_meshes.size()
	client.network.stop()
	for i in 1200:
		await ticks(1)
		if game.remote_meshes.is_empty(): break
	check("Remove departing peer",game.remote_meshes.is_empty(),"Server reconciles disconnect")
	game.network.stop()
	viewport.queue_free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(bad_path))
	finish()
