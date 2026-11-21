extends SceneTree

const BUILDER = preload("res://world_builder.gd")

func _initialize() -> void:
	call_deferred("_bake")

func _bake() -> void:
	var spec = JSON.parse_string(FileAccess.get_file_as_string("res://level.json"))
	if not spec is Dictionary:
		push_error("Missing level spec")
		quit(1)
		return
	var world := BUILDER.build(spec)
	if world == null or world.get_node_or_null("Spawn") == null or world.get_node_or_null("Goal") == null:
		push_error("Builder didn't produce a complete world")
		quit(1)
		return
	_assign_owner(world, world)
	var packed := PackedScene.new()
	var result := packed.pack(world)
	if result == OK:
		result = ResourceSaver.save(packed, "res://world.tscn")
	world.free()
	if result != OK:
		push_error("World pack/save failed")
		quit(1)
		return
	print("STUDIO_WORLD_BAKE_PASS")
	quit(0)

func _assign_owner(node: Node, root_node: Node) -> void:
	for child in node.get_children():
		child.owner = root_node
		# Preserve the imported scene's internal ownership.
		if child.scene_file_path.is_empty():
			_assign_owner(child, root_node)
