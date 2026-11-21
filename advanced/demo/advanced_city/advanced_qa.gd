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

func walk(target: Vector3,tolerance: float = 0.3,limit: int = 1800) -> bool:
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
	var b := float(game.config.block_size)
	var p: Vector3 = game.player.global_position
	var gx := roundf(p.x/b)*b
	var gz := roundf(p.z/b)*b
	if absf(p.z-gz) <= absf(p.x-gx):
		if not await walk(road(p.x,gz)): return false
	else:
		if not await walk(road(gx,p.z)): return false
	if not await walk(road(gx,gz)): return false
	var tz := roundf(target.z/b)*b
	if not await walk(road(gx,tz)): return false
	if not await walk(road(target.x,tz)): return false
	return await walk(target)

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks: ok = ok and row.status == "passed"
	metrics.physics_ticks = physics_ticks
	metrics.walk_m = walked_m
	print("STUDIO_ADVANCED_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func ride_floor(index: int) -> bool:
	if not await walk(game.tower.cabin_position()): return false
	if not game.interact_world(): return false
	await ticks(3)
	if game.tower.status().phase != "moving" or not game.tower.status().riding: return false
	if game.interact_world(): return false
	for i in 1200:
		if game.tower.status().floor == index and game.tower.status().phase == "docked": break
		await ticks(1)
	if game.tower.status().floor != index or game.tower.status().phase != "docked": return false
	await ticks(3)
	return await walk(game.tower.landing_position(index)) and absf(game.player.global_position.y-float(index)*3.0) < 0.3

func meet(id: String) -> Dictionary:
	# Dialogue is evaluated against real live resident positions. Place the test
	# actor near each resident (fixture setup, not counted as physical walking).
	for resident in game.civilians.status().civilians:
		if resident.id == id:
			game.player.global_position = game._vec(resident.position)+Vector3.UP*0.08
			game.player.velocity = Vector3.ZERO
			await ticks(3)
			return game.interact_resident()
	return {"accepted":false,"quest_stage":"missing","id":""}

func run() -> void:
	var scene = load("res://advanced.tscn")
	if not check("Load advanced city",scene is PackedScene,"Generated Godot project"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	if not check("Complete city initialized",game.advanced_ready and game.tower_ready and game.player.is_on_floor() and game.buildings.size() == game.config.buildings.size(),"Inherited interior and metro plus new tower and vehicle"):
		finish()
		return
	var offline_path := "user://advanced_qa_%d.json" % Time.get_ticks_usec()
	var online_path := offline_path+".session"
	game.session_path = online_path
	check("Three physical floors",game.tower.status().floor_count == 3,"Tower generated within its lot")
	check("Enter drivable car",game.interact_vehicle() and game.vehicle.status().driving,"Vehicle near spawn takes driver")
	var initial: Vector3 = game.vehicle.status().position
	game.set_vehicle_test_input(Vector2(0,1))
	await ticks(150)
	var moving: Dictionary = game.vehicle.status()
	check("Accelerate down the street",moving.position.distance_to(initial) > 8.0 and moving.speed > 1.0,"Real physics movement from driver throttle")
	check("Passenger follows driver seat",game.player.global_position.distance_to(moving.seat_position) < 0.3,"Camera actor follows moving vehicle")
	check("Driving blocks offline saves",not game.save_world(offline_path),"Do not checkpoint while driving")
	game.set_vehicle_test_input(Vector2.ZERO,true)
	await ticks(150)
	check("Brake to a halt",absf(game.vehicle.status().speed) < 0.2,"Brake decelerates before exit")
	check("Exit parked car",game.interact_vehicle() and not game.vehicle.status().driving,"Clear exit position restores walker")
	await ticks(10)
	check("Player grounded after exit",game.player.is_on_floor(),"Normal walking restored")
	var entrance: Vector3 = game.tower.entrance_position()
	check("Walk to tower facade",await grid(entrance),"Physical road-grid traversal to tower")
	check("Open tower entrance",game.interact_world(),"E operates the tower door")
	await ticks(3)
	check("Walk ground floor lobby",await walk(game.tower.landing_position(0)),"Real collision-backed lobby")
	check("Ride first upper floor",await ride_floor(1),"Cabin moves with passenger, opens at floor 1")
	check("Ride second upper floor",await ride_floor(2),"Walk out, reboard and travel to floor 2")
	check("Elevated checkpoint blocked",not game.save_world(offline_path),"Checkpoint only from accessible street")
	check("Return elevator to ground",await ride_floor(0),"Third continuous elevator trip returns to ground")
	check("Walk out to street",await walk(entrance),"Leave through ground-floor entrance")
	metrics.elevator_trips = game.tower.status().trips
	metrics.floors = game.tower.status().floor_count
	var dialog: Dictionary = game.dialogue.status()
	var giver: String = dialog.giver_id
	var recipient: String = dialog.recipient_id
	var accepted: Dictionary = await meet(giver)
	check("Start resident quest",accepted.accepted and accepted.quest_stage == "deliver","Talk to the actual giver resident")
	var delivered: Dictionary = await meet(recipient)
	check("Deliver to second resident",delivered.accepted and delivered.quest_stage == "return","Distinct resident advances the errand")
	var completed: Dictionary = await meet(giver)
	check("Complete resident quest",completed.accepted and completed.quest_stage == "complete","Return to giver and finish")
	# A safe surface fixture point for the checkpoint and server start.
	game.player.global_position = game._vec(game.config.spawn)+Vector3.UP*0.08
	game.player.velocity = Vector3.ZERO
	await ticks(5)
	var stored := {"tower":game.tower.snapshot(),"vehicle":game.vehicle.snapshot(),"dialogue":game.dialogue.snapshot()}
	var unsafe_parking: Dictionary = stored.vehicle.duplicate(true)
	unsafe_parking.position = [game.demolition_origin.x,stored.vehicle.position[1],game.demolition_origin.z-2.3]
	unsafe_parking.yaw = 0.0
	check("Guard checkpoint parking clearance",not game._vehicle_parking_safe(unsafe_parking),"Do not create a save that depends on a changed door or panel collider")
	check("Save combined advanced checkpoint",game.save_world(offline_path),"Tower, vehicle and quest alongside Vertical City")
	metrics.vehicle_distance_m = game.vehicle.status().distance
	metrics.quest_stage = game.dialogue.status().quest_stage
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	game.session_path = online_path
	check("Restore three new systems",game.load_world(offline_path) and same(game.tower.snapshot(),stored.tower) and same(game.vehicle.snapshot(),stored.vehicle) and same(game.dialogue.snapshot(),stored.dialogue),"Fresh-scene snapshots restore exact state")
	var invalid: Dictionary = game.persistence.read_checkpoint(offline_path)
	invalid.dialogue = {}
	var invalid_path := offline_path+".bad"
	check("Reject corrupt feature checkpoint",game.persistence.write_checkpoint(invalid_path,invalid) and not game.load_world(invalid_path) and game.dialogue.status().quest_stage == "complete","Preflight rejects malformed data")
	if not check("Start authoritative host",game.start_network("host",0),"Real ENet loopback session with journal"):
		finish()
		return
	await ticks(10)
	check("Reject distant objective",not game.network.request_objective(1),"Host position out of range")
	check("Claim spawn objective",game.request_nearest_objective() and game.network.session_snapshot().revision == 1,"Server accepts one validated claim")
	check("Prevent duplicate reward",not game.network.request_objective(0) and game.network.session_snapshot().revision == 1,"One-shot objective state")
	var viewport := SubViewport.new()
	viewport.own_world_3d = true
	root.add_child(viewport)
	var client = scene.instantiate()
	viewport.add_child(client)
	await ticks(10)
	var port: int = game.network.status().port
	check("Join actual client city",client.start_network("client",port),"Independent networked scene")
	for i in 2400:
		await ticks(1)
		if client.network.session_snapshot().get("revision",-1) == 1 and client.network.status().connected and client._applied_world_tick >= 1: break
	check("Late join receives objective and environment",client.network.session_snapshot().get("revision",-1) == 1 and client._applied_world_tick >= 1,"Progress and authoritative population arrive together")
	client.set_network_test_input(Vector2(0,-1))
	for i in 360:
		await ticks(1)
		if client.network.status().local_position.distance_to(game.objectives[1]) < 1.0: break
	client.set_network_test_input(Vector2.ZERO)
	check("Client walks to second objective",client.network.status().local_position.distance_to(game.objectives[1]) < 2.0,"Actual server-authoritative avatar movement")
	check("Submit remote objective claim",client.request_nearest_objective(),"Network request is queued to authority")
	for i in 2400:
		await ticks(1)
		if client.network.session_snapshot().get("revision",-1) == 2 and game.durable_revision == 2: break
	var durable: Dictionary = game.session_store.load(online_path,game.world_id)
	check("Persist shared remote claim",game.network.session_snapshot().revision == 2 and client.network.session_snapshot().get("revision",-1) == 2 and durable.get("revision",-1) == 2,"Host applies and persists client claim")
	check("Offline gameplay constrained while online",not game.interact_vehicle() and not game.interact_world() and not game.interact_resident().accepted and not game.save_world(offline_path),"No unsynchronized local mutations")
	metrics.network_peers = game.remote_meshes.size()
	client.network.stop()
	viewport.queue_free()
	game.network.stop()
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	game.session_path = online_path
	check("Restart host from durable progress",game.start_network("host",0) and game.network.session_snapshot().revision == 2,"Fresh scene loads saved claims before accepting players")
	game.set_network_test_input(Vector2(-1,0))
	for i in 360:
		await ticks(1)
		if game.network.status().local_position.distance_to(game.objectives[2]) < 1.0: break
	game.set_network_test_input(Vector2.ZERO)
	check("Complete final persistent objective",game.request_nearest_objective() and game.network.session_snapshot().revision == 3 and game.durable_revision == 3,"Remaining objective can be completed after restart")
	metrics.session_revision = game.network.session_snapshot().revision
	metrics.persisted_revision = game.durable_revision
	game.network.stop()
	for path in [offline_path,invalid_path,online_path,online_path+".bak"]:
		if FileAccess.file_exists(path): DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	finish()
