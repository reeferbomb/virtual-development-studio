extends Node3D

const CaptionOverlay = preload("res://caption_overlay.gd")

# In gameplay the arrow keys move the player's viewpoint along the street.
# Suspending this node's input handler gives the sequence exclusive control.
class GameplayControl:
	extends Node3D

	func _unhandled_input(event: InputEvent) -> void:
		if not event is InputEventKey or not event.pressed:
			return
		var key: Key = event.keycode if event.keycode != KEY_NONE else event.physical_keycode
		match key:
			KEY_LEFT: position.x = maxf(-2.0, position.x - 0.25)
			KEY_RIGHT: position.x = minf(2.0, position.x + 0.25)
			KEY_UP: position.z = maxf(-2.0, position.z - 0.25)
			KEY_DOWN: position.z = minf(2.0, position.z + 0.25)
			_: return
		get_viewport().set_input_as_handled()

var plan: Dictionary
var gameplay := GameplayControl.new()
var gameplay_camera := Camera3D.new()
var overlay := CaptionOverlay.new()
var cue_player := AudioStreamPlayer.new()
var cameras: Dictionary = {}
var actors: Dictionary = {}
var animations: Dictionary = {}
var skeletons: Dictionary = {}
var clip_names: Dictionary = {}

var frame := 0
var active := false
var paused := false
var story_state := ""
var caption := ""
var _line_id := ""
var _frame_remainder := 0.0
var _return_camera: Camera3D
var _return_input := true
var _ready_for_playback := false

func _ready() -> void:
	gameplay.name = "Gameplay"
	add_child(gameplay)
	gameplay_camera.name = "GameplayCamera"
	gameplay.add_child(gameplay_camera)
	gameplay_camera.position = Vector3(0, 1.7, 5.8)
	gameplay_camera.look_at(Vector3(0, 1.2, 0))
	gameplay_camera.make_current()
	cue_player.name = "ScratchCue"
	cue_player.volume_db = -14.0
	add_child(cue_player)
	overlay.name = "CaptionOverlay"
	add_child(overlay)
	overlay.clear_caption(false)

	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://production.json"))
	if not manifest is Dictionary or manifest.get("schema_version") != 1:
		push_error("Cannot read the version 1 cutscene production manifest.")
		return
	plan = manifest.plan
	var city_scene := load("res://assets/city.glb") as PackedScene
	var actor_scene := load("res://assets/animated_actor.glb") as PackedScene
	var scratch := load("res://assets/footstep.wav") as AudioStreamWAV
	if city_scene == null or actor_scene == null or scratch == null:
		push_error("Missing imported production assets.")
		return
	add_child(city_scene.instantiate())
	var loop := scratch.duplicate() as AudioStreamWAV
	loop.loop_begin = 0
	loop.loop_end = roundi(scratch.get_length() * scratch.mix_rate)
	loop.loop_mode = AudioStreamWAV.LOOP_FORWARD
	cue_player.stream = loop
	_create_cameras(manifest.bindings.cameras)
	if not _create_actors(manifest.bindings.actors, actor_scene):
		return
	story_state = plan.trigger.requires
	_ready_for_playback = true
	overlay.clear_caption()

func _vector(coordinates: Array) -> Vector3:
	return Vector3(coordinates[0], coordinates[1], coordinates[2])

func _create_cameras(bindings: Dictionary) -> void:
	for id in plan.cameras:
		var mount: Dictionary = bindings[id]
		var camera := Camera3D.new()
		camera.name = "Camera_" + id
		add_child(camera)
		camera.position = _vector(mount.position)
		camera.look_at(_vector(mount.look_at))
		camera.fov = mount.fov
		cameras[id] = camera

func _create_actors(bindings: Dictionary, scene: PackedScene) -> bool:
	for id in plan.actors:
		var actor := scene.instantiate() as Node3D
		actor.name = "Actor_" + id
		add_child(actor)
		actor.position = _vector(bindings[id].position)
		actor.rotation_degrees.y = float(bindings[id].rotation_y)
		var players := actor.find_children("*", "AnimationPlayer", true, false)
		var rigs := actor.find_children("*", "Skeleton3D", true, false)
		if players.size() != 1 or rigs.size() != 1:
			push_error("Actor %s needs one imported AnimationPlayer and Skeleton3D." % id)
			return false
		var player: AnimationPlayer = players[0]
		player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		player.stop()
		var names := {}
		for clip in player.get_animation_list():
			names[clip.to_lower()] = clip
		actors[id] = actor
		animations[id] = player
		skeletons[id] = rigs[0]
		clip_names[id] = names
	for cue in plan.blocking:
		if not clip_names[cue.actor].has(cue.clip):
			push_error("Missing imported animation %s for actor %s." % [cue.clip, cue.actor])
			return false
	return true

func start(event: String) -> bool:
	if not _ready_for_playback or active or event != plan.trigger.event or story_state != plan.trigger.requires:
		return false
	_return_camera = get_viewport().get_camera_3d()
	_return_input = gameplay.is_processing_unhandled_input()
	gameplay.set_process_unhandled_input(false)
	frame = 0
	_frame_remainder = 0.0
	active = true
	paused = false
	_present_frame()
	return true

func advance_frames(count: int) -> void:
	if count <= 0 or not active or paused:
		return
	for step in mini(count, int(plan.frame_count) - frame):
		frame += 1
		if frame == int(plan.frame_count):
			_finish("complete")
			return
		_present_frame()

func set_paused(value: bool) -> void:
	if not active or paused == value:
		return
	paused = value
	cue_player.stream_paused = paused
	overlay.show_caption(caption, paused, frame, int(plan.frame_count))

func skip() -> void:
	if active:
		frame = int(plan.frame_count)
		_finish("skip")

func interrupt() -> void:
	if active:
		frame = 0
		_finish("interrupt")

func _finish(path: String) -> void:
	active = false
	paused = false
	_frame_remainder = 0.0
	story_state = plan.exits[path].next_state
	cue_player.stop()
	cue_player.stream_paused = false
	_line_id = ""
	caption = ""
	overlay.clear_caption(story_state == plan.trigger.requires)
	for id in animations:
		_stop_actor(id)
	if is_instance_valid(_return_camera):
		_return_camera.make_current()
	else:
		gameplay_camera.make_current()
	gameplay.set_process_unhandled_input(_return_input)

func _contains_frame(cue: Dictionary) -> bool:
	return int(cue.start_frame) <= frame and frame < int(cue.end_frame)

func _current_cue(lane: Array) -> Dictionary:
	for cue in lane:
		if _contains_frame(cue):
			return cue
	return {}

func _present_frame() -> void:
	var shot := _current_cue(plan.shots)
	var camera: Camera3D = cameras[shot.camera]
	if not camera.current:
		camera.make_current()
	var blocking := {}
	for cue in plan.blocking:
		if _contains_frame(cue):
			blocking[cue.actor] = cue
	for id in animations:
		if blocking.has(id):
			_sample_actor(id, blocking[id])
		else:
			_stop_actor(id)
	var line := _current_cue(plan.dialogue)
	var next_line: String = line.get("line", "")
	if _line_id != next_line:
		cue_player.stop()
		if not line.is_empty():
			cue_player.play()
		_line_id = next_line
	var subtitle := _current_cue(plan.subtitles)
	caption = subtitle.get("text", "")
	overlay.set_speaker(str(line.get("speaker", "")).capitalize())
	overlay.show_caption(caption, paused, frame, int(plan.frame_count))

func _sample_actor(id: String, cue: Dictionary) -> void:
	var player: AnimationPlayer = animations[id]
	var clip: StringName = clip_names[id][cue.clip]
	if player.current_animation != clip:
		player.play(clip)
		player.advance(0.0)
	var seconds := float(frame - int(cue.start_frame)) / float(plan.fps)
	var length := player.get_animation(clip).length
	var offset := fmod(seconds, length)
	# An imported float length may put an exact wrap just inside the end.
	# Godot completes a non-looping animation when seeking that near its end.
	player.seek(0.0 if is_equal_approx(offset, length) else offset, true)

func _stop_actor(id: String) -> void:
	var player: AnimationPlayer = animations[id]
	if player.is_playing():
		player.stop()
		var rig: Skeleton3D = skeletons[id]
		rig.reset_bone_poses()

func snapshot() -> Dictionary:
	var current := get_viewport().get_camera_3d()
	var camera_id: String = cameras.find_key(current) if current in cameras.values() else "gameplay"
	var actor_clips := {}
	for id in animations:
		var player: AnimationPlayer = animations[id]
		actor_clips[id] = player.current_animation.to_lower()
	return {
		"frame": frame, "active": active, "paused": paused, "story_state": story_state,
		"camera_id": camera_id, "input_enabled": gameplay.is_processing_unhandled_input(),
		"caption": caption, "cue_playing": cue_player.playing, "actor_clips": actor_clips,
	}

func _process(delta: float) -> void:
	if not active or paused:
		return
	_frame_remainder += delta * float(plan.fps)
	var elapsed_frames := floori(_frame_remainder)
	_frame_remainder -= elapsed_frames
	advance_frames(elapsed_frames)

func _unhandled_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or not _ready_for_playback:
		return
	var key: Key = event.keycode if event.keycode != KEY_NONE else event.physical_keycode
	if not active:
		if key in [KEY_ENTER, KEY_KP_ENTER] and start(plan.trigger.event):
			get_viewport().set_input_as_handled()
		return
	match key:
		KEY_SPACE: set_paused(not paused)
		KEY_S: skip()
		KEY_ESCAPE: interrupt()
		_: return
	get_viewport().set_input_as_handled()
