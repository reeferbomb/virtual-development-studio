extends SceneTree

const Diplomacy := preload("res://diplomacy.gd")
const SEED := 9052126812324557
var failures := 0


func _initialize() -> void:
	var sim := Diplomacy.new()
	check(sim.snapshot().is_empty() and not sim.record("trade", "traders"), "unconfigured model")
	check(sim.configure(SEED), "configure")
	var initial := sim.snapshot()
	var original_relations: Dictionary = sim.status().relations
	check(sim.status().territories == {"crossing": "settlers", "ridge": "rangers", "outpost": "traders"}, "home districts")
	check(sim.record("greeting", "settlers"), "greeting")
	check(sim.status().standings.settlers == 2 and sim.status().standings.rangers == 1, "ally hears about greeting")
	check(sim.record("trade", "traders") and sim.status().standings.traders == 4, "merchant reputation")
	check(sim.record("hostile_encounter", "rangers") and sim.status().standings.rangers < 0, "hostile encounter")
	check(sim.snapshot().influence != initial.influence, "actions shift district influence")
	check(sim.status().last_event.kind == "hostile", "canonical event kind")
	var saved := sim.snapshot()
	check(not sim.record("trade", "unknown") and not sim.record("teleport", "settlers") and sim.snapshot() == saved, "no side effects for unknown inputs")
	sim.step(-1.0)
	sim.step(NAN)
	sim.step(INF)
	check(sim.snapshot() == saved, "invalid time has no effect")
	for i in 100:
		sim.record("hostile", "rangers")
	check(sim.status().standings.rangers == -100, "bounded hostility")
	for i in 100:
		sim.record("aid", "rangers")
	check(sim.status().standings.rangers == 100 and sim.status().event_log.size() == Diplomacy.HISTORY_LIMIT, "bounded reputation and event history")

	check(sim.configure(SEED) and sim.snapshot() == initial, "deterministic reset")
	var variant_seed := Diplomacy.new()
	variant_seed.configure(SEED + 1)
	check(variant_seed.status().influence != initial.influence or variant_seed.status().relations != initial.relations, "seed affects simulation")
	var partitioned := Diplomacy.new()
	partitioned.configure(SEED)
	sim.step(32.0)
	for i in 320:
		partitioned.step(0.1)
	check(sim.snapshot() == partitioned.snapshot(), "tick results independent of frame partition")
	check(sim.status().tick == 4 and sim.status().relations != original_relations, "autonomous diplomacy advances")
	var kinds := {}
	var changed_owner := false
	var first_owners := {"crossing": "settlers", "ridge": "rangers", "outpost": "traders"}
	for n in 220:
		sim.step(Diplomacy.TICK_SECONDS)
		var info := sim.status()
		kinds[info.last_event.kind] = true
		changed_owner = changed_owner or info.territories != first_owners
		for a in info.factions:
			for b in info.factions:
				check(info.relations[a][b] == info.relations[b][a] and absi(info.relations[a][b]) <= 100, "symmetric bounded diplomacy")
		for district in info.territories:
			var shares: Dictionary = info.influence[district]
			var total := 0
			for faction in info.factions:
				total += int(shares[faction])
				check(shares[faction] >= 0 and shares[info.territories[district]] >= shares[faction], "territorial majority")
			check(total == 100, "influence is conserved")
	check(kinds.size() == Diplomacy.WORLD_EVENTS.size() and changed_owner, "autonomy produces distinct events and district turnovers")

	sim.configure(SEED)
	partitioned.configure(SEED)
	var seconds := (Diplomacy.MAX_STEPS + 9) * Diplomacy.TICK_SECONDS + 1.25
	sim.step(seconds)
	check(sim.status().tick == Diplomacy.MAX_STEPS and sim.status().pending_ticks == 9, "large frame bounds work and preserves debt")
	var checkpoint := sim.snapshot()
	var resumed := Diplomacy.new()
	resumed.configure(SEED)
	var decoded: Dictionary = JSON.parse_string(JSON.stringify(checkpoint, "", true, true))
	check(resumed.restore(decoded) and resumed.snapshot() == checkpoint, "JSON accepted including exact 64-bit seed")
	check(not variant_seed.restore(decoded), "wrong world seed")
	sim.step(0.0)
	resumed.step(0.0)
	for i in Diplomacy.MAX_STEPS + 9:
		partitioned.step(Diplomacy.TICK_SECONDS)
	partitioned.step(1.25)
	check(sim.snapshot() == partitioned.snapshot() and sim.snapshot() == resumed.snapshot(), "deferred events survive save/resume in order")
	sim.record("trade", "traders")
	resumed.record("trade", "traders")
	sim.step(6.75)
	resumed.step(6.75)
	check(sim.snapshot() == resumed.snapshot() and sim.status().elapsed == 0.0, "actions and clock continue from checkpoint")
	var exposed := sim.status()
	exposed.relations.settlers.rangers = 200
	exposed.last_event.kind = "modified"
	exposed.event_log.clear()
	check(sim.snapshot() == resumed.snapshot(), "status is detached from live state")

	var state := sim.snapshot()
	for key in state:
		var broken := state.duplicate(true)
		broken.erase(key)
		reject(sim, broken, "missing " + key)
	var broken := state.duplicate(true)
	broken.relations.traders.rangers += 1
	reject(sim, broken, "asymmetric relation")
	broken = state.duplicate(true)
	broken.standings.traders = 7.5
	reject(sim, broken, "fractional score")
	broken = state.duplicate(true)
	broken.influence.crossing.settlers += 1
	reject(sim, broken, "inconsistent district shares")
	broken = state.duplicate(true)
	broken.relations.traders.traders = 99
	reject(sim, broken, "invalid self-relation")
	broken = state.duplicate(true)
	broken.pending_ticks = Diplomacy.MAX_TICK
	reject(sim, broken, "overflowing tick debt")
	broken = state.duplicate(true)
	broken.elapsed = INF
	reject(sim, broken, "invalid clock")
	broken = state.duplicate(true)
	broken.event_log.back().tick += 1
	reject(sim, broken, "event from future")
	broken = state.duplicate(true)
	broken.event_log.back().actor = "unknown"
	reject(sim, broken, "unknown actor")
	broken = state.duplicate(true)
	broken.event_log.back().actor = {}
	reject(sim, broken, "ill-typed actor")
	broken = state.duplicate(true)
	broken.event_log.remove_at(3)
	reject(sim, broken, "missing tick in recent event history")
	broken = state.duplicate(true)
	broken.seed = []
	reject(sim, broken, "ill-typed seed")
	decoded.influence.crossing.settlers = -200
	check(resumed.snapshot() == state, "restore detaches input")
	if failures == 0:
		print("DIPLOMACY_TEST_PASS")
	quit(int(failures > 0))


func check(ok: bool, label: String) -> void:
	if not ok:
		printerr("FAIL ", label)
		failures += 1


func reject(sim, bad: Dictionary, label: String) -> void:
	var before: Dictionary = sim.snapshot()
	check(not sim.restore(bad) and sim.snapshot() == before, "atomic rejection of " + label)
