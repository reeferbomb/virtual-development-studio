extends SceneTree

const Factions := preload("res://factions.gd")

var failures := 0


func check(passed: bool, detail: String) -> void:
	if not passed:
		printerr("FAIL ", detail)
		failures += 1


func _initialize() -> void:
	var factions := Factions.new()
	var neutral := {"settlers": 0, "rangers": 0}
	check(factions.configure() and factions.snapshot() == neutral, "initial scores")
	for unknown in ["", "outlanders", "Rangers", "settlers "]:
		check(not factions.adjust(unknown, 25), "reject unknown faction " + unknown)
		check(factions.reputation(unknown) == 0 and factions.disposition(unknown) == "neutral", "unknown reads")
	check(factions.snapshot() == neutral, "unknown IDs leave roster intact")

	check(factions.adjust("settlers", 24) and factions.disposition("settlers") == "neutral", "below allied threshold")
	check(factions.adjust("settlers", 1) and factions.disposition("settlers") == "allied", "allied threshold")
	check(factions.adjust("rangers", -24) and factions.disposition("rangers") == "neutral", "above hostile threshold")
	check(factions.adjust("rangers", -1) and factions.disposition("rangers") == "hostile", "hostile threshold")
	check(factions.reputation("settlers") == 25 and factions.reputation("rangers") == -25, "independent scores")
	check(factions.adjust("settlers", 9223372036854775807) and factions.reputation("settlers") == 100, "positive saturation")
	check(factions.adjust("rangers", -9223372036854775807 - 1) and factions.reputation("rangers") == -100, "negative saturation")
	check(factions.adjust("settlers", -100) and factions.disposition("settlers") == "neutral", "leave allied standing")

	var saved := factions.snapshot()
	var resumed := Factions.new()
	check(resumed.restore(JSON.parse_string(JSON.stringify(saved))) and resumed.snapshot() == saved, "JSON restore")
	saved.rangers = 100
	check(factions.reputation("rangers") == -100, "snapshot owns its scores")
	check(resumed.restore(saved), "restore opposite standing")
	saved.rangers = 0
	check(resumed.reputation("rangers") == 100, "restore owns its scores")
	var before := resumed.snapshot()
	for bad_shape in [{}, {"settlers": 5}, {"settlers": 5, "ranger": 0}, {"settlers": 5, "rangers": 0, "other": 1}]:
		check(not resumed.restore(bad_shape) and resumed.snapshot() == before, "reject invalid roster atomically")
	for bad_value in [null, true, "2", [], 4.5, -101, 101, NAN, INF, -INF]:
		check(not resumed.restore({"settlers": 50, "rangers": bad_value}) and resumed.snapshot() == before,
				"reject invalid second score atomically")
	check(resumed.configure() and resumed.snapshot() == neutral, "reset both scores")
	print("Faction assertions finished, failures=", failures)
	quit(int(failures != 0))
