extends RefCounted
## A field contract advances when gameplay reports its next exact event.

const MAX_SEED := 2147483647
const TITLES := ["Frontier Supply Run", "Outpost Refit", "Ridgeway Delivery"]
const STAGES := [
	{"action": "craft", "target": "tool"},
	{"action": "drive", "target": "checkpoint"},
	{"action": "trade", "target": "tool"},
	{"action": "defeat", "target": "drone"},
]

var _seed := -1
var _index := 0
var index: int:
	get:
		return _index
var completed: bool:
	get:
		return _index == STAGES.size()
var title: String:
	get:
		return TITLES[_seed % TITLES.size()] if _seed >= 0 else ""


func configure(seed: int) -> bool:
	if seed < 0 or seed > MAX_SEED:
		return false
	_seed = seed
	_index = 0
	return true


func current() -> Dictionary:
	if _seed < 0 or completed:
		return {}
	return STAGES[_index].duplicate()


func record(action: String, target: String) -> bool:
	if _seed < 0 or completed:
		return false
	var stage: Dictionary = STAGES[_index]
	if action != stage.action or target != stage.target:
		return false
	_index += 1
	return true


## Contract value. The game pays this once when an event completes the quest.
func reward() -> int:
	return 25 if _seed >= 0 else 0


func snapshot() -> Dictionary:
	return {"seed": _seed, "index": _index} if _seed >= 0 else {}


func restore(state: Dictionary) -> bool:
	if _seed < 0 or state.size() != 2 or not state.has_all(["seed", "index"]):
		return false
	# Godot's JSON parser returns floats for numbers. All valid seeds and
	# stages are within the exact integer range of a double.
	if not (state.seed is int or state.seed is float) or state.seed != _seed:
		return false
	var cursor: Variant = state.index
	if not (cursor is int or cursor is float) or not is_finite(float(cursor)):
		return false
	if cursor < 0 or cursor > STAGES.size() or int(cursor) != cursor:
		return false
	_index = int(cursor)
	return true
