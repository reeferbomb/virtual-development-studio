extends RefCounted

# A small original relay yard. A mission opens a subset of these links and assigns work to sites.
const SITES := [Vector2(0, 0), Vector2(-32, 20), Vector2(32, 20), Vector2(-32, 54),
	Vector2(32, 54), Vector2(-52, 78), Vector2(52, 78)]
const LINKS := [[0, 1], [0, 2], [1, 2], [1, 3], [2, 4], [3, 4], [3, 5], [4, 6], [5, 6]]
const DEFAULT_BATTERY := 18
const MAX_ATTEMPTS := 5
const MAX_TASKS := 6
const KINDS := ["collect-kit", "inspect", "align", "deliver", "sample"]
const SEEDS := [17, 41, 62, 79, 103, 149, 191, 233, 301, 409, 557, 701]


class HopGraph extends AStar2D:
	func _compute_cost(_from_id: int, _to_id: int) -> float:
		return 1.0

	func _estimate_cost(_from_id: int, _to_id: int) -> float:
		return 0.0


class Courier extends Node2D:
	var room := 0
	var charge: int
	var completed: Array[int] = []
	var traversed: Array[int] = [0]

	func _init(battery: int) -> void:
		charge = battery

	func travel(destination: int, graph: AStar2D, markers: Array[Marker2D]) -> bool:
		var path := graph.get_id_path(room, destination)
		if path.is_empty() or path.size() - 1 > charge:
			return false
		for index in range(1, path.size()):
			room = path[index]
			position = markers[room].position
			traversed.append(room)
			charge -= 1
		return room == destination and position == markers[destination].position

	func complete(task: Dictionary) -> bool:
		if room != task.site or task.id in completed or charge < task.cost:
			return false
		for prerequisite in task.requires:
			if prerequisite not in completed:
				return false
		charge += task.reward - task.cost
		completed.append(task.id)
		return true

	func snapshot() -> Dictionary:
		return {"room": room, "charge": charge, "completed": completed.duplicate(), "traversed": traversed.duplicate()}


func _task(id: int, site: int, kind: String, requires: Array, cost: int, reward: int, optional: bool) -> Dictionary:
	return {"id": id, "site": site, "kind": kind, "requires": requires, "cost": cost, "reward": reward, "optional": optional}


func _candidate(seed_value: int, battery: int, permitted: Array[int], rng: RandomNumberGenerator) -> Dictionary:
	var opened: Array[int] = []
	for link in permitted:
		if rng.randi_range(0, 99) < 82:
			opened.append(link)
	var kit := rng.randi_range(1, 2)
	var relay := rng.randi_range(3, 4)
	var delivery := rng.randi_range(0, 1) == 0
	var detour := rng.randi_range(5, 6)
	return {"version": 1, "seed": seed_value, "battery": battery, "links": opened, "target": 2, "tasks": [
		_task(0, kit, "collect-kit", [], 0, rng.randi_range(1, 3), false),
		_task(1, relay, "inspect", [0], 1, 0, false),
		_task(2, 0 if delivery else relay, "deliver" if delivery else "align", [1], 1 if delivery else 2, 0, false),
		_task(3, detour, "sample", [rng.randi_range(0, 1)], 1, 1, true),
	]}


func _fallback(seed_value: int, battery: int, permitted: Array[int]) -> Dictionary:
	return {"version": 1, "seed": seed_value, "battery": battery, "links": permitted.duplicate(), "target": 2, "tasks": [
		_task(0, 1, "collect-kit", [], 0, 2, false), _task(1, 3, "inspect", [0], 1, 0, false),
		_task(2, 3, "align", [1], 1, 0, false), _task(3, 5, "sample", [1], 1, 0, true),
	]}


func generate(seed_value: int, battery: int = DEFAULT_BATTERY, attempts: int = 4, blocked: Array = []) -> Dictionary:
	if not _integer(seed_value, 0, 2_147_483_647) or not _integer(battery, 0, 24) \
			or not _integer(attempts, 0, MAX_ATTEMPTS) or not _ids(blocked, LINKS.size()):
		return {"status": "unavailable", "attempts": 0, "mission": {}, "reason": "invalid-policy"}
	var permitted: Array[int] = []
	for link in range(LINKS.size()):
		if link not in blocked:
			permitted.append(link)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	for attempt in range(1, attempts + 1):
		var mission := _candidate(seed_value, battery, permitted, rng)
		if validate(mission).valid:
			return {"status": "generated", "attempts": attempt, "mission": mission, "reason": ""}
	var fallback := _fallback(seed_value, battery, permitted)
	var verification := validate(fallback)
	if verification.valid:
		return {"status": "fallback", "attempts": attempts, "mission": fallback, "reason": ""}
	return {"status": "unavailable", "attempts": attempts, "mission": {}, "reason": verification.reason}


func _integer(value: Variant, low: int, high: int) -> bool:
	return typeof(value) == TYPE_INT and value >= low and value <= high


func _fields(value: Variant, names: Array) -> bool:
	if typeof(value) != TYPE_DICTIONARY or value.size() != names.size():
		return false
	for name in names:
		if not value.has(name):
			return false
	return true


func _ids(values: Variant, limit: int) -> bool:
	if typeof(values) != TYPE_ARRAY or values.size() > limit:
		return false
	var seen := {}
	for id in values:
		if not _integer(id, 0, limit - 1) or seen.has(id):
			return false
		seen[id] = true
	return true


func _schema(mission: Variant) -> bool:
	if not _fields(mission, ["version", "seed", "battery", "links", "target", "tasks"]):
		return false
	if not _integer(mission.version, 1, 1) or not _integer(mission.seed, 0, 2_147_483_647) \
			or not _integer(mission.battery, 0, 24) or not _ids(mission.links, LINKS.size()):
		return false
	if typeof(mission.tasks) != TYPE_ARRAY or mission.tasks.size() < 3 or mission.tasks.size() > MAX_TASKS \
			or not _integer(mission.target, 0, mission.tasks.size() - 1):
		return false
	var tasks: Array = mission.tasks
	for index in range(tasks.size()):
		var task: Variant = tasks[index]
		if not _fields(task, ["id", "site", "kind", "requires", "cost", "reward", "optional"]):
			return false
		if not _integer(task.id, index, index) or not _integer(task.site, 0, SITES.size() - 1) \
				or typeof(task.kind) != TYPE_STRING or task.kind not in KINDS or not _ids(task.requires, tasks.size()) \
				or not _integer(task.cost, 0, 4) or not _integer(task.reward, 0, 4) or typeof(task.optional) != TYPE_BOOL:
			return false
	return true


func _topological(tasks: Array) -> Array[int]:
	var order: Array[int] = []
	# At most one bounded pass per task, with ID as the tie-break among ready tasks.
	while order.size() < tasks.size():
		var previous := order.size()
		for task in tasks:
			var ready: bool = task.id not in order
			for prerequisite in task.requires:
				ready = ready and prerequisite in order
			if ready:
				order.append(task.id)
				break
		if order.size() == previous:
			break
	return order


func _neighbors(opened: Array) -> Array:
	var result: Array = []
	for site in range(SITES.size()):
		result.append([])
	for link in opened:
		var pair: Array = LINKS[link]
		result[pair[0]].append(pair[1])
		result[pair[1]].append(pair[0])
	for neighbors in result:
		neighbors.sort()
	return result


func _path(neighbors: Array, start: int, finish: int) -> Array[int]:
	var queue: Array[int] = [start]
	var previous := {}
	previous[start] = -1
	var head := 0
	while head < queue.size() and not previous.has(finish):
		var room := queue[head]
		head += 1
		for neighbor in neighbors[room]:
			if not previous.has(neighbor):
				previous[neighbor] = room
				queue.append(neighbor)
	var path: Array[int] = []
	if previous.has(finish):
		var cursor := finish
		while cursor != -1:
			path.push_front(cursor)
			cursor = previous[cursor]
	return path


func _failed(reason: String) -> Dictionary:
	return {"valid": false, "reason": reason}


func _plan(neighbors: Array, tasks: Array, order: Array[int], budget: int) -> Dictionary:
	var room := 0
	var planned: Array = []
	for id in order:
		var task: Dictionary = tasks[id]
		var path := _path(neighbors, room, task.site)
		if path.is_empty():
			return _failed("unreachable")
		var cost: int = path.size() - 1 + task.cost
		if cost > budget:
			return _failed("budget")
		budget += task.reward - cost
		planned.append(path)
		room = task.site
	return {"valid": true, "paths": planned, "charge": budget}


func validate(mission: Variant) -> Dictionary:
	if not _schema(mission):
		return _failed("schema")
	var tasks: Array = mission.tasks
	var order := _topological(tasks)
	if order.size() != tasks.size():
		return _failed("cycle")
	var required: Array[int] = []
	for id in order:
		var task: Dictionary = tasks[id]
		if not task.optional:
			for prerequisite in task.requires:
				if tasks[prerequisite].optional:
					return _failed("required-optional")
			required.append(id)
	if required.size() < 2 or required.size() == tasks.size() or required.back() != mission.target:
		return _failed("goal-shape")
	var ancestors := {}
	var pending: Array = [mission.target]
	while not pending.is_empty():
		var id: int = pending.pop_back()
		if not ancestors.has(id):
			ancestors[id] = true
			pending.append_array(tasks[id].requires)
	if ancestors.size() != required.size():
		return _failed("goal-shape")
	var neighbors := _neighbors(mission.links)
	var main := _plan(neighbors, tasks, required, mission.battery)
	if not main.valid:
		return main
	var full := _plan(neighbors, tasks, order, mission.battery)
	if not full.valid:
		return full
	return {"valid": true, "reason": "", "order": order, "required_order": required, "main": main, "full": full}


func _markers(parent: Node2D) -> Array[Marker2D]:
	var result: Array[Marker2D] = []
	for point in SITES:
		var marker := Marker2D.new()
		marker.position = point
		parent.add_child(marker)
		result.append(marker)
	return result


func _star(mission: Dictionary, markers: Array[Marker2D]) -> HopGraph:
	var star := HopGraph.new()
	for id in range(markers.size()):
		star.add_point(id, markers[id].position)
	for link in mission.links:
		star.connect_points(LINKS[link][0], LINKS[link][1])
	return star


func _route_crosscheck(mission: Dictionary, star: HopGraph, markers: Array[Marker2D]) -> bool:
	var neighbors := _neighbors(mission.links)
	for start in range(SITES.size()):
		if star.get_point_position(start) != markers[start].position:
			return false
		for finish in range(SITES.size()):
			var path := star.get_id_path(start, finish)
			if path.size() != _path(neighbors, start, finish).size():
				return false
			for index in range(1, path.size()):
				if path[index] not in neighbors[path[index - 1]]:
					return false
	return true


func _drive(root: Node2D, mission: Dictionary, order: Array, star: HopGraph, markers: Array[Marker2D]) -> Dictionary:
	var courier := Courier.new(mission.battery)
	root.add_child(courier)
	for id in order:
		var task: Dictionary = mission.tasks[id]
		if not courier.travel(task.site, star, markers) or not courier.complete(task):
			return {}
	var before := courier.snapshot()
	var duplicate_rejected: bool = not courier.complete(mission.tasks[order.back()]) and courier.snapshot() == before
	return {"state": before, "duplicate_rejected": duplicate_rejected}


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var original_children := tree.root.get_child_count()
	var probe := Node2D.new()
	probe.name = "RelayMissionProbe"
	tree.root.add_child(probe)
	var matched := true
	var routes := {}
	var goals := {}
	var detours := {}
	var selected := {}
	var generated := 0
	for seed_value in SEEDS:
		var result := generate(seed_value)
		matched = matched and result == generate(seed_value)
		if result.status == "generated":
			generated += 1
			var proof := validate(result.mission)
			matched = matched and proof.valid and proof == validate(result.mission)
			if proof.valid:
				routes[JSON.stringify(proof.main.paths)] = true
				goals[result.mission.tasks[result.mission.target].kind] = true
				detours[result.mission.tasks[3].site] = true
				if selected.is_empty():
					selected = result.mission

	var valid_dependencies := false
	var reachable := false
	var within_budget := false
	var progressed := false
	var battery_left := 0
	if not selected.is_empty():
		var proof := validate(selected)
		var cycle := selected.duplicate(true)
		cycle.tasks[0].requires = [selected.target]
		var blocked_goal := selected.duplicate(true)
		blocked_goal.tasks[selected.target].requires.append(3)
		var disconnected := selected.duplicate(true)
		disconnected.links = selected.links.filter(func(link): return LINKS[link][0] != 0)
		var depleted := selected.duplicate(true)
		depleted.battery = 0
		var markers := _markers(probe)
		var star := _star(selected, markers)
		var cour := Courier.new(selected.battery)
		probe.add_child(cour)
		var target: Dictionary = selected.tasks[selected.target]
		var in_position := cour.travel(target.site, star, markers)
		var before := cour.snapshot()
		valid_dependencies = (validate(cycle).reason == "cycle" and validate(blocked_goal).reason == "required-optional"
				and in_position and not cour.complete(target) and cour.snapshot() == before)
		reachable = validate(disconnected).reason == "unreachable" and _route_crosscheck(selected, star, markers)
		var main := _drive(probe, selected, proof.required_order, star, markers)
		var full := _drive(probe, selected, proof.order, star, markers)
		if not main.is_empty() and not full.is_empty():
			battery_left = full.state.charge
			matched = matched and full == _drive(probe, selected, proof.order, star, markers)
			within_budget = (validate(depleted).reason == "budget" and main.state.charge == proof.main.charge
					and full.state.charge == proof.full.charge and battery_left >= 0)
			progressed = (main.state.completed == proof.required_order and full.state.completed == proof.order
					and selected.target in main.state.completed and 3 not in main.state.completed and 3 in full.state.completed
					and main.duplicate_rejected and full.duplicate_rejected)

	var fallback := generate(SEEDS[0], DEFAULT_BATTERY, 0)
	var impossible := generate(SEEDS[0], 0, MAX_ATTEMPTS)
	var cut_off := generate(SEEDS[0], DEFAULT_BATTERY, 2, [0, 1])
	var recovery: bool = (fallback.status == "fallback" and fallback.attempts == 0 and validate(fallback.mission).valid
			and impossible.status == "unavailable" and impossible.attempts == MAX_ATTEMPTS and impossible.reason == "budget"
			and cut_off.status == "unavailable" and cut_off.attempts == 2 and cut_off.reason == "unreachable")
	probe.free()
	var cleaned := not is_instance_valid(probe) and tree.root.get_child_count() == original_children
	return {"id": "missions", "checks": [
		_check("seeded-replay", matched and generated > 0, "Regenerated the fixed seed set and repeated a scene mission."),
		_check("route-variation", routes.size() > 1 and goals.size() == 2 and detours.size() == 2,
			"Observed distinct route plans, completion goals and optional-work locations."),
		_check("dependency-validation", valid_dependencies, "Rejected a cycle, an optional requirement and a premature goal attempt."),
		_check("route-reachability", reachable, "Matched shortest hop counts to Godot AStar2D and rejected an isolated starting site."),
		_check("resource-budget", within_budget, "Checked travel and task costs against actual charge and rejected zero starting charge."),
		_check("mission-progression", progressed, "Finished the required goal with and without the optional task and refused repeated rewards."),
		_check("bounded-recovery", recovery, "Validated a deterministic fallback and stopped at the attempt limit for two impossible policies."),
		_check("probe-cleanup", cleaned, "Freed the mission markers, agents and probe root before returning."),
	], "metrics": {"seeds": SEEDS.size(), "generated": generated, "route_variants": routes.size(),
		"goal_variants": goals.size(), "optional_sites": detours.size(), "remaining_battery": battery_left,
		"failed_attempts": impossible.attempts}}
