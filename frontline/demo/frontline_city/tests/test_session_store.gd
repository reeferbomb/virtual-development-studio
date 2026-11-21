extends SceneTree

const Store := preload("res://session_store.gd")
const WORLD := "connected-city/岩-23"
var failures := 0
var store := Store.new()


func _initialize() -> void:
	_run.call_deferred()


func _check(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL session store: ", label)


func _put(path: String, value: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	_check(file != null, "open test fixture")
	if file != null:
		_check(file.store_string(value), "write test fixture")
		file.close()


func _run() -> void:
	var base := DirAccess.open("user://")
	var name := "session-store-test-" + Crypto.new().generate_random_bytes(16).hex_encode()
	if base == null or base.make_dir(name) != OK:
		printerr("FAIL session store: could not create private directory")
		quit(1)
		return
	var folder := "user://".path_join(name)
	var dir := DirAccess.open(folder)
	var path := folder.path_join("progress.json")
	var backup := path + Store.BACKUP_SUFFIX
	var zero := {"version": 1, "revision": 0, "claimed": [false, false, false]}
	var one := {"version": 1, "revision": 1, "claimed": [false, true, false]}
	var two := {"version": 1, "revision": 2, "claimed": [true, true, false]}
	var fork := {"version": 1, "revision": 1, "claimed": [true, false, false]}

	_check(store.load(path, WORLD).is_empty(), "missing file")
	_check(store.save(path, WORLD, zero), "create initial checkpoint")
	_check(Store.new().load(path, WORLD) == zero, "fresh reader round trip")
	_check(not store.save(path, "other world", one) and store.load(path, "other world").is_empty(),
			"world identity bound on read and write")
	_check(store.save(path, WORLD, one) and store.load(path, WORLD) == one, "new revision commits")
	var original := FileAccess.get_file_as_string(path)
	var previous := FileAccess.get_file_as_string(backup)
	_check(not original.is_empty() and not previous.is_empty(), "two rotations materialized")
	_check(store.save(path, WORLD, one), "repeat latest revision is idempotent")
	_check(not store.save(path, WORLD, zero) and not store.save(path, WORLD, fork), "stale revision or fork rejected")
	_check(not store.save(path, WORLD, {"version": 1, "revision": 2, "claimed": [true, false, true]}),
			"higher revision cannot erase a claim")
	for bad in [{}, {"version": 1.0, "revision": 1, "claimed": [true]},
			{"version": 1, "revision": 1.0, "claimed": [true]},
			{"version": 2, "revision": 2, "claimed": [true, true, false]},
			{"version": 1, "revision": 1, "claimed": [1]}, {"version": 1, "revision": 0, "claimed": true},
			{"version": 1, "revision": 0, "claimed": [], "extra": true},
			{"version": 1, "revision": 2, "claimed": [false, true, false]},
			{"version": 1, "revision": 17, "claimed": Array(range(17)).map(func(_i): return true)},
			{"version": 1, "revision": 2, "claimed": [true, true]}]:
		_check(not store.save(path, WORLD, bad), "reject malformed or incompatible state")
	_check(FileAccess.get_file_as_string(path) == original and FileAccess.get_file_as_string(backup) == previous,
			"rejected and identical saves preserve both copies")
	_check(not store.save(path, "", two) and not store.save(path, "岩".repeat(100), two),
			"reject blank or oversized world identity")

	# Change only inner data while keeping the original checksum.
	var envelope: Dictionary = JSON.parse_string(original)
	envelope.payload = envelope.payload.replace(WORLD, "corrupted")
	_put(path, JSON.stringify(envelope))
	_check(store.load(path, WORLD) == zero, "checksum mismatch falls back to previous revision")
	_check(store.save(path, WORLD, two) and store.load(path, WORLD) == two, "replace a corrupt primary")
	_check(FileAccess.get_file_as_string(backup) == previous, "repair protects last valid backup")
	var good := FileAccess.get_file_as_string(path)
	# A verified checksum alone cannot make an unknown version or malformed state valid.
	envelope = JSON.parse_string(good)
	var body: String = envelope.payload
	for invalid in [body.replace('"format":1', '"format":2'), body.replace('"revision":2', '"revision":0'),
			body.replace('"revision":2', '"revision":2.0'), body.replace('"version":1', '"version":2,"version":1')]:
		_check(invalid != body, "corruption fixture changed")
		_put(path, JSON.stringify({"payload": invalid, "sha256": invalid.sha256_text()}))
		_check(store.load(path, WORLD) == zero, "reject noncanonical or invalid signed state")
	_put(path, "x".repeat(Store.MAX_FILE_BYTES + 1))
	_check(store.load(path, WORLD) == zero, "oversized primary ignored")
	_check(dir.remove("progress.json") == OK, "simulate loss of primary")
	_check(store.load(path, WORLD) == zero and store.save(path, WORLD, zero), "restore from backup alone")
	_check(FileAccess.file_exists(path) and store.load(path, WORLD) == zero, "idempotent save repairs primary")

	# Force a genuine filesystem failure after staging, independently of OS permissions.
	_check(dir.remove("progress.json.bak") == OK and dir.make_dir("progress.json.bak") == OK, "block backup rename")
	_check(not store.save(path, WORLD, one), "failed backup publication aborts new primary")
	_check(store.load(path, WORLD) == zero and FileAccess.get_file_as_string(path) == previous,
			"last committed bytes survive failed rotation")
	dir.include_hidden = true
	_check(dir.get_files() == PackedStringArray(["progress.json"]), "failed save cleans its staged files")
	_check(dir.remove("progress.json.bak") == OK and store.save(path, WORLD, one), "retry after failure")
	_check(not store.save(folder.path_join("missing/world"), WORLD, zero), "missing parent fails")
	_check(not store.save(folder, WORLD, zero), "directory destination fails")
	_check(store.save(path, WORLD, two), "rotate a nonzero revision to the backup")
	_put(path, "broken primary")
	_check(not store.save(path, WORLD, zero) and store.load(path, WORLD) == one,
			"backup alone guards against a stale write")
	_put(backup, "broken backup")
	_check(store.load(path, WORLD).is_empty(), "both copies corrupt")
	var complete: Array[bool] = []
	complete.resize(Store.MAX_OBJECTIVES)
	complete.fill(true)
	var full := {"version": 1, "revision": Store.MAX_OBJECTIVES, "claimed": complete}
	_check(store.save(path, WORLD, full) and store.load(path, WORLD) == full, "maximum objectives round trip")
	_check(dir.remove("progress.json") == OK and dir.remove("progress.json.bak") == OK and base.remove(name) == OK,
			"remove private test fixtures")
	if failures == 0:
		print("PASS session store ", JSON.stringify({"round_trip": true, "backup_recovery": true,
				"stale_refused": true, "failed_write_preserved": true, "world_bound": true}))
	quit(0 if failures == 0 else 1)
