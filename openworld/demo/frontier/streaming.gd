extends Node3D
## Synchronous square of terrain chunks centered on a tracked world position.
## Coordinates use half-open intervals. The top of the ground is local Y = 0.

var _seed: int = 0
var _chunk_size: float = 32.0
var _radius: int = 1
var _configured: bool = false
var _center := Vector2i.ZERO
var _chunks := {}
var _ground_mesh := BoxMesh.new()
var _ground_shape := BoxShape3D.new()
var _trunk_mesh := CylinderMesh.new()
var _crown_mesh := CylinderMesh.new()
var _tip_mesh := CylinderMesh.new()
var _rock_mesh := SphereMesh.new()


func configure(seed: int, chunk_size: float = 32.0, radius: int = 1) -> bool:
	if not is_finite(chunk_size) or chunk_size <= 0.0 or radius < 0:
		return false
	for chunk in _chunks.values():
		chunk.free()
	_chunks.clear()
	_seed = seed
	_chunk_size = chunk_size
	_radius = radius
	_prepare_meshes()
	_configured = true
	_update_chunks(Vector2i.ZERO)
	return true


func chunk_at(world_position: Vector3) -> Vector2i:
	var local_position := to_local(world_position) if is_inside_tree() else world_position
	return Vector2i(floori(local_position.x / _chunk_size), floori(local_position.z / _chunk_size))


func update_center(world_position: Vector3) -> void:
	if not _configured or not world_position.is_finite():
		return
	var next_center := chunk_at(world_position)
	if next_center != _center:
		_update_chunks(next_center)


func loaded_count() -> int:
	return _chunks.size()


func snapshot() -> Dictionary:
	var coords: Array = []
	var keys := _chunks.keys()
	keys.sort()
	for key: Vector2i in keys:
		coords.append([key.x, key.y])
	return {
		"seed": _seed, "chunk_size": _chunk_size, "radius": _radius,
		"center": [_center.x, _center.y], "loaded_count": loaded_count(), "chunks": coords
	}


func _update_chunks(next_center: Vector2i) -> void:
	_center = next_center
	for coord: Vector2i in _chunks.keys():
		if absi(coord.x - _center.x) > _radius or absi(coord.y - _center.y) > _radius:
			_chunks[coord].free()
			_chunks.erase(coord)
	for x in range(_center.x - _radius, _center.x + _radius + 1):
		for z in range(_center.y - _radius, _center.y + _radius + 1):
			var coord := Vector2i(x, z)
			if not _chunks.has(coord):
				_chunks[coord] = _make_chunk(coord)


func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 1.0
	return material


func _prepare_meshes() -> void:
	_ground_mesh.size = Vector3(_chunk_size, 1.0, _chunk_size)
	_ground_shape.size = _ground_mesh.size
	if _ground_mesh.material != null:
		return
	_ground_mesh.material = _material(Color("#73835c"))
	_trunk_mesh.radial_segments = 6
	_trunk_mesh.rings = 0
	_trunk_mesh.top_radius = 0.16
	_trunk_mesh.bottom_radius = 0.22
	_trunk_mesh.height = 1.5
	_trunk_mesh.material = _material(Color("#765343"))
	_crown_mesh.radial_segments = 7
	_crown_mesh.rings = 0
	_crown_mesh.top_radius = 0.0
	_crown_mesh.bottom_radius = 1.65
	_crown_mesh.height = 3.0
	_crown_mesh.material = _material(Color("#305c4a"))
	_tip_mesh.radial_segments = 7
	_tip_mesh.rings = 0
	_tip_mesh.top_radius = 0.0
	_tip_mesh.bottom_radius = 1.16
	_tip_mesh.height = 2.7
	_tip_mesh.material = _material(Color("#48785c"))
	_rock_mesh.radial_segments = 6
	_rock_mesh.rings = 2
	_rock_mesh.radius = 0.8
	_rock_mesh.height = 1.18
	_rock_mesh.material = _material(Color("#839185"))


func _place_mesh(parent: Node3D, label: String, mesh: Mesh, at: Vector3) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = label
	instance.mesh = mesh
	instance.position = at
	parent.add_child(instance)
	return instance


func _make_chunk(coord: Vector2i) -> Node3D:
	var chunk := Node3D.new()
	chunk.name = "Chunk_%d_%d" % [coord.x, coord.y]
	chunk.position = Vector3(coord.x * _chunk_size, 0.0, coord.y * _chunk_size)
	add_child(chunk)
	var floor_center := Vector3(_chunk_size * 0.5, -0.5, _chunk_size * 0.5)
	_place_mesh(chunk, "Ground", _ground_mesh, floor_center)
	var body := StaticBody3D.new()
	body.name = "TerrainBody"
	body.position = floor_center
	body.collision_layer = 1
	var collision := CollisionShape3D.new()
	collision.shape = _ground_shape
	body.add_child(collision)
	chunk.add_child(body)
	_place_decor(chunk, coord)
	return chunk


func _place_decor(chunk: Node3D, coord: Vector2i) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash([_seed, coord.x, coord.y])
	# Keep both main axes clear for the player's traversal routes.
	var corridor := minf(6.0, _chunk_size * 0.25)
	var decor_scale := minf(1.0, _chunk_size / 16.0)
	for i in 12:
		var point := Vector3(rng.randf_range(0.11, 0.89) * _chunk_size, 0.0,
			rng.randf_range(0.11, 0.89) * _chunk_size)
		var size := rng.randf_range(0.65, 1.35) * decor_scale
		var yaw := rng.randf_range(0.0, TAU)
		var terrain_point := chunk.position + point
		if minf(absf(terrain_point.x), absf(terrain_point.z)) < corridor + 1.65 * size:
			continue
		if i % 3 == 0:
			var rock := _place_mesh(chunk, "Rock%d" % i, _rock_mesh, point + Vector3.UP * 0.18 * size)
			rock.scale = Vector3(1.4, 0.72, 0.9) * size
			rock.rotation.y = yaw
		else:
			var tree := Node3D.new()
			tree.name = "Pine%d" % i
			tree.position = point
			tree.rotation.y = yaw
			tree.scale = Vector3.ONE * size
			chunk.add_child(tree)
			_place_mesh(tree, "Trunk", _trunk_mesh, Vector3.UP * 0.75)
			_place_mesh(tree, "Branches", _crown_mesh, Vector3.UP * 2.45)
			_place_mesh(tree, "Crown", _tip_mesh, Vector3.UP * 3.68)
