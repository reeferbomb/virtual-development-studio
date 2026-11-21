extends SceneTree

var checks: Array[Dictionary] = []

func _initialize() -> void:
	call_deferred("run")

func check(label: String, ok: bool, detail: String = "") -> void:
	checks.append({"name":label, "status":"passed" if ok else "failed", "detail":detail})

func frames(n: int) -> void:
	for i in n:
		await physics_frame

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	print("STUDIO_GAMEPLAY_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks}))
	quit(0 if ok else 1)

func run() -> void:
	if not ResourceLoader.exists("res://gameplay.tscn"):
		check("Gameplay scene", false, "Missing gameplay scene")
		finish()
		return
	var game = load("res://gameplay.tscn").instantiate()
	root.add_child(game)
	await frames(3)
	var actor = game.player
	actor.set_test_drive(Vector2.ZERO)
	check("Spawned opponents", game.enemies.size() == 2)
	check("Extraction locked", not game.mission.extract())
	# Patrol movement with no target in detection range.
	actor.global_position = Vector3(-9, 0.1, 8)
	var enemy = game.enemies["guard_b"]
	var before: Vector3 = enemy.global_position
	await frames(45)
	check("Autonomous patrol", enemy.global_position.distance_to(before) > 0.2 and enemy.state == "patrol", str(enemy.global_position))
	# Close to guard A, it should pursue or engage and hurt the player.
	actor.global_position = Vector3(-4, 0.1, 0)
	enemy = game.enemies["guard_a"]
	enemy.global_position = Vector3(0, 0.1, 0)
	var hp: int = game.combat.health
	await frames(160)
	check("NPC detects and attacks", game.combat.health < hp and enemy.state == "attack", str(game.combat.health))
	# Pause NPC movement/attacks for controlled raycast checks.
	for e in game.enemies.values():
		e.set_physics_process(false)
	actor.global_position = Vector3(0, 0.05, 1)
	enemy.global_position = Vector3(0, 0.05, 6)
	await frames(4)
	var target: Vector3 = enemy.global_position + Vector3.UP * 0.9
	var origin: Vector3 = actor.get_node("Camera3D").global_position
	var ehealth: int = enemy.health
	var ammo: int = game.combat.ammo
	game.shoot((target-origin).normalized())
	check("Cover blocks fire", enemy.health == ehealth and game.combat.ammo == ammo - 1)
	await frames(20)
	actor.global_position = Vector3(-4, 0.05, 0)
	enemy.global_position = Vector3(0, 0.05, 0)
	await frames(4)
	origin = actor.get_node("Camera3D").global_position
	target = enemy.global_position + Vector3.UP * 0.9
	game.shoot((target-origin).normalized())
	check("Hitscan damage", enemy.health < ehealth)
	await frames(20)
	game.shoot((target-origin).normalized())
	check("Elimination advances mission", enemy.health == 0 and not game.mission.remaining.has("guard_a"))
	var checkpoint := "user://studio_gameplay_qa_%s.json" % Time.get_ticks_usec()
	var saved_hp: int = game.combat.health
	var saved_ammo: int = game.combat.ammo
	var saved_position: Vector3 = actor.global_position
	check("Checkpoint write", game.save_game(checkpoint))
	game.combat.reload()
	game.combat.damage(5)
	actor.global_position = Vector3(2,0.1,0)
	check("Checkpoint restores state", game.load_game(checkpoint) and game.combat.health == saved_hp and game.combat.ammo == saved_ammo and actor.global_position.distance_to(saved_position) < 0.01 and game.enemies["guard_a"].health == 0)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(checkpoint))
	# Defeat guard B through the same weapon API, then physically run to extraction.
	enemy = game.enemies["guard_b"]
	enemy.global_position = Vector3(0,0.05,0)
	await frames(20)
	origin = actor.get_node("Camera3D").global_position
	target = enemy.global_position + Vector3.UP * 0.9
	game.shoot((target-origin).normalized())
	await frames(20)
	game.shoot((target-origin).normalized())
	check("All objectives defeated", game.mission.remaining.is_empty() and not game.mission.completed)
	actor.set_test_drive(Vector2(1,0), true)
	for i in 160:
		await physics_frame
		if game.mission.completed:
			break
	actor.set_test_drive(Vector2.ZERO)
	check("Physical extraction", game.mission.completed, str(actor.global_position))
	finish()
