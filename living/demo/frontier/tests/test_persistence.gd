extends SceneTree

const Persistence := preload("res://persistence.gd")

var failures := 0
var store := Persistence.new()

func _initialize() -> void:
	call_deferred("run")

func check(passed: bool, label: String) -> void:
	if not passed:
		failures += 1
		printerr("FAIL ", label)

func put_text(path: String, content: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	check(file != null, "open fixture")
	if file != null:
		check(file.store_string(content), "write fixture")
		file.close()

# Godot JSON decodes integer tokens as floats. Dictionary equality is type-sensitive.
func json_values(payload: Dictionary) -> Dictionary:
	return JSON.parse_string(JSON.stringify(payload, "", true, true))

func run() -> void:
	var name := "checkpoint-test-" + Crypto.new().generate_random_bytes(16).hex_encode()
	var base := DirAccess.open("user://")
	if base == null or base.make_dir(name) != OK:
		printerr("FAIL could not reserve private test directory")
		quit(1)
		return
	var folder := "user://".path_join(name)
	var path := folder.path_join("world.json")
	var first := {
		"seed": 477, "position": [12.125, -1.5, 40.0],
		"inventory": {"ore": 4}, "factions": {"Wardens": 1},
		"harvested": {"sector_1:2/岩": true},
	}
	check(store.read_checkpoint(path).is_empty(), "missing checkpoint")
	check(store.write_checkpoint(path, first), "first checkpoint")
	check(Persistence.new().read_checkpoint(path) == json_values(first), "fresh reader JSON round trip")
	var second := first.duplicate(true)
	second.inventory.ore = 9
	second.position = [0.125, 4.5, -2.25]
	check(store.write_checkpoint(path, second), "replace checkpoint")
	check(store.read_checkpoint(path) == json_values(second), "replacement is visible in full")
	var saved := FileAccess.get_file_as_string(path)
	var directory := DirAccess.open(folder)
	check(directory.get_files() == PackedStringArray(["world.json"]), "no staging file left behind")

	for invalid in [{}, {"invalid": Vector3.ONE}, {"invalid": NAN}, {17: "bad key"},
			{"invalid": 9007199254740993}, {"oversize": "x".repeat(Persistence.MAX_FILE_BYTES)}]:
		check(not store.write_checkpoint(path, invalid), "invalid overwrite rejected")
		check(FileAccess.get_file_as_string(path) == saved, "failed overwrite leaves original bytes")

	var parser := JSON.new()
	if parser.parse(saved) != OK or not parser.data is Dictionary:
		printerr("FAIL expected a JSON envelope")
		failures += 1
	else:
		var original: Dictionary = parser.data
		var corrupt := original.duplicate()
		corrupt.payload = JSON.stringify(first)
		put_text(path, JSON.stringify(corrupt))
		check(store.read_checkpoint(path).is_empty(), "old checksum rejects changed payload")
		corrupt = original.duplicate()
		corrupt.version = Persistence.FORMAT_VERSION + 1
		put_text(path, JSON.stringify(corrupt))
		check(store.read_checkpoint(path).is_empty(), "unsupported version")
		corrupt = original.duplicate()
		corrupt.erase("sha256")
		put_text(path, JSON.stringify(corrupt))
		check(store.read_checkpoint(path).is_empty(), "missing checksum")
		for wrong_body in ["[]", "{", "{}"]:
			corrupt = original.duplicate()
			corrupt.payload = wrong_body
			corrupt.sha256 = wrong_body.sha256_text()
			put_text(path, JSON.stringify(corrupt))
			check(store.read_checkpoint(path).is_empty(), "wrong inner payload schema or syntax")

	for corrupt_text in [saved.left(saved.length() / 2), "", "garbage", "[]", "{}",
			"x".repeat(Persistence.MAX_FILE_BYTES + 1)]:
		put_text(path, corrupt_text)
		check(store.read_checkpoint(path).is_empty(), "truncated, malformed or oversized input")
	check(store.write_checkpoint(path, first) and store.read_checkpoint(path) == json_values(first),
			"valid write replaces corrupted checkpoint")
	check(not store.write_checkpoint(folder, first), "directory target rejected")
	check(directory.remove("world.json") == OK and base.remove(name) == OK, "clean up private fixtures")
	if failures == 0:
		print("PASS persistence: disk round trip, replacement, checksum, format version, size and failure isolation")
	quit(int(failures > 0))
