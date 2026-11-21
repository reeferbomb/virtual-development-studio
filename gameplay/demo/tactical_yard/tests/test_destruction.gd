extends SceneTree

const Builder = preload("res://world_builder.gd")
const Planner = preload("res://navigation.gd")
const START := Vector3(-3, 0, 0)
const GOAL := Vector3(3, 0, 0)

var failures := 0

func check(condition: bool, label: String) -> void:
	if not condition:
		printerr("FAIL ", label)
		failures += 1

func _initialize() -> void:
	call_deferred("run")

func block(id: String, x: float, z: float, depth: float) -> Dictionary:
	return {"id": id, "position": [x, 1, z], "size": [1, 2, depth], "color": [0.4, 0.4, 0.4]}

func ray_body(world: Node3D) -> Object:
	var ray := PhysicsRayQueryParameters3D.create(START + Vector3.UP, GOAL + Vector3.UP, 1)
	return world.get_world_3d().direct_space_state.intersect_ray(ray).get("collider")

func settle_physics() -> void:
	await physics_frame
	await physics_frame

func run() -> void:
	if not ResourceLoader.exists("res://destruction.gd"):
		printerr("FAIL missing destructible cover module")
		quit(1)
		return
	var cover = load("res://destruction.gd").new()
	var planner := Planner.new()
	var spec := {
		"terrain": {"width": 18, "depth": 18, "flat_radius": 7, "segments": 8, "amplitude": 0},
		"blocks": [block("gate", 0, 0, 14), block("crate", 4, 5, 1), block("wall", 4, -5, 1)],
		"placements": [], "spawn": [-3, 0, 0], "goal": [3, 0, 0],
	}
	var original := spec.duplicate(true)
	var source := Builder.build(spec)
	for child in source.find_children("*", "", true, false):
		child.owner = source
	var packed := PackedScene.new()
	check(packed.pack(source) == OK, "pack constructed world")
	source.free()
	var world := packed.instantiate() as Node3D
	root.add_child(world)
	var gate := world.get_node("Blocks/gate") as MeshInstance3D
	var body := gate.get_node("Body") as StaticBody3D
	var shape := body.get_node("Collision") as CollisionShape3D
	var solid := world.get_node("Blocks/wall/Body") as StaticBody3D
	var crate := world.get_node("Blocks/crate/Body") as StaticBody3D

	check(cover.configure(world, spec, planner, []), "legacy world accepts empty selection")
	check(cover.snapshot() == {} and cover.restore({}) and not cover.damage(body, 50), "legacy cover is permanent")
	check(cover.configure(world, spec, planner, ["gate", "crate"]), "bind selected blocks")
	var full := {"gate": 50, "crate": 50}
	check(cover.snapshot() == full, "initial health")
	var detached: Dictionary = cover.snapshot()
	detached.gate = 1
	check(cover.snapshot() == full, "snapshot is independent")
	for ids in [["gate", "gate"], ["gate", "missing"], ["../../Bounds/West"], [123]]:
		check(not cover.configure(world, spec, planner, ids) and cover.snapshot() == full, "reject selection " + str(ids))
	var mismatch := spec.duplicate(true)
	mismatch.blocks[0].id = "absent"
	check(not cover.configure(world, mismatch, planner, ["gate"]), "reject block absent from specification")
	check(not cover.configure(world, mismatch, planner, ["absent"]), "reject block absent from baked world")
	check(not cover.damage(solid, 50) and not cover.damage(world.get_node("Bounds/West/Body"), 50), "only selected colliders accept hits")
	check(not cover.damage(gate, 25) and not cover.damage(body, 0) and not cover.damage(body, -25), "ignore non-collider and invalid damage")
	await settle_physics()
	check(ray_body(world) == body and planner.plan(START, GOAL).is_empty(), "sealed gate blocks ray and route")

	check(cover.damage(body, 25) and cover.damage(crate, 12), "partial hits")
	var partial := {"gate": 25, "crate": 38}
	check(cover.snapshot() == partial and gate.visible and not shape.disabled, "partial cover remains solid")
	check(cover.damage(body, 250) and not cover.damage(body, 1), "depletion and repeat hit")
	await settle_physics()
	var destroyed := {"gate": 0, "crate": 38}
	check(cover.snapshot() == destroyed and not gate.visible and shape.disabled, "destroyed mesh and collision")
	check(ray_body(world) == null and not planner.plan(START, GOAL).is_empty(), "destroying gate opens ray and route")
	check(planner.plan(Vector3(4, 0, -5), GOAL).is_empty(), "unselected wall stays in navigation")
	check(spec == original, "navigation rebuild preserves source level")
	for invalid in [{"gate": 50, "crate": -1}, {"gate": 50, "crate": 51}, {"gate": 50, "crate": 2.5},
			{"gate": 50, "crate": true}, {"gate": 50, "crate": "12"}, {"gate": 50, "crate": NAN},
			{"gate": 50, "crate": INF}, {"gate": 50}, {"gate": 50, "other": 25}]:
		check(not cover.restore(invalid) and cover.snapshot() == destroyed, "atomic rejection " + str(invalid))
	check(not gate.visible and not planner.plan(START, GOAL).is_empty(), "rejected save leaves geometry and navigation intact")

	spec.blocks[0].size[2] = 1
	check(cover.restore(JSON.parse_string(JSON.stringify(partial))), "restore saved partial health from JSON")
	await settle_physics()
	check(cover.snapshot() == partial and gate.visible and not shape.disabled, "restore health, mesh and collision")
	check(ray_body(world) == body and planner.plan(START, GOAL).is_empty(), "restore blocks ray and route using original level")
	check(cover.restore(destroyed), "restore depleted cover")
	await settle_physics()
	check(ray_body(world) == null and not planner.plan(START, GOAL).is_empty(), "restored depletion opens ray and route")
	check(cover.configure(world, original, planner, []), "remove optional feature from same world")
	await settle_physics()
	check(cover.snapshot().is_empty() and gate.visible and ray_body(world) == body and planner.plan(START, GOAL).is_empty(), "removed feature restores permanent geometry")
	world.free()
	if failures == 0:
		print("PASS destructible cover physics, navigation and checkpoint restoration")
	quit(int(failures > 0))
