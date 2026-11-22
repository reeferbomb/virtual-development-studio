extends Control

signal retry_requested

const INK := Color("#182f30")
const GREEN := Color("#275957")
const PAPER := Color("#f1e8ce")
const MUTED := Color("#c4d1c5")
const BRASS := Color("#f1c774")
const JUNCTION := Vector2i(3, 3)
const WINCH := Vector2i(3, 2)
const STAIRS := Vector2i(3, 5)
const DRY_RACK := Vector2i(6, 5)
const DISPATCH := Vector2i(7, 3)

var modal_open := false
var large_text := false
var _mode := "play"
var _retry_from := "play"
var _pad := false
var _state := {}
var _type_sizes := {}
var _brief: VBoxContainer
var _yard: VBoxContainer
var _journal: VBoxContainer
var _confirm: VBoxContainer
var _heading: Label
var _clock: Label
var _weather: Label
var _objective: Label
var _route: Label
var _optional: Label
var _reward: Label
var _cart: Label
var _crew: Label
var _history: Label
var _prompt: Label
var _controls: Label
var _journal_button: Button
var _close_button: Button
var _size_button: Button
var _retry_button: Button
var _cancel_button: Button
var _confirm_button: Button


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var header := VBoxContainer.new()
	_panel(Rect2(780, 16, 468, 96), header)
	header.add_theme_constant_override("separation", 0)
	var title := _label(header, "GameTitle", 30, PAPER)
	title.text = "The Morning Crossing"
	var conditions := HBoxContainer.new()
	header.add_child(conditions)
	conditions.add_theme_constant_override("separation", 14)
	_weather = _label(conditions, "Weather", 17, BRASS)
	_clock = _label(conditions, "Clock", 17, MUTED)

	var stack := VBoxContainer.new()
	_panel(Rect2(780, 120, 468, 428), stack)
	_brief = _column(stack, "Brief", 6)
	_heading = _label(_brief, "Heading", 21, BRASS)
	_objective = _label(_brief, "Objective", 24, PAPER, true)
	_route = _label(_brief, "Route", 18, MUTED)
	_optional = _label(_brief, "Optional", 18, MUTED, true)
	_reward = _label(_brief, "Reward", 18, MUTED)
	_yard = _column(stack, "YardStatus", 6)
	var yard_title := _label(_yard, "YardHeading", 20, BRASS)
	yard_title.text = "Glassworks"
	_cart = _label(_yard, "Cart", 18, PAPER, true)
	_crew = _label(_yard, "Crew", 17, MUTED, true)
	_journal = _column(stack, "Journal", 5)
	_history = _label(_journal, "History", 17, MUTED, true)
	_close_button = _button(_journal, "Close", "Close journal", _close)
	_size_button = _button(_journal, "LargeText", "Text size: Standard", _toggle_text)
	_retry_button = _button(_journal, "Retry", "Restart shift…", _ask_retry)
	_confirm = _column(stack, "RetryDialog", 12)
	var retry_heading := _label(_confirm, "RetryTitle", 25, BRASS)
	retry_heading.text = "Restart this shift?"
	var consequence := _label(_confirm, "RetryExplanation", 20, PAPER, true)
	consequence.text = "Your route, completed stops and rewards will reset."
	_cancel_button = _button(_confirm, "CancelRetry", "Keep playing", _cancel_retry)
	_confirm_button = _button(_confirm, "ConfirmRetry", "Restart shift", _confirm_retry)
	_cycle([_close_button, _size_button, _retry_button])
	_cycle([_cancel_button, _confirm_button])

	var foot := VBoxContainer.new()
	_panel(Rect2(780, 556, 468, 148), foot)
	foot.add_theme_constant_override("separation", 6)
	_prompt = _label(foot, "Prompt", 18, PAPER, true)
	var inputs := HBoxContainer.new()
	foot.add_child(inputs)
	inputs.add_theme_constant_override("separation", 6)
	_controls = _label(inputs, "Controls", 16, MUTED, true)
	_controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_journal_button = _button(inputs, "OpenJournal", "Journal [J]", _open_journal)
	_journal_button.focus_mode = Control.FOCUS_NONE
	_update()


func _style(bg: Color, line: Color, border: int, h_margin: int, v_margin: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = bg
	box.border_color = line
	box.set_border_width_all(border)
	box.set_corner_radius_all(3)
	box.set_content_margin(SIDE_LEFT, h_margin)
	box.set_content_margin(SIDE_RIGHT, h_margin)
	box.set_content_margin(SIDE_TOP, v_margin)
	box.set_content_margin(SIDE_BOTTOM, v_margin)
	return box


func _panel(area: Rect2, content: Container) -> void:
	var panel := PanelContainer.new()
	add_child(panel)
	panel.position = area.position
	panel.size = area.size
	panel.add_theme_stylebox_override("panel", _style(INK, GREEN, 1, 16, 9))
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(content)
	if content is VBoxContainer:
		content.add_theme_constant_override("separation", 12)


func _place(parent: Node, node: Control, key: String) -> void:
	node.name = key
	parent.add_child(node)
	node.owner = self
	node.unique_name_in_owner = true


func _column(parent: Node, key: String, gap: int) -> VBoxContainer:
	var column := VBoxContainer.new()
	_place(parent, column, key)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_theme_constant_override("separation", gap)
	return column


func _label(parent: Node, key: String, px: int, color: Color, wrap := false) -> Label:
	var label := Label.new()
	_place(parent, label, key)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	if wrap:
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", color)
	label.add_theme_font_size_override("font_size", px)
	_type_sizes[label] = px
	return label


func _button(parent: Node, key: String, text: String, callback: Callable) -> Button:
	var button := Button.new()
	_place(parent, button, key)
	button.text = text
	button.custom_minimum_size.y = 38
	button.add_theme_font_size_override("font_size", 18)
	_type_sizes[button] = 18
	button.add_theme_color_override("font_color", PAPER)
	button.add_theme_stylebox_override("normal", _style(GREEN, GREEN, 1, 12, 4))
	button.add_theme_stylebox_override("hover", _style(Color("#386863"), BRASS, 1, 12, 4))
	button.add_theme_stylebox_override("pressed", _style(INK, BRASS, 2, 12, 4))
	var ring := _style(Color.TRANSPARENT, BRASS, 3, 0, 0)
	ring.draw_center = false
	button.add_theme_stylebox_override("focus", ring)
	button.pressed.connect(callback)
	return button


func _cycle(items: Array) -> void:
	for i in items.size():
		var button: Button = items[i]
		button.focus_neighbor_top = button.get_path_to(items[posmod(i - 1, items.size())])
		button.focus_neighbor_bottom = button.get_path_to(items[(i + 1) % items.size()])


func sync(snapshot: Dictionary) -> void:
	_state = snapshot
	if _objective != null:
		_update()


func _update() -> void:
	_brief.visible = _mode != "confirm"
	_journal.visible = _mode == "journal"
	_yard.visible = _mode == "play"
	_confirm.visible = _mode == "confirm"
	_journal_button.visible = _mode == "play"
	_heading.text = "Mission journal" if _mode == "journal" else "Current objective"
	_size_button.text = "Text size: Large" if large_text else "Text size: Standard"
	_journal_button.text = "Journal [Y]" if _pad else "Journal [J]"
	var discovered: bool = _state.get("discovered", false)
	var branch: String = _state.get("route", "none")
	var selected := discovered and branch in ["stairs", "platform"]
	var delivered: bool = _state.get("delivered", false)
	var done: bool = _state.get("optional_done", false)
	if delivered:
		_objective.text = "Chart delivered"
	elif selected:
		_objective.text = "Deliver the chart at Dispatch."
	elif discovered:
		_objective.text = "Choose a crossing at the winch or stairhead."
	else:
		_objective.text = "Inspect the cable junction."
	_route.visible = discovered
	_route.text = ("Route: " + branch.capitalize() if selected else "Route: Not selected") if discovered else ""
	_optional.visible = selected
	_optional.text = ("Optional: Dry rack checked" if done else "Optional: Check the dry rack") if selected else ""
	_reward.visible = selected
	_reward.text = "Reward: %d" % int(_state.get("reward", 0)) if selected else ""
	var rain: bool = _state.get("rain", false)
	_weather.text = "Rain" if rain else "Dry"
	_clock.text = "Shift %d  ·  Tick %d" % [int(_state.get("epoch", 0)), int(_state.get("tick", 0))]
	_cart.text = _cart_report()
	var workers: Array = _state.get("workers", [])
	_crew.text = "Crew: %d     Shipments: %d" % [workers.size(), int(_state.get("shipments", 0))]
	_history.text = _last_milestone()
	_history.visible = not _history.text.is_empty()
	if _mode == "play":
		_prompt.text = _play_prompt(discovered, selected, branch, delivered, done)
		_controls.text = "D-pad move  ·  X wait" if _pad else "WASD / arrows move  ·  Q wait"
	else:
		_prompt.text = "Select a journal action." if _mode == "journal" else "Confirm or keep the current shift."
		_controls.text = "D-pad select  ·  A confirm  ·  B back" if _pad else "↑/↓ select  ·  Enter confirm  ·  Esc back"


func _cart_report() -> String:
	if _state.get("cart_state", "idle") == "warning":
		return "Cart due at the junction on tick %d. Clear the crossing." % int(_state.get("cart_due_tick", 0))
	var resolved := int(_state.get("cart_resolved_tick", -100))
	if resolved >= 0 and int(_state.get("tick", 0)) - resolved <= 3:
		match _state.get("cart_last_result", "none"):
			"occupied": return "Cart arrival canceled: the junction was occupied."
			"arrival": return "The cart reached the junction."
	return "No cart warning."


func _last_milestone() -> String:
	var history: Array = _state.get("trace", [])
	for i in range(history.size() - 1, -1, -1):
		match history[i].get("event", ""):
			"platform-return": return "Rain returned you to the entry bank."
			"deliver": return "Dispatch received the chart."
			"optional-complete": return "The dry rack was checked."
			"choose-route": return "Crossing selected."
			"discover": return "Cable junction inspected."
	return ""


func _play_prompt(discovered: bool, selected: bool, branch: String, delivered: bool, done: bool) -> String:
	var pos: Array = _state.get("player", [2, 3])
	var cell := Vector2i(int(pos[0]), int(pos[1]))
	var use := "[A] " if _pad else "[E / Space] "
	if not discovered:
		return use + "Inspect junction" if cell == JUNCTION else "Find the cable junction."
	if not selected:
		if cell == WINCH:
			return use + "Choose platform crossing"
		if cell == STAIRS:
			return use + "Choose stair crossing"
		return "Visit the winch or the stairhead."
	if cell == DRY_RACK and not done:
		return use + "Check dry rack"
	if cell == DISPATCH and not delivered:
		return use + "Deliver chart"
	if delivered:
		return "Shift complete." if done else "The dry rack is still open."
	if branch == "platform" and not _state.get("platform_open", false):
		return "Platform closed by rain. Use the lower stairs or wait."
	return "Carry the chart to Dispatch."


func _show(mode: String, first: Button = null) -> void:
	_mode = mode
	modal_open = mode != "play"
	_update()
	if first != null:
		first.grab_focus()


func _open_journal() -> void:
	_show("journal", _close_button)


func _close() -> void:
	_show("play")


func _ask_retry() -> void:
	if _mode != "confirm":
		_retry_from = _mode
		_show("confirm", _cancel_button)


func _cancel_retry() -> void:
	if _retry_from == "journal":
		_show("journal", _retry_button)
	else:
		_close()


func _confirm_retry() -> void:
	if _mode == "confirm":
		_close()
		retry_requested.emit()


func _toggle_text() -> void:
	large_text = not large_text
	for control in _type_sizes:
		control.add_theme_font_size_override("font_size", int(_type_sizes[control]) + (4 if large_text else 0))
	_update()


func _modal_action(action: String) -> void:
	var items := [_cancel_button, _confirm_button] if _mode == "confirm" else [_close_button, _size_button, _retry_button]
	var current := items.find(get_viewport().gui_get_focus_owner())
	if action == "back":
		if _mode == "confirm":
			_cancel_retry()
		else:
			_close()
	elif action == "accept":
		if current >= 0:
			items[current].pressed.emit()
		else:
			items[0].grab_focus()
	elif action in ["up", "down"]:
		var delta := 1 if action == "down" else -1
		items[posmod(current + delta, items.size()) if current >= 0 else 0].grab_focus()


func handle(event: InputEvent) -> bool:
	if event is InputEventMouse:
		return false
	var action := ""
	var old_pad := _pad
	if event is InputEventKey:
		if not event.pressed or event.echo:
			return modal_open
		_pad = false
		var key: Key = event.physical_keycode if event.physical_keycode != KEY_NONE else event.keycode
		match key:
			KEY_J, KEY_TAB: action = "journal"
			KEY_R: action = "retry"
			KEY_ESCAPE, KEY_BACKSPACE: action = "back"
			KEY_ENTER, KEY_KP_ENTER, KEY_SPACE, KEY_E: action = "accept"
			KEY_UP, KEY_W: action = "up"
			KEY_DOWN, KEY_S: action = "down"
	elif event is InputEventJoypadButton:
		if not event.pressed:
			return modal_open
		_pad = true
		match event.button_index:
			JOY_BUTTON_Y: action = "journal"
			JOY_BUTTON_START: action = "retry"
			JOY_BUTTON_B: action = "back"
			JOY_BUTTON_A: action = "accept"
			JOY_BUTTON_DPAD_UP: action = "up"
			JOY_BUTTON_DPAD_DOWN: action = "down"
	elif event is InputEventAction and event.pressed:
		match event.action:
			&"ui_up": action = "up"
			&"ui_down": action = "down"
			&"ui_accept": action = "accept"
			&"ui_cancel": action = "back"
	if old_pad != _pad:
		_update()
	if action == "journal":
		if modal_open:
			_close()
		else:
			_open_journal()
		return true
	if action == "retry":
		_ask_retry()
		return true
	if modal_open:
		_modal_action(action)
		return true
	return false
