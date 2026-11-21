extends SceneTree

const Inventory = preload("res://inventory.gd")

var failures := 0


func check(condition: bool, detail: String) -> void:
	if not condition:
		printerr("FAIL ", detail)
		failures += 1


func _initialize() -> void:
	var pack := Inventory.new()
	check(pack.snapshot() == {"version": "1", "capacity": 40, "items": {}}, "default empty pack")
	check(pack.configure(5), "configure small pack")
	check(pack.add("wood", 2) and pack.add("stone") and pack.add("fiber", 2), "fill to capacity")
	var full := pack.snapshot()
	check(not pack.add("wood") and pack.snapshot() == full, "refuse overflow")
	check(not pack.configure(0) and not pack.configure(-2) and pack.snapshot() == full, "invalid configuration preserves pack")
	check(not pack.add("ore") and pack.quantity("ore") == 0, "reject unknown item")
	for count in [-1, 0]:
		check(not pack.add("wood", count) and not pack.remove("wood", count), "reject nonpositive unit counts")
	check(not pack.remove("ore") and not pack.remove("wood", 3) and pack.snapshot() == full, "atomic removal")
	check(not pack.craft("ore") and pack.snapshot() == full, "unknown recipe preserves pack")
	check(pack.craft("tool"), "craft tool in full pack")
	check(pack.snapshot().items == {"tool": 1, "fiber": 2}, "tool costs exact ingredients")
	check(pack.craft("bandage") and pack.snapshot().items == {"tool": 1, "bandage": 1}, "craft bandage")
	check(pack.add("wood", 2), "stage wood without stone")
	var partial := pack.snapshot()
	check(not pack.craft("tool") and not pack.craft("bandage") and pack.snapshot() == partial, "missing ingredient preserves pack")
	check(pack.remove("wood") and pack.quantity("wood") == 1 and pack.remove("wood"), "remove partial and final units")
	check(not pack.snapshot().items.has("wood"), "zero units omitted")
	check(pack.configure() and pack.snapshot().capacity == 40 and pack.snapshot().items.is_empty(), "fresh configuration")

	var restored := Inventory.new()
	var checkpoint: Dictionary = JSON.parse_string(JSON.stringify(partial))
	check(restored.restore(checkpoint) and restored.snapshot() == partial, "JSON restore includes capacity and contents")
	checkpoint.items.wood = 999
	restored.snapshot().items.wood = 999
	check(restored.snapshot() == partial, "snapshot and restore own their data")
	var invalid_states := [{}, {"capacity": 5, "items": {}}, {"version": "2", "capacity": 5, "items": {}},
			{"version": "1", "capacity": 5, "items": {}, "extra": 1}, {"version": "1", "capacity": 5, "items": []}]
	for invalid in invalid_states:
		check(not restored.restore(invalid) and restored.snapshot() == partial, "invalid checkpoint schema")
	for invalid in [0, -1, 2.5, true, INF, NAN, 9223372036854775808.0, "3"]:
		check(not restored.restore({"version": "1", "capacity": invalid, "items": {}}) and restored.snapshot() == partial, "invalid saved capacity")
		check(not restored.restore({"version": "1", "capacity": 5, "items": {"wood": invalid}}) and restored.snapshot() == partial, "invalid saved count")
	for invalid in [{"ore": 1}, {1: 1}, {"wood": 3, "stone": 3}]:
		check(not restored.restore({"version": "1", "capacity": 5, "items": invalid}) and restored.snapshot() == partial, "invalid saved contents")
	var max_count := 9223372036854775807
	check(pack.configure(max_count) and pack.add("wood", max_count), "native integer maximum")
	check(not pack.add("stone") and not pack.add("wood", max_count), "no arithmetic overflow on addition")
	check(not restored.restore({"version": "1", "capacity": max_count, "items": {"wood": max_count, "stone": 1}}) and restored.snapshot() == partial, "no arithmetic overflow on restore")
	print("Inventory assertions finished, failures=", failures)
	quit(int(failures != 0))
