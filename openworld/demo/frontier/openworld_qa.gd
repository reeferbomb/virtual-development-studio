extends SceneTree

var checks: Array = []
var metrics := {}
var game: Node3D
var tick_count := 0
var travel := 0.0
var max_step := 0.0

func _initialize() -> void:
	call_deferred("run")

func check(name: String, passed: bool, detail: String) -> bool:
	checks.append({"name": name, "status": "passed" if passed else "failed", "detail": detail})
	return passed

func ticks(n: int) -> void:
	for i in n:
		await physics_frame
		tick_count += 1

func walk(target: Vector3, tolerance: float = 0.25, max_ticks: int = 1800) -> bool:
	for i in max_ticks:
		var old: Vector3 = game.player.global_position
		var offset := Vector2(target.x - old.x, target.z - old.z)
		if offset.length() <= tolerance:
			game.player.set_test_drive(Vector2.ZERO)
			await ticks(1)
			return true
		game.player.set_test_drive(offset.normalized(), true)
		await ticks(1)
		var amount: float = old.distance_to(game.player.global_position)
		travel += amount
		max_step = maxf(max_step, amount)
	game.player.set_test_drive(Vector2.ZERO)
	return false

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	metrics.physics_ticks = tick_count
	metrics.physical_walk_m = travel
	metrics.max_walk_step_m = max_step
	print("STUDIO_OPENWORLD_QA_JSON " + JSON.stringify({"pass":ok, "checks":checks, "metrics":metrics}))
	quit(0 if ok else 1)

func run() -> void:
	var scene = load("res://openworld.tscn")
	if not check("Load open world", scene is PackedScene, "Godot scene import"):
		finish()
		return
	game = scene.instantiate()
	root.add_child(game)
	await ticks(15)
	if not check("Initialize all systems", game.ready_for_play, "Streaming, NPCs, inventory, factions and persistence"):
		finish()
		return
	check("Player grounded", game.player.is_on_floor(), "Actual CharacterBody3D on generated terrain")
	check("Initial bounded window", game.stream.loaded_count() == 9 and game.population.loaded_count() <= 18, "Nine chunks, at most eighteen NPCs")
	var initial_ids: Dictionary = game.population.snapshot()
	var resource0: Vector3 = game.resource_position(Vector2i.ZERO, 0)
	var resource1: Vector3 = game.resource_position(Vector2i.ZERO, 1)
	var resource2: Vector3 = game.resource_position(Vector2i.ZERO, 2)
	check("Reject crafting with insufficient ingredients", not game.inventory.craft("tool") and game.inventory.quantity("tool") == 0, "Empty starting inventory")
	check("Harvest first wood", await walk(resource0) and game.harvest_near() and game.inventory.quantity("wood") == 1, "Physical proximity, one-unit resource")
	check("Reject repeat harvest", not game.harvest_near() and game.inventory.quantity("wood") == 1, "Consumed resource cannot be harvested again")
	check("Gather second wood", await walk(resource1) and game.harvest_near() and game.inventory.quantity("wood") == 2, "Another distinct world resource")
	check("Gather stone", await walk(resource2) and game.harvest_near() and game.inventory.quantity("stone") == 1, "Walk to stone marker")
	check("Craft tool atomically", game.inventory.craft("tool") and game.inventory.quantity("tool") == 1 and game.inventory.quantity("wood") == 0 and game.inventory.quantity("stone") == 0, "Recipe consumes two wood and one stone")
	var moved_east := await walk(Vector3(70, 0, 8))
	check("Stream east across two chunks", moved_east and game.stream.chunk_at(game.player.global_position) == Vector2i(2,0) and game.stream.loaded_count() == 9 and game.population.loaded_count() <= 18 and game.player.is_on_floor(), "Crossed actual chunk boundaries without falling")
	var far_ids: Dictionary = game.population.snapshot()
	var shared := 0
	for id in initial_ids:
		if far_ids.has(id):
			shared += 1
	check("Unload distant NPC population", shared < initial_ids.size() and far_ids.size() <= 18, "Distant identities removed from active window")
	var moved_west := await walk(Vector3(-8, 0, 8))
	check("Stream across negative coordinates", moved_west and game.stream.chunk_at(game.player.global_position) == Vector2i(-1,0) and game.stream.loaded_count() == 9 and game.player.is_on_floor(), "Floor-based negative cell mapping")
	check("Return to harvested chunk", await walk(resource0) and not game.harvest_near() and game.inventory.quantity("tool") == 1, "Unloaded resource remains consumed on revisit")
	var npc: Dictionary = game.population.nearest(game.player.global_position)
	var greeted := false
	var faction := ""
	if not npc.is_empty():
		for i in 12:
			var row: Dictionary = game.population.snapshot().get(npc.id, {})
			if row.is_empty():
				break
			var p: Array = row.position
			await walk(Vector3(p[0], p[1], p[2]), 1.0, 300)
			var near: Dictionary = game.population.nearest(game.player.global_position)
			if not near.is_empty() and near.distance <= 3.0:
				faction = near.faction
				greeted = game.greet_near()
				if greeted:
					break
	check("Talk to nearby NPC", greeted and game.factions.reputation(faction) > 0, "Physical proximity changes faction reputation")
	check("Reject repeat NPC reward", not game.greet_near(), "No repeated greeting reward")
	var saved_pos: Vector3 = game.player.global_position
	var saved_inv: Dictionary = game.inventory.snapshot()
	var saved_factions: Dictionary = game.factions.snapshot()
	var saved_harvest: Dictionary = game.harvested.duplicate()
	var saved_greeted: Dictionary = game.greeted.duplicate()
	var saved_seconds: float = game.world_seconds
	var path := "user://openworld_qa_%d.json" % Time.get_ticks_usec()
	check("Write checkpoint", game.save_world(path), "Atomic versioned checkpoint")
	game.queue_free()
	await process_frame
	game = scene.instantiate()
	root.add_child(game)
	await ticks(10)
	check("Fresh instance starts fresh", game.inventory.quantity("tool") == 0 and game.harvested.is_empty(), "New instance before load")
	var loaded: bool = game.load_world(path)
	await ticks(5)
	check("Restore fresh instance", loaded and game.player.global_position.distance_to(saved_pos) < 0.2 and game.inventory.snapshot() == saved_inv and game.factions.snapshot() == saved_factions and game.harvested == saved_harvest and game.greeted == saved_greeted, "Position, inventory, faction reputation and gathered resources restored")
	check("Restore population clock", absf(game.world_seconds - saved_seconds) < 0.2, "NPC movement clock resumes from checkpoint")
	var invalid: Dictionary = game.persistence.read_checkpoint(path)
	invalid.config = invalid.config.duplicate()
	invalid.config.seed = int(game.config.seed) + 1
	var bad_path := path + ".invalid"
	var old_inv: Dictionary = game.inventory.snapshot()
	var wrote_invalid: bool = game.persistence.write_checkpoint(bad_path, invalid)
	check("Reject different world checkpoint", wrote_invalid and not game.load_world(bad_path) and game.inventory.snapshot() == old_inv and game.greeted == saved_greeted, "Valid checksum does not bypass world identity")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(bad_path))
	check("Harvest remains consumed after restart", await walk(resource0) and not game.harvest_near(), "Restored harvested identity suppresses marker")
	check("Bounded physical traversal", travel > 100.0 and max_step < 0.2 and game.stream.loaded_count() == 9 and game.population.loaded_count() <= 18, "No teleport in movement checks")
	metrics.loaded_chunks = game.stream.loaded_count()
	metrics.loaded_npcs = game.population.loaded_count()
	metrics.harvested_resources = game.harvested.size()
	metrics.restored_tool_count = game.inventory.quantity("tool")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	finish()
