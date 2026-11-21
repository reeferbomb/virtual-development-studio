extends RefCounted

const MAX_HEALTH := 50

class CoverBlock:
	var mesh: MeshInstance3D
	var collision: CollisionShape3D

	func _init(visual: MeshInstance3D, shape: CollisionShape3D) -> void:
		mesh = visual
		collision = shape

	func set_present(present: bool) -> void:
		if is_instance_valid(mesh) and is_instance_valid(collision):
			mesh.visible = present
			collision.set_deferred("disabled", not present)

var health: Dictionary[String, int] = {}
var _blocks: Dictionary[String, CoverBlock] = {}
var _ids_by_body: Dictionary[StaticBody3D, String] = {}
var _source: Dictionary
var _navigator: RefCounted

func configure(world: Node3D, spec: Dictionary, nav: RefCounted, ids: Array) -> bool:
	if not is_instance_valid(world) or nav == null or not nav.has_method("configure"):
		return false
	if not spec.get("blocks", []) is Array:
		return false
	var specified := {}
	for row in spec.get("blocks", []):
		if not row is Dictionary or not row.get("id") is String or specified.has(row.id):
			return false
		specified[row.id] = true

	# Index direct children so a configured ID can never resolve as a node path.
	var candidates := {}
	var group := world.get_node_or_null("Blocks") as Node3D
	if group != null:
		for child in group.get_children():
			candidates[String(child.name)] = child
	var next_blocks: Dictionary[String, CoverBlock] = {}
	var next_ids_by_body: Dictionary[StaticBody3D, String] = {}
	var next_health: Dictionary[String, int] = {}
	for id in ids:
		if not id is String or not specified.has(id) or next_blocks.has(id):
			return false
		var mesh := candidates.get(id) as MeshInstance3D
		if mesh == null or mesh.mesh == null:
			return false
		var body := mesh.get_node_or_null("Body") as StaticBody3D
		var shape := mesh.get_node_or_null("Body/Collision") as CollisionShape3D
		if body == null or shape == null or shape.shape == null:
			return false
		next_blocks[id] = CoverBlock.new(mesh, shape)
		next_ids_by_body[body] = id
		next_health[id] = MAX_HEALTH

	# A successful reconfiguration also releases any cover from the previous world.
	for id in health:
		if health[id] == 0:
			_blocks[id].set_present(true)
	if _navigator != null and _navigator != nav and health.values().has(0):
		_navigator.configure(_source.duplicate(true))
	_blocks = next_blocks
	_ids_by_body = next_ids_by_body
	health = next_health
	_source = spec.duplicate(true)
	_navigator = nav
	_rebuild_navigation()
	return true

func damage(collider: Node, amount: int) -> bool:
	var body := collider as StaticBody3D
	if amount <= 0 or body == null or not _ids_by_body.has(body):
		return false
	var id := _ids_by_body[body]
	if health[id] == 0:
		return false
	health[id] = maxi(0, health[id] - amount)
	if health[id] == 0:
		_blocks[id].set_present(false)
		_rebuild_navigation()
	return true

func snapshot() -> Dictionary:
	return health.duplicate()

func restore(data: Dictionary) -> bool:
	if _navigator == null or data.size() != health.size() or not data.has_all(health.keys()):
		return false
	var next_health: Dictionary[String, int] = {}
	for id in health:
		var value = data[id]
		if not (value is int or value is float) or not is_finite(float(value)):
			return false
		if value < 0 or value > MAX_HEALTH or value != int(value):
			return false
		next_health[id] = int(value)
	health = next_health
	for id in health:
		_blocks[id].set_present(health[id] > 0)
	_rebuild_navigation()
	return true

func _rebuild_navigation() -> void:
	var level := _source.duplicate(true)
	var solid_blocks := []
	for row in level.get("blocks", []):
		if health.get(row.id, MAX_HEALTH) > 0:
			solid_blocks.append(row)
	level["blocks"] = solid_blocks
	_navigator.configure(level)
