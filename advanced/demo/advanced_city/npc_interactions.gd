extends RefCounted
## Street conversations and Ada's seed-saving errand use the live walkers' world positions.

const TALK_RADIUS := 3.0
const MAX_VISITS := 2_147_483_647
const NAMES := [
	"Ada", "Ben", "Camila", "Dev", "Esme", "Finn", "Grace", "Hana", "Ivo", "June",
	"Kai", "Lena", "Milo", "Nora", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tess",
	"Uma", "Vic", "Wren", "Xavi", "Yara", "Zeke", "Alma", "Bo", "Cleo", "Dara",
	"Eli", "Faye", "Gus", "Hope", "Iris", "Jules", "Kira", "Luis", "Mae", "Noel",
]

var _seed := -1
var _indices := {}
var _visits: Array[int] = []
var _recipient := -1
var _stage := "unavailable"


func configure(seed_value: int, civilian_count: int) -> bool:
	if seed_value < 0 or seed_value > 2_147_483_647 or civilian_count < 0 or civilian_count > NAMES.size():
		return false
	_seed = seed_value
	_indices.clear()
	_visits.resize(civilian_count)
	_visits.fill(0)
	for i in civilian_count:
		_indices[_id(i)] = i
	_recipient = 1 + (seed_value % (civilian_count - 1)) if civilian_count >= 2 else -1
	_stage = "available" if _recipient >= 0 else "unavailable"
	return true


func _id(index: int) -> String:
	return "civilian-%02d" % (index + 1) if index >= 0 else ""


func _target() -> int:
	match _stage:
		"available", "return":
			return 0
		"deliver":
			return _recipient
	return -1


func _objective() -> String:
	match _stage:
		"available":
			return "Speak to Ada about the seed exchange."
		"deliver":
			return "Take Ada's bean seeds to %s." % NAMES[_recipient]
		"return":
			return "Give Ada the planting note."
		"complete":
			return "Seed exchange complete."
	return "No seed exchange is scheduled."


func status() -> Dictionary:
	var total := 0
	for visits in _visits:
		total += visits
	var target := _target()
	return {
		"quest_stage": _stage, "giver_id": _id(0) if _recipient >= 0 else "",
		"recipient_id": _id(_recipient), "target_id": _id(target),
		"target_name": NAMES[target] if target >= 0 else "",
		"objective": _objective(), "conversations": total,
	}


func _numeric(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _nearby(position: Vector3, population: Dictionary) -> Dictionary:
	var rows: Variant = population.get("civilians")
	if not position.is_finite() or rows is not Array or rows.size() != _visits.size():
		return {}
	if not _numeric(population.get("count")) or population.count != _visits.size():
		return {}
	var seen := {}
	var nearest := {}
	var best := TALK_RADIUS * TALK_RADIUS
	for row in rows:
		if row is not Dictionary or row.get("id") is not String:
			return {}
		var id: String = row.id
		var coordinates: Variant = row.get("position")
		if not _indices.has(id) or seen.has(id) or coordinates is not Array or coordinates.size() != 3:
			return {}
		seen[id] = true
		for value in coordinates:
			if not _numeric(value):
				return {}
		var world := Vector3(coordinates[0], coordinates[1], coordinates[2])
		if not world.is_finite():
			return {}
		var distance := position.distance_squared_to(world)
		if distance < best or (distance == best and (nearest.is_empty() or id < nearest.id)):
			best = distance
			nearest = row
	return nearest


func interact(position: Vector3, civilian_status: Dictionary) -> Dictionary:
	var row := _nearby(position, civilian_status)
	if row.is_empty():
		return {"accepted": false, "message": "Move closer to a resident to talk.", "id": "", "quest_stage": _stage}
	var index: int = _indices[row.id]
	var visits := _visits[index]
	_visits[index] = mini(visits + 1, MAX_VISITS)
	var line := _dialogue(index, visits, str(row.get("activity", "")))
	return {"accepted": true, "message": "%s: %s" % [NAMES[index], line], "id": row.id, "quest_stage": _stage}


func _dialogue(index: int, previous_visits: int, activity: String) -> String:
	if index == 0 and _stage == "available":
		_stage = "deliver"
		return "These beans grew on my balcony. Will you take a packet to %s for the seed exchange?" % NAMES[_recipient]
	if index == _recipient and _stage == "deliver":
		_stage = "return"
		return "Ada's speckled beans! I saved her a planting note. Will you take it back to her?"
	if index == 0 and _stage == "return":
		_stage = "complete"
		return "‘Sow after the last frost.’ Just what I needed. Thank you! I'll keep you a pot on the balcony."
	if index == 0 and _stage == "deliver":
		return "%s is expecting the packet. Look for the name on your errand." % NAMES[_recipient]
	if index == _recipient and _stage == "return":
		return "Ada still needs the note. I drew a little trellis on the back."
	if _stage == "complete" and index == 0:
		return "I set aside the sunniest pot for the speckled beans."
	if _stage == "complete" and index == _recipient:
		return "A whole row of speckled beans from one little packet. That's the idea of an exchange."
	var line := _small_talk(activity, previous_visits)
	if _stage == "available":
		line += " Ada has a packet for the seed exchange."
	elif _stage == "deliver":
		line += " The seed packet goes to %s." % NAMES[_recipient]
	elif _stage == "return":
		line += " Ada will want to see the planting note."
	return line


func _small_talk(activity: String, previous_visits: int) -> String:
	if previous_visits % 2 == 1:
		return "Good to see you again. Have you spotted the balcony gardens?"
	match activity:
		"home", "to_home":
			return "I'm hoping the herbs outside my window survived the afternoon sun."
		"work", "to_work":
			return "The morning shift always starts with somebody putting the kettle on."
		"leisure", "to_leisure":
			return "It's a good day to take the long way round the block."
	return "Hello, neighbor. There's always someone to meet on this street."


func snapshot() -> Dictionary:
	if _seed < 0:
		return {}
	return {"version": 1, "seed": _seed, "count": _visits.size(), "quest_stage": _stage, "visits": _visits.duplicate()}


func valid_snapshot(state: Variant) -> bool:
	if _seed < 0 or state is not Dictionary or state.size() != 5:
		return false
	if not state.has_all(["version", "seed", "count", "quest_stage", "visits"]):
		return false
	for key in ["version", "seed", "count"]:
		if not _numeric(state[key]):
			return false
	if state.version != 1 or state.seed != _seed or state.count != _visits.size():
		return false
	if state.visits is not Array or state.visits.size() != _visits.size() or state.quest_stage is not String:
		return false
	for visits in state.visits:
		if not _numeric(visits) or visits < 0 or visits > MAX_VISITS or floorf(visits) != visits:
			return false
	if _recipient < 0:
		return state.quest_stage == "unavailable"
	var giver_visits: int = int(state.visits[0])
	var recipient_visits: int = int(state.visits[_recipient])
	match state.quest_stage:
		"available":
			return giver_visits == 0
		"deliver":
			return giver_visits >= 1
		"return":
			return giver_visits >= 1 and recipient_visits >= 1
		"complete":
			return giver_visits >= 2 and recipient_visits >= 1
	return false


func restore(state: Variant) -> bool:
	if not valid_snapshot(state):
		return false
	_stage = state.quest_stage
	for i in _visits.size():
		_visits[i] = int(state.visits[i])
	return true
