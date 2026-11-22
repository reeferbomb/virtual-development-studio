extends RefCounted


# Three groups of lantern-festival visitors can arrive during one evening.
class Festival extends Node2D:
	const CELL := 32
	const HOME := Vector2i(0, 2)
	const STEWARD := Vector2i(3, 3)
	const SITES := {
		Vector2i(2, 0): "Hazel Steps", Vector2i(4, 2): "Glass Arcade",
		Vector2i(3, 4): "Orchard Gate", Vector2i(2, 2): "Closed Bridge",
		Vector2i(6, 2): "Far Bank", STEWARD: "Steward Post", HOME: "Home Steps",
		Vector2i(1, 2): "Home Lane",
	}
	const PARTIES := {"Bell cart": 2, "Moth choir": 2, "Lantern keeper": 1}
	const WAVE_LIMIT := 3
	var grid := AStarGrid2D.new()
	var rng := RandomNumberGenerator.new()
	var actors := Node2D.new()
	var player := Node2D.new()
	var steward := Node2D.new()
	var warning := Label.new()
	var visitor: Node2D
	var phase := "idle"
	var remaining := 0
	var ticks_left := 0
	var warning_ticks := 2 * Engine.physics_ticks_per_second
	var cooldown_ticks := Engine.physics_ticks_per_second
	var party := ""
	var site := Vector2i.ZERO
	var arrivals: Array[Dictionary] = []

	func _ready() -> void:
		grid.region = Rect2i(0, 0, 7, 5)
		grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER
		grid.update()
		add_child(actors)
		actors.add_child(player)
		actors.add_child(steward)
		var hud := CanvasLayer.new()
		add_child(hud)
		hud.add_child(warning)
		warning.position = Vector2(12, 12)
		warning.mouse_filter = Control.MOUSE_FILTER_IGNORE
		reset_evening(73, 5)

	func reset_evening(seed_value: int, credits: int) -> void:
		if is_instance_valid(visitor):
			visitor.free()
		visitor = null
		grid.fill_solid_region(grid.region, false)
		for y in grid.region.size.y:
			grid.set_point_solid(Vector2i(5, y))
		grid.set_point_solid(Vector2i(2, 2))
		player.position = Vector2(HOME * CELL)
		steward.position = Vector2(STEWARD * CELL)
		rng.seed = seed_value
		remaining = maxi(0, credits)
		ticks_left = 0
		arrivals.clear()
		phase = "idle"
		clear_warning()

	func clear_warning() -> void:
		party = ""
		site = Vector2i.ZERO
		warning.text = ""
		warning.hide()

	func eligible(cell: Vector2i) -> bool:
		var origin := Vector2i(player.position / CELL)
		if not SITES.has(cell) or not grid.region.has_point(origin):
			return false
		if grid.is_point_solid(cell) or grid.is_point_solid(origin):
			return false
		if absi(cell.x - origin.x) + absi(cell.y - origin.y) < 2:
			return false
		for actor: Node2D in actors.get_children():
			if Vector2i(actor.position / CELL) == cell:
				return false
		return not grid.get_id_path(origin, cell).is_empty()

	func request_arrival() -> bool:
		if phase != "idle" or arrivals.size() >= WAVE_LIMIT:
			return false
		var sites: Array[Vector2i] = []
		for cell: Vector2i in SITES:
			if eligible(cell):
				sites.append(cell)
		var parties: Array[String] = []
		for name_key: String in PARTIES:
			if PARTIES[name_key] <= remaining:
				parties.append(name_key)
		if sites.is_empty() or parties.is_empty():
			return false
		party = parties[rng.randi_range(0, parties.size() - 1)]
		site = sites[rng.randi_range(0, sites.size() - 1)]
		warning.text = "%s approaching %s." % [party, SITES[site]]
		warning.show()
		phase = "warning"
		ticks_left = warning_ticks
		return true

	func _physics_process(_delta: float) -> void:
		step()

	func step() -> void:
		if phase != "warning" and phase != "cooldown":
			return
		ticks_left -= 1
		if ticks_left > 0:
			return
		if phase == "cooldown":
			if remaining == 0 or arrivals.size() >= WAVE_LIMIT:
				phase = "recovered"
			else:
				phase = "idle"
				request_arrival()
			return
		if eligible(site) and PARTIES[party] <= remaining:
			visitor = Node2D.new()
			visitor.name = party
			visitor.position = Vector2(site * CELL)
			actors.add_child(visitor)
			remaining -= PARTIES[party]
			arrivals.append({"party": party, "site": SITES[site], "cost": PARTIES[party]})
			phase = "active"
		else:
			phase = "cooldown"
			ticks_left = cooldown_ticks
		clear_warning()

	func resolve(actor: Node2D) -> bool:
		if phase != "active" or actor != visitor or not is_instance_valid(visitor):
			return false
		visitor.free()
		visitor = null
		phase = "cooldown"
		ticks_left = cooldown_ticks
		return true


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func _advance(festival: Festival, ticks: int) -> void:
	for tick in ticks:
		festival.step()


func _evening(festival: Festival, seed_value: int) -> Dictionary:
	festival.reset_evening(seed_value, 5)
	var ordered := festival.request_arrival()
	var spent := 0
	for wave in Festival.WAVE_LIMIT:
		var previous := festival.remaining
		var announced := festival.party
		var destination := festival.site
		ordered = ordered and festival.phase == "warning" and festival.warning.is_visible_in_tree()
		_advance(festival, festival.warning_ticks)
		if not is_instance_valid(festival.visitor):
			ordered = false
			break
		var cost: int = Festival.PARTIES[announced]
		spent += cost
		ordered = ordered and festival.phase == "active" and festival.visitor.name == announced
		ordered = ordered and festival.visitor.position == Vector2(destination * Festival.CELL)
		ordered = ordered and festival.actors.get_child_count() == 3 and festival.remaining == previous - cost
		var resolved := festival.resolve(festival.visitor)
		ordered = ordered and resolved and festival.phase == "cooldown"
		_advance(festival, festival.cooldown_ticks)
	_advance(festival, festival.warning_ticks)
	var recovered := festival.phase == "recovered" and not festival.request_arrival()
	recovered = recovered and festival.actors.get_child_count() == 2 and not festival.warning.is_visible_in_tree()
	return {"arrivals": festival.arrivals.duplicate(true), "spent": spent, "remaining": festival.remaining,
		"complete": ordered and recovered and festival.arrivals.size() == 3 and spent + festival.remaining == 5}


func run(tree: SceneTree) -> Dictionary:
	var festival := Festival.new()
	tree.root.add_child(festival)
	festival.set_physics_process(false)
	var checks: Array[Dictionary] = []
	var parties := {}
	var locations := {}
	for seed_value in range(1, 17):
		festival.reset_evening(seed_value, 5)
		if festival.request_arrival():
			parties[festival.party] = true
			locations[festival.site] = true
	checks.append(_check("seeded-choice", parties.size() > 1 and locations.size() > 1,
		"Sixteen seeds selected %d party types and %d locations." % [parties.size(), locations.size()]))

	festival.reset_evening(73, 5)
	var started := festival.request_arrival()
	var planned_site := festival.site
	var expected_text := "%s approaching %s." % [festival.party, Festival.SITES[planned_site]]
	var warned := started and festival.warning.is_visible_in_tree() and festival.warning.text == expected_text
	var full_warning := festival.ticks_left
	# Run one real physics callback and drive the remaining identical ticks explicitly.
	await tree.physics_frame
	festival.set_physics_process(true)
	await tree.physics_frame
	festival.set_physics_process(false)
	warned = warned and festival.ticks_left == full_warning - 1
	_advance(festival, full_warning - 2)
	warned = warned and festival.phase == "warning" and festival.visitor == null and festival.remaining == 5
	festival.step()
	warned = warned and festival.phase == "active" and is_instance_valid(festival.visitor) and not festival.warning.visible
	checks.append(_check("warning-window", warned,
		"The HUD named the approaching party and location for %d physics ticks before arrival." % full_warning))

	festival.reset_evening(73, 5)
	var safe := festival.eligible(Vector2i(2, 0))
	for cell in [Vector2i(-1, 2), Festival.HOME, Vector2i(1, 2), Festival.STEWARD, Vector2i(2, 2), Vector2i(6, 2)]:
		safe = safe and not festival.eligible(cell)
	var gates := [Vector2i(2, 0), Vector2i(4, 2), Vector2i(3, 4)]
	for gate in gates:
		festival.grid.set_point_solid(gate)
	safe = safe and not festival.request_arrival() and festival.phase == "idle" and not festival.warning.visible
	for gate in gates:
		festival.grid.set_point_solid(gate, false)
	checks.append(_check("spawn-eligibility", safe,
		"Checked the player, nearby and occupied cells, a closed bridge, a disconnected bank, an off-map cell and all gates closed."))

	var cancelled := true
	for obstruction in ["player", "resident", "wall"]:
		festival.reset_evening(73, 5)
		festival.request_arrival()
		var held_site := festival.site
		if obstruction == "player":
			festival.player.position = Vector2(held_site * Festival.CELL)
		elif obstruction == "resident":
			festival.steward.position = Vector2(held_site * Festival.CELL)
		else:
			festival.grid.set_point_solid(held_site)
		_advance(festival, festival.warning_ticks)
		cancelled = cancelled and festival.phase == "cooldown" and festival.visitor == null
		cancelled = cancelled and festival.arrivals.is_empty() and festival.remaining == 5 and not festival.warning.visible
	checks.append(_check("arrival-recheck", cancelled,
		"The player, a moved resident and a newly closed gate each cancelled the announced arrival without spending credits."))

	festival.reset_evening(73, 0)
	var budget_ok := not festival.request_arrival() and not festival.warning.visible
	festival.reset_evening(73, 1)
	budget_ok = budget_ok and festival.request_arrival() and festival.party == "Lantern keeper"
	_advance(festival, festival.warning_ticks)
	budget_ok = budget_ok and festival.remaining == 0 and not festival.resolve(festival.steward)
	budget_ok = budget_ok and not festival.request_arrival() and festival.arrivals.size() == 1
	var only_visitor := festival.resolve(festival.visitor)
	_advance(festival, festival.cooldown_ticks)
	budget_ok = budget_ok and only_visitor and festival.phase == "recovered" and festival.arrivals.size() == 1
	checks.append(_check("wave-budget", budget_ok,
		"Zero credits funded no warning. One credit funded one keeper, with no duplicate debit or unrelated actor resolution."))

	festival.reset_evening(73, 5)
	festival.request_arrival()
	_advance(festival, festival.warning_ticks)
	var resolved := festival.resolve(festival.visitor)
	var balance := festival.remaining
	_advance(festival, festival.cooldown_ticks - 1)
	var cooled := resolved and festival.phase == "cooldown" and not festival.request_arrival()
	cooled = cooled and festival.visitor == null and not festival.warning.visible and festival.remaining == balance
	festival.step()
	cooled = cooled and festival.phase == "warning" and festival.warning.visible and festival.remaining == balance
	checks.append(_check("cooldown", cooled,
		"A new party could be announced only after the full %d-tick recovery interval." % festival.cooldown_ticks))

	var first := _evening(festival, 70)
	var surplus := _evening(festival, 73)
	checks.append(_check("sequence-recovery", first.complete and surplus.complete and surplus.remaining > 0,
		"Two evenings recovered after three groups, including one with unspent credits. Only the two residents remained."))
	festival.reset_evening(99, 5)
	festival.request_arrival()
	_advance(festival, festival.warning_ticks)
	var interrupted := is_instance_valid(festival.visitor)
	var old_visitor := festival.visitor
	festival.grid.set_point_solid(Vector2i(4, 2))
	festival.steward.position = Vector2(Vector2i(2, 0) * Festival.CELL)
	var replay := _evening(festival, 70)
	var restored := not festival.grid.is_point_solid(Vector2i(4, 2))
	restored = restored and festival.steward.position == Vector2(Festival.STEWARD * Festival.CELL)
	checks.append(_check("deterministic-reset", interrupted and not is_instance_valid(old_visitor) and restored and replay.complete and replay == first,
		"Reset removed the active visitor, restored the gate and resident, and reproduced the original party, location and cost sequence."))
	festival.free()
	return {"id": "encounters", "checks": checks, "metrics": {"seed": 70, "initial_credits": 5,
		"arrivals": first.arrivals, "spent_credits": first.spent, "remaining_credits": first.remaining,
		"warning_ticks": full_warning, "cooldown_ticks": Engine.physics_ticks_per_second}}
