extends SceneTree

var game
var checks: Array = []
var metrics := {}
var ticks_elapsed := 0
var walk_m := 0.0
var drive_m := 0.0

func _initialize() -> void:
	call_deferred("run")

func check(label: String, passed: bool, detail: String) -> bool:
	checks.append({"name":label,"status":"passed" if passed else "failed","detail":detail})
	return passed

func ticks(count: int) -> void:
	for i in count:
		await physics_frame
		ticks_elapsed += 1

func walk(target: Vector3, tolerance: float = 0.25, maximum: int = 1800) -> bool:
	for i in maximum:
		var old: Vector3 = game.player.global_position
		var d := Vector2(target.x-old.x,target.z-old.z)
		if d.length() <= tolerance:
			game.player.set_test_drive(Vector2.ZERO)
			await ticks(1)
			return true
		game.player.set_test_drive(d.normalized(),true)
		await ticks(1)
		walk_m += old.distance_to(game.player.global_position)
	game.player.set_test_drive(Vector2.ZERO)
	return false

func gather(item: String) -> bool:
	var nearest_id := ""
	var nearest := INF
	var target := Vector3.ZERO
	for id in game.markers:
		var node: Node3D = game.markers[id]
		if node.get_meta("item") != item:
			continue
		var distance: float = node.position.distance_to(game.player.global_position)
		if distance < nearest:
			nearest = distance
			nearest_id = id
			target = node.position
	return not nearest_id.is_empty() and (await walk(target)) and game.harvest_near()

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	metrics.physics_ticks = ticks_elapsed
	metrics.walk_m = walk_m
	metrics.drive_m = drive_m
	print("STUDIO_LIVING_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://living.tscn")
	if not check("Load living scene",scene is PackedScene,"Imports new project"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(20)
	if not check("Living world initialization",game.living_ready and game.player.is_on_floor(),"Integrated inherited world and all four new modules"):
		finish()
		return
	var offers: Array = game.contracts.board()
	check("Three seeded contract offers",offers.size() == 3 and offers[0].id != offers[1].id,"Distinct board options")
	if not check("Accept contract",game.accept_contract(0) and not game.accept_contract(1),"One active contract at a time"):
		finish()
		return
	var objective: Dictionary = game.contracts.status().current
	var goal_count: int = objective.count
	var target_item: String = objective.target
	var gather_ok := true
	for i in goal_count:
		gather_ok = (await gather(target_item)) and gather_ok
	check("Physical gathering advances contract",gather_ok and game.contracts.status().complete,"Real resource nodes feed the generated objective")
	var prior_credits: int = game.economy.credits
	var reward: int = game.contracts.status().reward
	check("Claim reward and rotate board",game.claim_contract() and game.economy.credits == prior_credits + reward and game.contracts.status().generation == 1,"Wallet and procedural board progress together")
	check("Duplicate claim rejected",not game.claim_contract() and game.economy.credits == prior_credits+reward,"No duplicate reward")
	check("Accept new generated contract",game.accept_contract(0),"New generation playable")
	var saved_contract: Dictionary = game.contracts.snapshot()
	var saved_diplomacy: Dictionary = game.diplomacy.snapshot()
	var saved_encounters: Dictionary = game.encounters.snapshot()
	var path := "user://living_qa_%d.json" % Time.get_ticks_usec()
	check("Atomic living checkpoint",game.save_world(path),"Base plus contracts, diplomacy and encounters")
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	check("Restore all living modules",game.load_world(path) and game.contracts.snapshot() == saved_contract and game.diplomacy.snapshot() == saved_diplomacy and game.encounters.snapshot() == saved_encounters,"New scene restores generated progress and state")
	var invalid: Dictionary = game.persistence.read_checkpoint(path)
	invalid.contracts = {}
	var bad_path := path + ".bad"
	check("Reject malformed advanced checkpoint",game.persistence.write_checkpoint(bad_path,invalid) and not game.load_world(bad_path) and game.contracts.snapshot() == saved_contract and game.diplomacy.snapshot() == saved_diplomacy,"Checksummed invalid data cannot mutate world")
	var before_scout: Vector3 = game.scout.position
	await ticks(25)
	check("Animated scout moves",game.scout.position.distance_to(before_scout) > 0.3 and game.scout.status().state != "idle","Procedural character driven by actual patrol velocity")
	var material_ok := true
	while game.inventory.quantity("wood") < 2:
		if not await gather("wood"):
			material_ok = false
			break
	while game.inventory.quantity("stone") < 1:
		if not await gather("stone"):
			material_ok = false
			break
	check("Training remains playable",material_ok and game.craft_item("tool") and game.quests.index == 1,"Real resource and crafting gate preserved")
	var car_start: Vector3 = game.transport.vehicle.global_position
	if not check("Board integrated vehicle",(await walk(car_start,1.6)) and game.transport.enter(),"Actual proximity boarding"):
		finish()
		return
	game.transport.set_drive(0.6,0.0)
	for i in 1200:
		var old: Vector3 = game.transport.vehicle.global_position
		if old.z <= game.drive_checkpoint.z + 2.9:
			break
		await ticks(1)
		drive_m += old.distance_to(game.transport.vehicle.global_position)
	game.transport.set_drive(0,0,true)
	await ticks(65)
	check("Physical streamed drive",drive_m > 40 and game.quests.index == 2 and game.stream.loaded_count() == 9,"Driving traverses chunks")
	if not check("Exit and visit outpost",game.transport.exit() and (await walk(game.shop_position,1.0)),"Near-stopped exit and physical movement"):
		finish()
		return
	var trade_standing: int = game.diplomacy.status().standings.traders
	check("Trade changes diplomacy",game.trade("sell","tool") and game.quests.index == 3 and game.diplomacy.status().standings.traders > trade_standing,"Actual trade event affects reputation")
	check("Buy medical supply",game.trade("buy","bandage") and not game.use_bandage(),"Purchase a bandage, full-health use rejected")
	var aim: Vector3 = game.target_position - game.player.get_node("Camera3D").global_position
	var first: Dictionary = game.shoot_target(aim.normalized())
	await ticks(20)
	var second: Dictionary = game.shoot_target((game.target_position-game.player.get_node("Camera3D").global_position).normalized())
	if not check("Complete training range",first.hit and second.defeated and game.quests.completed,"Two real drone hits unlock hostile territory"):
		finish()
		return
	check("Autonomous faction simulation",game.diplomacy.status().tick > 0,"Physics time advances diplomacy events")
	var destination: Vector3 = game.encounter_origin + Vector3(0,0,12)
	check("Reach encounter zone",await walk(destination,1.0),"Walk through newly streamed terrain")
	await ticks(20)
	var enemy_state: Dictionary = game.encounters.status()
	if not check("Hostile encounters activate",enemy_state.active_count > 0 and enemy_state.alive_count > 0,"Proximity activates bounded enemy AI"):
		finish()
		return
	var hit_count := 0
	var defeated := false
	for shot in 10:
		var nearest_enemy: Dictionary = {}
		var best := INF
		var eye: Vector3 = game.player.get_node("Camera3D").global_position
		for enemy in game.encounters.status().enemies:
			if enemy.hp <= 0 or not enemy.active:
				continue
			var p: Array = enemy.position
			var point := Vector3(p[0],p[1]+0.8,p[2])
			if eye.distance_to(point) < best:
				best = eye.distance_to(point)
				nearest_enemy = {"point":point,"id":enemy.id}
		if nearest_enemy.is_empty():
			break
		if game.combat_range.ammo == 0:
			game.combat_range.reload()
		var outcome: Dictionary = game.shoot_target((nearest_enemy.point-eye).normalized())
		if outcome.hit:
			hit_count += 1
		if outcome.defeated:
			defeated = true
			break
		await ticks(24)
	check("Live hostile collision combat",hit_count > 0 and defeated,"Physics ray hits reduce hostile HP and defeat an enemy")
	check("Encounters use shared ammunition",game.combat_range.ammo < game.combat_range.MAGAZINE_SIZE,"Hostile shots consume inherited weapon ammunition")
	var survivor: Dictionary = {}
	var nearest_distance := INF
	for enemy in game.encounters.status().enemies:
		if enemy.hp <= 0 or not enemy.active:
			continue
		var p: Array = enemy.position
		var point := Vector3(p[0],p[1],p[2])
		var d: float = point.distance_to(game.player.global_position)
		if d < nearest_distance:
			nearest_distance = d
			survivor = {"point":point,"id":enemy.id}
	var initial_health: int = game.encounters.status().health
	if not survivor.is_empty():
		await walk(survivor.point,1.0)
		for i in 150:
			if game.encounters.status().health < initial_health:
				break
			await ticks(1)
	var hurt_health: int = game.encounters.status().health
	check("Hostiles deal real proximity damage",hurt_health < initial_health and hurt_health > 0,"Live attack modifies player health")
	var supplies: int = game.inventory.quantity("bandage")
	check("Bandage consumes supply and heals",game.use_bandage() and game.inventory.quantity("bandage") == supplies-1 and game.encounters.status().health > hurt_health,"Health and inventory update together")
	var final_enemies: Dictionary = game.encounters.snapshot()
	var final_contracts: Dictionary = game.contracts.snapshot()
	check("Save combat and medical progress",game.save_world(path),"Checkpoint persists actual post-combat progress")
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	check("Restore defeated enemies and health",game.load_world(path) and game.encounters.snapshot() == final_enemies and game.contracts.snapshot() == final_contracts and game.quests.completed,"No respawn or lost health on reload")
	metrics.hostile_hits = hit_count
	metrics.health = game.encounters.status().health
	metrics.faction_ticks = game.diplomacy.status().tick
	metrics.contract_generation = game.contracts.status().generation
	metrics.credits = game.economy.credits
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(bad_path))
	finish()
