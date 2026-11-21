extends SceneTree

const ENCOUNTERS = preload("res://encounters.gd")
var failures := 0
var damage_log: Array = []

func check(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", label)

func _initialize() -> void:
	call_deferred("_run")

func _vec(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])

func _wall(at: Vector3, size: Vector3) -> StaticBody3D:
	var wall := StaticBody3D.new()
	wall.collision_layer = 1
	wall.position = at
	var collider := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collider.shape = shape
	wall.add_child(collider)
	root.add_child(wall)
	return wall

func _run() -> void:
	var game := ENCOUNTERS.new()
	root.add_child(game)
	game.position = Vector3(3.0, 1.0, -2.0)
	var origin := Vector3(24, 0, -70)
	check(game.configure(971, origin), "configured with world-space origin")
	var fresh := game.snapshot()
	var initial := game.status()
	var home := _vec(initial.enemies[0].home)
	check(game.valid_snapshot(fresh) and initial.enemies.size() == game.POST_COUNT, "seeded post records")
	check(initial.active_count == game.MAX_ACTIVE and game.get_child_count() == game.MAX_ACTIVE, "bounded active actor instances")
	check(game.configure(123, origin) and game.status().enemies != initial.enemies, "different seeds place different posts")
	check(not game.restore(fresh), "checkpoint requires the same seed")
	check(game.configure(971, origin) and game.snapshot() == fresh, "same seed reproduces positions and states")
	check(not game.configure(971, Vector3(INF, 0, 0)) and game.snapshot() == fresh, "invalid configuration preserves state")
	var sentinel: StaticBody3D = game.get_node("Sentry0")
	check(sentinel.global_position.is_equal_approx(home), "sentry body uses world-space coordinates")
	var floor_body := _wall(origin - Vector3.UP * 0.5, Vector3(90, 1, 90))
	await physics_frame
	await physics_frame

	game.step(0.1, origin + Vector3.UP * 100.0)
	check(game.get_child_count() == 0 and game.status().active_count == 0, "distant posts release all physics bodies")
	for point in initial.enemies:
		game.step(0.1, _vec(point.home))
		check(game.get_child_count() <= game.MAX_ACTIVE, "activation cap while crossing overlapping posts")
	check(game.restore(fresh), "restore active actor pool")
	game.step(0.25, home + Vector3.RIGHT * 12.0)
	var patroller: Dictionary = game.status().enemies[0]
	check(patroller.active and patroller.state == "patrol" and _vec(patroller.position).distance_to(home) > 0.1, "patrol advances beyond detection range")

	check(game.restore(fresh), "reset before sensing")
	var player := home + Vector3.RIGHT * 5.0
	game.step(0.02, player)
	check(game.status().enemies[0].state == "pursuit", "visible player triggers pursuit")
	var barrier := _wall(home + Vector3(2.5, 1, 0), Vector3(0.5, 2.0, 3.2))
	await physics_frame
	await physics_frame
	game.step(0.04, player)
	check(game.status().enemies[0].state == "investigate", "a solid wall breaks sight")
	var blocked := game.shoot(player + game.EYE, -Vector3.RIGHT)
	check(blocked.fired and not blocked.hit and game.status().enemies[0].hp == game.ENEMY_HP, "world geometry stops a shot")
	var max_lateral := 0.0
	var crossed := false
	var clipped := false
	for tick in 110:
		game.step(0.05, player)
		var p := _vec(game.status().enemies[0].position) - home
		max_lateral = maxf(max_lateral, absf(p.z))
		if absf(p.x - 2.5) <= 0.25 and absf(p.z) < 1.6 + 0.40:
			clipped = true
		if p.x > 2.8 and game.status().enemies[0].state == "pursuit":
			crossed = true
	check(crossed and not clipped and max_lateral >= 2.0, "hull detours past wall edge and reacquires player")
	barrier.free()
	await physics_frame
	await physics_frame

	# Losing a player without leaving the encounter window lets us observe the
	# investigate timer and return home before the next patrol leg.
	check(game.restore(fresh), "reset before alert lifecycle")
	for i in 8:
		game.step(0.1, home + Vector3.RIGHT * 5.0)
	var observer := home + Vector3.UP * 13.0
	game.step(0.05, observer)
	check(game.status().enemies[0].state == "investigate", "investigation remembers the last visible point")
	var saw_return := false
	var at_home := false
	for i in 200:
		game.step(0.05, observer)
		var row: Dictionary = game.status().enemies[0]
		saw_return = saw_return or row.state == "return"
		if saw_return and row.state == "patrol" and _vec(row.position).distance_to(home) <= 0.2:
			at_home = true
			break
	check(saw_return and at_home, "returns to home and resumes patrol")

	game.player_damaged.connect(func(amount: int, enemy_id: int): damage_log.append([amount, enemy_id]))
	check(game.restore(fresh), "reset before close contact")
	game.step(0.02, home)
	check(game.health == game.MAX_HEALTH - game.ATTACK_DAMAGE and damage_log == [[game.ATTACK_DAMAGE, 0]], "proximity attack emits credited damage")
	game.step(0.5, home)
	check(damage_log.size() == 1, "cooldown prevents repeated hits")
	game.step(0.76, home)
	check(damage_log.size() == 2 and game.health == 84, "cooldown permits next hit")
	check(game.heal(10) and game.health == 94, "health recovery")
	check(game.restore(fresh), "reset before aiming")
	await physics_frame
	await physics_frame
	var muzzle := home + game.EYE + Vector3.RIGHT * 3.0
	check(not game.shoot(muzzle, Vector3.ZERO).fired, "invalid aim preserves cooldown")
	var hit := game.shoot(muzzle, Vector3.LEFT)
	check(hit.fired and hit.hit and not hit.defeated and hit.id == 0, "ray hits live enemy body")
	check(not game.shoot(muzzle, Vector3.LEFT).fired, "player fire interval")
	var wounded := game.snapshot()
	var loaded = JSON.parse_string(JSON.stringify(wounded, "", true, true))
	check(game.valid_snapshot(loaded) and game.restore(loaded) and game.snapshot() == wounded, "JSON checkpoint retains a wounded enemy and timers")
	game.step(game.SHOT_INTERVAL, home)
	var defeat := game.shoot(muzzle, Vector3.LEFT)
	check(defeat.defeated and defeat.id == 0, "second hit defeats enemy")
	game.step(0.1, origin + Vector3.RIGHT * 400.0)
	game.step(0.1, home)
	var after := game.status()
	check(not after.enemies[0].active and after.enemies[0].state == "defeated" and after.alive_count == game.POST_COUNT - 1, "defeated enemy stays dead after streaming")
	var saved := game.snapshot()
	for patch in [{"origin": [0,0,0]}, {"seed": "no"}, {"health": false}, {"health": -1}, {"shot_cooldown": NAN}, {"enemies": null}, {"extra": 0}]:
		var invalid := saved.merged(patch, true)
		check(not game.valid_snapshot(invalid) and not game.restore(invalid) and game.snapshot() == saved, "top-level rejection is atomic")
	for patch in [{"id": 2.5}, {"state": "unknown"}, {"active": true}, {"position": [0,0,0]}, {"last_seen": [NAN,0,0]}, {"cooldown": INF}, {"route": [[1,2]]}, {"waypoint": 4}]:
		var invalid := saved.duplicate(true)
		invalid.enemies[0].merge(patch, true)
		check(not game.valid_snapshot(invalid) and not game.restore(invalid) and game.snapshot() == saved, "enemy rejection is atomic")
	var too_many := fresh.duplicate(true)
	for row in too_many.enemies:
		row.active = true
	check(not game.restore(too_many) and game.snapshot() == saved, "restore enforces active cap")
	check(game.restore(wounded) and game.status().enemies[0].hp == 1 and game.has_node("Sentry0"), "checkpoint revives the saved collider")
	floor_body.free()
	game.free()
	if failures == 0:
		print("PASS living encounters")
	quit(1 if failures else 0)
