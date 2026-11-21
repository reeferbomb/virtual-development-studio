extends SceneTree

const Objectives = preload("res://objectives.gd")

var failures := 0


func check(condition: bool, detail: String) -> void:
	if not condition:
		printerr("FAIL ", detail)
		failures += 1


func _initialize() -> void:
	var plan := [
		{"action": "interact", "target": "relay"},
		{"action": "drive", "target": "checkpoint"},
		{"action": "visit", "target": "goal"},
	]
	var mission := Objectives.new()
	check(not mission.completed and mission.current().is_empty(), "fresh mission")
	check(not mission.record("visit", "goal"), "reject event before setup")
	var supplied := plan.duplicate(true)
	check(mission.configure(supplied), "configure valid stages")
	supplied[0].target = "changed"
	mission.current().target = "changed"
	check(mission.current() == plan[0], "mission owns its stages")
	check(not mission.record("visit", "goal") and mission.index == 0, "cannot skip")
	check(not mission.record("drive", "relay") and not mission.record("interact", "goal"), "match both fields")
	check(mission.record("interact", "relay") and mission.index == 1, "consume exactly one stage")
	check(not mission.record("interact", "relay") and mission.current() == plan[1], "no duplicate events")

	var partial := mission.snapshot()
	for invalid in [[], [plan[0], plan[0]], ["visit"], [{}], [{"action": "fly", "target": "goal"}],
			[{"action": "visit", "target": ""}], [{"action": "visit", "target": " goal "}],
			[{"action": 4, "target": "goal"}], [{"action": "visit", "target": 4}],
			[{"action": "visit", "target": "goal", "extra": true}]]:
		check(not mission.configure(invalid) and mission.snapshot() == partial, "reject invalid plan atomically")

	var resumed := Objectives.new()
	check(resumed.configure(plan), "configure second mission")
	check(resumed.restore(JSON.parse_string(JSON.stringify(partial))), "restore through JSON")
	check(resumed.snapshot() == partial, "restored same stage")
	for bad_index in [-1, 4, 1.5, true, "1", INF]:
		var invalid := partial.duplicate(true)
		invalid.index = bad_index
		check(not resumed.restore(invalid) and resumed.snapshot() == partial, "reject invalid progress")
	var foreign := partial.duplicate(true)
	foreign.stages.reverse()
	check(not resumed.restore(foreign) and resumed.current() == plan[1], "reject other plan")
	check(resumed.record("drive", "checkpoint") and not resumed.completed, "drive unlocks final stage")
	check(resumed.record("visit", "goal") and resumed.completed and resumed.index == 3, "finish")
	check(resumed.current().is_empty() and not resumed.record("visit", "goal"), "terminal state")
	check(mission.restore(resumed.snapshot()) and mission.completed, "restore terminal state")
	check(mission.configure(plan) and mission.index == 0 and not mission.completed, "start again")
	print("Objective assertions finished, failures=", failures)
	quit(int(failures != 0))
