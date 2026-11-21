extends SceneTree

var host
var client
var checks: Array = []
var metrics := {}
var frames := 0

func _initialize() -> void:
	call_deferred("run")

func check(name_value: String,ok: bool,detail: String) -> bool:
	checks.append({"name":name_value,"status":"passed" if ok else "failed","detail":detail})
	return ok

func ticks(n: int) -> void:
	for i in n:
		await physics_frame
		frames += 1

func move_peer(game,target: Vector3,tolerance: float = 0.7,limit: int = 1600) -> bool:
	for i in limit:
		var p: Vector3 = game.network.status().local_position
		var offset := Vector2(target.x-p.x,target.z-p.z)
		if offset.length() <= tolerance:
			game.set_network_test_input(Vector2.ZERO)
			await ticks(3)
			return true
		game.set_network_test_input(offset.normalized())
		await ticks(1)
	game.set_network_test_input(Vector2.ZERO)
	return false

func route(game,target: Vector3) -> bool:
	# Follow a connected road centerline to avoid solid building lots.
	var p: Vector3 = game.network.status().local_position
	var block := float(game.config.block_size)
	var gx := roundf(p.x/block)*block
	var gz := roundf(p.z/block)*block
	if absf(p.x-gx) <= absf(p.z-gz):
		if not await move_peer(game,Vector3(gx,0,p.z)): return false
	else:
		if not await move_peer(game,Vector3(p.x,0,gz)): return false
	if not await move_peer(game,Vector3(gx,0,gz)): return false
	var tz := roundf(target.z/block)*block
	if not await move_peer(game,Vector3(gx,0,tz)): return false
	if not await move_peer(game,Vector3(target.x,0,tz)): return false
	return await move_peer(game,target)

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks: ok = ok and row.status == "passed"
	metrics.physics_ticks = frames
	print("STUDIO_FRONTLINE_QA_JSON "+JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://frontline.tscn")
	if not check("Load Frontline City",scene is PackedScene,"Full generated project scene"):
		finish(); return
	host = scene.instantiate()
	root.add_child(host)
	await ticks(20)
	if not check("Initialize shared features",host.frontline_ready and host.advanced_ready and host.network.feature_ready,"All five new and inherited systems configured"):
		finish(); return
	var path := "user://frontline_qa_%d.json" % Time.get_ticks_usec()
	host.session_path = path
	check("Offline simulation features concealed",not host.feature_root.visible and host.vehicle.visible,"Preserve ordinary Advanced City offline")
	if not check("Start host",host.start_network("host",0),"ENet local authority with session checkpoint"):
		finish(); return
	var viewport := SubViewport.new()
	viewport.own_world_3d = true
	root.add_child(viewport)
	client = scene.instantiate()
	viewport.add_child(client)
	await ticks(10)
	check("Join a second city",client.start_network("client",host.network.status().port),"Real ENet client with independent scene")
	for i in 2400:
		await ticks(1)
		if client.network.feature_received > 0 and client.network.status().connected: break
	if not check("Receive feature snapshots",client.network.feature_received > 0 and client.network.status().connected and client.feature_root.visible,"Car, lift, cover, mission and AI replicate"):
		finish(); return
	var spawn: Vector3 = host._vec(host.config.spawn)
	check("Reject distant lift request",not host.request_frontline(1),"Host validates authoritative distance")
	var rejected_before: int = host.network.feature_rejected
	check("Remote requests cannot bypass proximity",client.request_frontline(1),"Client requests but server decides")
	for i in 180:
		await ticks(1)
		if host.network.feature_rejected > rejected_before: break
	check("Reject malicious out-of-range remote action",host.network.feature_rejected > rejected_before and not host.shared_lift.occupied(client.network.status().peer_id),"Remote position checked by host")
	rejected_before = host.network.feature_rejected
	client.network._api.send_bytes(PackedByteArray([6,1,0,0,99]),1,MultiplayerPeer.TRANSFER_MODE_RELIABLE,3)
	for i in 180:
		await ticks(1)
		if host.network.feature_rejected > rejected_before: break
	check("Reject malformed action packet",host.network.feature_rejected > rejected_before,"Extra bytes refused by fixed-length decoder")
	var malformed: Dictionary = host.network.feature_snapshot()
	malformed.cover.health = [999,3,3]
	check("Reject malformed aggregate snapshot",not host.network.valid_feature_snapshot(malformed) and host.shared_cover.snapshot().health[0] == 3,"Validate complete state before applying any feature")
	await ticks(10)
	check("Damage shared cover",host.request_frontline(2,1),"Server accepts nearby panel hit")
	check("Reject repeated rapid hit",not host.request_frontline(2,1),"Request cooldown")
	await ticks(20)
	host.request_frontline(2,1)
	await ticks(20)
	host.request_frontline(2,1)
	for i in 600:
		await ticks(1)
		if client.shared_cover.snapshot().health[1] == 0: break
	check("Replicate destroyed cover",host.shared_cover.snapshot().health[1] == 0 and client.shared_cover.snapshot().health[1] == 0,"Host and client see identical destroyed panel")
	# Clear the lane in front of the parked car as well.
	for i in 3:
		await ticks(20)
		host.request_frontline(2,2)
	await ticks(20)
	var car_at: Vector3 = host.shared_car.status().position
	check("Client approaches car",await move_peer(client,car_at,1.5),"Actual server-authoritative movement")
	check("Remote vehicle entry request",client.request_frontline(0),"Client requests board")
	for i in 600:
		await ticks(1)
		if client.shared_car.occupied(client.network.status().peer_id): break
	var peer: int = client.network.status().peer_id
	check("Host grants driver ownership",host.shared_car.occupied(peer) and client.shared_car.occupied(peer),"Single driver replicated")
	check("Second driver refused",not host.request_frontline(0),"Occupied car cannot be stolen")
	client.set_network_test_input(Vector2(0,1))
	await ticks(120)
	client.set_network_test_input(Vector2.ZERO)
	var driven: Vector3 = host.shared_car.status().position
	check("Remote driver moves real shared car",driven.distance_to(car_at)>3.0,"Host authoritative steering and driving")
	await ticks(20)
	check("Replicate car transform and seated avatar",client.shared_car.status().position.distance_to(driven)<3.0 and client.network.status().local_position.distance_to(client.shared_car.status().position)<2.0,"Client sees drive state and follows car")
	check("Driver requests exit",client.request_frontline(0),"Only owner may release")
	for i in 600:
		await ticks(1)
		if not client.shared_car.occupied(peer): break
	check("Driver exit replicated",not host.shared_car.occupied(peer) and not client.shared_car.occupied(peer),"Ownership released")
	metrics.car_distance_m = driven.distance_to(car_at)
	var lift_at := spawn+Vector3(-4,0,5)
	check("Host approaches lift",await move_peer(host,lift_at,1.0),"Walk to observation lift")
	check("Lift boarding accepted",host.request_frontline(1),"Ground proximity and empty cabin validated")
	await ticks(12)
	check("Lift travel requested",host.request_frontline(1),"Begin moving platform")
	await ticks(12)
	check("Moving lift rejects control",not host.request_frontline(1),"Travel interlock")
	for i in 900:
		await ticks(1)
		if host.shared_lift.snapshot().phase == "upper" and client.shared_lift.snapshot().phase == "upper": break
	check("Replicate upper lift and rider",host.shared_lift.snapshot().phase == "upper" and client.shared_lift.snapshot().phase == "upper" and host.network.status().local_position.y > 5.5,"Host raises rider, client receives lift state")
	await ticks(12)
	check("Lift descends",host.request_frontline(1),"Return to street")
	for i in 900:
		await ticks(1)
		if host.shared_lift.snapshot().phase == "returned": break
	await ticks(12)
	check("Exit grounded lift",host.request_frontline(1),"Release only at ground")
	await ticks(20)
	check("Return to normal walking",not host.shared_lift.occupied(1) and host.network.status().local_position.y < 0.5,"Grounded network avatar")
	# Complete one dynamic contract via host movement and accepted requests.
	var mission_ok := true
	for i in 3:
		var target: Vector3 = host.missions.status().target
		var reached: bool = await route(host,target)
		await ticks(10)
		var accepted: bool = host.request_frontline(3)
		mission_ok = mission_ok and reached and accepted
		await ticks(10)
	check("Complete dynamic contract",mission_ok and host.missions.status().phase == "completed","Three proximity-authorized stages")
	for i in 600:
		await ticks(1)
		if client.missions.status().phase == "completed": break
	check("Replicate completed mission",client.missions.status().phase == "completed" and client.missions.status().score == host.missions.status().score,"Shared reward and mission phase")
	var squad: Dictionary = host.squads.status()
	check("Autonomous AI engagement",squad.shots>0 and squad.tick>0,"Host squad agents engage without player inputs")
	check("Replicate squad simulation",client.squads.status().shots>0 and client.squads.status().tick>0,"Client renders replicated AI state")
	metrics.ai_shots = squad.shots
	metrics.mission_score = host.missions.status().score
	metrics.feature_updates = client.network.feature_received
	metrics.feature_snapshot_bytes = JSON.stringify(host.network.feature_snapshot()).to_utf8_buffer().size()
	metrics.cover_health = host.shared_cover.snapshot().health
	# Late join after the shared state has changed.
	client.network.stop()
	viewport.queue_free()
	await process_frame
	var late_view := SubViewport.new()
	late_view.own_world_3d = true
	root.add_child(late_view)
	var late = scene.instantiate()
	late_view.add_child(late)
	await ticks(10)
	check("Late client joins",late.start_network("client",host.network.status().port),"New scene, no prior local feature state")
	for i in 2400:
		await ticks(1)
		if late.network.feature_received>0: break
	check("Late join receives destruction and mission",late.network.feature_received>0 and late.shared_cover.snapshot().health[1]==0 and late.missions.status().phase=="completed","Full snapshots recover current world without event history")
	late.network.stop()
	host.network.stop()
	for f in [path,path+".bak"]:
		if FileAccess.file_exists(f): DirAccess.remove_absolute(ProjectSettings.globalize_path(f))
	finish()
