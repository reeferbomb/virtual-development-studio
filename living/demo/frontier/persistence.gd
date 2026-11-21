extends RefCounted

const FORMAT_VERSION := 1
const MAX_FILE_BYTES := 1024 * 1024
const MAX_DEPTH := 32
const MAX_SAFE_INTEGER := 9007199254740991

## The caller owns the destination and validates the world's gameplay rules.
## The destination's parent directory must already exist.
func write_checkpoint(path: String, payload: Dictionary) -> bool:
	if path.is_empty() or path.get_file() in ["", ".", ".."] or payload.is_empty():
		return false
	if not _fits_json(payload, 0, [MAX_FILE_BYTES]):
		return false
	# Hash the exact inner JSON text. Parsing and reformatting it could alter numbers.
	var body := JSON.stringify(payload, "", true, true)
	var envelope := JSON.stringify({
		"version": FORMAT_VERSION,
		"payload": body,
		"sha256": body.sha256_text(),
	}).to_utf8_buffer()
	if envelope.size() > MAX_FILE_BYTES:
		return false
	var destination := ProjectSettings.globalize_path(path)
	var directory := DirAccess.open(destination.get_base_dir())
	if directory == null or directory.dir_exists(destination.get_file()):
		return false
	var nonce := Crypto.new().generate_random_bytes(16)
	if nonce.size() != 16:
		return false
	var temp_name := ".checkpoint-" + nonce.hex_encode() + ".tmp"
	if directory.file_exists(temp_name) or directory.dir_exists(temp_name):
		return false
	var temp_path := destination.get_base_dir().path_join(temp_name)
	var file := FileAccess.open(temp_path, FileAccess.WRITE)
	if file == null:
		return false
	var stored := file.store_buffer(envelope)
	file.flush()
	var complete := stored and file.get_position() == envelope.size() and file.get_error() == OK
	file.close()
	if complete and _read_bytes(temp_path) == envelope:
		# A single same-directory rename commits the write. Never remove the old save first.
		if directory.rename(temp_name, destination.get_file()) == OK:
			return true
	directory.remove(temp_name)
	return false

## An empty dictionary indicates a missing, invalid or unsupported checkpoint.
func read_checkpoint(path: String) -> Dictionary:
	var bytes := _read_bytes(path)
	if bytes.is_empty():
		return {}
	var text := bytes.get_string_from_utf8()
	if text.to_utf8_buffer() != bytes:
		return {}
	var parser := JSON.new()
	if parser.parse(text) != OK or not parser.data is Dictionary:
		return {}
	var envelope: Dictionary = parser.data
	if envelope.size() != 3 or not envelope.has_all(["version", "payload", "sha256"]):
		return {}
	if not (envelope.version is float or envelope.version is int) or envelope.version != FORMAT_VERSION:
		return {}
	if not envelope.payload is String or not envelope.sha256 is String:
		return {}
	var body: String = envelope.payload
	if body.sha256_text() != envelope.sha256 or parser.parse(body) != OK:
		return {}
	if not parser.data is Dictionary or parser.data.is_empty():
		return {}
	return parser.data if _fits_json(parser.data, 0, [MAX_FILE_BYTES]) else {}

func _read_bytes(path: String) -> PackedByteArray:
	if path.is_empty() or not FileAccess.file_exists(path):
		return PackedByteArray()
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return PackedByteArray()
	var length := file.get_length()
	if length <= 0 or length > MAX_FILE_BYTES:
		return PackedByteArray()
	var bytes := file.get_buffer(length)
	return bytes if bytes.size() == length else PackedByteArray()

# Bound traversal before serialization, including cyclic or heavily shared input.
# The byte check on the actual envelope also accounts for Unicode and JSON escaping.
func _fits_json(value: Variant, depth: int, budget: Array) -> bool:
	budget[0] -= 1
	if depth > MAX_DEPTH or budget[0] < 0:
		return false
	match typeof(value):
		TYPE_NIL, TYPE_BOOL:
			return true
		TYPE_INT:
			return value >= -MAX_SAFE_INTEGER and value <= MAX_SAFE_INTEGER
		TYPE_FLOAT:
			return is_finite(value)
		TYPE_STRING:
			budget[0] -= value.length()
			return budget[0] >= 0
		TYPE_ARRAY:
			for item in value:
				if not _fits_json(item, depth + 1, budget):
					return false
		TYPE_DICTIONARY:
			for key in value:
				if not key is String or not _fits_json(key, depth + 1, budget):
					return false
				if not _fits_json(value[key], depth + 1, budget):
					return false
		_:
			return false
	return true
