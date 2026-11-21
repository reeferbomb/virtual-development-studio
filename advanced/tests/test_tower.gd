extends SceneTree

const Tower = preload("res://tower.gd")
const Player = preload("res://player.gd")
const ROW := {"id": "b3_0_1", "district": "industrial", "style": "warehouse", "center": [175.5, 0, 24], "size": [13, 10, 30]}
const DT := 1.0 / 60.0
var failures := 0
var tower := Tower.new()


func _initialize() -> void:
	call_deferred("_run")


func check(condition: bool, detail: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL tower: ", detail)


func _sync() -> void:
	await physics_frame
	await physics_frame


func _avatar(at: Vector3) -> CharacterBody3D:
	var player := Player.new()
	player.position = at + Vector3.UP * 0.04
	root.add_child(player)
	player.set_test_drive(Vector2.ZERO)
	return player


func _hit(p: Vector3, q: Vector3) -> String:
	var query := PhysicsRayQueryParameters3D.create(p, q, 1)
	var hit := root.world_3d.direct_space_state.intersect_ray(query)
	return str(hit.collider.name) if not hit.is_empty() else ""


# Use the shipped player controller and normal physics, including floor snapping and gravity.
func _walk(player: CharacterBody3D, target: Vector3, limit: int) -> bool:
	for frame in limit:
		var offset := Vector2(target.x - player.global_position.x, target.z - player.global_position.z)
		if offset.length() < 0.085:
			player.set_test_drive(Vector2.ZERO)
			return true
		player.set_test_drive(offset.normalized(), true)
		await physics_frame
	player.set_test_drive(Vector2.ZERO)
	return false


func _travel(player: CharacterBody3D, from: int, to: int) -> void:
	check(tower.interact(player), "cab button starts %d to %d" % [from, to])
	check(tower.status().phase == "moving" and tower.status().riding and tower.status().target_floor == to, "interlocked moving state")
	await _sync()
	var pad := tower.landing_position(from) + Vector3.UP * 1.2
	check(_hit(pad, pad + Vector3.BACK * 2.8) == "LandingDoor%d" % from, "origin landing closes behind the real player")
	for frame in 22:
		# The containing city enables ordinary player physics before stepping offline subsystems.
		player.set_physics_process(true)
		player.velocity = Vector3(0, -4, 2)
		tower.step(DT, player)
		await physics_frame
	check(not player.is_physics_processing() and player.velocity.is_zero_approx(), "ordinary city controller stays suspended between floors")
	check(absf(player.global_position.y - tower.cabin_position().y) < 0.06 and absf(player.global_position.y - from * Tower.STOREY) > 0.3, "occupied cabin continuously carries the avatar")
	var mid: Dictionary = JSON.parse_string(JSON.stringify(tower.snapshot()))
	check(tower.valid_snapshot(mid) and tower.valid_player_position(player.global_position, mid), "in-flight player and snapshot round-trip through JSON")
	var stale := mid.duplicate(true)
	stale.height = 200
	check(not tower.restore(stale, player), "malformed restore is rejected")
	check(is_equal_approx(tower.status().height, mid.height), "rejected restore keeps the cabin in place")
	var before := player.global_position
	tower.step(0.25, player)
	check(tower.restore(mid, player) and player.global_position.distance_to(before) < 0.002, "mid-trip restore reattaches physical passenger")
	for frame in 280:
		tower.step(DT, player)
		await physics_frame
		if tower.status().phase == "docked":
			break
	check(tower.status().floor == to and tower.status().phase == "docked" and not tower.status().riding and player.is_physics_processing(), "arriving at floor %d returns player controls" % to)
	await _sync()
	pad = tower.landing_position(to) + Vector3.UP * 1.2
	check(_hit(pad, pad + Vector3.BACK * 1.95).is_empty(), "destination gate physically opens")
	check(_hit(tower.cabin_position() + Vector3.UP, tower.cabin_position() + Vector3.DOWN * 0.30) == "ElevatorCabin", "moving car floor has collision at destination")
	check(await _walk(player, tower.landing_position(to), 90), "ordinary player walks out of cab onto floor %d" % to)
	await _sync()
	check(player.is_on_floor() and tower.contains_walkable_position(player.global_position), "destination landing supports the city player")
	check(_hit(tower.landing_position(to) + Vector3.UP, tower.landing_position(to) + Vector3.DOWN * 0.30) == "Slab%d" % to, "load-bearing slab at floor %d" % to)


func _run() -> void:
	root.add_child(tower)
	check(tower.configure(225, ROW), "build generated footprint")
	var initial := tower.snapshot()
	check(tower.status().floor_count == 3 and tower.status().floor_names.size() == 3 and not tower.status().door_open, "three signed storeys and a closed street entrance")
	var disabled := ROW.duplicate(true)
	disabled.size[1] = 8.9
	check(not tower.configure(225, disabled) and tower.snapshot() == initial, "ineligible geometry leaves original tower intact")
	# Only the sidewalk outside is supplied by the city. All interior supporting surfaces belong to the tower.
	var pavement := StaticBody3D.new()
	var collider := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(8, 0.2, 4)
	collider.shape = box
	pavement.add_child(collider)
	pavement.position = tower.entrance_position() + Vector3(0, -0.1, -0.75)
	root.add_child(pavement)
	var player := _avatar(tower.entrance_position())
	await _sync()
	var front := tower.entrance_position() + Vector3.BACK * 1.35
	check(not await _walk(player, front + Vector3.BACK * 0.75, 40), "closed street door blocks real avatar")
	check(tower.interact(player), "open street door")
	check(await _walk(player, front, 45), "walk across street threshold")
	check(not tower.interact(player) and tower.status().door_open, "street door interlock protects operator")
	check(await _walk(player, tower.landing_position(0), 450), "walk across lobby by normal city input")
	for floor_index in 3:
		check(await _walk(player, tower.cabin_position(), 90), "walk into docked cabin")
		await _sync()
		await _travel(player, floor_index, (floor_index + 1) % 3)
	check(tower.status().trips == 3, "ride count after two ascents and full descent")
	check(await _walk(player, tower.entrance_position(), 450), "walk through lobby and exit onto street")
	check(tower.interact(player) and not tower.status().door_open, "street door closes after exiting")
	# A second caller waits upstairs. Its closed landing door holds the capsule while the car is away.
	var caller := _avatar(tower.landing_position(2))
	await _sync()
	check(not await _walk(caller, tower.landing_position(2) + Vector3.BACK * 1.8, 38), "unserved landing door prevents a fall into shaft")
	check(await _walk(caller, tower.landing_position(2), 40), "caller steps back to call panel")
	check(tower.interact(caller) and not tower.status().riding, "remote landing calls an empty cab")
	tower.step(10.0, player)
	await _sync()
	check(tower.status().floor == 2 and tower.status().trips == 3, "empty call docks without counting a passenger")
	check(await _walk(caller, tower.cabin_position(), 90), "caller can board after arrival")
	var stable := tower.snapshot()
	for edits: Dictionary in [{"version": 3}, {"building_id": []}, {"floor": -1}, {"target_floor": 2.5}, {"height": INF}, {"riding": 1}, {"offset": [20, 0]}, {"trips": -1}, {"extra": 1}]:
		var malformed := stable.duplicate(true)
		malformed.merge(edits, true)
		check(not tower.valid_snapshot(malformed) and not tower.restore(malformed) and tower.snapshot() == stable, "invalid state rejected atomically")
	caller.free()
	player.free()
	check(tower.configure(225, ROW) and tower.snapshot() == initial and tower.get_child_count() == 1, "same seed and footprint reproduce the original layout and state")
	var moving := initial.duplicate(true)
	moving.target_floor = 1
	moving.riding = true
	check(not tower.restore(moving), "occupied restore requires a live passenger")
	tower.free()
	pavement.free()
	if failures == 0:
		print("PASS advanced tower")
	quit(1 if failures else 0)
