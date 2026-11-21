extends RefCounted
## Three seeded offers share a board. Claiming a finished job opens the next board.

const MAX_SEED := 2_147_483_647
const MAX_GENERATION := 2_147_483_647
const RESOURCES := ["wood", "stone", "fiber"]
const SUPPLY_TITLES := ["Timber for the sawmill", "Stone for the foundations", "Fiber for the weavers"]

var _seed := -1
var _generation := 0
var _offers: Array = []
var _active_slot := -1
var _step_index := 0
var _progress := 0


func configure(seed: int) -> bool:
	if seed < 0 or seed > MAX_SEED:
		return false
	_seed = seed
	_open_board(0)
	return true


func board() -> Array:
	return _offers.duplicate(true)


func accept(id: String) -> bool:
	if _active_slot != -1:
		return false
	var slot := _find_offer(_offers, id)
	if slot < 0:
		return false
	_active_slot = slot
	return true


## Each call represents one successful world interaction. Steps must be performed in order.
func record(action: String, target: String) -> bool:
	if _active_slot < 0:
		return false
	var steps: Array = _offers[_active_slot].steps
	if _step_index >= steps.size():
		return false
	var expected: Dictionary = steps[_step_index]
	if action != expected.action or target != expected.target:
		return false
	_progress += 1
	if _progress == expected.count:
		_step_index += 1
		_progress = 0
	return true


## Returns the amount payable once. A second claim without another completed job returns zero.
func claim() -> int:
	if _active_slot < 0:
		return 0
	var offer: Dictionary = _offers[_active_slot]
	if _step_index != offer.steps.size():
		return 0
	var reward: int = offer.reward
	_open_board((_generation + 1) % (MAX_GENERATION + 1))
	return reward


func status() -> Dictionary:
	var offer: Dictionary = {} if _active_slot < 0 else _offers[_active_slot]
	var steps: Array = offer.get("steps", [])
	var current: Dictionary = {} if _step_index >= steps.size() else steps[_step_index].duplicate()
	return {
		"generation": _generation if _seed >= 0 else -1,
		"active_id": offer.get("id", ""), "title": offer.get("title", ""),
		"step_index": _step_index, "step_count": steps.size(), "progress": _progress,
		"current": current, "complete": _active_slot >= 0 and _step_index == steps.size(),
		"reward": offer.get("reward", 0),
	}


func snapshot() -> Dictionary:
	if _seed < 0:
		return {}
	return {
		"version": 1, "seed": _seed, "generation": _generation,
		"active_id": "" if _active_slot < 0 else _offers[_active_slot].id,
		"step_index": _step_index, "progress": _progress,
	}


func restore(state: Dictionary) -> bool:
	if _seed < 0 or state.size() != 6 or not state.has_all([
		"version", "seed", "generation", "active_id", "step_index", "progress",
	]):
		return false
	if _integer(state.version, 1) != 1 or _integer(state.seed, MAX_SEED) != _seed:
		return false
	var generation := _integer(state.generation, MAX_GENERATION)
	if generation < 0 or state.active_id is not String:
		return false
	var offers := _make_offers(generation)
	var slot := _find_offer(offers, state.active_id)
	if slot < 0 and state.active_id != "":
		return false
	var steps: Array = [] if slot < 0 else offers[slot].steps
	var index := _integer(state.step_index, steps.size())
	if index < 0:
		return false
	# Advancing a step immediately resets its count, including the final step.
	var max_progress: int = steps[index].count - 1 if index < steps.size() else 0
	var progress := _integer(state.progress, max_progress)
	if progress < 0:
		return false
	_generation = generation
	_offers = offers
	_active_slot = slot
	_step_index = index
	_progress = progress
	return true


func _integer(value: Variant, maximum: int) -> int:
	# JSON restores integers as doubles. The serialized counters all fit exactly.
	if value is int or value is float:
		if is_finite(float(value)) and value >= 0 and value <= maximum and value == int(value):
			return int(value)
	return -1


func _open_board(generation: int) -> void:
	_generation = generation
	_offers = _make_offers(generation)
	_active_slot = -1
	_step_index = 0
	_progress = 0


func _find_offer(offers: Array, id: String) -> int:
	for i in offers.size():
		if offers[i].id == id:
			return i
	return -1


func _step(action: String, target: String, count: int = 1) -> Dictionary:
	return {"action": action, "target": target, "count": count}


func _make_offers(generation: int) -> Array:
	var rng := RandomNumberGenerator.new()
	var issue := "%d/%d" % [_seed, generation]
	rng.seed = ("contract-board/" + issue).hash()
	var resource_index := (_seed + generation) % RESOURCES.size()
	var quantity := rng.randi_range(1, 2)
	var supply := {
		"id": issue + "/supply", "title": SUPPLY_TITLES[resource_index],
		"steps": [_step("gather", RESOURCES[resource_index], quantity)],
		"reward": 6 + 3 * quantity,
	}
	var faction: String = ["rangers", "settlers"][rng.randi_range(0, 1)]
	var route_steps := [_step("drive", "checkpoint"), _step("greet", faction)]
	var route_title := "Bring checkpoint news to the " + faction
	if rng.randi_range(0, 1) == 1:
		route_steps.reverse()
		route_title = "Carry the %s' dispatch to the checkpoint" % faction
	var route := {
		"id": issue + "/dispatch", "title": route_title,
		"steps": route_steps, "reward": 16 + rng.randi_range(0, 4),
	}
	var steps: Array
	var title: String
	match rng.randi_range(0, 2):
		0:
			title = "Stock the field infirmary"
			steps = [_step("gather", "fiber", 2), _step("craft", "bandage")]
		1:
			title = "Fill the outpost tool order"
			steps = [_step("craft", "tool"), _step("sell", "tool")]
		_:
			title = "Equip the " + faction
			steps = [_step("craft", "tool"), _step("greet", faction)]
	var workshop := {
		"id": issue + "/workshop", "title": title,
		"steps": steps, "reward": 19 + rng.randi_range(0, 5),
	}
	return [supply, route, workshop]
