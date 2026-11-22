extends RefCounted


class DecisionAgent extends RefCounted:
	# Equal utilities use this order. Each goal owns at most one observed site.
	const GOALS := ["survival", "task", "resource", "social"]
	const SIGHT_RADIUS := 4
	const MEMORY_TICKS := 6
	const SWITCH_MARGIN := 6
	const CRITICAL_NEED := 90

	var grid: AStarGrid2D
	var cell: Vector2i
	var clock := 0
	var needs := {"survival": 0, "task": 0, "resource": 0, "social": 0}
	var known := {}
	var goal := ""
	var path: Array[Vector2i] = []
	var unreachable: Array[String] = []

	func _init(map: AStarGrid2D, start: Vector2i) -> void:
		grid = map
		cell = start

	func set_need(kind: String, amount: int) -> void:
		if kind in GOALS:
			needs[kind] = clampi(amount, 0, 100)

	func observe(kind: String, site: Vector2i) -> bool:
		if kind not in GOALS or not grid.is_in_boundsv(site) or cell.distance_squared_to(site) > SIGHT_RADIUS ** 2:
			return false
		for point in Geometry2D.bresenham_line(cell, site):
			if grid.is_point_solid(point):
				return false
		known[kind] = {"site": site, "seen": clock}
		return true

	func choose() -> String:
		var routes := {}
		var scores := {}
		var best := ""
		var best_score := 0
		unreachable.clear()
		for kind: String in GOALS:
			if not known.has(kind) or needs[kind] == 0:
				continue
			var site: Vector2i = known[kind].site
			var route: Array[Vector2i] = []
			if not grid.is_point_solid(site):
				route = grid.get_id_path(cell, site, false)
			if route.is_empty():
				unreachable.append(kind)
				continue
			routes[kind] = route
			# Each cardinal step costs two utility points.
			var score := int(needs[kind]) - 2 * (route.size() - 1)
			scores[kind] = score
			if best.is_empty() or score > best_score:
				best = kind
				best_score = score
		if routes.has("survival") and needs.survival >= CRITICAL_NEED:
			best = "survival"
		elif scores.has(goal) and best_score <= int(scores[goal]) + SWITCH_MARGIN:
			best = goal
		goal = best
		path.clear()
		if not goal.is_empty():
			path.assign(routes[goal])
		return goal

	func step() -> String:
		clock += 1
		for kind: String in GOALS:
			if known.has(kind) and clock - int(known[kind].seen) >= MEMORY_TICKS:
				known.erase(kind)
		var action := choose()
		if action.is_empty():
			return ""
		if path.size() > 1:
			path.pop_front()
			cell = path[0]
		if cell == known[action].site:
			needs[action] = 0
			known.erase(action)
			goal = ""
			path.clear()
		return action


func _grid() -> AStarGrid2D:
	var grid := AStarGrid2D.new()
	grid.region = Rect2i(0, 0, 10, 8)
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER
	grid.default_compute_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	grid.default_estimate_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	grid.update()
	return grid


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func _tie_agent(map: AStarGrid2D, reverse: bool) -> DecisionAgent:
	var actor := DecisionAgent.new(map, Vector2i(3, 3))
	var sites := {"task": Vector2i(2, 3), "resource": Vector2i(4, 3)}
	var order := ["resource", "task"] if reverse else ["task", "resource"]
	for kind: String in order:
		actor.observe(kind, sites[kind])
		actor.set_need(kind, 60)
	return actor


func run(tree: SceneTree) -> Dictionary:
	var checks: Array[Dictionary] = []
	var screened := _grid()
	screened.set_point_solid(Vector2i(3, 2))
	var witness := DecisionAgent.new(screened, Vector2i(2, 2))
	witness.set_need("survival", 100)
	witness.set_need("resource", 90)
	witness.set_need("task", 65)
	var far := witness.observe("survival", Vector2i(9, 7))
	var occluded := witness.observe("resource", Vector2i(4, 2))
	var nearby := witness.observe("task", Vector2i(2, 3))
	var observed_goal := witness.choose()
	checks.append(_check("observed-goals",
		not far and not occluded and nearby and witness.known.size() == 1 and observed_goal == "task",
		"Far and occluded observations accepted: %s/%s. The visible site selected %s." % [far, occluded, observed_goal]))

	var open := _grid()
	var worker := _tie_agent(open, false)
	var reversed := _tie_agent(open, true)
	var normal_tie := worker.choose()
	var reverse_tie := reversed.choose()
	reversed.set_need("task", 0)
	reversed.observe("social", Vector2i(3, 6))
	reversed.set_need("social", 63)
	var cheaper := reversed.choose()
	checks.append(_check("utility-ties",
		normal_tie == "task" and reverse_tie == "task" and cheaper == "resource",
		"Opposite observation orders selected %s/%s. A shorter route then favored %s." % [normal_tie, reverse_tie, cheaper]))

	worker.set_need("resource", 66)
	var held := worker.choose()
	worker.set_need("resource", 67)
	var switched := worker.choose()
	checks.append(_check("switch-margin", held == "task" and switched == "resource",
		"At the six-point margin the agent held %s. A seven-point lead selected %s." % [held, switched]))

	worker.set_need("resource", 100)
	worker.observe("survival", Vector2i(3, 5))
	worker.set_need("survival", 89)
	var ordinary := worker.choose()
	worker.set_need("survival", 90)
	var urgent := worker.choose()
	checks.append(_check("survival-preemption", ordinary == "resource" and urgent == "survival",
		"Survival needs 89/90 selected %s/%s against a nearer resource with need 100." % [ordinary, urgent]))

	var memory := DecisionAgent.new(open, Vector2i(3, 3))
	var nearby_sites := [Vector2i(2, 3), Vector2i(4, 3), Vector2i(3, 2), Vector2i(3, 4)]
	for i in DecisionAgent.GOALS.size():
		memory.observe(DecisionAgent.GOALS[i], nearby_sites[i])
	var slot_peak := memory.known.size()
	var latest := Vector2i(3, 5)
	var refresh_ok := false
	for elapsed in range(1, DecisionAgent.MEMORY_TICKS + 1):
		await tree.physics_frame
		memory.step()
		if elapsed == 2:
			refresh_ok = memory.observe("social", latest)
			slot_peak = maxi(slot_peak, memory.known.size())
	var fresh_only: bool = memory.known.size() == 1 and memory.known.has("social") and memory.known.social.site == latest
	memory.set_need("survival", 100)
	memory.set_need("social", 10)
	var retained := memory.choose()
	memory.set_need("social", 0)
	for i in range(2):
		await tree.physics_frame
		memory.step()
	checks.append(_check("memory-bounds",
		refresh_ok and slot_peak == 4 and fresh_only and retained == "social" and memory.known.is_empty() and memory.choose().is_empty(),
		"Peak %d slots. Refresh retained %s at tick six. At tick eight %d sites remained." % [slot_peak, retained, memory.known.size()]))

	var canal := _grid()
	var mover := DecisionAgent.new(canal, Vector2i(3, 3))
	mover.observe("task", Vector2i(6, 3))
	mover.observe("social", Vector2i(3, 5))
	mover.observe("survival", Vector2i(5, 3))
	mover.set_need("task", 90)
	mover.set_need("social", 55)
	var original := mover.choose()
	for y in range(canal.region.size.y):
		canal.set_point_solid(Vector2i(4, y))
	mover.set_need("survival", 100)
	await tree.physics_frame
	var fallback := mover.step()
	var fallback_cell := mover.cell
	checks.append(_check("route-fallback",
		original == "task" and fallback == "social" and fallback_cell == Vector2i(3, 4)
		and mover.unreachable.has("survival") and mover.unreachable.has("task") and mover.known.has("task"),
		"The closed crossing ruled out %s. The agent advanced to %s on %s." % [mover.unreachable, fallback_cell, fallback]))

	var gate := Vector2i(4, 4)
	canal.set_point_solid(gate, false)
	mover.set_need("survival", 0)
	await tree.physics_frame
	var recovered := mover.step()
	var legal_path: bool = not mover.path.is_empty() and mover.path[0] == mover.cell and mover.path.back() == Vector2i(6, 3)
	for i in range(1, mover.path.size()):
		legal_path = legal_path and not canal.is_point_solid(mover.path[i]) and mover.path[i - 1].distance_squared_to(mover.path[i]) == 1
	checks.append(_check("route-recovery",
		recovered == "task" and mover.cell == gate and legal_path and mover.unreachable.is_empty(),
		"After the crossing opened the agent selected %s, entered %s and had %d path cells left." % [recovered, mover.cell, mover.path.size()]))

	var finish_steps := 0
	while mover.goal == "task" and finish_steps < 8:
		await tree.physics_frame
		mover.step()
		finish_steps += 1
	var finished: bool = mover.cell == Vector2i(6, 3) and not mover.known.has("task") and mover.needs.task == 0 and mover.goal.is_empty()
	var following := mover.choose()
	checks.append(_check("goal-completion", finish_steps == 3 and finished and following == "social",
		"After %d more steps the agent stood at %s, task need was %d and the next goal was %s." % [finish_steps, mover.cell, mover.needs.task, following]))

	return {"id": "decision", "checks": checks, "metrics": {"peak_observation_slots": slot_peak,
		"memory_ticks": DecisionAgent.MEMORY_TICKS, "switch_margin": DecisionAgent.SWITCH_MARGIN,
		"fallback_goal": fallback, "recovered_goal": recovered, "steps_from_gate_to_task": finish_steps, "next_goal": following}}
