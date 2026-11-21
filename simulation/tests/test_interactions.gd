extends SceneTree

const Interactions := preload("res://interactions.gd")
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(passed: bool, label: String) -> void:
	if not passed:
		failures += 1
		printerr("FAIL ", label)

func run() -> void:
	var world := Node3D.new()
	root.add_child(world)
	world.position = Vector3(12, 3, -5)
	world.rotation.y = PI * 0.5
	var interactions := Interactions.new()
	root.add_child(interactions)
	var objects := [
		{"id": "relay", "position": [1, 0, 2], "kind": "beacon"},
		{"id": "stores", "position": [4, 0, 2], "kind": "supply"},
		{"id": "lever", "position": [8, 0, 0], "kind": "switch"}
	]
	check(interactions.configure(world, objects), "all marker kinds configure")
	var initial := {"relay": false, "stores": false, "lever": false}
	check(interactions.snapshot() == initial, "initial states")
	var group := world.get_node_or_null("InteractionMarkers")
	if group == null or group.get_child_count() != objects.size():
		printerr("FAIL marker count")
		quit(1)
		return
	var markers := {}
	for child in group.get_children():
		markers[child.get_meta("interaction_id")] = child
	for row in objects:
		var marker: Node3D = markers[row.id]
		var point := Vector3(row.position[0], row.position[1], row.position[2])
		check(marker.global_position.is_equal_approx(world.to_global(point)), "world position " + row.id)
		check(marker.get_meta("interaction_kind") == row.kind, "kind " + row.id)
		var visuals := marker.find_children("*", "MeshInstance3D", true, false)
		check(visuals.size() >= 1, "has visible geometry " + row.id)
		for visual in visuals:
			check(visual.is_visible_in_tree() and visual.mesh != null and visual.material_override != null,
					"visible material and geometry " + row.id)
	check(group.find_children("*", "CollisionObject3D", true, false).is_empty(), "markers do not obstruct physics")
	var relay: Vector3 = markers.relay.global_position
	var stores: Vector3 = markers.stores.global_position
	check(interactions.nearest(relay.lerp(stores, 0.6)) == "stores", "nearest chooses closer of two candidates")
	check(interactions.nearest(relay + Vector3.UP * 2.001).is_empty(), "outside radius in three dimensions")
	check(not interactions.activate("missing", relay), "unknown id")
	check(not interactions.activate("relay", relay + Vector3.UP * 2.001), "out-of-reach activation")
	check(not interactions.activate("relay", Vector3(NAN, 0, 0)), "invalid player position")
	check(interactions.nearest(relay + Vector3.UP * 2) == "relay", "exact radius candidate")
	check(interactions.activate("relay", relay + Vector3.UP * 2), "exact radius activation")
	check(not interactions.activate("relay", relay) and interactions.nearest(relay).is_empty(), "consumed markers are skipped")
	check(not markers.relay.is_visible_in_tree() and markers.stores.is_visible_in_tree(), "activation updates just its own visual")
	var used := {"relay": true, "stores": false, "lever": false}
	var detached := interactions.snapshot()
	detached["stores"] = true
	check(interactions.snapshot() == used, "detached snapshot")

	for bad in [null, {}, {"id": "", "position": [0, 0, 0], "kind": "supply"},
			{"id": "bad", "position": [0, 0, 0], "kind": "other"},
			{"id": "bad", "position": [1, 2], "kind": "beacon"},
			{"id": "bad", "position": [false, 0, 0], "kind": "beacon"},
			{"id": "bad", "position": [0, "0", 0], "kind": "beacon"},
			{"id": "bad", "position": [0, INF, 0], "kind": "beacon"},
			{"id": "bad", "position": [0, NAN, 0], "kind": "beacon"}, objects[0]]:
		check(not interactions.configure(world, [objects[0], bad]), "reject malformed or duplicate object")
		check(interactions.snapshot() == used and is_instance_valid(group), "configuration failure preserves live world")
	check(not interactions.configure(null, []), "invalid world")
	check(interactions.configure(world, [objects[1]]) and not is_instance_valid(group), "reconfiguration removes old geometry")
	check(interactions.snapshot() == {"stores": false}, "reconfiguration resets state")
	check(interactions.configure(world, []) and world.get_child_count() == 0, "empty configuration clears world")
	check(interactions.configure(world, objects), "configure before teardown")
	interactions.free()
	check(world.get_child_count() == 0, "manager teardown releases its markers")
	var next := Interactions.new()
	root.add_child(next)
	next.configure(world, objects)
	world.free()
	check(next.nearest(relay).is_empty() and not next.activate("relay", relay), "released world cannot be interacted with")
	next.free()
	if failures == 0:
		print("PASS interactions: marker geometry, world positions, proximity, one-shot state, validation and cleanup")
	quit(int(failures > 0))
