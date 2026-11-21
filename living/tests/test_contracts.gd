extends SceneTree

const Contracts := preload("res://contracts.gd")
const SUPPORTED := {
	"gather": ["wood", "stone", "fiber"], "craft": ["tool", "bandage"],
	"greet": ["settlers", "rangers"], "sell": ["tool"], "drive": ["checkpoint"],
}

var failures := 0


func check(condition: bool, detail: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", detail)


func _initialize() -> void:
	var jobs := Contracts.new()
	check(jobs.board().is_empty() and jobs.snapshot().is_empty(), "unconfigured board")
	check(not jobs.accept("") and not jobs.record("gather", "wood") and jobs.claim() == 0,
			"unconfigured actions fail")
	check(jobs.configure(237), "configure")
	var first := jobs.board()
	var idle := jobs.snapshot()
	check(first.size() == 3 and jobs.status().active_id == "", "three choices and idle status")
	var copy := jobs.board()
	copy[0].steps[0].count = -1
	copy.clear()
	check(jobs.board() == first, "returned offers isolate nested steps")
	var same := Contracts.new()
	same.configure(237)
	check(same.board() == first and same.snapshot() == idle, "stable seed")
	same.configure(238)
	check(same.board()[0].steps != first[0].steps, "another seed changes objectives")
	check(not same.restore(idle), "foreign seed rejected")
	check(not jobs.accept("unknown") and jobs.snapshot() == idle, "unknown offer rejected")
	check(jobs.configure(0) and jobs.configure(2_147_483_647), "inclusive seed range")
	var boundary := jobs.snapshot()
	check(not jobs.configure(-1) and not jobs.configure(2_147_483_648) and jobs.snapshot() == boundary,
			"bad configuration preserves state")
	var observed := {}
	for seed_number in range(32):
		var original := Contracts.new()
		original.configure(seed_number)
		var offers := original.board()
		var ids := {}
		for offer: Dictionary in offers:
			check(not ids.has(offer.id), "unique offer IDs")
			ids[offer.id] = true
			_exercise_offer(seed_number, offer, observed)
	for action: String in SUPPORTED:
		for target: String in SUPPORTED[action]:
			check(observed.has(action + "/" + target), "generated objective %s/%s" % [action, target])
	_check_invalid_states()
	_check_long_run()
	print("Contract board assertions finished, failures=", failures)
	quit(int(failures != 0))


func _exercise_offer(seed_number: int, offer: Dictionary, observed: Dictionary) -> void:
	var jobs := Contracts.new()
	jobs.configure(seed_number)
	var initial := jobs.board()
	check(jobs.accept(offer.id) and jobs.status().title == offer.title, "accept displayed offer")
	var accepted := jobs.snapshot()
	check(not jobs.accept(offer.id) and not jobs.accept(initial[1].id), "only one job can be active")
	check(jobs.claim() == 0 and jobs.snapshot() == accepted, "premature claim preserves job")
	for index in offer.steps.size():
		var step: Dictionary = offer.steps[index]
		observed[step.action + "/" + step.target] = true
		check(SUPPORTED.get(step.action, []).has(step.target) and step.count > 0,
				"repeatable supported objective")
		var next: Dictionary = jobs.status().current
		next.target = "broken"
		check(jobs.status().current == step, "status isolates nested current step")
		for count_index in step.count:
			var before := jobs.snapshot()
			check(not jobs.record("gather", "") and not jobs.record("bad", step.target), "incorrect event")
			if index + 1 < offer.steps.size():
				var later: Dictionary = offer.steps[index + 1]
				check(not jobs.record(later.action, later.target), "out-of-order event ignored")
			check(jobs.snapshot() == before and jobs.status().progress == count_index,
					"rejected events preserve counter")
			check(jobs.record(step.action, step.target), "valid interaction")
			var saved := jobs.snapshot()
			var resumed := Contracts.new()
			resumed.configure(seed_number)
			check(resumed.restore(JSON.parse_string(JSON.stringify(saved))), "JSON checkpoint resumes")
			check(resumed.snapshot() == saved and resumed.status() == jobs.status(), "exact cursor restored")
			jobs = resumed
	check(jobs.status().complete and jobs.status().current.is_empty() and jobs.status().reward == offer.reward,
			"completed contract is ready for payout")
	check(not jobs.record(offer.steps[-1].action, offer.steps[-1].target), "completion is idempotent")
	check(jobs.claim() == offer.reward and offer.reward > 0, "grant exact reward")
	check(jobs.claim() == 0 and jobs.status().generation == 1, "repeat claim neither pays nor rotates")
	check(not jobs.accept(offer.id) and jobs.status().active_id == "" and jobs.status().reward == 0,
			"claimed ID retired")
	check(jobs.board()[0].steps != initial[0].steps, "rotation changes actual work")
	var restored := Contracts.new()
	restored.configure(seed_number)
	check(restored.restore(jobs.snapshot()) and restored.board() == jobs.board() and restored.claim() == 0,
			"paid checkpoint reopens deterministic board")


func _check_invalid_states() -> void:
	var jobs := Contracts.new()
	jobs.configure(17)
	jobs.accept(jobs.board()[1].id)
	var current: Dictionary = jobs.status().current
	jobs.record(current.action, current.target)
	var saved := jobs.snapshot()
	var before := jobs.board()
	var failures_to_try: Array = [{}]
	var extra := saved.duplicate()
	extra["offers"] = []
	failures_to_try.append(extra)
	for key: String in saved:
		var missing := saved.duplicate()
		missing.erase(key)
		failures_to_try.append(missing)
	for key: String in ["version", "seed", "generation", "step_index", "progress"]:
		for bad in [null, true, "", [], -1, 0.5, 2_147_483_648, INF, -INF, NAN]:
			var invalid := saved.duplicate()
			invalid[key] = bad
			failures_to_try.append(invalid)
	for edits: Dictionary in [
		{"version": 2}, {"seed": 18}, {"generation": 1}, {"active_id": null},
		{"active_id": 0}, {"active_id": "fake"}, {"active_id": ""},
		{"step_index": 3}, {"progress": 1}, {"step_index": 2, "progress": 1},
		{"active_id": "", "step_index": 0, "progress": 1},
	]:
		var invalid := saved.duplicate()
		invalid.merge(edits, true)
		failures_to_try.append(invalid)
	for invalid: Dictionary in failures_to_try:
		check(not jobs.restore(invalid) and jobs.snapshot() == saved and jobs.board() == before,
				"reject malformed checkpoint atomically")
	var blank := Contracts.new()
	check(not blank.restore(saved), "restore requires configured world seed")


func _check_long_run() -> void:
	var jobs := Contracts.new()
	jobs.configure(2_147_483_647)
	for generation in range(100):
		var supply: Dictionary = jobs.board()[0]
		check(jobs.status().generation == generation and jobs.accept(supply.id), "successive generation")
		for i in supply.steps[0].count:
			check(jobs.record(supply.steps[0].action, supply.steps[0].target), "fill rotating supply order")
		check(jobs.claim() == supply.reward, "rotate through many claims")
	check(jobs.snapshot().size() == 6 and JSON.stringify(jobs.snapshot()).length() < 180,
			"snapshot size independent of number of jobs")
	var last := jobs.snapshot()
	last.generation = 2_147_483_647
	check(jobs.restore(last), "last representable board")
	var supply: Dictionary = jobs.board()[0]
	jobs.accept(supply.id)
	for i in supply.steps[0].count:
		jobs.record(supply.steps[0].action, supply.steps[0].target)
	check(jobs.claim() == supply.reward and jobs.status().generation == 0, "generation safely wraps")
