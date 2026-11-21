extends SceneTree

const DOCUMENT := "res://production.json"
const CITY_ASSET := "res://assets/city.glb"
const ACTOR_ASSET := "res://assets/animated_actor.glb"
const CUE_ASSET := "res://assets/footstep.wav"

class GameplayFallback:
	extends Node
	var presses: Array[Key] = []

	func _unhandled_input(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed:
			presses.append(event.keycode)

var fallback := GameplayFallback.new()
var checks: Array[Dictionary] = []
var plan: Dictionary
var bindings: Dictionary
var stage
var skeletons: Dictionary = {}
var reference_actor: Node3D
var reference_player: AnimationPlayer
var reference_rig: Skeleton3D
var caption_label: Label
var speaker_label: Label
var scratch_stream: AudioStreamWAV
var finished := false

func _initialize() -> void:
	call_deferred("run")

func check(id: String, name_: String, ok: bool, detail: String) -> void:
	checks.append({"id": id, "name": name_, "status": "passed" if ok else "failed", "detail": detail})

func finish() -> void:
	if finished:
		return
	finished = true
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	if is_instance_valid(stage):
		stage.free()
	if is_instance_valid(reference_actor):
		reference_actor.free()
	fallback.free()
	scratch_stream = null
	# Let the audio mixer release stopped playbacks before the headless process exits.
	await create_timer(0.35).timeout
	var digest := FileAccess.get_sha256(DOCUMENT) if FileAccess.file_exists(DOCUMENT) else ""
	print("STUDIO_PRODUCTION_QA_JSON " + JSON.stringify({
		"schema_version": 1, "production_sha256": digest, "pass": ok, "checks": checks}))
	quit(0 if ok else 1)

func timed_out() -> void:
	if not finished:
		check("timeout", "Engine QA completed", false, "Playback checks stopped before completion.")
		finish()

func fresh_stage(scene: PackedScene) -> void:
	if is_instance_valid(stage):
		stage.free()
	skeletons.clear()
	stage = scene.instantiate()
	root.add_child(stage)
	stage.set_process(false)

func vec(values: Array) -> Vector3:
	return Vector3(values[0], values[1], values[2])

# Compare the real camera transforms, instances and skin resources with the bindings.
func inspect_bindings() -> String:
	if not stage.gameplay_camera is Camera3D or not stage.gameplay is Node3D:
		return "Gameplay camera or input receiver is missing."
	if not stage.cue_player is AudioStreamPlayer or not stage.overlay is CanvasLayer:
		return "Audio player or caption overlay is missing."
	var city_found := false
	for child in stage.get_children():
		if child.scene_file_path == CITY_ASSET and not child.find_children("*", "MeshInstance3D", true, false).is_empty():
			city_found = true
	if not city_found:
		return "The imported city has no instantiated meshes."
	# The director duplicates the resource to loop it. Compare the sampled bytes, not its path.
	var imported_wav := load(CUE_ASSET) as AudioStreamWAV
	scratch_stream = stage.cue_player.stream as AudioStreamWAV
	if imported_wav == null or scratch_stream == null or scratch_stream.data.is_empty():
		return "No imported scratch WAV is bound."
	if scratch_stream.data != imported_wav.data or scratch_stream.format != imported_wav.format or scratch_stream.mix_rate != imported_wav.mix_rate or scratch_stream.stereo != imported_wav.stereo:
		return "Scratch cue differs from the expected WAV data or format."
	if scratch_stream.loop_mode != AudioStreamWAV.LOOP_FORWARD or scratch_stream.loop_begin != 0 or scratch_stream.loop_end != roundi(imported_wav.get_length() * imported_wav.mix_rate):
		return "Scratch cue does not loop over the complete source recording."
	speaker_label = stage.overlay.get_node_or_null("CaptionLayout/Speaker") as Label
	caption_label = stage.overlay.get_node_or_null("CaptionLayout/Caption") as Label
	if caption_label == null or speaker_label == null:
		return "Caption label is missing."
	var seen_cameras := [stage.gameplay_camera]
	for id in plan.cameras:
		var camera := stage.cameras.get(id) as Camera3D
		if camera == null or camera in seen_cameras or not stage.is_ancestor_of(camera):
			return "Missing or reused Camera3D for %s." % id
		seen_cameras.append(camera)
		var binding: Dictionary = bindings.cameras[id]
		var eye := vec(binding.position)
		var direction := eye.direction_to(vec(binding.look_at))
		if not camera.global_position.is_equal_approx(eye) or not is_equal_approx(camera.fov, binding.fov) or (-camera.global_basis.z).dot(direction) < 0.9999:
			return "Camera %s differs from its declared position, target or field of view." % id
	var seen_actors := []
	for id in plan.actors:
		var actor := stage.actors.get(id) as Node3D
		var player := stage.animations.get(id) as AnimationPlayer
		if actor == null or actor in seen_actors or actor.scene_file_path != ACTOR_ASSET:
			return "Missing or reused imported actor for %s." % id
		seen_actors.append(actor)
		if player == null or not actor.is_ancestor_of(player) or not stage.is_ancestor_of(actor):
			return "AnimationPlayer for %s is detached from its model." % id
		var binding: Dictionary = bindings.actors[id]
		var facing := Basis(Vector3.UP, deg_to_rad(binding.rotation_y))
		if not actor.global_position.is_equal_approx(vec(binding.position)) or not actor.global_basis.orthonormalized().is_equal_approx(facing):
			return "Actor %s differs from its declared position or yaw." % id
		var rigs := actor.find_children("*", "Skeleton3D", true, false)
		if rigs.size() != 1 or rigs[0].get_bone_count() == 0:
			return "No imported skeleton for %s." % id
		var skinned := false
		for mesh in actor.find_children("*", "MeshInstance3D", true, false):
			if mesh.skin != null and mesh.get_node_or_null(mesh.skeleton) == rigs[0]:
				skinned = true
		if not skinned:
			return "No mesh is bound to the skeleton of %s." % id
		skeletons[id] = rigs[0]
	return ""

func row_at(rows: Array, frame: int) -> Dictionary:
	for row in rows:
		if int(row.start_frame) <= frame and frame < int(row.end_frame):
			return row
	return {}

func send_key(code: Key) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = true
	root.push_input(event, true)
	var release := InputEventKey.new()
	release.keycode = code
	root.push_input(release, true)

func key_reaches_gameplay(code: Key) -> bool:
	fallback.presses.clear()
	send_key(code)
	return fallback.presses == [code]

func input_moves() -> bool:
	var before: Vector3 = stage.gameplay.position
	send_key(KEY_RIGHT)
	var moved := not before.is_equal_approx(stage.gameplay.position)
	send_key(KEY_LEFT)
	return moved

func clean_handoff(story: String) -> bool:
	var state: Dictionary = stage.snapshot()
	return (not state.active and not state.paused and state.story_state == story
		and state.camera_id == "gameplay" and root.get_camera_3d() == stage.gameplay_camera
		and state.input_enabled and stage.gameplay.is_processing_unhandled_input() and input_moves()
		and state.caption == "" and caption_label.text == "" and not caption_label.is_visible_in_tree()
		and speaker_label.text == "" and not speaker_label.is_visible_in_tree()
		and not state.cue_playing and not stage.cue_player.playing and not stage.cue_player.stream_paused)

func timeline_error(frame: int) -> String:
	var state: Dictionary = stage.snapshot()
	if not state.active or state.paused or int(state.frame) != frame or state.story_state != plan.trigger.requires:
		return "Playback clock or guarded story state differs."
	if state.input_enabled or stage.gameplay.is_processing_unhandled_input():
		return "Gameplay input is enabled during the sequence."
	var shot := row_at(plan.shots, frame)
	if shot.is_empty() or state.camera_id != shot.camera or root.get_camera_3d() != stage.cameras[shot.camera]:
		return "Viewport does not own the planned shot camera."
	var caption := row_at(plan.subtitles, frame)
	var expected_text: String = caption.get("text", "")
	if state.caption != expected_text or caption_label.text != expected_text or caption_label.is_visible_in_tree() != (not caption.is_empty()):
		return "Caption text or visibility differs from the subtitle track."
	var dialogue := row_at(plan.dialogue, frame)
	var voiced := not dialogue.is_empty()
	var speaker := str(dialogue.get("speaker", "")).capitalize()
	if speaker_label.text != speaker or speaker_label.is_visible_in_tree() != voiced:
		return "Speaker attribution differs from the dialogue track."
	if state.cue_playing != voiced or stage.cue_player.playing != voiced or stage.cue_player.stream_paused:
		return "Scratch audio playback differs from the dialogue window."
	if voiced and stage.cue_player.stream != scratch_stream:
		return "The dialogue window did not bind the expected scratch WAV."
	return ""

# A second copy of the same GLB evaluates each authored pose independently of the director.
func pose_error(frame: int) -> String:
	var active_clips: Dictionary = stage.snapshot().actor_clips
	var blocking := {}
	for cue in plan.blocking:
		if int(cue.start_frame) <= frame and frame < int(cue.end_frame):
			blocking[cue.actor] = cue
	for actor in plan.actors:
		var cue: Dictionary = blocking.get(actor, {})
		var clip: String = cue.get("clip", "")
		var player: AnimationPlayer = stage.animations[actor]
		if active_clips.get(actor, "") != clip:
			return "%s reported %s, expected %s." % [actor, active_clips.get(actor, ""), clip]
		if cue.is_empty():
			if player.is_playing():
				return "%s played outside its blocking window." % actor
			var idle_rig: Skeleton3D = skeletons[actor]
			for bone in idle_rig.get_bone_count():
				if not idle_rig.get_bone_pose(bone).is_equal_approx(idle_rig.get_bone_rest(bone)):
					return "%s retained an animated pose outside its blocking window." % actor
			continue
		var imported := clip.capitalize()
		if player.current_animation != imported or not reference_player.has_animation(imported):
			return "%s did not play the imported %s animation." % [actor, imported]
		var resource := reference_player.get_animation(imported)
		var time := fmod(float(frame - int(cue.start_frame)) / float(plan.fps), resource.length)
		# GLB clip length is stored as a float; intended wraps can land just below the end.
		if is_equal_approx(time, resource.length):
			time = 0.0
		if not is_equal_approx(player.current_animation_position, time):
			return "%s animation clock differs for %s." % [actor, imported]
		reference_player.play(imported)
		reference_player.advance(0)
		reference_player.seek(time, true)
		var rig: Skeleton3D = skeletons[actor]
		for bone in reference_rig.get_bone_count():
			if not rig.get_bone_pose(bone).is_equal_approx(reference_rig.get_bone_pose(bone)):
				return "%s bone %s differs from the imported %s pose." % [actor, rig.get_bone_name(bone), imported]
	return ""

func sample_frames() -> Array:
	var total := int(plan.frame_count)
	var frames := {0: true, total - 1: true}
	for lane in [plan.shots, plan.subtitles, plan.dialogue, plan.blocking]:
		for cue in lane:
			var start := int(cue.start_frame)
			var end := int(cue.end_frame)
			# Sample both sides of each transition, plus interior poses and the middle of long holds.
			for n in [start - 1, start, start + 1, start + 3, start + 7, floori((start + end) * 0.5), end - 1, end]:
				if n >= 0 and n < total:
					frames[n] = true
	var ordered := frames.keys()
	ordered.sort()
	return ordered

func check_full_playback() -> void:
	var frames := sample_frames()
	var timeline_issue := ""
	var pose_issue := ""
	var previous := 0
	var cue_playbacks := {}
	for frame in frames:
		stage.advance_frames(frame - previous)
		previous = frame
		if timeline_issue.is_empty():
			var issue := timeline_error(frame)
			var dialogue := row_at(plan.dialogue, frame)
			if issue.is_empty() and not dialogue.is_empty():
				var playback := stage.cue_player.get_stream_playback() as AudioStreamPlayback
				if playback == null:
					issue = "A voiced frame has no engine audio playback."
				else:
					var playback_id := playback.get_instance_id()
					if cue_playbacks.has(dialogue.line) and cue_playbacks[dialogue.line] != playback_id:
						issue = "Scratch audio restarted inside one line."
					elif not cue_playbacks.has(dialogue.line) and playback_id in cue_playbacks.values():
						issue = "Scratch audio did not restart for the new line."
					cue_playbacks[dialogue.line] = playback_id
			if not issue.is_empty():
				timeline_issue = "Frame %d: %s" % [frame, issue]
		if pose_issue.is_empty():
			var issue := pose_error(frame)
			if not issue.is_empty():
				pose_issue = "Frame %d: %s" % [frame, issue]
	check("timeline", "Shot, caption and audio windows", timeline_issue.is_empty(),
		"Verified %d distinct frame samples." % frames.size() if timeline_issue.is_empty() else timeline_issue)
	check("skeletal-motion", "Imported animation clocks and skeletal poses", pose_issue.is_empty(),
		"Compared blocking against a separately sampled imported rig at %d frame samples." % frames.size() if pose_issue.is_empty() else pose_issue)
	stage.advance_frames(1)
	check("completion", "Normal completion and gameplay return", clean_handoff(plan.exits.complete.next_state)
		and int(stage.snapshot().frame) == int(plan.frame_count), "Advanced exactly one frame beyond the last visible sample.")
	check("completion-guard", "Completed sequence rejects repeat entry", not stage.start(plan.trigger.event)
		and key_reaches_gameplay(KEY_ENTER) and clean_handoff(plan.exits.complete.next_state), "Repeated the original trigger after completion.")

func run() -> void:
	create_timer(15).timeout.connect(timed_out)
	var document = JSON.parse_string(FileAccess.get_file_as_string(DOCUMENT))
	var scene := load("res://production.tscn") as PackedScene
	var actor_scene := load(ACTOR_ASSET) as PackedScene
	var readable: bool = scene != null and actor_scene != null and document is Dictionary and document.get("schema_version") == 1 and document.get("plan") is Dictionary and document.get("bindings") is Dictionary
	check("production-scene", "Production scene and source document", readable, "Loaded the compiled timeline and the Godot scene resources.")
	if not readable:
		finish()
		return
	plan = document.plan
	bindings = document.bindings
	# Godot dispatches unhandled input in reverse tree order. This receiver follows the director.
	root.add_child(fallback)
	fresh_stage(scene)
	var binding_issue := inspect_bindings()
	check("bindings", "Imported skinned actors and distinct camera bindings", binding_issue.is_empty(),
		"Verified city geometry, scratch WAV, %d actor models and %d cameras." % [plan.actors.size(), plan.cameras.size()] if binding_issue.is_empty() else binding_issue)
	if not binding_issue.is_empty():
		finish()
		return
	reference_actor = actor_scene.instantiate()
	root.add_child(reference_actor)
	reference_actor.hide()
	reference_player = reference_actor.find_children("*", "AnimationPlayer", true, false)[0]
	reference_rig = reference_actor.find_children("*", "Skeleton3D", true, false)[0]
	reference_player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	var event: String = plan.trigger.event
	check("wrong-trigger", "Unrelated event preserves gameplay", not stage.start(event + "-unrelated")
		and clean_handoff(plan.trigger.requires) and key_reaches_gameplay(KEY_SPACE)
		and key_reaches_gameplay(KEY_S) and key_reaches_gameplay(KEY_ESCAPE),
		"Checked the rejected event and inactive key propagation to a gameplay receiver.")
	check("entry", "Guarded entry and gameplay lock", not key_reaches_gameplay(KEY_ENTER) and timeline_error(0).is_empty()
		and not stage.start(event) and not input_moves(), "Checked frame zero, active re-entry and a real movement key.")
	var voiced_frame := int(plan.dialogue[0].start_frame)
	stage.advance_frames(voiced_frame)
	var cue_started: bool = timeline_error(voiced_frame).is_empty() and stage.cue_player.playing
	var consumed_pause := not key_reaches_gameplay(KEY_SPACE)
	stage.advance_frames(int(plan.frame_count))
	var held: Dictionary = stage.snapshot()
	check("pause", "Pause holds picture, captions and scratch sound", cue_started and consumed_pause and held.active and held.paused
		and int(held.frame) == voiced_frame and stage.cue_player.stream_paused
		and root.get_camera_3d() == stage.cameras[row_at(plan.shots, voiced_frame).camera]
		and caption_label.is_visible_in_tree() and caption_label.text == plan.dialogue[0].text
		and pose_error(voiced_frame).is_empty(), "Paused inside dialogue at frame %d and advanced an entire edit." % voiced_frame)
	stage.set_paused(false)
	check("resume", "Resume keeps the held frame", timeline_error(voiced_frame).is_empty(), "Checked the active cue and picture after resuming.")
	var consumed_skip := not key_reaches_gameplay(KEY_S)
	check("skip", "Skip during dialogue restores gameplay", consumed_skip and clean_handoff(plan.exits.skip.next_state), "Checked the viewport, movement input, story, caption and audio.")
	check("skip-guard", "Skipped sequence rejects repeat entry", not stage.start(event) and key_reaches_gameplay(KEY_ENTER) and clean_handoff(plan.exits.skip.next_state), "Repeated the original trigger after skipping.")
	fresh_stage(scene)
	binding_issue = inspect_bindings()
	if not binding_issue.is_empty():
		check("interrupt", "Fresh gameplay scene for interruption", false, binding_issue)
		finish()
		return
	var cut_frame := int(plan.shots[1].start_frame)
	for shot in plan.shots:
		if shot.camera != plan.shots[0].camera:
			cut_frame = int(shot.start_frame)
			break
	var started: bool = stage.start(event)
	# Drive the actual update callback with two deterministic sub-frame deltas.
	stage._process(0.6 / float(plan.fps))
	var clock_ok: bool = stage.snapshot().frame == 0
	stage._process(0.6 / float(plan.fps))
	clock_ok = clock_ok and stage.snapshot().frame == 1
	stage.advance_frames(cut_frame - 1)
	var reached_cut := started and clock_ok and timeline_error(cut_frame).is_empty()
	var consumed_interrupt := not key_reaches_gameplay(KEY_ESCAPE)
	check("interrupt", "Interruption at a camera cut restores gameplay", reached_cut and consumed_interrupt and clean_handoff(plan.exits.interrupt.next_state),
		"Interrupted on the first frame of a distinct camera at frame %d." % cut_frame)
	check("retry", "Interrupted sequence retries from its first frame", stage.start(event) and timeline_error(0).is_empty(), "Retried the same event and checked the opening camera.")
	check_full_playback()
	finish()
