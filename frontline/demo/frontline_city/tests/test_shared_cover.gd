extends SceneTree

const Cover = preload("res://shared_cover.gd")
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(ok: bool, label_text: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL shared_cover: ", label_text)


func settle() -> void:
	await physics_frame
	await physics_frame


func ray_at(model: Node3D, target: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(target + Vector3.BACK * 2.0, target + Vector3.FORWARD * 2.0, 1)
	return model.get_world_3d().direct_space_state.intersect_ray(query)


func _run() -> void:
	var host := Cover.new()
	var replica := Cover.new()
	root.add_child(host)
	root.add_child(replica)
	var origin := Vector3(48, 0, 40)
	var replica_origin := Vector3(68, 0, 40)
	check(host.snapshot().is_empty() and not host.request(1, origin, 0), "unconfigured model rejects requests")
	check(host.configure(origin) and replica.configure(replica_origin), "configure host and replica")
	var initial := host.snapshot()
	check(initial == {"version": 1, "health": [3, 3, 3]}, "three intact panels")
	check(not host.configure(Vector3(NAN, 0, 0)) and host.snapshot() == initial, "invalid setup is atomic")
	var center := host.panel_center(1)
	var replica_center := replica.panel_center(1)
	var start := origin + Vector3.BACK * 4.0
	var finish := origin + Vector3.FORWARD * 4.0
	var center_panel := host.get_node("SharedCoverRow/WorkshopPanels/Panel1") as StaticBody3D
	var rubble := host.get_node("SharedCoverRow/WorkshopPanels/Rubble1") as Node3D
	var character := CharacterBody3D.new()
	character.collision_layer = 2
	character.collision_mask = 1
	var collider := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = Cover.PLAYER_RADIUS
	capsule.height = 1.7
	collider.shape = capsule
	character.add_child(collider)
	root.add_child(character)
	character.position = start + Vector3.UP * 0.85
	await settle()
	check(ray_at(host, center).get("collider") == center_panel and center_panel.is_visible_in_tree(),
			"intact shared cover has matching mesh and physics")
	check(character.test_move(character.global_transform, finish - start), "physical avatar is blocked by the intact row")
	var blocked := host.move(start, finish)
	check(blocked.z > origin.z and blocked.z < start.z and blocked.x == start.x,
			"authoritative movement stops at the near face")
	check(host.move(blocked, finish) == blocked and host.move(blocked, start) == start,
			"repeated input against the face stays blocked and backing away works")
	var slide := host.move(start, finish + Vector3.RIGHT * 0.7)
	check(is_equal_approx(slide.z, blocked.z) and is_equal_approx(slide.x, start.x + 0.7),
			"diagonal movement slides along intact cover")
	var diagonal := host.move(start + Vector3.LEFT * 3.0, finish + Vector3.RIGHT * 3.0)
	check(is_equal_approx(diagonal.z, blocked.z), "a long diagonal cannot tunnel through the row")
	check(host.move(start, finish, 0.9).z > blocked.z, "larger actors stop at their own swept radius")
	check(host.move(start + Vector3.UP * 4.0, finish + Vector3.UP * 4.0) == finish + Vector3.UP * 4.0,
			"the street-level row leaves upper floors clear")
	for peer in [-1, 0, 2147483648]:
		check(not host.request(peer, start, 1), "invalid peer ID")
	check(not host.request(4, start, -1) and not host.request(4, start, 3), "invalid panel indices")
	check(not host.request(4, Vector3(INF, 0, 0), 1) and not host.request(4, center + Vector3.UP * 9.0, 1)
			and not host.request(4, center + Vector3.RIGHT * 8.01, 1), "invalid or distant authoritative position")
	check(host.snapshot() == initial, "bad requests preserve all panel health")
	check(host.request(4, center + Vector3.BACK * Cover.REACH, 1), "first accepted hit at range boundary")
	check(not host.request(4, start, 1) and not host.request(4, start, 2), "per-peer cooldown spans all targets")
	var damaged := host.snapshot()
	check(damaged.health == [3, 2, 3] and center_panel.get_node("FirstCrack").is_visible_in_tree(), "damage is visible")
	host.step(NAN)
	host.step(INF)
	host.step(-0.2)
	host.step(Cover.COOLDOWN * 0.5)
	check(not host.request(4, start, 1), "invalid and short time steps do not bypass the rate limit")
	check(host.request(7, start, 1) and host.snapshot().health == [3, 1, 3], "another peer has an independent rate limit")
	check(center_panel.get_node("SecondCrack").is_visible_in_tree(), "second hit shows the deeper fracture")
	host.step(Cover.COOLDOWN * 0.5)
	check(host.request(4, start, 1) and host.snapshot().health == [3, 0, 3], "third accepted hit breaks only this panel")
	check(not host.request(11, start, 1), "destroyed panel rejects further hits")
	await settle()
	check(ray_at(host, center).is_empty() and rubble.is_visible_in_tree() and rubble.get_child_count() > 0
			and not center_panel.is_visible_in_tree(), "destruction removes physics and leaves visible fragments")
	check(not character.test_move(character.global_transform, finish - start), "physical avatar crosses the breached row")
	check(host.move(start, finish) == finish, "authoritative movement passes through the opening")
	var offset := host.panel_center(0) - center
	check(host.move(start + offset, finish + offset) != finish + offset, "neighboring solid panel still blocks movement")

	var wire: Variant = JSON.parse_string(JSON.stringify(host.snapshot()))
	check(replica.valid_snapshot(wire) and replica.restore(wire) and replica.snapshot() == host.snapshot(),
			"late replica restores complete JSON state")
	await settle()
	check(ray_at(replica, replica_center).is_empty() and replica.move(replica_origin + Vector3.BACK * 4,
			replica_origin + Vector3.FORWARD * 4) == replica_origin + Vector3.FORWARD * 4,
			"replica physics and movement match the opened breach")
	check(replica.restore(damaged), "restore a partially damaged checkpoint")
	await settle()
	check(not ray_at(replica, replica_center).is_empty() and replica.snapshot() == damaged,
			"restore reconstructs solid, partially damaged cover")
	for bad in [null, {}, {"health": [3, 3, 3]}, {"version": 2, "health": [3, 3, 3]},
			{"version": true, "health": [3, 3, 3]}, {"version": 1, "health": [1, 2]},
			{"version": 1, "health": [0, 0, 4]}, {"version": 1, "health": [0, 0, -1]},
			{"version": 1, "health": [0, 0, 1.5]}, {"version": 1, "health": [0, 0, true]},
			{"version": 1, "health": [0, 0, NAN]}, {"version": 1, "health": [3, 3, 3], "extra": 1}]:
		check(not replica.valid_snapshot(bad) and not replica.restore(bad) and replica.snapshot() == damaged,
				"reject malformed replica state before mutation")
	var detached := replica.snapshot()
	detached.health[0] = 0
	check(replica.snapshot() == damaged, "snapshots are detached")
	host.release_peer(7)
	check(host.request(7, start, 2) and not host.request(4, start, 2), "disconnect releases only that peer's cooldown")
	replica.set_active(false)
	check(replica.restore(initial) and not replica.request(1, replica_origin, 0), "offline replica can restore but cannot fire")
	await settle()
	check(ray_at(replica, replica_center).is_empty() and not replica.get_node("SharedCoverRow/WorkshopPanels/Panel1").is_visible_in_tree(),
			"inactive row releases its physical geometry and visuals")
	replica.set_active(true)
	await settle()
	check(not ray_at(replica, replica_center).is_empty(), "activating restores live collision from health")
	check(host.configure(origin) and host.snapshot() == initial and host.request(4, start, 1), "new session resets the row and cooldowns")
	character.free()
	host.free()
	replica.free()
	if failures == 0:
		print("PASS shared_cover: host range and rate limits, damaged mesh, debris, swept passage and replica collision")
	quit(int(failures > 0))
