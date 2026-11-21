extends SceneTree

var checks: Array[Dictionary] = []

func _initialize() -> void:
	call_deferred("run")

func check(label: String, ok: bool, detail: String = "") -> void:
	checks.append({"name":label,"status":"passed" if ok else "failed","detail":detail})

func finish() -> void:
	var ok := not checks.is_empty()
	for row in checks:
		ok = ok and row.status == "passed"
	print("STUDIO_CINEMATIC_QA_JSON " + JSON.stringify({"pass":ok,"checks":checks}))
	quit(0 if ok else 1)

func run() -> void:
	if not ResourceLoader.exists("res://cinematic.tscn"):
		check("Cinematic scene",false,"Missing cinematic scene")
		finish()
		return
	var stage = load("res://cinematic.tscn").instantiate()
	root.add_child(stage)
	await process_frame
	stage.set_process(false)
	check("Imported city",stage.city.find_children("*","MeshInstance3D",true,false).size() >= 15)
	check("Imported skeleton",stage.skeleton.get_bone_count() >= 16,str(stage.skeleton.get_bone_count()))
	var names: PackedStringArray = stage.animation.get_animation_list()
	check("Animation library",names.size() >= 5,str(names))
	stage.seek(.2)
	var before: Vector3 = stage.camera.position
	var actor_before: Vector3 = stage.actor.position
	var poses: Array[Quaternion] = []
	for index in stage.skeleton.get_bone_count():
		poses.append(stage.skeleton.get_bone_pose_rotation(index))
	stage.seek(.7)
	var changed := false
	for index in poses.size():
		changed = changed or absf(poses[index].dot(stage.skeleton.get_bone_pose_rotation(index))) < .9999
	check("Animated bone motion",changed)
	check("Camera dolly",stage.camera.position.distance_to(before) > .1)
	check("Actor blocking",stage.actor.position.distance_to(actor_before) > .1)
	stage.seek(4.5)
	check("Shot cut",stage.shot_index == 1 and stage.animation.current_animation == "Aim")
	stage.seek(8.5)
	check("Weather transition",stage.shot_index == 2 and stage.rain.emitting and stage.environment.fog_density > .01)
	check("Spatial sound",stage.ambience is AudioStreamPlayer3D and stage.thunder is AudioStreamPlayer3D and stage.ambience.stream != null and stage.thunder.stream != null)
	stage.seek(1000)
	check("Timeline end",stage.finished and absf(stage.time - stage.total_duration) < .001)
	stage.seek(-2)
	check("Timeline rewind",stage.time == 0 and stage.shot_index == 0 and not stage.finished)
	finish()
