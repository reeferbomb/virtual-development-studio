extends RefCounted

var members: Dictionary = {}
var started := false
var _capacity := 16
var _minimum := 2
var _name_pattern := RegEx.create_from_string("\\A[A-Za-z0-9 _-]{1,24}\\z")

func configure(capacity: int = 16, min_players: int = 2) -> void:
	_capacity = maxi(1, capacity)
	_minimum = clampi(min_players, 1, _capacity)
	members.clear()
	started = false

func join(peer: int, display_name: String) -> bool:
	if started or peer <= 0 or members.has(peer) or members.size() >= _capacity:
		return false
	if _name_pattern.search(display_name) == null:
		return false
	var occupied := {}
	for member in members.values():
		occupied[member.slot] = true
	for slot in range(_capacity):
		if not occupied.has(slot):
			members[peer] = {"name": display_name, "ready": false, "slot": slot}
			return true
	return false

func leave(peer: int) -> bool:
	return members.erase(peer)

func set_ready(peer: int, value: bool) -> bool:
	if started or not members.has(peer):
		return false
	members[peer].ready = value
	return true

func start(requester: int) -> bool:
	if started or requester != 1 or not members.has(requester) or members.size() < _minimum:
		return false
	for member in members.values():
		if not member.ready:
			return false
	started = true
	return true

func snapshot() -> Dictionary:
	return {"members": members.duplicate(true), "started": started}
