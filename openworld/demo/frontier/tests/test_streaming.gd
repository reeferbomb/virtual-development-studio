extends SceneTree

const Streaming = preload("res://streaming.gd")
var errors: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _check(ok: bool, message: String) -> void:
	if not ok:
		errors.append(message)
		printerr("FAIL ", message)


func _ray(position: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(position + Vector3.UP * 2.0,
		position + Vector3.DOWN * 2.0, 1)
	return root.world_3d.direct_space_state.intersect_ray(query)


func _decor(chunk: Node3D) -> Array:
	var transforms := []
	for prop: Node3D in chunk.get_children():
		if str(prop.name).begins_with("Pine") or str(prop.name).begins_with("Rock"):
			transforms.append([str(prop.name), prop.transform])
	return transforms


func _node_count(node: Node) -> int:
	var count := 1
	for child in node.get_children():
		count += _node_count(child)
	return count


func _run() -> void:
	var terrain := Streaming.new()
	root.add_child(terrain)
	_check(terrain.configure(709), "configure default terrain")
	var origin := terrain.snapshot()
	_check(terrain.loaded_count() == 9 and origin.center == [0, 0], "origin has a 3 by 3 neighborhood")
	_check(origin.chunks.size() == 9 and origin.chunks[0] == [-1, -1]
		and origin.chunks[8] == [1, 1], "stable coordinate list")
	_check(terrain.chunk_at(Vector3(-0.001, 99.0, -32.0)) == Vector2i(-1, -1),
		"negative coordinates and exact negative boundary")
	_check(terrain.chunk_at(Vector3(-32.001, -9.0, 32.0)) == Vector2i(-2, 1),
		"negative near-boundary floors and positive exact boundary")
	var original_chunk := terrain.get_node("Chunk_0_0") as Node3D
	var original_layout := _decor(original_chunk)
	_check(not original_layout.is_empty(), "source chunk contains visible seeded props")
	var original_ground := original_chunk.get_node("Ground") as MeshInstance3D
	_check(original_ground.mesh is BoxMesh, "ground instantiates a visible mesh")

	await physics_frame
	await physics_frame
	for x in [-0.01, 0.0, 0.01, 31.99, 32.0, 32.01]:
		var hit := _ray(Vector3(x, 0.0, -1.75))
		_check(not hit.is_empty() and is_zero_approx(hit.position.y) and hit.normal.dot(Vector3.UP) > 0.99,
			"continuous y=0 collider and upward surface normal at x=%s" % x)

	var walker := CharacterBody3D.new()
	walker.collision_layer = 2
	walker.collision_mask = 1
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.32
	capsule.height = 1.8
	var shape := CollisionShape3D.new()
	shape.shape = capsule
	walker.add_child(shape)
	root.add_child(walker)
	walker.position = Vector3(31.6, 1.0, -1.75)
	for tick in 20:
		await physics_frame
		walker.velocity = Vector3.DOWN * 2.0
		walker.move_and_slide()
	_check(walker.is_on_floor(), "character settles onto real terrain")
	var stayed_on_floor := true
	for tick in 45:
		await physics_frame
		walker.velocity = Vector3(4.0, -1.0, 0.0)
		walker.move_and_slide()
		terrain.update_center(walker.global_position)
		stayed_on_floor = stayed_on_floor and walker.is_on_floor() and absf(walker.position.y - 0.9) < 0.03
	_check(stayed_on_floor and walker.position.x > 32.5, "character traverses a streamed seam on foot")
	walker.free()
	_check(is_instance_valid(original_chunk), "overlapping chunks retain their live instances")

	for step in 40:
		terrain.update_center(Vector3(-320.5 - 96.0 * step, 5.0, 224.5 + 64.0 * step))
		_check(terrain.get_child_count() == 9 and terrain.loaded_count() == 9,
			"active chunk count stays bounded at every update")
		# Per chunk: root, mesh, body, shape, and at most twelve four-node props.
		_check(_node_count(terrain) <= 1 + 9 * 52, "no obsolete descendants accumulate")
	_check(not is_instance_valid(original_chunk), "unloaded chunk was freed")
	await physics_frame
	await physics_frame
	_check(_ray(Vector3(12.0, 0.0, 12.0)).is_empty(), "unloaded chunk's collision disappears")
	_check(not _ray(Vector3(-320.5 - 96.0 * 39, 0.0, 224.5 + 64.0 * 39)).is_empty(),
		"distant streamed ground participates in physics")

	terrain.update_center(Vector3.ZERO)
	_check(terrain.snapshot() == origin and _decor(terrain.get_node("Chunk_0_0")) == original_layout,
		"revisiting a chunk recreates identical visible placement and snapshot")
	_check(not terrain.configure(155, 0.0, 1) and not terrain.configure(155, NAN, 1)
		and not terrain.configure(155, 32.0, -1) and terrain.snapshot() == origin,
		"invalid reconfiguration preserves live world")
	_check(terrain.configure(710) and _decor(terrain.get_node("Chunk_0_0")) != original_layout,
		"changing seed changes the visible layout")
	_check(terrain.configure(709, 16.0, 0) and terrain.loaded_count() == 1, "single-chunk radius")
	terrain.update_center(Vector3(-0.1, 0.0, -16.01))
	_check(terrain.snapshot().center == [-1, -2] and terrain.loaded_count() == 1, "custom chunk size")
	terrain.free()
	if errors.is_empty():
		print("STREAMING_TEST_PASS")
	quit(0 if errors.is_empty() else 1)
