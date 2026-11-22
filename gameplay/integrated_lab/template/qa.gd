extends SceneTree

const CHECKS := ["movement", "branch-platform", "branch-stairs", "world-consequence",
	"hud-consistency", "modal-input", "retry-isolation", "deterministic-replay"]
const DESCRIPTIONS := {
	"movement": "Engine input moved the courier one cell. Key release, echo, a boundary and a wall preserved state.",
	"branch-platform": "Chose and crossed the platform, covered the dry rack for three, and delivered once for thirteen total.",
	"branch-stairs": "Crossed the stairs, skipped the rack and received ten credits for one delivery.",
	"world-consequence": "Observed occupied-cart cancellation, rain evacuation, dry reopening, worker routes and shipments.",
	"hud-consistency": "Checked actual HUD control text and visibility at entry, discovery, crossing, rack and delivery.",
	"modal-input": "Checked focus, journal and cancellation input isolation, and gameplay resumption.",
	"retry-isolation": "Confirmed retry restored initial state and views and rejected a command from the previous epoch.",
	"deterministic-replay": "Compared every input observation on fresh instances for each route and distinguished the branch traces.",
}
const REQUIRED := ["epoch", "tick", "player", "discovered", "route", "platform_open",
	"rain", "delivered", "reward", "optional_done", "workers", "shipments", "trace",
	"worker_platform_steps", "worker_stair_steps", "cart_due_tick", "cart_arrivals", "cart_cancellations"]
const MAIN := "res://main.tscn"
var failures := {}
var tested := {}
var metrics := {}


func _initialize() -> void:
	call_deferred("_execute")


func _expect(id: String, ok: bool, detail: String) -> void:
	tested[id] = tested.get(id, 0) + 1
	if not ok and failures[id].size() < 4:
		failures[id].append(detail)


func _key(stage, key: Key, pressed := true, echo := false) -> bool:
	var event := InputEventKey.new()
	event.keycode = key
	event.pressed = pressed
	event.echo = echo
	return stage.dispatch(event)


func _view_matches(stage, state: Dictionary) -> bool:
	var cell := Vector2i(state.player[0], state.player[1])
	var center := Vector2(32, 112) + (Vector2(cell) + Vector2(0.5, 0.5)) * 72
	if stage.player.position != center or stage.yard.cell_center(cell) != center:
		return false
	var positions: Array = []
	for worker in state.workers:
		positions.append(stage.yard.cell_center(Vector2i(worker[0], worker[1])))
	return positions == stage.yard.worker_positions and stage.yard.wet == state.rain \
		and stage.yard.crossing_open == (state.platform_open and not state.rain) \
		and stage.yard.shipment_count == state.shipments and stage.yard.rack_covered == state.optional_done \
		and stage.yard.receipt_visible == state.delivered


func _hud_matches(stage, state: Dictionary) -> bool:
	var hud = stage.hud
	var route: Label = hud.get_node("%Route")
	var optional: Label = hud.get_node("%Optional")
	var reward: Label = hud.get_node("%Reward")
	var objective: Label = hud.get_node("%Objective")
	var selected: bool = state.route != "none"
	if not objective.is_visible_in_tree() or hud.get_node("%Weather").text != ("Rain" if state.rain else "Dry"):
		return false
	if route.is_visible_in_tree() != state.discovered or optional.is_visible_in_tree() != selected or reward.is_visible_in_tree() != selected:
		return false
	if not state.discovered:
		return objective.text == "Inspect the cable junction." and route.text.is_empty() and optional.text.is_empty() and reward.text.is_empty()
	if not selected:
		return objective.text == "Choose a crossing at the winch or stairhead." and route.text == "Route: Not selected" \
			and optional.text.is_empty() and reward.text.is_empty()
	var expected_goal := "Chart delivered" if state.delivered else "Deliver the chart at Dispatch."
	var expected_optional := "Optional: Dry rack checked" if state.optional_done else "Optional: Check the dry rack"
	return objective.text == expected_goal and route.text == "Route: " + state.route.capitalize() \
		and optional.text == expected_optional and reward.text == "Reward: %d" % state.reward


func _movement(stage) -> void:
	var initial: Dictionary = stage.snapshot()
	_expect("movement", initial.player == [2, 3] and _view_matches(stage, initial), "Entry position or scene binding.")
	_key(stage, KEY_RIGHT, false)
	_key(stage, KEY_RIGHT, true, true)
	_expect("movement", initial == stage.snapshot(), "Release or repeated key changed the session.")
	var engine_key := InputEventKey.new()
	engine_key.keycode = KEY_A
	engine_key.pressed = true
	Input.parse_input_event(engine_key)
	Input.flush_buffered_events()
	await process_frame
	var release: InputEventKey = engine_key.duplicate()
	release.pressed = false
	Input.parse_input_event(release)
	Input.flush_buffered_events()
	var west: Dictionary = stage.snapshot()
	_expect("movement", west.player == [1, 3] and west.tick == initial.tick + 1 and _view_matches(stage, west), "WASD move did not reach the west tile.")
	_key(stage, KEY_LEFT)
	_expect("movement", west == stage.snapshot(), "Blocked boundary move advanced the world.")
	var pad := InputEventJoypadButton.new()
	pad.button_index = JOY_BUTTON_DPAD_RIGHT
	pad.pressed = true
	stage.dispatch(pad)
	_expect("movement", stage.snapshot().player == [2, 3], "Gamepad direction did not return to the start cell.")
	_key(stage, KEY_RIGHT)
	var junction: Dictionary = stage.snapshot()
	_key(stage, KEY_RIGHT)
	_expect("movement", junction.player == [3, 3] and junction == stage.snapshot() and _view_matches(stage, junction), "Barrier cell admitted the player or advanced time.")
	_key(stage, KEY_UP)
	var undiscovered: Dictionary = stage.snapshot()
	_key(stage, KEY_E)
	_expect("branch-platform", not undiscovered.discovered and undiscovered.player == [3, 2] and undiscovered == stage.snapshot(),
		"The winch selected a route before the junction was discovered.")


func _modal(stage) -> void:
	var before: Dictionary = stage.snapshot()
	var hud = stage.hud
	_key(stage, KEY_J)
	_expect("modal-input", hud.modal_open and hud.get_node("%Journal").is_visible_in_tree()
		and hud.get_node("%Close").has_focus(), "Journal did not open on its close control.")
	for key in [KEY_D, KEY_Q, KEY_E]:
		# E confirms the focused button. Refocus the journal before each probe.
		if not hud.modal_open:
			_key(stage, KEY_J)
		_key(stage, key)
	if hud.modal_open:
		_key(stage, KEY_ESCAPE)
	_expect("modal-input", not hud.modal_open and stage.snapshot() == before, "A journal input leaked into the running mission.")
	_key(stage, KEY_R)
	_expect("modal-input", hud.modal_open and hud.get_node("%CancelRetry").has_focus(), "Retry did not start on the safe cancel choice.")
	_key(stage, KEY_ESCAPE)
	_expect("modal-input", not hud.modal_open and before == stage.snapshot(), "Cancelling retry changed the session.")
	_key(stage, KEY_Q)
	_expect("modal-input", stage.snapshot().tick == before.tick + 1, "Closing the modal did not restore gameplay input.")


func _world(stage) -> void:
	_key(stage, KEY_RIGHT)
	_key(stage, KEY_E)
	var warned: Dictionary = stage.snapshot()
	_key(stage, KEY_Q)
	var pending: Dictionary = stage.snapshot()
	_key(stage, KEY_Q)
	var cancelled: Dictionary = stage.snapshot()
	_expect("world-consequence", warned.cart_due_tick == warned.tick + 2 and pending.cart_cancellations == warned.cart_cancellations
		and cancelled.cart_cancellations == warned.cart_cancellations + 1 and cancelled.cart_arrivals == warned.cart_arrivals
		and cancelled.player == [3, 3] and cancelled.reward == 0, "An occupied junction did not cancel the due cart without credit.")
	_key(stage, KEY_UP)
	_key(stage, KEY_E)
	_key(stage, KEY_RIGHT)
	var crossing: Dictionary = stage.snapshot()
	_key(stage, KEY_Q)
	var wet: Dictionary = stage.snapshot()
	_expect("world-consequence", crossing.tick == 7 and crossing.player == [4, 2] and not crossing.rain
		and wet.tick == 8 and wet.rain and wet.player == [3, 2] and _view_matches(stage, wet),
		"Rain did not close the occupied platform and return the courier to its entry bank.")
	_key(stage, KEY_RIGHT)
	_expect("world-consequence", wet == stage.snapshot(), "The closed platform accepted a move or advanced time.")
	for i in 4:
		_key(stage, KEY_Q)
	var dry: Dictionary = stage.snapshot()
	_expect("world-consequence", not dry.rain and dry.tick == 12 and stage.yard.crossing_open and _view_matches(stage, dry),
		"Dry weather did not reopen the selected platform in the world view.")
	metrics["cart_cancellations_at_due_tick"] = cancelled.cart_cancellations


# Keep every input observation, including rejected interactions, so a replay
# that arrives at the same endpoint by different intermediate states fails.
func _observe(stage, keys: Array, observations: Array) -> void:
	for key in keys:
		_key(stage, key)
		observations.append(stage.snapshot().duplicate(true))


func _route(stage, route: String) -> Dictionary:
	var id := "branch-" + route
	var observations: Array = [stage.snapshot().duplicate(true)]
	_expect("hud-consistency", _hud_matches(stage, observations[0]), "Entry HUD revealed unavailable objectives or had stale text.")
	_observe(stage, [KEY_D, KEY_SPACE], observations)
	var junction: Dictionary = stage.snapshot()
	_expect(id, junction.discovered and junction.route == "none" and junction.player == [3, 3], "The junction did not reveal the route decision.")
	_expect("hud-consistency", _hud_matches(stage, junction), "Discovery did not update visible route and optional controls.")
	if route == "platform":
		_observe(stage, [KEY_UP, KEY_E, KEY_RIGHT], observations)
	else:
		_observe(stage, [KEY_DOWN, KEY_DOWN, KEY_E, KEY_RIGHT], observations)
	var crossing: Dictionary = stage.snapshot()
	var gate := [4, 2] if route == "platform" else [4, 5]
	_expect(id, crossing.route == route and crossing.player == gate and _view_matches(stage, crossing),
		"The courier and yard did not use the chosen crossing.")
	_expect("hud-consistency", _hud_matches(stage, crossing), "Selected crossing was missing from the HUD.")
	if route == "platform":
		_observe(stage, [KEY_RIGHT, KEY_DOWN, KEY_DOWN, KEY_DOWN, KEY_RIGHT, KEY_E], observations)
		var optional: Dictionary = stage.snapshot()
		_expect(id, optional.player == [6, 5] and optional.optional_done and optional.reward == 3
			and not optional.delivered and _view_matches(stage, optional), "The optional dry rack did not award exactly three before delivery.")
		_expect("hud-consistency", _hud_matches(stage, optional), "Dry rack HUD did not match the earned optional reward.")
		_observe(stage, [KEY_E, KEY_UP, KEY_UP, KEY_RIGHT], observations)
	else:
		_observe(stage, [KEY_RIGHT, KEY_RIGHT, KEY_RIGHT, KEY_UP, KEY_UP], observations)
	_observe(stage, [KEY_E], observations)
	var delivered: Dictionary = stage.snapshot()
	var reward := 13 if route == "platform" else 10
	_expect(id, delivered.player == [7, 3] and delivered.delivered and delivered.reward == reward
		and delivered.optional_done == (route == "platform") and _view_matches(stage, delivered), "The delivery or reward disagreed with the selected route.")
	_observe(stage, [KEY_E], observations)
	_expect(id, stage.snapshot() == delivered, "Repeated delivery changed world state or credited a duplicate reward.")
	_expect("hud-consistency", _hud_matches(stage, delivered), "Delivered status or final reward disagreed with the HUD.")
	for i in 32:
		_observe(stage, [KEY_Q], observations)
	var end: Dictionary = stage.snapshot()
	var lane_used: bool = end.worker_platform_steps > 0 if route == "platform" else end.worker_stair_steps > 0 and end.worker_platform_steps == 0
	_expect("world-consequence", end.shipments > 0 and lane_used and end.cart_arrivals > 0 and _view_matches(stage, end),
		"Workers, shipments or subsequent clear-junction cart arrivals disagreed with the %s outcome." % route)
	return {"observations": observations, "route": end.route, "reward": end.reward, "shipments": end.shipments,
		"platform_steps": end.worker_platform_steps, "stair_steps": end.worker_stair_steps, "trace": end.trace.duplicate(true)}


func _retry(stage, initial: Dictionary) -> void:
	var before: Dictionary = stage.snapshot()
	_key(stage, KEY_R)
	_key(stage, KEY_DOWN)
	var focus_ok: bool = stage.hud.get_node("%ConfirmRetry").has_focus()
	_key(stage, KEY_ENTER)
	var reset: Dictionary = stage.snapshot()
	_expect("retry-isolation", focus_ok and not stage.hud.modal_open and reset.epoch == before.epoch + 1, "Confirmed retry failed to advance the epoch and close the modal.")
	var expected := initial.duplicate(true)
	expected.epoch = reset.epoch
	_expect("retry-isolation", reset == expected and _view_matches(stage, reset) and _hud_matches(stage, reset), "Retry left mission, yard, courier or HUD state behind.")
	var accepted: bool = stage.session.command(before.epoch, "wait")
	_expect("retry-isolation", not accepted and stage.snapshot() == reset, "A stale command advanced the new world.")


func _new_stage(scene: PackedScene) -> Node:
	var stage := scene.instantiate()
	root.add_child(stage)
	await process_frame
	return stage


func _exercise(scene: PackedScene) -> void:
	var stage = await _new_stage(scene)
	if not stage.has_method("snapshot") or not stage.snapshot().has_all(REQUIRED):
		for id in CHECKS:
			_expect(id, false, "Integrated scene has an incomplete snapshot contract.")
		stage.free()
		return
	await _movement(stage)
	_modal(stage)
	stage.free()
	stage = await _new_stage(scene)
	_world(stage)
	stage.free()
	var traces := {}
	for route in ["platform", "stairs"]:
		stage = await _new_stage(scene)
		var initial: Dictionary = stage.snapshot()
		var first := _route(stage, route)
		_retry(stage, initial)
		stage.free()
		stage = await _new_stage(scene)
		var replay := _route(stage, route)
		_expect("deterministic-replay", first == replay, "A fresh %s run differed at an input observation." % route)
		stage.free()
		traces[route] = first.trace
		metrics[route] = {"inputs": first.observations.size() - 1, "reward": first.reward, "shipments": first.shipments,
			"worker_platform_steps": first.platform_steps, "worker_stair_steps": first.stair_steps,
			"trace_sha256": JSON.stringify(first.trace).sha256_text()}
	_expect("deterministic-replay", not traces.platform.is_empty() and not traces.stairs.is_empty()
		and traces.platform != traces.stairs, "The two chosen routes produced indistinguishable world traces.")


func _execute() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or args[0].length() != 64 or not args[0].is_valid_hex_number(false):
		quit(2)
		return
	for id in CHECKS:
		failures[id] = []
	var original_children := root.get_child_count()
	var scene: PackedScene = load(MAIN)
	if scene != null:
		await _exercise(scene)
	await process_frame
	_expect("retry-isolation", original_children == root.get_child_count(), "An integrated scene left root children behind.")
	var checks: Array = []
	var passed := true
	for id in CHECKS:
		var ok: bool = tested.get(id, 0) > 0 and failures[id].is_empty()
		var detail: String = DESCRIPTIONS[id] if ok else "; ".join(failures[id])
		if detail.is_empty():
			detail = "Check did not run."
		checks.append({"id": id, "passed": ok, "detail": detail})
		passed = passed and ok
	print("GRAVEFORGE_INTEGRATED_QA " + JSON.stringify({"schema_version": 1, "source_sha256": args[0],
		"passed": passed, "reports": [{"id": "integrated", "checks": checks, "metrics": metrics}]}))
	quit(0 if passed else 1)
