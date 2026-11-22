extends RefCounted

# Reuse Director independently of the verification entry point below. A host can
# show policy(), each round's brief, and the finish receipt in its settings UI.
class Director extends RefCounted:
	signal tier_changed(previous: int, current: int, reason: String)

	const TIER_NAMES := ["Practice", "Easy", "Standard", "Hard", "Expert"]
	const OPPORTUNITIES := 6
	const RADIUS := 8.0
	const SHORTFALL_ROUNDS := 2
	const SUCCESS_ROUNDS := 3
	const REST_ROUNDS := 2

	var _tier := 2
	var _opted_in := false
	var _locked := false
	var _large_text := false
	var _reduced_motion := false
	var _shortfalls := 0
	var _successes := 0
	var _rest := 0
	var _active := false
	var _eligible := false
	var _attempts := 0
	var _captures := 0

	func policy() -> Dictionary:
		return {"opted_in": _opted_in, "locked": _locked, "tier": _tier,
				"name": TIER_NAMES[_tier], "quota": _tier + 2,
				"opportunities": OPPORTUNITIES, "radius": RADIUS, "cooldown": _rest,
				"rule": "Two consecutive rounds at or below half quota lower one tier. Three consecutive rounds meeting quota raise one tier. Two completed rounds rest after each change."}

	func _forget_streaks() -> void:
		_shortfalls = 0
		_successes = 0

	func set_preferences(opt_in: bool, lock_tier: bool) -> void:
		if _opted_in == opt_in and _locked == lock_tier:
			return
		_opted_in = opt_in
		_locked = lock_tier
		_eligible = false  # A partially observed round cannot vote after a settings change.
		_forget_streaks()
		_rest = 0

	func select_tier(value: int) -> bool:
		if _active or _locked or value < 0 or value >= TIER_NAMES.size():
			return false
		_forget_streaks()
		_rest = 0
		if _tier != value:
			var previous := _tier
			_tier = value
			tier_changed.emit(previous, _tier, "player_selection")
		return true

	func set_accessibility(large_text: bool, reduced_motion: bool) -> void:
		_large_text = large_text
		_reduced_motion = reduced_motion

	func begin_round() -> Dictionary:
		if _active:
			return {}
		_active = true
		_eligible = _opted_in and not _locked
		_attempts = 0
		_captures = 0
		var brief := policy()
		brief["label_size_px"] = 32 if _large_text else 20
		brief["animate_marker"] = not _reduced_motion
		return brief

	# Resolve one marker against its center in local coordinates. No device,
	# timing data, accessibility preference, or session duration enters scoring.
	func resolve_marker(offset: Vector2) -> bool:
		if not _active or _attempts >= OPPORTUNITIES or not offset.is_finite():
			return false
		_attempts += 1
		if offset.length_squared() <= RADIUS * RADIUS:
			_captures += 1
		return true

	func cancel_round() -> bool:
		if not _active:
			return false
		_active = false
		_eligible = false
		_forget_streaks()
		return true

	func _adjust(goal: int) -> String:
		if not _eligible:
			return "fixed"
		if _rest > 0:
			_rest -= 1
			return "cooldown"
		if _captures >= goal:
			_successes += 1
			_shortfalls = 0
			if _successes < SUCCESS_ROUNDS:
				return "observe"
		elif _captures * 2 <= goal:
			_shortfalls += 1
			_successes = 0
			if _shortfalls < SHORTFALL_ROUNDS:
				return "observe"
		else:
			_forget_streaks()
			return "neutral"

		var direction := 1 if _successes == SUCCESS_ROUNDS else -1
		_forget_streaks()
		var previous := _tier
		_tier = clampi(_tier + direction, 0, TIER_NAMES.size() - 1)
		if _tier == previous:
			return "tier_limit"
		_rest = REST_ROUNDS
		return "quota_streak" if direction > 0 else "shortfall_streak"

	func finish_round() -> Dictionary:
		if not _active or _attempts != OPPORTUNITIES:
			return {}
		_active = false
		var previous := _tier
		var goal := previous + 2
		var reason := _adjust(goal)
		_eligible = false
		var receipt := {"tier": previous, "quota": goal, "captures": _captures, "completed": _captures >= goal,
				"next_tier": _tier, "next_quota": _tier + 2, "reason": reason, "cooldown": _rest}
		if previous != _tier:
			tier_changed.emit(previous, _tier, reason)
		return receipt


func _offset(index: int, hits: int) -> Vector2:
	# The boundary point scores, the point just outside it misses.
	return Vector2(8.0, 0.0) if index < hits else Vector2(8.25, 0.0)


func _round(director: Director, hits: int) -> Dictionary:
	director.begin_round()
	for index in Director.OPPORTUNITIES:
		director.resolve_marker(_offset(index, hits))
	return director.finish_round()


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var checks: Array[Dictionary] = []
	var manual := Director.new()
	var fixed_ok: bool = not manual.policy().opted_in
	for hits in [0, 0, 6, 6, 6]:
		var fixed := _round(manual, hits)
		fixed_ok = fixed_ok and fixed.reason == "fixed" and fixed.next_tier == 2
	manual.set_preferences(true, true)
	fixed_ok = fixed_ok and not manual.select_tier(4)
	for hits in [6, 6, 6, 0, 0]:
		var locked := _round(manual, hits)
		fixed_ok = fixed_ok and locked.reason == "fixed" and locked.next_tier == 2
	checks.append(_check("consent-lock", fixed_ok, "Five default rounds and five opted-in locked rounds kept the selected Standard quota."))

	var director := Director.new()
	var notifications: Array = []
	director.tier_changed.connect(func(a: int, b: int, why: String): notifications.append([a, b, why]))
	director.set_preferences(true, false)
	var history: Array[Dictionary] = []
	var frame_ticks := 0
	# Six real SceneTree frame notifications resolve each round. Outcomes depend
	# on the deterministic marker samples, never on the wall time between frames.
	for hits in [2, 3, 2, 1, 6, 6, 6, 6, 6]:
		director.begin_round()
		for i in Director.OPPORTUNITIES:
			await tree.process_frame
			director.resolve_marker(_offset(i, hits))
			frame_ticks += 1
		history.append(director.finish_round())
	var tiers: Array = []
	var reasons: Array = []
	for receipt in history:
		tiers.append(receipt.next_tier)
		reasons.append(receipt.reason)
	var lower_ok := tiers.slice(0, 4) == [2, 2, 2, 1] and reasons.slice(0, 4) == ["observe", "neutral", "observe", "shortfall_streak"]
	checks.append(_check("hysteresis", lower_ok, "Six markers per round produced captures [2, 3, 2, 1]. Next tiers were %s." % [tiers.slice(0, 4)]))
	var return_ok := tiers.slice(4) == [1, 1, 1, 1, 2] and reasons.slice(4) == ["cooldown", "cooldown", "observe", "observe", "quota_streak"]
	return_ok = return_ok and history[4].quota == 3 and history[8].next_quota == 4
	checks.append(_check("cooldown-recovery", return_ok, "After easing, five quota completions produced %s." % [reasons.slice(4)]))
	var notices_ok := notifications == [[2, 1, "shortfall_streak"], [1, 2, "quota_streak"]]
	checks.append(_check("change-receipts", notices_ok, "Emitted actual tier-change signals %s; receipts state the completed quota and next quota." % [notifications]))

	var boundaries := Director.new()
	boundaries.set_preferences(true, false)
	var limits_ok := not boundaries.select_tier(-1) and not boundaries.select_tier(5)
	var limits: Array = []
	for edge in [0, 4]:
		limits_ok = boundaries.select_tier(edge) and limits_ok
		var clamp_seen := false
		for i in 12:
			var result := _round(boundaries, 0 if edge == 0 else 6)
			limits_ok = limits_ok and result.next_tier == edge and result.next_quota == edge + 2
			clamp_seen = clamp_seen or result.reason == "tier_limit"
		limits_ok = limits_ok and clamp_seen
		limits.append(boundaries.policy().quota)
	checks.append(_check("tier-limits", limits_ok, "Twelve extreme rounds at each bound retained quotas %s." % [limits]))

	var freeze := Director.new()
	freeze.set_preferences(true, false)
	_round(freeze, 0)
	freeze.begin_round()
	freeze.resolve_marker(Vector2.ZERO)
	var freeze_ok := freeze.finish_round().is_empty() and freeze.begin_round().is_empty() and not freeze.select_tier(4)
	freeze.set_preferences(false, false)
	freeze.set_preferences(true, false)
	for i in 5:
		freeze.resolve_marker(Vector2(12, 0))
	var resumed := freeze.finish_round()
	freeze_ok = freeze_ok and resumed.reason == "fixed" and resumed.next_tier == 2
	freeze_ok = freeze_ok and freeze.finish_round().is_empty() and not freeze.resolve_marker(Vector2.ZERO)
	freeze_ok = freeze_ok and _round(freeze, 0).reason == "observe"
	freeze.begin_round()
	freeze.resolve_marker(Vector2.ZERO)
	freeze_ok = freeze_ok and freeze.cancel_round() and freeze.finish_round().is_empty()
	freeze_ok = freeze_ok and _round(freeze, 0).reason == "observe" and freeze.policy().tier == 2
	checks.append(_check("midround-freeze", freeze_ok, "No partial, canceled or stale pre-consent round contributed to the next adjustment."))

	var plain := Director.new()
	var accessible := Director.new()
	plain.set_preferences(true, false)
	accessible.set_preferences(true, false)
	accessible.set_accessibility(true, true)
	var parity := true
	for hits in [1, 1, 6, 6, 6, 6, 6]:
		var stock := plain.begin_round()
		var alternate := accessible.begin_round()
		parity = parity and stock.animate_marker and not alternate.animate_marker and alternate.label_size_px > stock.label_size_px
		for i in Director.OPPORTUNITIES:
			var offset := _offset(i, hits)
			plain.resolve_marker(offset)
			accessible.resolve_marker(offset)
		var a := plain.finish_round()
		var b := accessible.finish_round()
		parity = parity and a == b
	checks.append(_check("accessibility-parity", parity, "Large labels and reduced motion changed the round brief. Identical marker positions produced equal scoring and tier receipts across seven rounds."))

	return {"id": "difficulty", "checks": checks, "metrics": {
		"rounds": history.size(), "engine_frame_ticks": frame_ticks, "next_tiers": tiers,
		"reasons": reasons, "tier_change_signals": notifications, "bounded_quotas": limits,
		"rest_rounds_after_change": Director.REST_ROUNDS, "opportunities_per_round": Director.OPPORTUNITIES}}
