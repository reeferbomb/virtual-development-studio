extends SceneTree

const Population := preload("res://population.gd")
const SEED := 241
const SIZE := 32.0
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	if not condition:
		printerr("FAIL ", message)
		failures += 1

func _point(row: Dictionary) -> Vector3:
	return Vector3(row.position[0], row.position[1], row.position[2])

func _check_window(population: Node3D, center: Vector2i, radius: int) -> void:
	var state: Dictionary = population.snapshot()
	var capacity := (2 * radius + 1) ** 2
	check(population.get_child_count() == capacity, "old chunk nodes removed synchronously")
	check(state.size() == population.loaded_count() and state.size() <= 2 * capacity, "resident count bounded")
	var counts := {}
	var unique_ids := {}
	for group in population.get_children():
		for npc in group.get_children():
			var id: String = npc.get_meta("npc_id")
			check(not unique_ids.has(id) and state.has(id), "unique live ID in snapshot")
			unique_ids[id] = true
			var entry: Dictionary = state[id]
			var key := Vector2i(entry.chunk[0], entry.chunk[1])
			check(absi(key.x - center.x) <= radius and absi(key.y - center.y) <= radius, "inside streamed window")
			counts[key] = counts.get(key, 0) + 1
			var p := _point(entry)
			check(key == Vector2i(floori(p.x / SIZE), floori(p.z / SIZE)) and p.y == 0.0, "wander stays in home chunk")
			check(npc.global_position.is_equal_approx(p), "visible node follows snapshot")
			check(entry.faction in ["settlers", "rangers"] and entry.faction == npc.get_meta("faction"), "valid faction")
			check(npc.get_node("Coat").mesh is CapsuleMesh and npc.get_node("Coat").is_visible_in_tree(), "visible capsule body")
			check(npc.get_node("Head").mesh is CapsuleMesh and npc.get_child_count() >= 6, "humanoid silhouette")
	check(counts.size() == capacity and unique_ids.size() == state.size(), "populated whole window")
	for count in counts.values():
		check(count >= 1 and count <= 2, "one or two residents in each chunk")

func run() -> void:
	var travel := Population.new()
	var stay := Population.new()
	root.add_child(travel)
	root.add_child(stay)
	check(travel.nearest(Vector3.ZERO).is_empty() and travel.loaded_count() == 0, "unconfigured queries")
	check(travel.configure(SEED) and stay.configure(SEED), "configure two identical worlds")
	var initial := travel.snapshot()
	check(initial == stay.snapshot(), "same seed reproduces origin")
	_check_window(travel, Vector2i.ZERO, 1)
	for id in initial:
		var row: Dictionary = initial[id]
		var near := travel.nearest(_point(row))
		check(near.id == id and near.faction == row.faction and is_zero_approx(near.distance), "nearest matches rendered resident")
	var query := Vector3(13, 7, -19)
	var nearest := travel.nearest(query)
	var true_min := INF
	for row in initial.values():
		true_min = minf(true_min, query.distance_to(_point(row)))
	check(is_equal_approx(nearest.distance, true_min), "nearest uses world distance")
	check(travel.nearest(Vector3(NAN, 0, 0)).is_empty(), "invalid proximity query")

	for seconds in [0.125, 0.375, 2.0]:
		travel.step(seconds)
		stay.step(seconds)
	var moved := travel.snapshot()
	for id in initial:
		check(not _point(moved[id]).is_equal_approx(_point(initial[id])), "each resident wanders after stepping")
	check(moved == stay.snapshot(), "deterministic movement")
	var id = moved.keys()[0]
	moved[id].position[0] = 1e8
	check(travel.snapshot() == stay.snapshot(), "detached snapshot")
	for i in range(1, 17):
		var query_point := Vector3(-i * SIZE + 0.2, 3, i * SIZE - 0.2)
		travel.update_center(query_point)
		travel.step(0.67)
		stay.step(0.67)
		_check_window(travel, Vector2i(-i, i - 1), 1)
	travel.update_center(Vector3.ZERO)
	check(travel.snapshot() == stay.snapshot(), "reloaded residents match continuously active world")
	var before := travel.snapshot()
	travel.step(-2.0)
	travel.step(NAN)
	travel.update_center(Vector3(INF, 0, 0))
	check(not travel.configure(SEED, 0) and not travel.configure(SEED, INF) and not travel.configure(SEED, SIZE, 4), "invalid configuration rejected")
	check(travel.snapshot() == before, "invalid inputs preserve active population")

	check(travel.configure(SEED, SIZE, 0), "single chunk configuration")
	travel.update_center(Vector3(-0.01, 0, -SIZE))
	_check_window(travel, Vector2i(-1, -1), 0)
	check(travel.configure(SEED), "reconfiguration")
	check(travel.snapshot() == initial, "reconfigure resets clock and origin")
	check(stay.configure(SEED + 1), "alternate seed")
	var sample: Dictionary = initial.values()[0]
	var other: Dictionary = stay.snapshot().values()[0]
	check(not _point(sample).is_equal_approx(_point(other)), "seed influences positions")
	travel.free()
	stay.free()
	if failures == 0:
		print("PASS population: bounded streaming, stable identities, visible NPCs, factions, movement, nearest and reload parity")
	quit(int(failures > 0))
