extends RefCounted


class Mission extends RefCounted:
	signal changed

	const TITLES := {
		"junction": "Inspect the cable junction", "approach": "Choose a crossing at the junction",
		"winch": "Raise the winch platform", "stairs": "Reach the upper stair landing",
		"delivery": "Deliver the route chart", "ledger": "Recover the survey ledger",
	}
	const FAILURE := "High water closed the crossing. Retry from the cable junction."
	var stage := "unknown"
	var records := {}
	var tracked := ""
	var revision := 0

	func _publish() -> void:
		revision += 1
		changed.emit()

	func _advance(next: String) -> void:
		if records.has(stage):
			records[stage] = "Done"
		stage = next
		records[next] = "Active"
		if records.get(tracked) != "Active":
			tracked = next

	func reset() -> void:
		records.clear()
		stage = "unknown"
		tracked = ""
		_publish()

	func track(key: String) -> void:
		if records.get(key) == "Active" and tracked != key:
			tracked = key
			_publish()

	func receive(event: String) -> bool:
		# Only accepted transitions announce a change. Stale acknowledgements cannot advance another route.
		match event:
			"discover" when stage == "unknown":
				_advance("junction")
			"inspect-junction" when stage == "junction":
				_advance("approach")
			"choose-winch" when stage == "approach":
				_advance("winch")
			"choose-stairs" when stage == "approach":
				_advance("stairs")
			"raise-platform" when stage == "winch":
				_advance("delivery")
			"reach-landing" when stage == "stairs":
				_advance("delivery")
			"find-ledger" when records.get(stage) == "Active" and not records.has("ledger"):
				records["ledger"] = "Active"
			"recover-ledger" when records.get("ledger") == "Active":
				records["ledger"] = "Done"
				if tracked == "ledger":
					tracked = stage
			"deliver-chart" when stage == "delivery":
				records[stage] = "Done"
				if records.get("ledger") == "Active":
					records["ledger"] = "Skipped"
				stage = "complete"
				tracked = ""
			"crossing-closed" when records.get(stage) == "Active":
				records[stage] = "Failed"
				if records.get("ledger") == "Active":
					records["ledger"] = "Closed"
				stage = "failed"
				tracked = ""
			"retry" when stage == "failed":
				records.clear()
				_advance("junction")
			_:
				return false
		_publish()
		return true

	func summary() -> String:
		match stage:
			"unknown":
				return "No mission discovered"
			"failed":
				return FAILURE
			"complete":
				return "Mission complete: route chart delivered"
		var prefix := "Optional: " if tracked == "ledger" else "Next: "
		return prefix + TITLES[tracked]


class Journal extends MarginContainer:
	var mission: Mission
	var hud := Label.new()
	var open_button := Button.new()
	var panel := VBoxContainer.new()
	var title := Label.new()
	var entries := VBoxContainer.new()
	var retry := Button.new()
	var close_button := Button.new()
	var buttons := {}
	var refreshes := 0
	var ink := StyleBoxFlat.new()

	func bind_mission(next: Mission) -> void:
		if mission != null and mission.changed.is_connected(refresh):
			mission.changed.disconnect(refresh)
		mission = next
		if mission != null:
			mission.changed.connect(refresh)
		if is_node_ready():
			refresh()

	func _ready() -> void:
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		ink.bg_color = Color(0.08, 0.12, 0.15)
		for side in [SIDE_LEFT, SIDE_RIGHT]:
			ink.set_content_margin(side, 12)
		for side in [SIDE_TOP, SIDE_BOTTOM]:
			ink.set_content_margin(side, 4)
		var body := VBoxContainer.new()
		body.add_theme_constant_override("separation", 8)
		add_child(body)
		_label(body, hud, "TrackedObjective")
		_action(body, open_button, "OpenJournal", "Open mission journal", open_journal)
		body.add_child(panel)
		_label(panel, title, "JournalTitle")
		title.text = "Mission journal"
		panel.add_child(entries)
		entries.add_theme_constant_override("separation", 4)
		_action(panel, retry, "Retry", "Retry from junction", _retry)
		_action(panel, close_button, "Close", "Close journal", close_journal)
		panel.hide()
		_insets()
		get_viewport().size_changed.connect(_insets)
		refresh()

	func _label(parent: Control, label: Label, key: String) -> void:
		label.name = key
		label.add_theme_font_size_override("font_size", 21)
		label.add_theme_stylebox_override("normal", ink)
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		parent.add_child(label)

	func _action(parent: Control, button: Button, key: String, text: String, callback: Callable) -> void:
		button.name = key
		button.text = text
		button.custom_minimum_size.y = 42
		button.add_theme_font_size_override("font_size", 18)
		for state in ["normal", "hover", "pressed", "disabled"]:
			button.add_theme_stylebox_override(state, ink)
		button.pressed.connect(callback)
		parent.add_child(button)

	func _insets() -> void:
		var area := get_viewport_rect().size
		for edge in ["left", "right"]:
			add_theme_constant_override("margin_" + edge, ceili(area.x * 0.05))
		for edge in ["top", "bottom"]:
			add_theme_constant_override("margin_" + edge, ceili(area.y * 0.05))

	func _retry() -> void:
		if mission != null:
			mission.receive("retry")

	func _track(key: String) -> void:
		if mission != null:
			mission.track(key)

	func _preferred() -> Button:
		if retry.visible:
			return retry
		if mission != null and buttons.has(mission.tracked):
			return buttons[mission.tracked]
		return close_button

	func open_journal() -> void:
		open_button.hide()
		panel.show()
		_preferred().grab_focus()

	func close_journal() -> void:
		panel.hide()
		open_button.show()
		open_button.grab_focus()

	func refresh() -> void:
		refreshes += 1
		var owner_before := get_viewport().gui_get_focus_owner()
		var owned_focus := owner_before != null and panel.is_ancestor_of(owner_before)
		var records: Dictionary = mission.records if mission != null else {}
		open_button.disabled = mission == null
		hud.text = mission.summary() if mission != null else "No mission discovered"
		for key in buttons.keys():
			if not records.has(key):
				var removed: Button = buttons[key]
				buttons.erase(key)
				entries.remove_child(removed)
				removed.queue_free()
		var actions: Array[Button] = []
		for key in records:
			if not buttons.has(key):
				var entry := Button.new()
				_action(entries, entry, key, "", _track.bind(key))
				buttons[key] = entry
			var button: Button = buttons[key]
			var prefix := "Optional · " if key == "ledger" else ""
			var state: String = "Tracking" if key == mission.tracked else mission.records[key]
			button.text = "%s%s · %s" % [prefix, state, Mission.TITLES[key]]
			button.disabled = mission.records[key] != "Active"
			button.focus_mode = Control.FOCUS_NONE if button.disabled else Control.FOCUS_ALL
			if not button.disabled:
				actions.append(button)
		retry.visible = mission != null and mission.stage == "failed"
		if retry.visible:
			actions.append(retry)
		actions.append(close_button)
		for i in actions.size():
			var control := actions[i]
			control.focus_neighbor_top = control.get_path_to(actions[posmod(i - 1, actions.size())])
			control.focus_neighbor_bottom = control.get_path_to(actions[(i + 1) % actions.size()])
		if panel.visible and owned_focus and owner_before not in actions:
			_preferred().grab_focus()


func _press(view: SubViewport, action: StringName) -> void:
	for down in [true, false]:
		var event := InputEventAction.new()
		event.action = action
		event.pressed = down
		view.push_input(event, true)


func _settle(tree: SceneTree) -> void:
	for _frame in 3:
		await tree.process_frame


func _layout(ui: Journal, view: SubViewport) -> Dictionary:
	var inset := Vector2(ui.get_theme_constant("margin_left"), ui.get_theme_constant("margin_top"))
	var safe := Rect2(inset, Vector2(view.size) - 2 * inset)
	var rows: Array = [ui.hud, ui.title]
	rows.append_array(ui.entries.get_children())
	rows.append(ui.close_button)
	if ui.retry.is_visible_in_tree():
		rows.append(ui.retry)
	var rects: Array[Rect2] = []
	var fits := true
	var min_px := 1000
	for control in rows:
		var box: Rect2 = control.get_global_rect()
		var font: Font = control.get_theme_font("font")
		var px: int = control.get_theme_font_size("font_size")
		var text_size := font.get_string_size(control.text, HORIZONTAL_ALIGNMENT_LEFT, -1, px)
		var padding := ui.ink.get_minimum_size()
		fits = fits and control.is_visible_in_tree() and safe.encloses(box)
		fits = fits and text_size.x + padding.x <= box.size.x + 0.01 and text_size.y + padding.y <= box.size.y + 0.01
		for other in rects:
			fits = fits and not other.intersects(box)
		rects.append(box)
		min_px = mini(min_px, px)
	return {"fits": fits, "rows": rows.size(), "min_font_px": min_px, "viewport": [view.size.x, view.size.y]}


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var view := SubViewport.new()
	view.size = Vector2i(1280, 720)
	view.disable_3d = true
	tree.root.add_child(view)
	var mission := Mission.new()
	var ui := Journal.new()
	ui.bind_mission(mission)
	view.add_child(ui)
	await _settle(tree)
	ui.open_button.grab_focus()
	var clean := ui.entries.get_child_count() == 0 and ui.hud.text == "No mission discovered"
	var silent := ui.refreshes
	var rejected := not mission.receive("deliver-chart") and ui.refreshes == silent
	mission.receive("discover")
	var discovery := ui.buttons.keys() == ["junction"] and ui.hud.text == "Next: Inspect the cable junction"
	var closed_focus := view.gui_get_focus_owner() == ui.open_button
	_press(view, &"ui_accept")
	mission.receive("inspect-junction")
	mission.receive("choose-winch")
	var winch_only := ui.buttons.has("winch") and not ui.buttons.has("stairs") and not ui.buttons.has("delivery")
	winch_only = winch_only and not mission.receive("reach-landing")
	var prior := view.gui_get_focus_owner()
	mission.receive("find-ledger")
	var stable: bool = prior == ui.buttons.winch and view.gui_get_focus_owner() == prior
	_press(view, &"ui_down")
	var reached: bool = view.gui_get_focus_owner() == ui.buttons.ledger
	_press(view, &"ui_accept")
	var optional := mission.tracked == "ledger" and ui.hud.text == "Optional: Recover the survey ledger"
	mission.receive("recover-ledger")
	var fallback: bool = view.gui_get_focus_owner() == ui.buttons.winch and mission.tracked == "winch"
	var optional_done: bool = ui.buttons.ledger.disabled and ui.buttons.ledger.text.begins_with("Optional · Done")
	var checks := [
		_check("discovery-gating", clean and rejected and discovery and closed_focus,
				"Empty before discovery %s, premature event ignored %s, only junction revealed %s." % [clean, rejected, discovery]),
		_check("optional-tracking", reached and optional and optional_done and fallback,
				"D-pad reached optional row %s, HUD tracked it %s, completed row disabled %s, main objective restored %s." %
				[reached, optional, optional_done, fallback]),
	]
	mission.receive("raise-platform")
	await _settle(tree)
	var wide := _layout(ui, view)
	view.size = Vector2i(960, 540)
	await _settle(tree)
	var compact := _layout(ui, view)
	checks.append(_check("handheld-layout", wide.fits and compact.fits and wide.rows >= 7 and compact.min_font_px >= 18,
			"Measured %d visible labels/buttons at %s and %s; fit %s/%s, smallest configured font %d px." %
			[wide.rows, wide.viewport, compact.viewport, wide.fits, compact.fits, compact.min_font_px]))
	_press(view, &"ui_down")
	var reached_close := view.gui_get_focus_owner() == ui.close_button
	_press(view, &"ui_accept")
	var restored := not ui.panel.visible and view.gui_get_focus_owner() == ui.open_button
	mission.receive("crossing-closed")
	var blocked := not mission.receive("deliver-chart") and not mission.receive("choose-stairs")
	var failure_message := ui.hud.text == Mission.FAILURE and view.gui_get_focus_owner() == ui.open_button
	_press(view, &"ui_accept")
	var retry_focus := view.gui_get_focus_owner() == ui.retry
	checks.append(_check("focus-reconciliation", stable and fallback and reached_close and restored,
			"Kept existing focused row %s, redirected completed row %s, close reachable %s, opener restored %s." %
			[stable, fallback, reached_close, restored]))
	checks.append(_check("failure-guidance", blocked and failure_message and retry_focus and mission.tracked.is_empty(),
			"Terminal events ignored %s, failure reason and retry instruction shown %s, retry focused %s." %
			[blocked, failure_message, retry_focus]))
	_press(view, &"ui_accept")
	var reset_ids := ui.buttons.keys()
	var retried: bool = reset_ids == ["junction"] and view.gui_get_focus_owner() == ui.buttons.junction
	retried = retried and not ui.retry.visible and mission.tracked == "junction"
	mission.receive("inspect-junction")
	mission.receive("choose-stairs")
	var stairs_only := ui.buttons.has("stairs") and not ui.buttons.has("winch") and not mission.receive("raise-platform")
	checks.append(_check("branch-exclusivity", winch_only and stairs_only, "Winch route excluded stairs %s; retry selected stairs and excluded winch %s." % [winch_only, stairs_only]))
	mission.receive("find-ledger")
	mission.receive("reach-landing")
	mission.receive("deliver-chart")
	var completed: bool = mission.stage == "complete" and ui.hud.text == "Mission complete: route chart delivered"
	var skipped: bool = mission.records.get("ledger") == "Skipped" and ui.buttons.ledger.disabled
	var final_focus := view.gui_get_focus_owner() == ui.close_button
	var rev := mission.revision
	var repeat_ignored := not mission.receive("deliver-chart") and not mission.receive("recover-ledger") and rev == mission.revision
	mission.reset()
	var emptied := ui.entries.get_child_count() == 0 and ui.hud.text == "No mission discovered"
	checks.append(_check("retry-reset", retried and emptied, "Retry exposed only %s and restored tracking/focus %s; reset removed every objective %s." % [reset_ids, retried, emptied]))
	checks.append(_check("completion", completed and skipped and final_focus and repeat_ignored,
			"Delivered via stairs %s, optional skipped without blocking %s, focus on close %s, duplicate events ignored %s." %
			[completed, skipped, final_focus, repeat_ignored]))
	var metrics := {"revision": mission.revision, "ui_refreshes": ui.refreshes, "profiles": [wide, compact],
			"retry_visible_ids": reset_ids, "routes_checked": 2}
	view.free()
	return {"id": "journal", "checks": checks, "metrics": metrics}
