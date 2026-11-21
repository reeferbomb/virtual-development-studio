extends SceneTree

const Mission = preload("res://mission.gd")
var failures := 0

func check(condition: bool, description: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", description)

func _initialize() -> void:
	var targets: Array[String] = ["a", "b", "c", "a"]
	var mission = Mission.new()
	mission.configure(42, targets)
	var replay = Mission.new()
	replay.configure(42, targets)
	check(mission.remaining == replay.remaining and mission.remaining.size() == 3, "deterministic unique order")
	check(not mission.extract() and not mission.eliminate("unknown"), "gate and unknown ID")
	var last: String = mission.remaining.back()
	check(mission.eliminate(last) and not mission.eliminate(last), "arbitrary defeat order and duplicate")
	var partial: Dictionary = mission.snapshot()
	var path := "user://mission-test-%s.json" % Time.get_ticks_usec()
	check(Mission.write_checkpoint(path, partial), "write checkpoint")
	check(replay.restore(Mission.read_checkpoint(path)) and replay.snapshot() == partial, "restore from disk")
	for invalid in [{"remaining": []}, {"remaining": ["unknown"]}, {"remaining": [last, last]}, {"completed": true}, {"seed": "123"}, {"targets": ["a"]}]:
		var damaged := partial.duplicate(true)
		damaged.merge(invalid, true)
		if invalid == {"remaining": []}:
			damaged["unexpected"] = "field"
		check(not replay.restore(damaged) and replay.snapshot() == partial, "atomic rejection %s" % [invalid])
	for id in replay.remaining.duplicate():
		check(replay.eliminate(id), "remaining defeat")
	check(replay.extract() and replay.completed and not replay.extract(), "single extraction")
	check(Mission.write_checkpoint(path, replay.snapshot()), "replace existing checkpoint")
	check(mission.restore(Mission.read_checkpoint(path)) and mission.completed, "restore completion")
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string("{broken")
	file.close()
	check(Mission.read_checkpoint(path).is_empty(), "malformed checkpoint")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	print("mission assertions finished, failures=", failures)
	quit(int(failures != 0))
