extends RefCounted

# The relay can only be repaired by fetching two couplers and installing them at the far end.
# One engine RNG draw per tick determines battery drain. Positions are always whole cells.
enum Op { EAST, SALVAGE, INSTALL, HOLD }

const VERSION := 1
const START_SEED := 147_029
const MAX_TICKS := 32
const BATTERY_MAX := 28
const END_CELL := 4
const CELL_WIDTH := 16.0
const SAVE_TICK := 4
const SNAPSHOT_FIELDS := ["version", "seed", "rng_state", "tick", "cell", "battery", "couplers", "claimed", "online", "wind"]
const TAPE := [Op.EAST, Op.SALVAGE, Op.SALVAGE, Op.EAST, Op.EAST, Op.SALVAGE, Op.EAST, Op.INSTALL, Op.HOLD]


class RelayRun extends Node2D:
	var initial_seed: int
	var rng := RandomNumberGenerator.new()
	var tick := 0
	var battery := BATTERY_MAX
	var couplers := 0
	var claimed := 0
	var online := false
	var wind := 0

	func _init(seed_value: int) -> void:
		initial_seed = seed_value
		rng.seed = seed_value

	func cell() -> int:
		return roundi(position.x / CELL_WIDTH)

	func step(op: int) -> bool:
		if op < Op.EAST or op > Op.HOLD or tick >= MAX_TICKS or battery <= 0:
			return false
		tick += 1
		wind = rng.randi() % 3
		if op == Op.HOLD:
			battery = mini(battery + 1, BATTERY_MAX)
			return true
		battery = maxi(0, battery - 1 - wind)
		if battery == 0:
			return true
		match op:
			Op.EAST:
				position.x = float(mini(cell() + 1, END_CELL)) * CELL_WIDTH
			Op.SALVAGE:
				var bit := 1 if cell() == 1 else (2 if cell() == 3 else 0)
				if bit != 0 and (claimed & bit) == 0:
					claimed |= bit
					couplers += 1
			Op.INSTALL:
				if cell() == END_CELL and couplers == 2:
					couplers = 0
					online = true
		return true

	func snapshot() -> Dictionary:
		return {"version": VERSION, "seed": initial_seed, "rng_state": rng.state, "tick": tick, "cell": cell(),
			"battery": battery, "couplers": couplers, "claimed": claimed, "online": online, "wind": wind}

	func restore(candidate: Variant) -> bool:
		if typeof(candidate) != TYPE_DICTIONARY:
			return false
		var record: Dictionary = candidate
		if record.size() != SNAPSHOT_FIELDS.size():
			return false
		for key in SNAPSHOT_FIELDS:
			var value_type := TYPE_BOOL if key == "online" else TYPE_INT
			if not record.has(key) or typeof(record[key]) != value_type:
				return false
		if record.version != VERSION or record.seed != initial_seed or record.tick < 0 or record.tick > MAX_TICKS:
			return false
		if record.cell < 0 or record.cell > END_CELL or record.cell > record.tick \
				or record.battery < 1 or record.battery > BATTERY_MAX or record.claimed < 0 or record.claimed > 3:
			return false
		var recovered := int((record.claimed & 1) != 0) + int((record.claimed & 2) != 0)
		if (record.online and (record.cell != END_CELL or recovered != 2)) \
				or record.couplers != recovered - 2 * int(record.online):
			return false

		# Verify that the declared random state belongs to this seed and tick before committing anything.
		var oracle := RandomNumberGenerator.new()
		oracle.seed = initial_seed
		var last_wind := 0
		for index in range(record.tick):
			last_wind = oracle.randi() % 3
		if oracle.state != record.rng_state or last_wind != record.wind:
			return false

		position = Vector2(float(record.cell) * CELL_WIDTH, 0.0)
		tick = record.tick
		battery = record.battery
		couplers = record.couplers
		claimed = record.claimed
		online = record.online
		wind = record.wind
		rng.state = record.rng_state
		return true


func _create_run(parent: Node2D) -> RelayRun:
	var relay := RelayRun.new(START_SEED)
	parent.add_child(relay)
	return relay


func _play(relay: RelayRun, actions: Array) -> Array[Dictionary]:
	var observations: Array[Dictionary] = []
	if actions.is_empty() or actions.size() > MAX_TICKS - relay.tick:
		return observations
	for action in actions:
		if typeof(action) != TYPE_INT or action < Op.EAST or action > Op.HOLD:
			return observations
	for action in actions:
		if not relay.step(action):
			break
		observations.append(relay.snapshot())
	return observations


func _divergence(expected: Array, actual: Array) -> int:
	var common := mini(expected.size(), actual.size())
	for index in range(common):
		if expected[index] != actual[index]:
			return index + 1
	return common + 1 if expected.size() != actual.size() else 0


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var probe := Node2D.new()
	probe.name = "RelayReplayProbe"
	var original_children := tree.root.get_child_count()
	tree.root.add_child(probe)
	var relay := _create_run(probe)
	var prefix := _play(relay, TAPE.slice(0, SAVE_TICK))
	var checkpoint := relay.snapshot()
	var packet := var_to_bytes(checkpoint)
	var decoded: Variant = bytes_to_var(packet)
	var suffix := _play(relay, TAPE.slice(SAVE_TICK))
	var final := relay.snapshot()
	var reference := prefix + suffix

	var replayed := _play(_create_run(probe), TAPE)
	var complete := reference.size() == TAPE.size()
	var single_pickup: bool = prefix.size() == SAVE_TICK and prefix[1].couplers == 1 and prefix[2].couplers == 1
	var route_ok: bool = (complete and single_pickup and final.cell == END_CELL and final.claimed == 3
			and final.online and final.couplers == 0 and final.battery > 0)

	var resumed := _create_run(probe)
	var restored := resumed.restore(decoded)
	var restored_before := resumed.snapshot()
	var continuation := _play(resumed, TAPE.slice(SAVE_TICK)) if restored else []
	var save_matches: bool = restored and checkpoint.tick == SAVE_TICK and restored_before == checkpoint
	var checkpoint_ok: bool = (complete and save_matches and _divergence(suffix, continuation) == 0
			and resumed.snapshot() == final)

	var retry := _create_run(probe)
	_play(retry, TAPE.slice(0, SAVE_TICK))
	for index in range(MAX_TICKS):
		if not retry.step(Op.EAST):
			break
	var failed := retry.snapshot()
	var reset := retry.restore(decoded)
	var retry_start := retry.snapshot()
	var after_retry := _play(retry, TAPE.slice(SAVE_TICK)) if reset else []
	var retried: bool = (complete and failed.battery == 0 and failed.tick > checkpoint.tick and reset
			and retry_start == checkpoint and _divergence(suffix, after_retry) == 0 and retry.snapshot() == final)

	var invalid_version := checkpoint.duplicate()
	invalid_version.version += 1
	var invalid_rng := checkpoint.duplicate()
	invalid_rng.rng_state ^= 1
	var invalid_inventory := checkpoint.duplicate()
	invalid_inventory.couplers += 1
	var invalid_cell := checkpoint.duplicate()
	invalid_cell.cell = END_CELL + 1
	var invalid_rejected := true
	var before_rejection := retry.snapshot()
	for corrupted in [invalid_version, invalid_rng, invalid_inventory, invalid_cell, null]:
		var accepted := retry.restore(corrupted)
		invalid_rejected = invalid_rejected and not accepted and retry.snapshot() == before_rejection
	var overlong: Array = []
	overlong.resize(MAX_TICKS + 1)
	overlong.fill(Op.HOLD)
	var invalid_tape := _play(retry, [Op.HOLD, 99, Op.EAST]).is_empty() and _play(retry, overlong).is_empty()
	invalid_rejected = invalid_rejected and invalid_tape and retry.snapshot() == before_rejection

	var modified := TAPE.duplicate()
	modified[SAVE_TICK - 1] = Op.HOLD
	var changed := _play(_create_run(probe), modified)
	var divergence_tick := _divergence(reference, changed)
	var divergence_ok := (complete and changed.size() == TAPE.size() and divergence_tick == SAVE_TICK
			and _divergence(reference, reference.slice(0, reference.size() - 1)) == TAPE.size())

	probe.free()
	var cleaned := not is_instance_valid(probe) and tree.root.get_child_count() == original_children
	return {"id": "replay", "checks": [
		_check("recorded-route", route_ok, "Applied the opcode tape to a Node2D and installed both unique couplers."),
		_check("deterministic-replay", complete and _divergence(reference, replayed) == 0,
			"Compared every observed field, including engine RNG state, on a second seeded run."),
		_check("checkpoint-roundtrip", checkpoint_ok, "Marshalled the versioned checkpoint in memory and replayed its suffix."),
		_check("retry-reset", retried, "Exhausted the live battery, restored the checkpoint and matched every retried step."),
		_check("invalid-rejected", invalid_rejected, "Rejected corrupt checkpoint fields and invalid tapes before mutation."),
		_check("divergence-detected", divergence_ok, "Detected a changed legal opcode and a truncated observation trace."),
		_check("probe-cleanup", cleaned, "Freed the probe root and its gameplay nodes before returning."),
	], "metrics": {"seed": START_SEED, "actions": TAPE.size(), "checkpoint_tick": checkpoint.tick,
		"checkpoint_bytes": packet.size(), "divergence_tick": divergence_tick, "failed_tick": failed.tick,
		"restored_battery": retry_start.battery, "final_tick": final.tick, "final_cell": final.cell,
		"final_battery": final.battery}}
