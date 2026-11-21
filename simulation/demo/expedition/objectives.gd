extends RefCounted
## Ordered mission progress. An event consumes at most one configured stage.

const ACTIONS := ["visit", "interact", "drive"]

var _stages: Array[Dictionary] = []
var _cursor := 0
var index: int:
	get:
		return _cursor
var completed: bool:
	get:
		return not _stages.is_empty() and _cursor == _stages.size()


## Start a fresh mission. Invalid plans preserve the current mission and progress.
func configure(stages: Array) -> bool:
	if stages.is_empty():
		return false
	var validated: Array[Dictionary] = []
	var seen := {}
	for stage in stages:
		if typeof(stage) != TYPE_DICTIONARY or stage.size() != 2 or not stage.has_all(["action", "target"]):
			return false
		if typeof(stage.action) != TYPE_STRING or not ACTIONS.has(stage.action):
			return false
		if typeof(stage.target) != TYPE_STRING or stage.target.is_empty() or stage.target != stage.target.strip_edges():
			return false
		if not seen.has(stage.action):
			seen[stage.action] = {}
		if seen[stage.action].has(stage.target):
			return false
		seen[stage.action][stage.target] = true
		validated.append({"action": stage.action, "target": stage.target})
	_stages = validated
	_cursor = 0
	return true


## The next required event, or an empty dictionary before setup and after completion.
func current() -> Dictionary:
	if _cursor >= _stages.size():
		return {}
	return _stages[_cursor].duplicate()


func record(action: String, target: String) -> bool:
	if _cursor >= _stages.size():
		return false
	var stage := _stages[_cursor]
	if action != stage.action or target != stage.target:
		return false
	_cursor += 1
	return true


## Independent, JSON-compatible checkpoint bound to the ordered plan.
func snapshot() -> Dictionary:
	return {"version": "1", "stages": _stages.duplicate(true), "index": _cursor}


## Restore a checkpoint into its configured mission, rejecting invalid data atomically.
func restore(state: Dictionary) -> bool:
	if _stages.is_empty() or state.size() != 3 or not state.has_all(["version", "stages", "index"]):
		return false
	if typeof(state.version) != TYPE_STRING or state.version != "1":
		return false
	if typeof(state.stages) != TYPE_ARRAY or state.stages != _stages:
		return false
	# Godot's JSON parser represents even whole numbers as floats.
	if typeof(state.index) != TYPE_INT and typeof(state.index) != TYPE_FLOAT:
		return false
	if not is_finite(float(state.index)) or state.index < 0 or state.index > _stages.size():
		return false
	if int(state.index) != state.index:
		return false
	_cursor = int(state.index)
	return true
