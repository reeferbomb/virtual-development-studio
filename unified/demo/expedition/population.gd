extends Node3D

# Residents belong to a seeded chunk. Their routes use the same simulation clock
# even after streaming away, so revisiting a chunk needs no saved NPC transforms.
class Resident extends Node3D:
	var id: String
	var faction: String
	var chunk: Vector2i
	var home: Vector3
	var orbit: Vector2
	var phase: float
	var speed: float
	var left_leg: MeshInstance3D
	var right_leg: MeshInstance3D

	func move_at(seconds: float) -> void:
		var angle := phase + seconds * speed
		position = home + Vector3(orbit.x * cos(angle), 0, orbit.y * sin(angle))
		rotation.y = atan2(-orbit.x * sin(angle), orbit.y * cos(angle))
		var stride := sin(angle * 8.0) * 0.22
		left_leg.rotation.x = stride
		right_leg.rotation.x = -stride

var _world_seed: int
var _size: float
var _radius: int
var _time := 0.0
var _center := Vector2i.ZERO
var _chunks: Dictionary[Vector2i, Node3D] = {}
var _residents: Dictionary[String, Resident] = {}
var _torso: CapsuleMesh
var _head: CapsuleMesh
var _leg: CapsuleMesh
var _arm: CapsuleMesh
var _outfits: Dictionary[String, StandardMaterial3D] = {}
var _skin: StandardMaterial3D
var _boots: StandardMaterial3D

func configure(seed: int, chunk_size: float = 32.0, radius: int = 1) -> bool:
	if not is_finite(chunk_size) or chunk_size < 8.0 or chunk_size > 128.0 or radius < 0 or radius > 3:
		return false
	for group in _chunks.values():
		group.free()
	_chunks.clear()
	_residents.clear()
	_world_seed = seed
	_size = chunk_size
	_radius = radius
	_time = 0
	if _torso == null:
		_torso = _capsule(0.25, 0.78)
		_head = _capsule(0.16, 0.34)
		_leg = _capsule(0.105, 0.69)
		_arm = _capsule(0.085, 0.55)
		_skin = _material(Color("e7af88"))
		_boots = _material(Color("28384a"))
		_outfits["settlers"] = _material(Color("dc8850"))
		_outfits["rangers"] = _material(Color("438f86"))
	_stream(Vector2i.ZERO)
	return true

# The center and proximity queries are in world coordinates. Chunk coordinates
# are measured along this Node3D's local X/Z axes.
func update_center(position: Vector3) -> void:
	if _size == 0.0 or not position.is_finite():
		return
	var local := to_local(position) if is_inside_tree() else position
	var next := Vector2i(floori(local.x / _size), floori(local.z / _size))
	if next != _center:
		_stream(next)

func step(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0:
		return
	_time += delta
	for npc in _residents.values():
		npc.move_at(_time)

func loaded_count() -> int:
	return _residents.size()

func snapshot() -> Dictionary:
	var result := {}
	for npc in _residents.values():
		var p := _world_position(npc)
		result[npc.id] = {"faction": npc.faction, "chunk": [npc.chunk.x, npc.chunk.y], "position": [p.x, p.y, p.z]}
	return result

func nearest(position: Vector3) -> Dictionary:
	if not position.is_finite():
		return {}
	var closest: Resident
	var best := INF
	for npc in _residents.values():
		var distance := position.distance_squared_to(_world_position(npc))
		if distance < best or (distance == best and closest != null and npc.id < closest.id):
			best = distance
			closest = npc
	if closest == null:
		return {}
	return {"id": closest.id, "faction": closest.faction, "distance": sqrt(best)}

func _world_position(npc: Resident) -> Vector3:
	return npc.global_position if npc.is_inside_tree() else npc.position

func _stream(center: Vector2i) -> void:
	_center = center
	for key: Vector2i in _chunks.keys():
		if absi(key.x - center.x) > _radius or absi(key.y - center.y) > _radius:
			var group := _chunks[key]
			for npc: Resident in group.get_children():
				_residents.erase(npc.id)
			group.free()
			_chunks.erase(key)
	for z in range(center.y - _radius, center.y + _radius + 1):
		for x in range(center.x - _radius, center.x + _radius + 1):
			var key := Vector2i(x, z)
			if not _chunks.has(key):
				_load_chunk(key)

func _load_chunk(key: Vector2i) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = ("%d/%d/%d/population" % [_world_seed, key.x, key.y]).hash()
	var group := Node3D.new()
	group.name = "Residents_%d_%d" % [key.x, key.y]
	add_child(group)
	_chunks[key] = group
	var count := rng.randi_range(1, 2)
	for slot in range(count):
		var npc := Resident.new()
		npc.id = "npc_%d_%d_%d_%d" % [_world_seed, key.x, key.y, slot]
		npc.name = npc.id
		npc.faction = "settlers" if rng.randi_range(0, 1) == 0 else "rangers"
		npc.set_meta("faction", npc.faction)
		npc.set_meta("npc_id", npc.id)
		npc.chunk = key
		npc.home = Vector3(key.x + rng.randf_range(0.25, 0.75), 0.0, key.y + rng.randf_range(0.25, 0.75)) * _size
		npc.orbit = Vector2(rng.randf_range(0.07, 0.17), rng.randf_range(0.07, 0.17)) * _size
		npc.phase = rng.randf_range(0.0, TAU)
		npc.speed = rng.randf_range(0.65, 1.35) / maxf(npc.orbit.x, npc.orbit.y)
		_build_humanoid(npc)
		group.add_child(npc)
		npc.move_at(_time)
		_residents[npc.id] = npc

func _build_humanoid(npc: Resident) -> void:
	var outfit := _outfits[npc.faction]
	_part(npc, "Coat", _torso, outfit, Vector3(0, 0.98, 0))
	_part(npc, "Head", _head, _skin, Vector3(0, 1.52, 0))
	_part(npc, "LeftSleeve", _arm, outfit, Vector3(-0.27, 0.99, 0)).rotation.z = -0.13
	_part(npc, "RightSleeve", _arm, outfit, Vector3(0.27, 0.99, 0)).rotation.z = 0.13
	npc.left_leg = _part(npc, "LeftLeg", _leg, _boots, Vector3(-0.12, 0.35, 0))
	npc.right_leg = _part(npc, "RightLeg", _leg, _boots, Vector3(0.12, 0.35, 0))

func _part(parent: Node3D, label: String, mesh: Mesh, material: Material, offset: Vector3) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.mesh = mesh
	visual.material_override = material
	visual.position = offset
	parent.add_child(visual)
	return visual

func _capsule(radius: float, height: float) -> CapsuleMesh:
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 8
	mesh.rings = 3
	return mesh

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material
