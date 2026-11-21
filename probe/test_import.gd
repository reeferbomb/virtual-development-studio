extends SceneTree

func _initialize() -> void:
	var asset = load("res://probe.glb")
	if not asset is PackedScene:
		push_error("Expected an imported PackedScene")
		quit(1)
		return
	var model = asset.instantiate()
	var meshes = model.find_children("*", "MeshInstance3D", true, false)
	if model is MeshInstance3D:
		meshes.push_back(model)
	if meshes.is_empty():
		push_error("No mesh in imported scene")
		model.free()
		quit(1)
		return
	model.free()
	print("STUDIO_IMPORT_PASS")
	quit(0)
