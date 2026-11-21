extends Node3D

var city: Node3D
var actor: Node3D
var animation: AnimationPlayer
var skeleton: Skeleton3D
var camera: Camera3D
var rain: CPUParticles3D
var environment: Environment
var key_light: DirectionalLight3D
var ambience: AudioStreamPlayer3D
var thunder: AudioStreamPlayer3D
var footstep: AudioStreamPlayer3D
var shots: Array
var time := 0.0
var total_duration := 0.0
var shot_index := 0
var finished := false
var paused := false
var label: Label
var title := "Nightfall Patrol"

func vec(row: Array) -> Vector3:
	return Vector3(float(row[0]),float(row[1]),float(row[2]))

func _ready() -> void:
	var spec: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://sequence.json"))
	shots = spec.shots
	title = str(spec.id).replace("_"," ").to_upper()
	for shot in shots:
		total_duration += float(shot.duration)
	city = load("res://assets/city.glb").instantiate()
	add_child(city)
	actor = load("res://assets/animated_actor.glb").instantiate()
	add_child(actor)
	animation = actor.find_children("*","AnimationPlayer",true,false)[0]
	skeleton = actor.find_children("*","Skeleton3D",true,false)[0]
	# The timeline samples the imported animation explicitly instead of free-running.
	animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	camera = Camera3D.new()
	add_child(camera)
	camera.current = true
	create_environment()
	create_rain()
	ambience = player_3d("Street ambience","res://assets/ambience.wav",Vector3(0,2,0),-12.0)
	if ambience.stream is AudioStreamWAV:
		ambience.stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		ambience.stream.loop_end = roundi(ambience.stream.get_length()*ambience.stream.mix_rate)
	if DisplayServer.get_name() != "headless":
		ambience.play()
	thunder = player_3d("Distant thunder","res://assets/thunder.wav",Vector3(8,12,-9),-5.0)
	footstep = player_3d("Footstep","res://assets/footstep.wav",Vector3.ZERO,-8.0)
	var hud := CanvasLayer.new()
	add_child(hud)
	label = Label.new()
	label.position = Vector2(24,24)
	label.add_theme_font_size_override("font_size",20)
	hud.add_child(label)
	seek(0.0)
	print("STUDIO_CINEMATIC_READY")

func player_3d(title: String, path: String, pos: Vector3, db: float) -> AudioStreamPlayer3D:
	var sound := AudioStreamPlayer3D.new()
	sound.name = title
	sound.stream = load(path)
	sound.position = pos
	sound.volume_db = db
	sound.unit_size = 5.0
	sound.max_distance = 60.0
	add_child(sound)
	return sound

func create_environment() -> void:
	environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(.065,.10,.17)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(.38,.49,.65)
	environment.ambient_light_energy = .8
	environment.fog_enabled = true
	environment.fog_light_color = Color(.18,.24,.34)
	var node := WorldEnvironment.new()
	node.environment = environment
	add_child(node)
	key_light = DirectionalLight3D.new()
	key_light.rotation_degrees = Vector3(-45,-30,0)
	key_light.light_color = Color(.55,.72,1.0)
	key_light.shadow_enabled = true
	add_child(key_light)
	for z in [-9,0,9]:
		for x in [-3.4,3.4]:
			var lamp := OmniLight3D.new()
			lamp.position = Vector3(x,3.3,z)
			lamp.light_color = Color(1.0,.64,.30)
			lamp.light_energy = 2.8
			lamp.omni_range = 7.0
			add_child(lamp)

func create_rain() -> void:
	rain = CPUParticles3D.new()
	rain.amount = 300
	rain.lifetime = 1.8
	rain.position = Vector3(0,8,0)
	rain.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	rain.emission_box_extents = Vector3(5,.1,13)
	rain.direction = Vector3(.1,-1,0)
	rain.spread = 3.0
	rain.gravity = Vector3(0,-8,0)
	rain.initial_velocity_min = 7.0
	rain.initial_velocity_max = 9.0
	var streak := BoxMesh.new()
	streak.size = Vector3(.018,.22,.018)
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(.65,.8,1.0,.45)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	streak.material = mat
	rain.mesh = streak
	rain.emitting = false
	add_child(rain)

func seek(at: float) -> void:
	time = clampf(at,0.0,total_duration)
	finished = time >= total_duration
	var start := 0.0
	shot_index = shots.size()-1
	for index in shots.size():
		if time < start+float(shots[index].duration) or index == shots.size()-1:
			shot_index = index
			break
		start += float(shots[index].duration)
	var shot: Dictionary = shots[shot_index]
	var local := clampf(time-start,0.0,float(shot.duration))
	var factor := local/float(shot.duration)
	camera.position = vec(shot.camera_from).lerp(vec(shot.camera_to),factor)
	camera.look_at(vec(shot.look_from).lerp(vec(shot.look_to),factor),Vector3.UP)
	camera.fov = float(shot.fov)
	actor.position = vec(shot.actor_from).lerp(vec(shot.actor_to),factor)
	actor.rotation.y = PI
	var clip: String = shot.clip
	if animation.current_animation != clip:
		animation.play(clip)
		animation.advance(0.0)
	var length := animation.get_animation(clip).length
	animation.seek(fmod(local,maxf(length,.001)),true)
	var intensity: float = shot.rain
	rain.emitting = intensity > .05
	var count := maxi(1,roundi(intensity*300.0))
	if rain.amount != count:
		rain.amount = count
	environment.fog_density = .003+.033*intensity
	key_light.light_energy = float(shot.light)
	footstep.position = actor.position+Vector3.UP*.1
	label.text = "%s   |   %s   |   %04.1f / %.1f s\nSpace pause • R replay" % [title,str(shot.id).to_upper(),time,total_duration]

func _process(delta: float) -> void:
	if paused or finished:
		return
	var old := time
	var previous_shot := shot_index
	seek(time+delta)
	if DisplayServer.get_name() != "headless" and previous_shot != shot_index and float(shots[shot_index].rain) >= .8:
		thunder.play()
	if DisplayServer.get_name() != "headless" and shots[shot_index].clip in ["Walk","Run"] and int(old*2.0) != int(time*2.0):
		footstep.play()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.physical_keycode == KEY_SPACE:
			paused = not paused
		if event.physical_keycode == KEY_R:
			paused = false
			seek(0.0)
