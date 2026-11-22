extends RefCounted


class Activity extends Node:
	var ticks := 0

	func _process(_delta: float) -> void:
		ticks += 1


class StationInterface extends MarginContainer:
	var screen := ""
	var attempts := 0
	var inspections := 0
	var large_text := false
	var return_page := ""
	var opener: Button
	var activity := Activity.new()
	var pages := {}
	var controls := {}
	var box_style := StyleBoxFlat.new()

	func _ready() -> void:
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		add_child(activity)
		box_style.bg_color = Color(0.08, 0.12, 0.15)
		for side in [SIDE_LEFT, SIDE_RIGHT]:
			box_style.set_content_margin(side, 16)
		for side in [SIDE_TOP, SIDE_BOTTOM]:
			box_style.set_content_margin(side, 8)
		for key in ["title", "play", "paused", "settings", "failed"]:
			var page := VBoxContainer.new()
			page.name = key
			page.alignment = BoxContainer.ALIGNMENT_CENTER
			page.add_theme_constant_override("separation", 12)
			add_child(page)
			pages[key] = page

		_label("title", "heading", "Windward Station")
		_button("title", "start", "Begin shift", _start_attempt)
		_button("title", "title_options", "Display settings", _open_settings.bind("title", "title_options"))
		_label("play", "status", "Intake needs inspection")
		_button("play", "inspect", "Inspect intake", _inspect)
		_button("play", "pause_game", "Pause", _show_page.bind("paused", "resume"))
		_label("paused", "pause_heading", "Shift paused")
		_button("paused", "resume", "Resume shift", _show_page.bind("play", "pause_game"))
		_button("paused", "pause_options", "Display settings", _open_settings.bind("paused", "pause_options"))
		_label("settings", "settings_heading", "Display settings")
		var toggle := _button("settings", "large", "Large text", _toggle_text)
		toggle.toggle_mode = true
		_button("settings", "settings_back", "Back", _close_settings)
		_label("failed", "failure_heading", "Shift interrupted")
		_button("failed", "retry", "Retry shift", _start_attempt)
		_button("failed", "to_title", "Return to title", _show_page.bind("title", "start"))
		for pair in [["start", "title_options"], ["inspect", "pause_game"], ["resume", "pause_options"],
				["large", "settings_back"], ["retry", "to_title"]]:
			var a: Button = controls[pair[0]]
			var b: Button = controls[pair[1]]
			for side in [SIDE_TOP, SIDE_BOTTOM]:
				a.set_focus_neighbor(side, a.get_path_to(b))
				b.set_focus_neighbor(side, b.get_path_to(a))
		apply_safe_area()
		get_viewport().size_changed.connect(apply_safe_area)
		_show_page("title", "start")

	func _label(page: String, key: String, text: String) -> void:
		var label := Label.new()
		label.text = text
		label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		label.add_theme_stylebox_override("normal", box_style)
		_add_control(page, key, label)

	func _button(page: String, key: String, text: String, action: Callable) -> Button:
		var button := Button.new()
		button.text = text
		button.custom_minimum_size = Vector2(300, 52)
		for state in ["normal", "hover", "pressed", "hover_pressed"]:
			button.add_theme_stylebox_override(state, box_style)
		button.pressed.connect(action)
		_add_control(page, key, button)
		return button

	func _add_control(page: String, key: String, control: Control) -> void:
		control.name = key
		control.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		control.add_theme_font_size_override("font_size", 20)
		pages[page].add_child(control)
		controls[key] = control

	func apply_safe_area() -> void:
		var area := get_viewport().get_visible_rect().size
		for edge in ["left", "right"]:
			add_theme_constant_override("margin_" + edge, ceili(area.x * 0.05))
		for edge in ["top", "bottom"]:
			add_theme_constant_override("margin_" + edge, ceili(area.y * 0.05))

	func _show_page(page: String, first: String) -> void:
		screen = page
		for key in pages:
			pages[key].visible = key == page
		activity.set_process(page == "play")
		controls[first].grab_focus()

	func _start_attempt() -> void:
		attempts += 1
		inspections = 0
		controls.status.text = "Intake needs inspection"
		_show_page("play", "inspect")

	func _inspect() -> void:
		inspections += 1
		controls.status.text = "Intake checked"

	func _open_settings(page: String, key: String) -> void:
		return_page = page
		opener = controls[key]
		_show_page("settings", "large")

	func _toggle_text() -> void:
		large_text = controls.large.button_pressed
		for control in controls.values():
			control.add_theme_font_size_override("font_size", 30 if large_text else 20)

	func _close_settings() -> void:
		_show_page(return_page, opener.name)

	func fail_attempt() -> void:
		if screen == "play":
			_show_page("failed", "retry")


func _press(view: SubViewport, action: StringName) -> void:
	for down in [true, false]:
		var event := InputEventAction.new()
		event.action = action
		event.pressed = down
		view.push_input(event, true)


func _focused(view: SubViewport) -> String:
	var owner := view.gui_get_focus_owner()
	return str(owner.name) if owner != null else ""


func _settle(tree: SceneTree) -> void:
	# Container sort and minimum-size propagation are deferred.
	for _frame in 3:
		await tree.process_frame


func _profile(view: SubViewport, ui: StationInterface, id: String) -> Dictionary:
	var insets := []
	for side in ["left", "top", "right", "bottom"]:
		insets.append(ui.get_theme_constant("margin_" + side))
	var safe := Rect2(insets[0], insets[1], view.size.x - insets[0] - insets[2], view.size.y - insets[1] - insets[3])
	var widgets := []
	var rectangles: Array[Rect2] = []
	var fits := true
	var text_height := 0.0
	for control in ui.pages.play.get_children():
		var rect: Rect2 = control.get_global_rect()
		var font: Font = control.get_theme_font("font")
		var font_size: int = control.get_theme_font_size("font_size")
		var extent := font.get_string_size(control.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size)
		var style: StyleBox = control.get_theme_stylebox("normal")
		var padding := [style.get_margin(SIDE_LEFT), style.get_margin(SIDE_TOP),
				style.get_margin(SIDE_RIGHT), style.get_margin(SIDE_BOTTOM)]
		fits = fits and control.is_visible_in_tree() and safe.encloses(rect)
		fits = fits and extent.x + padding[0] + padding[2] <= rect.size.x + 0.01
		fits = fits and extent.y + padding[1] + padding[3] <= rect.size.y + 0.01
		for prior in rectangles:
			fits = fits and not prior.intersects(rect)
		rectangles.append(rect)
		if control == ui.controls.status:
			text_height = extent.y
		widgets.append({"id": str(control.name), "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
				"padding": padding, "measured_text": [extent.x, extent.y],
				"focusable": control.focus_mode == Control.FOCUS_ALL})

	var initial := _focused(view)
	var edges := []
	for key in ["inspect", "pause_game"]:
		ui.controls[key].grab_focus()
		for action in [&"ui_down", &"ui_up"]:
			_press(view, action)
			var edge := [key, _focused(view)]
			if edge not in edges:
				edges.append(edge)
			ui.controls[key].grab_focus()
	if initial in ui.controls:
		ui.controls[initial].grab_focus()
	var nav_ok := edges.size() == 2 and ["inspect", "pause_game"] in edges and ["pause_game", "inspect"] in edges
	var capture := {"id": id, "locale": "en", "viewport": [view.size.x, view.size.y], "safe_insets": insets,
			"widgets": widgets, "initial_focus": initial, "focus_edges": edges}
	return {"ok": fits and nav_ok and widgets.size() == 3, "height": text_height, "capture": capture}


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var view := SubViewport.new()
	view.size = Vector2i(1920, 1080)
	view.disable_3d = true
	tree.root.add_child(view)
	var ui := StationInterface.new()
	view.add_child(ui)
	await _settle(tree)
	var checks := []
	checks.append(_check("startup-focus", ui.screen == "title" and _focused(view) == "start"
			and not ui.pages.play.is_visible_in_tree() and not ui.activity.is_processing(),
			"Startup screen %s, focus %s, activity enabled %s." % [ui.screen, _focused(view), ui.activity.is_processing()]))

	_press(view, &"ui_down")
	var title_next := _focused(view)
	_press(view, &"ui_up")
	var title_previous := _focused(view)
	_press(view, &"ui_accept")
	var entered := ui.screen == "play" and _focused(view) == "inspect"
	_press(view, &"ui_accept")
	await _settle(tree)
	checks.append(_check("menu-navigation", title_next == "title_options" and title_previous == "start"
			and entered and ui.inspections == 1,
			"Down reached %s, up returned to %s, start entered play %s, inspections %d." %
			[title_next, title_previous, entered, ui.inspections]))
	var desktop := _profile(view, ui, "desktop-menu-hud")
	checks.append(_check("desktop-layout", desktop.ok and desktop.capture.viewport == [1920, 1080],
			"Desktop viewport %s, HUD text height %.1f px, focus edges %s." %
			[desktop.capture.viewport, desktop.height, desktop.capture.focus_edges]))

	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	var paused: bool = ui.screen == "paused" and _focused(view) == "resume" and not ui.pages.play.is_visible_in_tree()
	var paused_ticks := ui.activity.ticks
	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	var options_open := ui.screen == "settings" and _focused(view) == "large"
	_press(view, &"ui_accept")
	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	await _settle(tree)
	var pause_restore := ui.screen == "paused" and _focused(view) == "pause_options"
	var frozen := ui.activity.ticks == paused_ticks
	_press(view, &"ui_up")
	_press(view, &"ui_accept")
	await _settle(tree)
	var resumed := ui.screen == "play" and _focused(view) == "pause_game"
	checks.append(_check("pause-resume", paused and frozen and resumed and ui.activity.ticks > paused_ticks
			and ui.inspections == 1 and ui.attempts == 1,
			"Entered pause %s, ticks held %s, resumed at %s, inspections %d, attempt %d." %
			[paused, frozen, _focused(view), ui.inspections, ui.attempts]))

	view.size = Vector2i(1280, 720)
	await _settle(tree)
	var handheld := _profile(view, ui, "handheld-large-hud")
	checks.append(_check("handheld-layout", handheld.ok and handheld.capture.viewport == [1280, 720]
			and handheld.height > desktop.height and ui.large_text,
			"Handheld viewport %s, enlarged HUD text height %.1f px, focus edges %s." %
			[handheld.capture.viewport, handheld.height, handheld.capture.focus_edges]))

	ui.fail_attempt()
	var failure_focus := _focused(view)
	var failure: bool = ui.screen == "failed" and not ui.pages.play.is_visible_in_tree()
	_press(view, &"ui_accept")
	var retry_focus := _focused(view)
	var retried: bool = ui.screen == "play" and ui.activity.is_processing() and not ui.pages.failed.is_visible_in_tree()
	checks.append(_check("retry-state", failure and failure_focus == "retry" and retried and retry_focus == "inspect"
			and ui.attempts == 2 and ui.inspections == 0 and ui.controls.status.text == "Intake needs inspection" and ui.large_text,
			"Failure focus %s, retry focus %s, attempt %d, inspections reset to %d, large text %s." %
			[failure_focus, retry_focus, ui.attempts, ui.inspections, ui.large_text]))

	ui.fail_attempt()
	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	var title_clean := ui.screen == "title" and _focused(view) == "start"
	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	var saved: bool = ui.screen == "settings" and ui.controls.large.button_pressed and ui.controls.status.get_theme_font_size("font_size") == 30
	_press(view, &"ui_down")
	_press(view, &"ui_accept")
	checks.append(_check("settings-restore", options_open and pause_restore and title_clean and saved
			and ui.screen == "title" and _focused(view) == "title_options",
			"Pause opener restored %s, returned to title %s, enlarged setting retained %s, title focus %s." %
			[pause_restore, title_clean, saved, _focused(view)]))
	var metrics := {"attempts": ui.attempts, "desktop_text_height_px": desktop.height,
			"handheld_text_height_px": handheld.height, "capture": {"required_controls": ["inspect", "pause_game"],
			"profiles": [desktop.capture, handheld.capture]}}
	view.free()
	return {"id": "interface", "checks": checks, "metrics": metrics}
