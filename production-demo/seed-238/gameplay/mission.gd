extends RefCounted

var remaining: Array[String] = []
var completed := false
var _targets: Array[String] = []
var _seed_value := 0

func configure(seed_value: int, targets: Array[String]) -> void:
	_seed_value = seed_value
	_targets.clear()
	for id in targets:
		if not _targets.has(id):
			_targets.append(id)
	_targets.sort()
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	for i in range(_targets.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var swap := _targets[i]
		_targets[i] = _targets[j]
		_targets[j] = swap
	remaining.assign(_targets)
	completed = false

func eliminate(id: String) -> bool:
	if not remaining.has(id):
		return false
	remaining.erase(id)
	return true

func extract() -> bool:
	if completed or not remaining.is_empty():
		return false
	completed = true
	return true

func snapshot() -> Dictionary:
	# JSON numbers cannot represent every 64-bit seed exactly.
	return {"version": "1", "seed": str(_seed_value), "targets": _targets.duplicate(),
		"remaining": remaining.duplicate(), "completed": completed}

func restore(data: Dictionary) -> bool:
	var fields := ["version", "seed", "targets", "remaining", "completed"]
	if data.size() != fields.size() or not data.has_all(fields):
		return false
	if typeof(data.version) != TYPE_STRING or data.version != "1":
		return false
	if typeof(data.seed) != TYPE_STRING or data.seed != str(_seed_value):
		return false
	if typeof(data.completed) != TYPE_BOOL or typeof(data.targets) != TYPE_ARRAY or typeof(data.remaining) != TYPE_ARRAY:
		return false
	if data.targets != _targets or (data.completed and not data.remaining.is_empty()):
		return false
	var verified: Array[String] = []
	var previous_index := -1
	for id in data.remaining:
		if typeof(id) != TYPE_STRING:
			return false
		var index := _targets.find(id)
		if index <= previous_index:
			return false
		verified.append(id)
		previous_index = index
	remaining = verified
	completed = data.completed
	return true

static func write_checkpoint(path: String, data: Dictionary) -> bool:
	var temp_path := "%s.%s.tmp" % [path, ResourceUID.create_id()]
	var file := FileAccess.open(temp_path, FileAccess.WRITE)
	if file == null:
		return false
	var written := file.store_string(JSON.stringify(data))
	file.flush()
	var success := written and file.get_error() == OK
	file.close()
	var temp_absolute := ProjectSettings.globalize_path(temp_path)
	if success and DirAccess.rename_absolute(temp_absolute, ProjectSettings.globalize_path(path)) == OK:
		return true
	DirAccess.remove_absolute(temp_absolute)
	return false

static func read_checkpoint(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK or typeof(parser.data) != TYPE_DICTIONARY:
		return {}
	return parser.data
