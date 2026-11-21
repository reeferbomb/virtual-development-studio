extends SceneTree

var failures := 0

func check(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", label)

func _initialize() -> void:
	var path: String = "res://combat.gd"
	if not ResourceLoader.exists(path):
		printerr("FAIL missing combat module")
		quit(1)
		return
	var state = load(path).new()
	var initial: Dictionary = state.snapshot()
	check(initial == {"health": 100, "ammo": 6, "reserve": 18, "cooldown": 0.0}, "initial state")
	check(not state.reload(), "full magazine")
	check(state.fire() and state.ammo == 5 and state.cooldown == 0.25, "first shot")
	state.tick(-1.0)
	check(state.cooldown == 0.25 and not state.fire(), "invalid delta")
	state.tick(0.125)
	check(not state.fire() and state.ammo == 5, "cooldown")
	state.tick(0.125)
	for i in range(5):
		check(state.fire(), "fire after cooldown")
		state.tick(1.0)
	check(not state.fire() and state.ammo == 0, "empty")
	check(state.reload() and state.ammo == 6 and state.reserve == 12, "reload")
	check(state.restore({"health": 40, "ammo": 1, "reserve": 2, "cooldown": 0.0}), "restore")
	check(state.reload() and state.ammo == 3 and state.reserve == 0 and not state.reload(), "partial reload")
	check(not state.damage(-1) and not state.damage(0) and state.health == 40, "invalid damage")
	check(state.damage(15) and state.health == 25, "damage")
	check(state.damage(1000) and state.health == 0, "lethal damage")
	check(not state.damage(1) and not state.fire() and not state.reload(), "dead state")
	var dead: Dictionary = state.snapshot()
	for changes in [{"health": -1}, {"ammo": 7}, {"reserve": -1}, {"cooldown": NAN}, {"cooldown": INF}, {"cooldown": 0.3}, {"health": "20"}, {"ammo": true}, {"unknown": 1}]:
		var invalid := initial.merged(changes, true)
		check(not state.restore(invalid) and state.snapshot() == dead, "invalid snapshot " + str(changes))
	check(not state.restore({}) and state.snapshot() == dead, "missing fields")
	check(state.restore(initial) and state.snapshot() == initial, "snapshot round trip")
	check(state.restore(JSON.parse_string(JSON.stringify(initial))) and state.snapshot() == initial, "JSON checkpoint round trip")
	check(not state.restore(initial.merged({"ammo": 1.5}, true)), "fractional ammo rejected")
	if failures == 0:
		print("PASS combat state")
	quit(1 if failures else 0)
