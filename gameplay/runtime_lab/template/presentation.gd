extends RefCounted
## An original flood-relief gallery. All geometry, labels and audio are created in memory.


class ReliefGallery extends Node2D:
	const CUE_DELAY := 0.15
	const PULSE_TIME := 0.30
	const CAPTION_TAIL := 1.15
	const WAITING := "Float down  /  Awaiting flow"
	const CLEAR := "Float up  /  Channel clear"
	const BELL_CAPTION := "[Bell rings once] Relief channel clear."

	var flood_mark: Line2D
	var repair_tag: Label
	var patch: Polygon2D
	var float_marker: Polygon2D
	var status_text: Label
	var caption: Label
	var bell: AudioStreamPlayer
	var ripple: Line2D
	var sequence: Tween
	var active := false
	var reduced_motion := false
	var captions_on := true
	var cue_count := 0
	var pulse_count := 0

	func _line(title: String, vertices: PackedVector2Array, tint: Color, thickness: float) -> Line2D:
		var line := Line2D.new()
		line.name = title
		line.points = vertices
		line.default_color = tint
		line.width = thickness
		add_child(line)
		return line

	func _shape(title: String, vertices: PackedVector2Array, tint: Color) -> Polygon2D:
		var shape := Polygon2D.new()
		shape.name = title
		shape.polygon = vertices
		shape.color = tint
		add_child(shape)
		return shape

	func _label(title: String, words: String, at: Vector2, font_size: int) -> Label:
		var label := Label.new()
		label.name = title
		label.text = words
		label.position = at
		label.add_theme_font_size_override("font_size", font_size)
		add_child(label)
		return label

	func _make_bell() -> AudioStreamWAV:
		const RATE := 22050
		var frames := roundi(RATE * PULSE_TIME)
		var pcm := PackedByteArray()
		pcm.resize(frames * 2)
		for sample in range(frames):
			var t := float(sample) / RATE
			var attack := minf(1.0, t / 0.006)
			var tail := maxf(0.0, 1.0 - float(sample) / (frames - 1))
			var tone := sin(TAU * 510.0 * t) + 0.26 * sin(TAU * 972.0 * t)
			pcm.encode_s16(sample * 2, roundi(6000.0 * attack * tail * tail * tone))
		var voice := AudioStreamWAV.new()
		voice.format = AudioStreamWAV.FORMAT_16_BITS
		voice.mix_rate = RATE
		voice.stereo = false
		voice.data = pcm
		return voice

	func _ready() -> void:
		var iron := Color("#48636a")
		var chalk := Color("#e8c995")
		_shape("Masonry", PackedVector2Array([
			Vector2(28, 20), Vector2(528, 20), Vector2(528, 276), Vector2(28, 276)
		]), Color("#253639"))
		_line("ReliefPipe", PackedVector2Array([
			Vector2(48, 160), Vector2(228, 160), Vector2(278, 208), Vector2(490, 208)
		]), iron, 17.0)
		# The flood stain predates a visible patch in the descending run of pipe.
		flood_mark = _line("HighWaterMark", PackedVector2Array([
			Vector2(42, 112), Vector2(83, 112), Vector2(91, 109), Vector2(149, 110)
		]), chalk, 3.0)
		_label("MarkInscription", "Last flood", Vector2(47, 113), 15)
		patch = _shape("GasketClamp", PackedVector2Array([
			Vector2(-14, -7), Vector2(8, -7), Vector2(14, 7), Vector2(-8, 7)
		]), Color("#d69a65"))
		patch.position = Vector2(252, 184)
		_line("TagCord", PackedVector2Array([patch.position, Vector2(264, 135)]), chalk, 2.0)
		repair_tag = _label("RepairTag", "Bypass gasket replaced\nDawn shift", Vector2(261, 94), 16)
		_line("FloatGuide", PackedVector2Array([Vector2(119, 179), Vector2(119, 229)]), chalk, 2.0)
		float_marker = _shape("Float", PackedVector2Array([
			Vector2(-11, 0), Vector2(0, -7), Vector2(11, 0), Vector2(0, 7)
		]), Color("#99dad0"))
		float_marker.position = Vector2(119, 223)
		status_text = _label("Indicator", WAITING, Vector2(43, 42), 23)
		caption = _label("CueCaption", "", Vector2(42, 241), 17)
		caption.hide()
		bell = AudioStreamPlayer.new()
		bell.name = "ReliefBell"
		bell.stream = _make_bell()
		bell.volume_db = -8.0
		add_child(bell)

	func begin(quiet_motion: bool, display_captions: bool) -> bool:
		if active:
			return false
		reduced_motion = quiet_motion
		captions_on = display_captions
		active = true
		status_text.text = WAITING
		float_marker.position.y = 223
		sequence = create_tween()
		sequence.tween_interval(CUE_DELAY)
		sequence.tween_callback(_announce)
		if reduced_motion:
			sequence.tween_interval(PULSE_TIME)
		else:
			sequence.tween_method(_move_ripple, 0.0, 1.0, PULSE_TIME)
		sequence.tween_callback(_end_pulse)
		sequence.tween_interval(CAPTION_TAIL)
		sequence.tween_callback(_complete)
		return true

	func _announce() -> void:
		cue_count += 1
		status_text.text = CLEAR
		float_marker.position.y = 186
		bell.play()
		if captions_on:
			caption.text = BELL_CAPTION
			caption.show()
		if not reduced_motion:
			pulse_count += 1
			ripple = _line("OutletRipple", PackedVector2Array([
				Vector2(-12, 2), Vector2(-6, -1), Vector2(0, 1), Vector2(6, -1), Vector2(12, 2)
			]), Color("#a8e3db"), 2.0)
			ripple.position = Vector2(457, 218)

	func _move_ripple(progress: float) -> void:
		if is_instance_valid(ripple):
			ripple.scale.x = 1.0 + 1.5 * progress
			ripple.modulate.a = 1.0 - progress

	func _end_pulse() -> void:
		bell.stop()
		if is_instance_valid(ripple):
			ripple.hide()
			ripple.queue_free()
			ripple = null

	func _complete() -> void:
		caption.hide()
		caption.text = ""
		active = false
		sequence = null

	func interrupt() -> void:
		if not active:
			return
		sequence.kill()
		_end_pulse()
		_complete()
		status_text.text = WAITING
		float_marker.position.y = 223


func _check(key: String, passed: bool, detail: String) -> Dictionary:
	return {"id": key, "passed": passed, "detail": detail}


func run(tree: SceneTree) -> Dictionary:
	var scene := ReliefGallery.new()
	scene.name = "TidalReliefGallery"
	tree.root.add_child(scene)
	# A SceneTree runner may itself be entering the tree during initialization.
	if not scene.is_node_ready():
		await scene.ready
	var checks: Array[Dictionary] = []
	var cord := scene.get_node("TagCord") as Line2D
	var inscription := scene.get_node("MarkInscription") as Label
	var wall_marked := (scene.flood_mark.is_visible_in_tree() and scene.flood_mark.get_point_count() == 4
		and scene.flood_mark.get_point_position(0).y < scene.patch.position.y
		and inscription.text == "Last flood")
	var tag_attached := (scene.repair_tag.is_visible_in_tree() and scene.repair_tag.text.contains("Bypass gasket")
		and cord.get_point_position(0).is_equal_approx(scene.patch.position)
		and scene.patch.is_visible_in_tree())
	checks.append(_check("environment-clues", wall_marked and tag_attached,
		"High-water line is above the pipe repair. Its clamp anchors the cord of the dawn-shift maintenance tag."))

	scene.begin(false, true)
	# Pausing and manually stepping the actual engine tween makes boundary probes independent of render rate.
	var full := scene.sequence
	full.pause()
	full.custom_step(0.149)
	var before_cue := (scene.cue_count == 0 and not scene.bell.playing and not scene.caption.visible
		and scene.status_text.text == scene.WAITING)
	var reentry_blocked := not scene.begin(false, true)
	full.custom_step(0.002)
	var pcm := scene.bell.stream as AudioStreamWAV
	var audio_started := scene.bell.playing
	var announced := (scene.cue_count == 1 and audio_started and pcm.mix_rate == 22050
		and absf(pcm.get_length() - scene.PULSE_TIME) < 0.001 and scene.status_text.text == scene.CLEAR
		and scene.caption.is_visible_in_tree() and scene.caption.text == scene.BELL_CAPTION)
	checks.append(_check("cue-onset", before_cue and reentry_blocked and announced,
		"Waiting at 149 ms=%s. At 151 ms one cue started the bell and showed the caption=%s. Reentry blocked=%s." % [
			before_cue, announced, reentry_blocked]))

	var pulse_ref: WeakRef
	var first_scale := 0.0
	if is_instance_valid(scene.ripple):
		pulse_ref = weakref(scene.ripple)
		first_scale = scene.ripple.scale.x
	full.custom_step(0.17)
	var second_scale := scene.ripple.scale.x if is_instance_valid(scene.ripple) else 0.0
	var fading := scene.ripple.modulate.a if is_instance_valid(scene.ripple) else 0.0
	var moved := first_scale >= 1.0 and second_scale > first_scale and fading > 0.0 and fading < 1.0
	full.custom_step(0.20)
	var pulse_ended := not scene.bell.playing and not is_instance_valid(scene.ripple) and scene.caption.visible
	await tree.process_frame
	await tree.process_frame
	checks.append(_check("effect-lifetime", moved and pulse_ended and pulse_ref != null and pulse_ref.get_ref() == null,
		"Outlet ripple expanded and faded. Its node was freed and audio stopped while the caption remained visible."))

	full.custom_step(1.20)
	var natural := (not scene.active and not scene.caption.visible and scene.caption.text.is_empty()
		and not scene.bell.playing and scene.status_text.text == scene.CLEAR and scene.float_marker.position.y == 186)
	checks.append(_check("normal-completion", natural,
		"Completion cleared the transient caption and retained the raised float and final static sign."))

	scene.begin(false, true)
	var early := scene.sequence
	early.pause()
	early.custom_step(0.08)
	scene.interrupt()
	var early_clean := (not early.is_valid() and not scene.active and scene.cue_count == 1
		and not scene.bell.playing and not scene.caption.visible and scene.status_text.text == scene.WAITING)
	scene.begin(false, true)
	var during := scene.sequence
	during.pause()
	during.custom_step(0.24)
	var interrupt_pulse: WeakRef
	if is_instance_valid(scene.ripple):
		interrupt_pulse = weakref(scene.ripple)
	var live := scene.bell.playing and scene.caption.visible and is_instance_valid(scene.ripple)
	scene.interrupt()
	await tree.process_frame
	await tree.process_frame
	var late_clean := (not during.is_valid() and not scene.active and not scene.bell.playing
		and not scene.caption.visible and scene.caption.text.is_empty()
		and interrupt_pulse != null and interrupt_pulse.get_ref() == null
		and scene.status_text.text == scene.WAITING and scene.float_marker.position.y == 223)
	checks.append(_check("interruption", early_clean and live and late_clean,
		"Interrupt before the cue suppressed it. Interrupt during the cue stopped audio, freed its ripple and restored the waiting sign."))

	var prior_pulses := scene.pulse_count
	var retry_started := scene.begin(true, true)
	var reduced := scene.sequence
	reduced.pause()
	reduced.custom_step(0.30)
	var reduced_ok := (retry_started and scene.pulse_count == prior_pulses and not is_instance_valid(scene.ripple)
		and scene.status_text.text == scene.CLEAR and scene.float_marker.position.y == 186
		and scene.caption.text == scene.BELL_CAPTION and scene.caption.is_visible_in_tree() and scene.bell.playing)
	reduced.custom_step(1.50)
	scene.begin(true, false)
	var captions_off := scene.sequence
	captions_off.pause()
	captions_off.custom_step(0.30)
	var sign_only := (not scene.caption.visible and scene.caption.text.is_empty() and scene.status_text.text == scene.CLEAR
		and not is_instance_valid(scene.ripple) and scene.pulse_count == prior_pulses)
	scene.interrupt()
	checks.append(_check("accessible-alternatives", reduced_ok and sign_only,
		"Reduced motion kept the static float and sign without a ripple. The sound caption honored its own setting."))

	var metrics := {"cue_delay_ms": roundi(scene.CUE_DELAY * 1000.0), "ripple_duration_ms": roundi(scene.PULSE_TIME * 1000.0),
		"caption_duration_ms": roundi((scene.PULSE_TIME + scene.CAPTION_TAIL) * 1000.0),
		"bell_sample_rate_hz": pcm.mix_rate, "bell_sample_frames": pcm.data.size() / 2,
		"cue_starts": scene.cue_count, "ripples_created": scene.pulse_count, "sampled_ripple_scale_x": second_scale}
	var scene_ref: WeakRef = weakref(scene)
	var player_ref: WeakRef = weakref(scene.bell)
	var wave_ref: WeakRef = weakref(pcm)
	pcm = null
	scene.queue_free()
	await tree.process_frame
	await tree.process_frame
	# The mixer can own stopped playback until its next audio buffers have drained.
	# Poll the actual resource so a runner can quit immediately after this module.
	var deadline := Time.get_ticks_msec() + 1500
	while wave_ref.get_ref() != null and Time.get_ticks_msec() < deadline:
		await tree.process_frame
	var released := scene_ref.get_ref() == null and player_ref.get_ref() == null and wave_ref.get_ref() == null
	checks.append(_check("scene-cleanup", released,
		"Gallery, player and source wave released after the last interrupted take=%s." % released))
	return {"id": "presentation", "checks": checks, "metrics": metrics}
