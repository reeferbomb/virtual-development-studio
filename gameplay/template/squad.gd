extends RefCounted

const ALERT_SECONDS := 5.0

var _members: Array[String] = []
var _last_seen := Vector3.ZERO
var _seconds_left := 0.0
var _pursuer := ""
var _flanker := ""

func configure(ids: Array) -> void:
	_members.clear()
	for value in ids:
		if value is String or value is StringName:
			var id := String(value)
			if not id.is_empty() and not _members.has(id):
				_members.append(id)
	_members.sort()
	_clear_alert()

func tick(delta: float) -> void:
	if _seconds_left <= 0.0 or delta <= 0.0 or not is_finite(delta):
		return
	_seconds_left = maxf(0.0, _seconds_left - delta)
	if is_zero_approx(_seconds_left):
		_clear_alert()

func report(id: String, target: Vector3) -> void:
	if not _members.has(id) or not target.is_finite():
		return
	# Keep the original observer in pursuit while the location is refreshed.
	if _seconds_left <= 0.0:
		_assign_roles(id)
	_last_seen = target
	_seconds_left = ALERT_SECONDS

func forget(id: String) -> void:
	if not _members.has(id):
		return
	_members.erase(id)
	if _members.is_empty():
		_clear_alert()
	elif id == _pursuer:
		_assign_roles(_members[0])
	elif id == _flanker:
		_assign_roles(_pursuer)

func intel(id: String) -> Dictionary:
	if _seconds_left <= 0.0 or not _members.has(id):
		return {"active": false, "target": Vector3.ZERO, "role": "support"}
	var role := "support"
	if id == _pursuer:
		role = "pursuer"
	elif id == _flanker:
		role = "flanker"
	return {"active": true, "target": _last_seen, "role": role}

func _assign_roles(observer: String) -> void:
	_pursuer = observer
	_flanker = ""
	for member in _members:
		if member != _pursuer:
			_flanker = member
			break

func _clear_alert() -> void:
	_last_seen = Vector3.ZERO
	_seconds_left = 0.0
	_pursuer = ""
	_flanker = ""
