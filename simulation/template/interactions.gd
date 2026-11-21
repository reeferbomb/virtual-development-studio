extends Node

const REACH_SQUARED := 4.0
const KINDS := ["beacon", "supply", "switch"]

var _group: Node3D
var _markers: Dictionary[String, Node3D] = {}
var _used: Dictionary[String, bool] = {}

# Marker coordinates are local to world. Player queries use global coordinates.
func configure(world: Node3D, objects: Array) -> bool:
	if not is_instance_valid(world) or world.is_queued_for_deletion():
		return false
	var coordinates: Dictionary[String, Vector3] = {}
	for row in objects:
		if not row is Dictionary or not row.get("id") is String:
			return false
		var id: String = row.id
		if id.strip_edges().is_empty() or coordinates.has(id) or not KINDS.has(row.get("kind")):
			return false
		var values = row.get("position")
		if not values is Array or values.size() != 3:
			return false
		for value in values:
			if not (value is int or value is float):
				return false
		var point := Vector3(values[0], values[1], values[2])
		if not point.is_finite():
			return false
		coordinates[id] = point

	_clear_markers()
	if objects.is_empty():
		return true
	_group = Node3D.new()
	_group.name = "InteractionMarkers"
	world.add_child(_group, true)
	for row in objects:
		var marker := _make_marker(row.kind)
		marker.name = row.kind.capitalize()
		marker.position = coordinates[row.id]
		marker.set_meta("interaction_id", row.id)
		marker.set_meta("interaction_kind", row.kind)
		_group.add_child(marker, true)
		_markers[row.id] = marker
		_used[row.id] = false
	return true

func nearest(position: Vector3) -> String:
	var best_id := ""
	var best_distance := REACH_SQUARED
	for id in _markers:
		var distance := _distance_squared(id, position)
		if distance < best_distance or (best_id.is_empty() and distance == best_distance):
			best_id = id
			best_distance = distance
	return best_id

func activate(id: String, position: Vector3) -> bool:
	if not (_distance_squared(id, position) <= REACH_SQUARED):
		return false
	_used[id] = true
	_markers[id].hide()
	return true

func snapshot() -> Dictionary:
	return _used.duplicate()

func _distance_squared(id: String, position: Vector3) -> float:
	if _used.get(id, true) or not position.is_finite():
		return INF
	var marker := _markers[id]
	if not is_instance_valid(marker) or not marker.is_inside_tree():
		return INF
	return marker.global_position.distance_squared_to(position)

func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE:
		_clear_markers()

func _clear_markers() -> void:
	if is_instance_valid(_group):
		_group.free()
	_group = null
	_markers.clear()
	_used.clear()

func _make_marker(kind: String) -> Node3D:
	var marker := Node3D.new()
	var housing := StandardMaterial3D.new()
	housing.albedo_color = Color("#304455")
	housing.metallic = 0.55
	var indicator := StandardMaterial3D.new()
	indicator.emission_enabled = true
	match kind:
		"beacon":
			indicator.albedo_color = Color("#4de1ff")
			_add_mesh(marker, _box(Vector3(0.48, 0.78, 0.48)), housing, 0.39)
			var lamp := CylinderMesh.new()
			lamp.top_radius = 0.19
			lamp.bottom_radius = 0.22
			lamp.height = 0.32
			lamp.radial_segments = 12
			_add_mesh(marker, lamp, indicator, 0.94)
		"supply":
			indicator.albedo_color = Color("#ffba55")
			_add_mesh(marker, _box(Vector3(0.94, 0.48, 0.62)), housing, 0.24)
			_add_mesh(marker, _box(Vector3(0.2, 0.51, 0.64)), indicator, 0.255)
		"switch":
			indicator.albedo_color = Color("#b3f483")
			_add_mesh(marker, _box(Vector3(0.56, 0.62, 0.44)), housing, 0.31)
			var lever := _add_mesh(marker, _box(Vector3(0.14, 0.42, 0.14)), indicator, 0.75)
			lever.rotation.x = -0.45
	indicator.emission = indicator.albedo_color
	return marker

func _box(dimensions: Vector3) -> BoxMesh:
	var mesh := BoxMesh.new()
	mesh.size = dimensions
	return mesh

func _add_mesh(marker: Node3D, mesh: PrimitiveMesh, material: Material, height: float) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.mesh = mesh
	visual.material_override = material
	visual.position.y = height
	marker.add_child(visual)
	return visual
