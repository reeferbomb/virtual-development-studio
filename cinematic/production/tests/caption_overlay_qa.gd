extends SceneTree
## godot --headless --path GENERATED --script /absolute/path/to/caption_overlay_qa.gd

const Overlay = preload("res://caption_overlay.gd")
const SAMPLE := "[b]Seal the gate.[/b] We have one more relay to bring online before the water reaches the stairwell."
const SIZES := [Vector2i(1920, 1080), Vector2i(640, 360), Vector2i(320, 570), Vector2i(1024, 450), Vector2i(280, 240)]

var errors: Array[String] = []


func _initialize() -> void:
	check_overlay.call_deferred()


func check(condition: bool, message: String) -> void:
	if not condition:
		errors.append(message)


func check_overlay() -> void:
	var viewport := SubViewport.new()
	root.add_child(viewport)
	var overlay := Overlay.new()
	viewport.add_child(overlay)
	var layout: VBoxContainer = overlay.get_node("CaptionLayout")
	var speaker: Label = layout.get_node("Speaker")
	var caption: Label = layout.get_node("Caption")
	var status: Label = layout.get_node("Status")
	check(status.visible and status.text.contains("Enter") and not caption.visible, "initial prompt")
	for control in [layout, speaker, caption, status]:
		check(control.mouse_filter == Control.MOUSE_FILTER_IGNORE, "mouse pass-through")
		check(control.focus_mode == Control.FOCUS_NONE, "keyboard focus")

	overlay.set_speaker("Mara")
	overlay.show_caption(SAMPLE, false, 12, 144)
	check(speaker.visible and speaker.text == "Mara", "speaker label")
	check(caption.visible and caption.text == SAMPLE, "literal subtitle")
	for cue in ["Space pause", "S skip", "Escape interrupt", "12/144"]:
		check(status.text.contains(cue), "missing active cue " + cue)

	for dimensions in SIZES:
		viewport.size = dimensions
		# Let the container resolve widths, wrap the text, and apply its new heights.
		for _pass in 4:
			await process_frame
		var bounds := Rect2(Vector2.ZERO, Vector2(dimensions))
		var subtitle_rect := caption.get_global_rect()
		var status_rect := status.get_global_rect()
		var speaker_rect := speaker.get_global_rect()
		for rect in [subtitle_rect, status_rect, speaker_rect]:
			check(bounds.encloses(rect), "label outside viewport %s" % dimensions)
		check(subtitle_rect.size.x <= 881, "maximum caption width at %s" % dimensions)
		check(subtitle_rect.position.x >= dimensions.x * 0.05, "side inset at %s" % dimensions)
		check(speaker_rect.end.y <= subtitle_rect.position.y, "speaker overlap at %s" % dimensions)
		check(subtitle_rect.end.y <= status_rect.position.y, "controls overlap at %s" % dimensions)
		check(status_rect.end.y <= dimensions.y * 0.95 + 1, "bottom inset at %s" % dimensions)

	overlay.show_caption("  ", true, 12, 144)
	check(not caption.visible and not speaker.visible, "whitespace cue")
	check(status.visible and status.text.contains("Paused") and status.text.contains("Space resume"), "paused prompt")
	overlay.clear_caption(false)
	check(not caption.visible and not speaker.visible and not status.visible, "replay lock")
	overlay.clear_caption()
	check(status.visible and status.text.contains("Enter"), "return to gameplay")
	check(caption.text.is_empty() and speaker.text.is_empty(), "stale dialogue")
	viewport.queue_free()
	await process_frame
	for message in errors:
		push_error(message)
	print("CAPTION_LAYOUT_QA ", "passed" if errors.is_empty() else "failed")
	quit(0 if errors.is_empty() else 1)
