extends SceneTree

var errors: Array[String] = []
var options := {}
var mesh_count := 0
var triangles := 0
var materials := {}
var skeleton_count := 0
var bones := 0
var skinned_meshes := 0
var animation_names: Array[String] = []
var bounds := AABB()
var has_bounds := false

func _initialize() -> void:
	call_deferred("_run")

func _parse_arguments() -> void:
	var args := OS.get_cmdline_user_args()
	var keys := ["--kind", "--max-triangles", "--max-materials"]
	if args.size() % 2 != 0:
		errors.append("Expected a value after each option.")
		return
	for i in range(0, args.size(), 2):
		var key := args[i]
		var value := args[i + 1]
		if not keys.has(key) or options.has(key):
			errors.append("Unknown or repeated option: " + key)
			continue
		options[key] = value
		if key == "--kind":
			if value not in ["prop", "character"]:
				errors.append("Kind must be prop or character.")
		elif not value.is_valid_int() or value.to_int() < 0 or str(value.to_int()) != value:
			errors.append("Expected a nonnegative decimal integer for " + key)
	for key in keys:
		if not options.has(key):
			errors.append("Missing " + key)

func _run() -> void:
	_parse_arguments()
	if errors.is_empty():
		var packed := load("res://asset.glb") as PackedScene
		if packed == null:
			errors.append("Could not load asset.glb as a PackedScene.")
		else:
			var asset := packed.instantiate()
			if asset == null:
				errors.append("Could not instantiate asset.glb.")
			else:
				root.add_child(asset)
				_walk(asset)
				asset.free()
				_validate()
	animation_names.sort()
	var box = null
	if has_bounds:
		box = {"position": _xyz(bounds.position), "size": _xyz(bounds.size)}
	var report := {"pass": errors.is_empty(), "mesh_count": mesh_count, "triangles": triangles,
		"materials": materials.size(), "skeleton_count": skeleton_count, "bones": bones,
		"skinned_meshes": skinned_meshes, "animation_names": animation_names,
		"bounds": box, "errors": errors}
	print("STUDIO_ASSET_QA_JSON " + JSON.stringify(report))
	quit(0 if errors.is_empty() else 1)

func _xyz(v: Vector3) -> Array:
	return [v.x, v.y, v.z]

func _walk(node: Node) -> void:
	if node is MeshInstance3D:
		_inspect_mesh(node)
	if node is Skeleton3D:
		skeleton_count += 1
		bones = maxi(bones, node.get_bone_count())
	if node is AnimationPlayer:
		for name in node.get_animation_list():
			var anim: Animation = node.get_animation(name)
			if name == "RESET" or anim == null or anim.length <= 0:
				continue
			for track in anim.get_track_count():
				if anim.track_is_enabled(track) and anim.track_get_key_count(track) > 0:
					if not animation_names.has(name):
						animation_names.append(name)
					break
	for child in node.get_children():
		_walk(child)

func _inspect_mesh(instance: MeshInstance3D) -> void:
	var mesh := instance.mesh as ArrayMesh
	if mesh == null:
		errors.append("Expected an imported ArrayMesh at " + str(instance.get_path()))
		return
	mesh_count += 1
	var world_box := instance.global_transform * mesh.get_aabb()
	if not world_box.is_finite() or not world_box.has_surface():
		errors.append("Invalid bounds at " + str(instance.get_path()))
	else:
		bounds = bounds.merge(world_box) if has_bounds else world_box
		has_bounds = true
	var weighted := false
	for surface in mesh.get_surface_count():
		var material := instance.get_active_material(surface)
		if material != null:
			materials[material.get_instance_id()] = true
		var arrays := mesh.surface_get_arrays(surface)
		var indices = arrays[Mesh.ARRAY_INDEX]
		var vertices = arrays[Mesh.ARRAY_VERTEX]
		var count: int = indices.size() if indices != null and indices.size() > 0 else vertices.size()
		match mesh.surface_get_primitive_type(surface):
			Mesh.PRIMITIVE_TRIANGLES:
				if count % 3 != 0:
					errors.append("Incomplete triangle in " + str(instance.get_path()))
				@warning_ignore("integer_division")
				triangles += count / 3
			Mesh.PRIMITIVE_TRIANGLE_STRIP:
				triangles += maxi(0, count - 2)
		if not weighted and arrays[Mesh.ARRAY_BONES] != null and arrays[Mesh.ARRAY_WEIGHTS] != null:
			for weight in arrays[Mesh.ARRAY_WEIGHTS]:
				if weight > 0.0:
					weighted = true
					break
	var skeleton := instance.get_node_or_null(instance.skeleton) as Skeleton3D
	if weighted and skeleton != null and skeleton.get_bone_count() >= 6 and instance.skin != null and instance.skin.get_bind_count() > 0:
		skinned_meshes += 1

func _validate() -> void:
	if mesh_count == 0 or triangles == 0 or not has_bounds:
		errors.append("Expected a mesh with triangles and valid world bounds.")
	if triangles > str(options["--max-triangles"]).to_int():
		errors.append("Triangle budget exceeded.")
	if materials.size() > str(options["--max-materials"]).to_int():
		errors.append("Material budget exceeded.")
	if options["--kind"] == "character":
		if bones < 6:
			errors.append("Character requires a skeleton with at least six bones.")
		if skinned_meshes == 0:
			errors.append("Character requires a weighted mesh bound to its skeleton.")
		if animation_names.is_empty():
			errors.append("Character requires a nonempty animation.")
