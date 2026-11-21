extends SceneTree

var game: Node3D
var checks: Array = []
var metrics := {}
var tick_count := 0
var walk_m := 0.0
var drive_m := 0.0
var max_drive_step := 0.0

func _initialize() -> void:
	call_deferred("run")

func check(name: String, pass_check: bool, detail: String) -> bool:
	checks.append({"name":name,"status":"passed" if pass_check else "failed","detail":detail})
	return pass_check

func ticks(n: int) -> void:
	for i in n:
		await physics_frame
		tick_count += 1

func walk(target: Vector3, tolerance: float = 0.25, max_ticks: int = 1800) -> bool:
	for i in max_ticks:
		var old: Vector3 = game.player.global_position
		var d := Vector2(target.x-old.x,target.z-old.z)
		if d.length() <= tolerance:
			game.player.set_test_drive(Vector2.ZERO)
			await ticks(1)
			return true
		game.player.set_test_drive(d.normalized(), true)
		await ticks(1)
		walk_m += old.distance_to(game.player.global_position)
	game.player.set_test_drive(Vector2.ZERO)
	return false

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	metrics.physics_ticks = tick_count
	metrics.walk_m = walk_m
	metrics.drive_m = drive_m
	metrics.max_drive_step_m = max_drive_step
	print("STUDIO_UNIFIED_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks,"metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://unified.tscn")
	if not check("Load unified scene", scene is PackedScene, "Imported scene"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(15)
	if not check("Initialize integrated world", game.unified_ready and game.player.is_on_floor(), "All modules ready and physical ground"):
		finish()
		return
	var starting_credits: int = game.economy.credits
	var initial_clock: Dictionary = game.population.clock_snapshot()
	check("Initial quest and bounded streaming", game.quests.current() == {"action":"craft","target":"tool"} and game.stream.loaded_count() == 9, "Crafting is the first required objective")
	check("Reject remote boarding and trading", not game.transport.enter() and not game.trade("sell","tool") and game.economy.credits == starting_credits, "Physical proximity required")
	check("Reject early combat", not game.shoot_target(Vector3.FORWARD).fired and game.combat_range.target_alive("drone"), "Quest prevents irreversible early defeat")
	check("Reject early craft", not game.craft_item("tool") and game.quests.index == 0, "Missing materials cannot advance quest")
	var material_ok := true
	for i in 3:
		material_ok = (await walk(game.resource_position(Vector2i.ZERO,i))) and game.harvest_near() and material_ok
	check("Collect actual materials", material_ok and game.inventory.quantity("wood") == 2 and game.inventory.quantity("stone") == 1, "Walked to three distinct resource nodes")
	check("Craft and advance quest", game.craft_item("tool") and game.inventory.quantity("tool") == 1 and game.quests.index == 1, "Atomic recipe and quest event")
	var car_start: Vector3 = game.transport.vehicle.global_position
	var boarded: bool = (await walk(car_start,1.6)) and game.transport.enter()
	if not check("Physically board vehicle", boarded and game.transport.driving, "Approach and enter existing arcade vehicle"):
		finish()
		return
	game.transport.set_drive(0.6,0.0)
	await ticks(20)
	check("Moving exit rejected", game.transport.vehicle.speed > 0.8 and not game.transport.exit(), "No airborne/unsafe dismount")
	var seam_seen := false
	var stable := true
	for i in 1000:
		var old: Vector3 = game.transport.vehicle.global_position
		if old.z <= game.drive_checkpoint.z + 2.9:
			break
		await ticks(1)
		var d: float = old.distance_to(game.transport.vehicle.global_position)
		drive_m += d
		max_drive_step = maxf(max_drive_step,d)
		stable = stable and game.stream.loaded_count() == 9 and game.transport.vehicle.global_position.y > -0.5
		seam_seen = seam_seen or game.stream.chunk_at(game.player.global_position).y < 0
	game.transport.set_drive(0,0,true)
	await ticks(65)
	check("Vehicle traverses streamed chunks", seam_seen and stable and drive_m > 40 and max_drive_step < 0.35 and game.stream.chunk_at(game.player.global_position).y <= -2, "Measured physical driving, terrain follows vehicle")
	check("Drive objective advances", game.quests.index == 2 and game.transport.vehicle.global_position.distance_to(game.drive_checkpoint) < 4.0, "Crossed the destination radius in vehicle")
	check("Brake and dismount", absf(game.transport.vehicle.speed) < 0.1 and game.transport.exit() and not game.transport.driving, "Foot controller restored")
	await ticks(3)
	check("Approach trading outpost", await walk(game.shop_position,1.0), "Physical movement after exiting vehicle")
	var sale_price: int = game.economy.price("tool","sell")
	check("Sell crafted tool", game.trade("sell","tool") and game.inventory.quantity("tool") == 0 and game.economy.credits == starting_credits + sale_price and game.quests.index == 3, "Inventory and wallet changed together")
	check("Reject duplicate sale", not game.trade("sell","tool") and game.economy.credits == starting_credits + sale_price, "No free credits")
	var aim: Vector3 = game.target_position - game.player.get_node("Camera3D").global_position
	var first: Dictionary = game.shoot_target(aim.normalized())
	check("Raycast hits range drone", first.fired and first.hit and not first.defeated and game.combat_range.target_alive("drone"), "Actual collision target and damage state")
	check("Cooldown blocks rapid second shot", not game.shoot_target(aim.normalized()).fired, "Weapon timing enforced")
	await ticks(20)
	var second: Dictionary = game.shoot_target((game.target_position-game.player.get_node("Camera3D").global_position).normalized())
	check("Defeat and reward", second.defeated and game.quests.completed and not game.combat_range.target_alive("drone") and game.economy.credits == starting_credits + sale_price + game.quests.reward(), "Ordered quest completed, reward paid exactly once")
	var earned: int = game.economy.credits
	await ticks(20)
	game.shoot_target(aim.normalized())
	check("Reject duplicate reward", game.economy.credits == earned, "Completed quest cannot pay again")
	await ticks(1800)
	var clock: Dictionary = game.population.clock_snapshot()
	check("NPC clock advances through schedules", clock.hour > initial_clock.hour + 5.0 and clock.phase != initial_clock.phase, "Simulation clock advanced by actual physics frames")
	var saved_inventory: Dictionary = game.inventory.snapshot()
	var saved_economy: Dictionary = game.economy.snapshot()
	var saved_quest: Dictionary = game.quests.snapshot()
	var saved_combat: Dictionary = game.combat_range.snapshot()
	var saved_car: Dictionary = game.transport.snapshot()
	var saved_pos: Vector3 = game.player.global_position
	var saved_time: float = game.world_seconds
	var path := "user://unified_qa_%d.json" % Time.get_ticks_usec()
	check("Save integrated state", game.save_world(path), "Atomic checksummed whole-world checkpoint")
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	check("Fresh world has initial quest and credits", game.quests.index == 0 and game.economy.credits == starting_credits and game.combat_range.target_alive("drone"), "New scene before load")
	var loaded: bool = game.load_world(path)
	await ticks(5)
	check("Restore integrated checkpoint", loaded and game.quests.snapshot() == saved_quest and game.inventory.snapshot() == saved_inventory and game.economy.snapshot() == saved_economy and game.combat_range.snapshot().targets == saved_combat.targets and game.combat_range.ammo == saved_combat.ammo and not game.combat_range.target_alive("drone") and game.player.global_position.distance_to(saved_pos) < 0.2 and absf(game.world_seconds-saved_time) < 0.2, "Economy, quests, combat, player, inventory and schedule clock restored")
	var car: Array = saved_car.position
	check("Restore parked vehicle", game.transport.vehicle.global_position.distance_to(Vector3(car[0],car[1],car[2])) < 0.25 and not game.transport.driving, "Parked vehicle position restored")
	var invalid: Dictionary = game.persistence.read_checkpoint(path)
	invalid.quest.index = 999
	var bad_path := path + ".bad"
	check("Reject malformed checkpoint atomically", game.persistence.write_checkpoint(bad_path,invalid) and not game.load_world(bad_path) and game.quests.snapshot() == saved_quest and game.economy.snapshot() == saved_economy, "Valid checksum cannot bypass schema validation")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(bad_path))
	metrics.loaded_chunks = game.stream.loaded_count()
	metrics.loaded_npcs = game.population.loaded_count()
	metrics.final_credits = game.economy.credits
	metrics.quest_completed = game.quests.completed
	metrics.active_hour = clock.hour
	finish()
