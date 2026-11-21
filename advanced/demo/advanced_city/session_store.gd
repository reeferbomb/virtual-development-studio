extends RefCounted

const FORMAT_VERSION := 1
const MAX_OBJECTIVES := 16
const MAX_WORLD_ID_BYTES := 256
const MAX_FILE_BYTES := 4096
const BACKUP_SUFFIX := ".bak"

# A checkpoint belongs to one authority process. Serialize saves from all of
# that process's threads/instances so their revision checks and rotations agree.
static var _save_lock := Mutex.new()


## The directory must already exist. Repeating a committed save is idempotent.
func save(path: String, world_id: String, state: Dictionary) -> bool:
	if not _valid_path(path) or not _valid_world_id(world_id):
		return false
	var clean := _clean_state(state, false)
	if clean.is_empty():
		return false
	_save_lock.lock()
	var saved := _save_locked(ProjectSettings.globalize_path(path), world_id, clean)
	_save_lock.unlock()
	return saved


## Returns a detached state with native integer fields, or {} if neither copy is usable.
func load(path: String, world_id: String) -> Dictionary:
	if not _valid_path(path) or not _valid_world_id(world_id):
		return {}
	var primary := _read_record(path)
	var backup := _read_record(path + BACKUP_SUFFIX)
	var latest := _latest(primary, backup)
	return latest.state if latest.get("world_id", "") == world_id else {}


func _save_locked(path: String, world_id: String, state: Dictionary) -> bool:
	var directory := DirAccess.open(path.get_base_dir())
	var name := path.get_file()
	if directory == null or directory.dir_exists(name):
		return false
	var primary := _read_record(path)
	var backup := _read_record(path + BACKUP_SUFFIX)
	var latest := _latest(primary, backup)
	if not latest.is_empty():
		if latest.world_id != world_id or not _continues(latest.state, state):
			return false
		if latest == primary and latest.state == state:
			return true

	var encoded := _encode(world_id, state)
	var staged := _stage(directory, encoded)
	if staged.is_empty():
		return false

	# Keep the current good primary in the backup before publishing its successor.
	# If only the backup is valid (including after an interrupted repair), leave it
	# in place. Every rename has its source and destination in the same directory.
	if not primary.is_empty() and latest == primary and backup != primary:
		var previous := _stage(directory, _encode(world_id, primary.state))
		if previous.is_empty() or directory.rename(previous, name + BACKUP_SUFFIX) != OK:
			if not previous.is_empty():
				directory.remove(previous)
			directory.remove(staged)
			return false
	if directory.rename(staged, name) == OK:
		return true
	directory.remove(staged)
	return false


func _latest(primary: Dictionary, backup: Dictionary) -> Dictionary:
	if primary.is_empty():
		return backup
	if backup.get("world_id", "") == primary.world_id and backup.state.revision > primary.state.revision:
		return backup
	return primary


func _continues(previous: Dictionary, next: Dictionary) -> bool:
	if next.claimed.size() != previous.claimed.size() or next.revision < previous.revision:
		return false
	for index in previous.claimed.size():
		if previous.claimed[index] and not next.claimed[index]:
			return false
	return true


func _encode(world_id: String, state: Dictionary) -> PackedByteArray:
	var body := JSON.stringify({"format": FORMAT_VERSION, "world_id": world_id, "state": state}, "", true)
	return JSON.stringify({"payload": body, "sha256": body.sha256_text()}, "", true).to_utf8_buffer()


func _stage(directory: DirAccess, contents: PackedByteArray) -> String:
	var nonce := Crypto.new().generate_random_bytes(16)
	if nonce.size() != 16 or contents.size() > MAX_FILE_BYTES:
		return ""
	var name := ".session-" + nonce.hex_encode() + ".tmp"
	if directory.file_exists(name) or directory.dir_exists(name):
		return ""
	var path := directory.get_current_dir().path_join(name)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return ""
	var written := file.store_buffer(contents)
	file.flush()
	var complete := written and file.get_position() == contents.size() and file.get_error() == OK
	file.close()
	if complete and _read_bytes(path) == contents:
		return name
	directory.remove(name)
	return ""


func _read_bytes(path: String) -> PackedByteArray:
	if not FileAccess.file_exists(path):
		return PackedByteArray()
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return PackedByteArray()
	var length := file.get_length()
	if length < 1 or length > MAX_FILE_BYTES:
		return PackedByteArray()
	var bytes := file.get_buffer(length)
	return bytes if bytes.size() == length else PackedByteArray()


func _read_record(path: String) -> Dictionary:
	var bytes := _read_bytes(path)
	if bytes.is_empty():
		return {}
	var parser := JSON.new()
	if parser.parse(bytes.get_string_from_utf8()) != OK or not parser.data is Dictionary:
		return {}
	var envelope: Dictionary = parser.data
	if envelope.size() != 2 or not envelope.has_all(["payload", "sha256"]):
		return {}
	if not envelope.payload is String or not envelope.sha256 is String:
		return {}
	var body: String = envelope.payload
	if body.sha256_text() != envelope.sha256 or parser.parse(body) != OK or not parser.data is Dictionary:
		return {}
	var record: Dictionary = parser.data
	if record.size() != 3 or not record.has_all(["format", "world_id", "state"]):
		return {}
	if not _is_integer(record.format, true) or record.format != FORMAT_VERSION or not record.state is Dictionary:
		return {}
	if not record.world_id is String or not _valid_world_id(record.world_id):
		return {}
	var clean := _clean_state(record.state, true)
	# Canonical re-encoding also rejects duplicate keys, loose JSON syntax,
	# non-integral number spellings, and invalid UTF-8 replaced by the decoder.
	if clean.is_empty() or _encode(record.world_id, clean) != bytes:
		return {}
	return {"world_id": record.world_id, "state": clean}


func _clean_state(state: Dictionary, from_json: bool) -> Dictionary:
	if state.size() != 3 or not state.has_all(["version", "revision", "claimed"]):
		return {}
	if not _is_integer(state.version, from_json) or state.version != 1:
		return {}
	if not _is_integer(state.revision, from_json) or state.revision < 0 or state.revision > MAX_OBJECTIVES:
		return {}
	if not state.claimed is Array or state.claimed.size() > MAX_OBJECTIVES:
		return {}
	var claimed: Array[bool] = []
	var total := 0
	for flag in state.claimed:
		if not flag is bool:
			return {}
		claimed.append(flag)
		if flag:
			total += 1
	if total != state.revision:
		return {}
	return {"version": 1, "revision": total, "claimed": claimed}


func _is_integer(value: Variant, from_json: bool) -> bool:
	# Godot decodes JSON numbers as floats. The canonical byte comparison further
	# requires integer tokens on disk.
	return value is int or (from_json and value is float and is_finite(value) and value == floor(value))


func _valid_world_id(world_id: String) -> bool:
	return not world_id.strip_edges().is_empty() and world_id.length() <= MAX_WORLD_ID_BYTES and world_id.to_utf8_buffer().size() <= MAX_WORLD_ID_BYTES


func _valid_path(path: String) -> bool:
	return not path.is_empty() and path.get_file() not in ["", ".", ".."]
