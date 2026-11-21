extends RefCounted
## A district's 100 influence points are shared by the three factions.
## Each simulation tick has its own random stream so checkpoints resume exactly.

const FACTIONS := ["settlers", "rangers", "traders"]
const DISTRICTS := ["crossing", "ridge", "outpost"]
const HOME := {"settlers": "crossing", "rangers": "ridge", "traders": "outpost"}
const REPUTATION := {"greet": 2, "trade": 4, "aid": 7, "hostile": -12}
const WORLD_EVENTS := ["trade_route", "border_dispute", "joint_patrol"]
const TICK_SECONDS := 8.0
const MAX_STEPS := 16
const HISTORY_LIMIT := 24
const MAX_TICK := 1_000_000_000
const SNAP_KEYS := ["version", "seed", "tick", "elapsed", "pending_ticks", "standings", "relations", "influence", "event_log"]
const EVENT_KEYS := ["kind", "actor", "partner", "territory", "tick"]

var _seed := 0
var _tick := 0
var _elapsed := 0.0
var _pending_ticks := 0
var _standings := {}
var _relations := {}
var _influence := {}
var _events: Array = []


func configure(seed: int) -> bool:
	_seed = seed
	_tick = 0
	_elapsed = 0.0
	_pending_ticks = 0
	_events = []
	_standings = {}
	_relations = {}
	_influence = {}
	var rng := _tick_rng()
	for faction: String in FACTIONS:
		_standings[faction] = 0
		_relations[faction] = {faction: 100}
	for a in FACTIONS.size():
		for b in range(a + 1, FACTIONS.size()):
			var baseline := 8
			if a == 0 and b == 1:
				baseline = 27
			elif a == 1 and b == 2:
				baseline = -27
			_set_relation(FACTIONS[a], FACTIONS[b], baseline + rng.randi_range(-5, 5))
		var home_share := rng.randi_range(43, 52)
		var neighbor_share := rng.randi_range(22, 28)
		var shares := {}
		shares[FACTIONS[a]] = home_share
		shares[FACTIONS[(a + 1) % FACTIONS.size()]] = neighbor_share
		shares[FACTIONS[(a + 2) % FACTIONS.size()]] = 100 - home_share - neighbor_share
		_influence[HOME[FACTIONS[a]]] = shares
	return true


func _tick_rng() -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = ("%d/diplomacy/%d" % [_seed, _tick]).hash()
	return rng


func _set_relation(a: String, b: String, score: int) -> void:
	_relations[a][b] = clampi(score, -100, 100)
	_relations[b][a] = _relations[a][b]


func _owner(district: String) -> String:
	var shares: Dictionary = _influence[district]
	var winner: String = FACTIONS[0]
	for faction: String in FACTIONS:
		# Stable faction order breaks ties, even after JSON key sorting.
		if shares[faction] > shares[winner]:
			winner = faction
	return winner


func _transfer(district: String, from: String, to: String, amount: int) -> void:
	var shares: Dictionary = _influence[district]
	var moved := mini(amount, int(shares[from]))
	shares[from] -= moved
	shares[to] += moved


func _log(kind: String, actor: String, partner: String, district: String) -> void:
	_events.append({"kind": kind, "actor": actor, "partner": partner, "territory": district, "tick": _tick})
	if _events.size() > HISTORY_LIMIT:
		_events.pop_front()


func _simulate_tick() -> void:
	_tick += 1
	var rng := _tick_rng()
	var district: String = DISTRICTS[rng.randi_range(0, DISTRICTS.size() - 1)]
	var holder := _owner(district)
	var visitor: String = FACTIONS[(FACTIONS.find(holder) + rng.randi_range(1, FACTIONS.size() - 1)) % FACTIONS.size()]
	var affinity: int = _relations[holder][visitor]
	var outcome := rng.randi_range(0, 99)
	# Friends are more likely to trade or patrol together. Rivals dispute borders.
	var dispute_chance := clampi(roundi(42.0 - affinity * 0.4), 8, 84)
	var event := "trade_route"
	var shift := 4
	var pressure := 3
	if outcome < dispute_chance:
		event = "border_dispute"
		shift = -7
		pressure = rng.randi_range(6, 10)
	elif outcome >= 86:
		event = "joint_patrol"
		shift = 6
		pressure = 2
	_set_relation(holder, visitor, affinity + shift)
	_transfer(district, holder, visitor, pressure)
	_log(event, visitor, holder, district)


## Retain deferred ticks after a hitch. A zero-delta step can drain that debt.
func step(delta: float) -> void:
	if _standings.is_empty() or not is_finite(delta) or delta < 0.0:
		return
	# Limit the lifetime clock before converting a very large float to integer.
	var room := MAX_TICK - _tick - _pending_ticks
	var total := minf(_elapsed + delta, room * TICK_SECONDS)
	var due := floori((total + 0.0000000001) / TICK_SECONDS)
	_elapsed = maxf(0.0, total - due * TICK_SECONDS)
	_pending_ticks += due
	var count := mini(_pending_ticks, MAX_STEPS)
	for i in count:
		_simulate_tick()
	_pending_ticks -= count


func record(action: String, faction: String) -> bool:
	if not _standings.has(faction):
		return false
	if action == "greeting":
		action = "greet"
	elif action == "hostile_encounter":
		action = "hostile"
	if not REPUTATION.has(action):
		return false
	var change: int = REPUTATION[action]
	_standings[faction] = clampi(_standings[faction] + change, -100, 100)
	for other: String in FACTIONS:
		if other == faction:
			continue
		# Close allies and rivals notice how the player treats this faction.
		var affinity: int = _relations[faction][other]
		if absi(affinity) >= 20:
			var ripple := signi(affinity) * signi(change)
			_standings[other] = clampi(_standings[other] + ripple, -100, 100)
	var district: String = HOME[faction]
	var competitor: String = ""
	for other: String in FACTIONS:
		if other != faction and (competitor == "" or _influence[district][other] > _influence[district][competitor]):
			competitor = other
	match action:
		"trade", "aid":
			_transfer(district, competitor, faction, 2)
		"hostile":
			_transfer(district, faction, competitor, 4)
	_log(action, "player", faction, district)
	return true


func snapshot() -> Dictionary:
	if _standings.is_empty():
		return {}
	# Keep all signed 64-bit seeds intact through JSON numeric decoding.
	return {
		"version": "1", "seed": str(_seed), "tick": _tick, "elapsed": _elapsed,
		"pending_ticks": _pending_ticks, "standings": _standings.duplicate(),
		"relations": _relations.duplicate(true), "influence": _influence.duplicate(true),
		"event_log": _events.duplicate(true),
	}


func status() -> Dictionary:
	var state := snapshot()
	if not state.is_empty():
		state.seed = _seed
		state.factions = FACTIONS.duplicate()
		state.territories = {}
		for district: String in DISTRICTS:
			state.territories[district] = _owner(district)
		state.last_event = {} if _events.is_empty() else _events.back().duplicate()
	return state


func _whole(value: Variant, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and value >= low and value <= high and value == floor(value)


func _score_row(row: Variant, minimum: int) -> Dictionary:
	if not row is Dictionary or row.size() != FACTIONS.size() or not row.has_all(FACTIONS):
		return {}
	var result := {}
	for faction: String in FACTIONS:
		if not _whole(row[faction], minimum, 100):
			return {}
		result[faction] = int(row[faction])
	return result


func _valid_event(event: Variant, earliest: int, latest: int) -> bool:
	if not event is Dictionary or event.size() != EVENT_KEYS.size() or not event.has_all(EVENT_KEYS):
		return false
	for key in ["kind", "actor", "partner", "territory"]:
		if not event[key] is String:
			return false
	if not _whole(event.tick, earliest, latest) or event.partner not in FACTIONS or event.territory not in DISTRICTS:
		return false
	if event.actor == "player":
		return REPUTATION.has(event.kind) and event.territory == HOME[event.partner]
	return event.tick > 0 and event.kind in WORLD_EVENTS and event.actor in FACTIONS and event.actor != event.partner


func restore(state: Dictionary) -> bool:
	if _standings.is_empty() or state.size() != SNAP_KEYS.size() or not state.has_all(SNAP_KEYS):
		return false
	if not state.version is String or not state.seed is String or state.version != "1" or state.seed != str(_seed):
		return false
	if not _whole(state.tick, 0, MAX_TICK):
		return false
	if not _whole(state.pending_ticks, 0, MAX_TICK - int(state.tick)):
		return false
	if not (state.elapsed is float or state.elapsed is int) or not is_finite(float(state.elapsed)) or state.elapsed < 0.0 or state.elapsed >= TICK_SECONDS:
		return false
	if int(state.tick) + int(state.pending_ticks) == MAX_TICK and state.elapsed != 0.0:
		return false
	var standings := _score_row(state.standings, -100)
	if standings.is_empty() or not state.relations is Dictionary or state.relations.size() != FACTIONS.size():
		return false
	var relations := {}
	for faction: String in FACTIONS:
		var row := _score_row(state.relations.get(faction), -100)
		if row.is_empty() or row[faction] != 100:
			return false
		relations[faction] = row
	for faction: String in FACTIONS:
		for other: String in FACTIONS:
			if relations[faction][other] != relations[other][faction]:
				return false
	if not state.influence is Dictionary or state.influence.size() != DISTRICTS.size():
		return false
	var influence := {}
	for district: String in DISTRICTS:
		var shares := _score_row(state.influence.get(district), 0)
		if shares.is_empty() or shares.values().reduce(func(a, b): return a + b, 0) != 100:
			return false
		influence[district] = shares
	if not state.event_log is Array or state.event_log.size() > HISTORY_LIMIT or (state.tick > 0 and state.event_log.is_empty()):
		return false
	var events: Array = []
	var previous_tick := 0
	for entry in state.event_log:
		if not _valid_event(entry, previous_tick, int(state.tick)):
			return false
		# A truncated log may start mid-tick. Every later tick starts with
		# exactly one world event, followed by any number of player actions.
		if not events.is_empty() or state.event_log.size() < HISTORY_LIMIT:
			var expected := previous_tick if entry.actor == "player" else previous_tick + 1
			if entry.tick != expected:
				return false
		previous_tick = int(entry.tick)
		var event: Dictionary = entry.duplicate()
		event.tick = previous_tick
		events.append(event)
	if not events.is_empty() and previous_tick != int(state.tick):
		return false
	# All cross-field invariants hold before any live state is replaced.
	_tick = int(state.tick)
	_elapsed = float(state.elapsed)
	_pending_ticks = int(state.pending_ticks)
	_standings = standings
	_relations = relations
	_influence = influence
	_events = events
	return true
