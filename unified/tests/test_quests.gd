extends SceneTree

const Quests := preload("res://quests.gd")
const EXPECTED := [
	{"action": "craft", "target": "tool"},
	{"action": "drive", "target": "checkpoint"},
	{"action": "trade", "target": "tool"},
	{"action": "defeat", "target": "drone"},
]

var failures := 0


func check(passed: bool, detail: String) -> void:
	if not passed:
		printerr("FAIL ", detail)
		failures += 1


func _initialize() -> void:
	var quest := Quests.new()
	check(quest.snapshot().is_empty() and quest.current().is_empty(), "empty before setup")
	check(not quest.record("craft", "tool") and not quest.completed, "unconfigured quest ignores events")
	check(not quest.restore({"seed": 237, "index": 1}), "must configure before restore")
	check(quest.configure(237) and quest.reward() == 25, "seed 237 contract")
	check(quest.current() == EXPECTED[0], "initial stage")
	quest.current().target = "changed"
	check(quest.current() == EXPECTED[0], "current returns independent stage data")
	for event in [["defeat", "drone"], ["", ""], ["craft", "scrap"], ["Craft", "tool"], ["trade", "tool"]]:
		check(not quest.record(event[0], event[1]) and quest.index == 0, "ignore unrelated event")
	check(quest.record("craft", "tool") and quest.index == 1, "accept craft once")
	check(not quest.record("craft", "tool") and quest.index == 1, "ignore repeated craft")

	var saved := quest.snapshot()
	for bad_seed in [-1, 2147483648]:
		check(not quest.configure(bad_seed) and quest.snapshot() == saved, "invalid setup preserves state")
	var resumed := Quests.new()
	check(resumed.configure(237) and resumed.title == quest.title, "same seed recreates title")
	check(resumed.restore(JSON.parse_string(JSON.stringify(saved))) and resumed.snapshot() == saved,
			"resume partial progress through JSON")
	check(resumed.current() == EXPECTED[1], "restored next event")
	for shape in [{}, {"seed": 237}, {"seed": 237, "index": 0, "extra": 0}]:
		check(not resumed.restore(shape) and resumed.snapshot() == saved, "invalid shape preserves state")
	for foreign_seed in [null, false, "237", 237.5, NAN, INF, 238, -1]:
		check(not resumed.restore({"seed": foreign_seed, "index": 0}) and resumed.snapshot() == saved,
				"invalid or foreign seed preserves state")
	for bad_cursor in [null, true, "1", -1, 5, 1.5, NAN, INF, -INF]:
		check(not resumed.restore({"seed": 237, "index": bad_cursor}) and resumed.snapshot() == saved,
				"invalid cursor preserves state")
	for i in range(1, EXPECTED.size()):
		var event: Dictionary = EXPECTED[i]
		check(not resumed.completed and resumed.current() == event, "ordered stage %d" % i)
		check(resumed.record(event.action, event.target) and resumed.index == i + 1, "accepted stage %d" % i)
		check(not resumed.record(event.action, event.target), "cannot repeat stage %d" % i)
	check(resumed.completed and resumed.current().is_empty(), "completed terminal state")
	check(quest.restore(resumed.snapshot()) and quest.completed, "restore completed quest")
	check(not quest.record("defeat", "drone"), "restoring a completed quest cannot trigger another payout")

	var first_title := quest.title
	check(quest.configure(238) and quest.title != first_title, "another seed selects another title")
	for event: Dictionary in EXPECTED:
		check(quest.current() == event and quest.record(event.action, event.target), "alternate seed is playable")
	check(quest.configure(2147483647) and quest.configure(0), "seed bounds inclusive")
	check(quest.configure(237) and not quest.completed and quest.title == first_title and quest.index == 0,
			"reconfigure resets progress and reproduces title")
	print("Quest assertions finished, failures=", failures)
	quit(int(failures != 0))
