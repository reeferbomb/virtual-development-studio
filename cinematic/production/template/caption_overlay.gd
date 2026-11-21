extends CanvasLayer

const MAX_CAPTION_WIDTH := 880.0
const SIDE_INSET := 0.06
const START_HINT := "Enter to start"

var _layout := VBoxContainer.new()
var _speaker := Label.new()
var _caption := Label.new()
var _status := Label.new()


func _init() -> void:
	layer = 20
	_layout.name = "CaptionLayout"
	_layout.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_layout.alignment = BoxContainer.ALIGNMENT_END
	_layout.add_theme_constant_override("separation", 4)
	add_child(_layout)
	_layout.anchor_left = 0.5
	_layout.anchor_right = 0.5
	_layout.anchor_top = 0.06
	_layout.anchor_bottom = 0.94

	_speaker.name = "Speaker"
	_configure_label(_speaker, Color(1.0, 0.86, 0.57))
	_caption.name = "Caption"
	_configure_label(_caption, Color.WHITE)
	var plate := StyleBoxFlat.new()
	plate.bg_color = Color(0.035, 0.045, 0.055, 0.92)
	plate.set_corner_radius_all(4)
	plate.content_margin_left = 16
	plate.content_margin_right = 16
	plate.content_margin_top = 8
	plate.content_margin_bottom = 8
	_caption.add_theme_stylebox_override("normal", plate)

	_status.name = "Status"
	_configure_label(_status, Color(0.94, 0.96, 1.0))
	clear_caption()


func _ready() -> void:
	get_viewport().size_changed.connect(_fit_width)
	_fit_width()


func _configure_label(label: Label, color: Color) -> void:
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_color_override("font_color", color)
	label.add_theme_color_override("font_outline_color", Color(0.02, 0.025, 0.03))
	label.add_theme_constant_override("outline_size", 4)
	_layout.add_child(label)


func _fit_width() -> void:
	var viewport_size := get_viewport().get_visible_rect().size
	var safe_width := viewport_size.x * (1.0 - 2.0 * SIDE_INSET)
	var width := minf(MAX_CAPTION_WIDTH, safe_width)
	_layout.offset_left = -width * 0.5
	_layout.offset_right = width * 0.5
	var scale_factor := clampf(minf(viewport_size.x / 720.0, viewport_size.y / 480.0), 0.65, 1.0)
	_caption.add_theme_font_size_override("font_size", roundi(25 * scale_factor))
	_speaker.add_theme_font_size_override("font_size", maxi(14, roundi(18 * scale_factor)))
	_status.add_theme_font_size_override("font_size", maxi(13, roundi(16 * scale_factor)))


func set_speaker(speaker: String) -> void:
	_speaker.text = speaker
	_speaker.visible = _caption.visible and not speaker.strip_edges().is_empty()


func show_caption(text: String, paused: bool, frame: int, total: int) -> void:
	_caption.text = text
	_caption.visible = not text.strip_edges().is_empty()
	_speaker.visible = _caption.visible and not _speaker.text.strip_edges().is_empty()
	var action := "Paused   ·   Space resume" if paused else "Space pause"
	_status.text = "%s   ·   S skip   ·   Escape interrupt   |   Frame %d/%d" % [action, frame, total]
	_status.show()


func clear_caption(available: bool = true) -> void:
	_caption.text = ""
	_caption.hide()
	set_speaker("")
	_status.text = START_HINT if available else ""
	_status.visible = available
