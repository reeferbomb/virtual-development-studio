extends RefCounted

const CELL := 0.5
const CLEARANCE := 0.5
const MAX_EXTENT := 128.0

var grid := AStarGrid2D.new()
var limits := Vector2.ZERO
var ready := false

func configure(spec: Dictionary) -> void:
	ready = false
	grid.clear()
	var terrain: Dictionary = spec.get("terrain", {})
	var flat := float(terrain.get("flat_radius", 0))
	var half_width := float(terrain.get("width", 0)) * 0.5
	var half_depth := float(terrain.get("depth", 0)) * 0.5
	if not Vector3(flat, half_width, half_depth).is_finite():
		return
	if maxf(half_width, half_depth) > MAX_EXTENT:
		return
	limits = Vector2(minf(flat, half_width), minf(flat, half_depth)) - Vector2.ONE * CLEARANCE
	if minf(limits.x, limits.y) <= 0:
		return
	var extent := Vector2i((limits / CELL).floor())
	grid.region = Rect2i(-extent, 2 * extent + Vector2i.ONE)
	grid.cell_size = Vector2.ONE * CELL
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER
	grid.default_compute_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	grid.default_estimate_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	grid.update()
	for block: Dictionary in spec.get("blocks", []):
		_mark_obstacle(block, block.get("size", []))
	for prop: Dictionary in spec.get("placements", []):
		if prop.has("collider_size"):
			_mark_obstacle(prop, prop.collider_size)
	ready = true

func _mark_obstacle(data: Dictionary, size: Array) -> void:
	var pos: Array = data.get("position", [])
	if pos.size() != 3 or size.size() != 3:
		return
	var center := Vector2(pos[0], pos[2])
	var yaw := deg_to_rad(float(data.get("yaw_deg", 0)))
	var c := absf(cos(yaw))
	var s := absf(sin(yaw))
	var half := Vector2(c * size[0] + s * size[2], s * size[0] + c * size[2]) * 0.5
	# Mark every cell touching the footprint, including its edges and agent clearance.
	half += Vector2.ONE * (CLEARANCE + CELL * 0.5)
	var first := Vector2i(((center - half) / CELL).ceil())
	var last := Vector2i(((center + half) / CELL).floor())
	var solid := Rect2i(first, last - first + Vector2i.ONE).intersection(grid.region)
	if solid.has_area():
		grid.fill_solid_region(solid)

func plan(start: Vector3, goal: Vector3) -> PackedVector3Array:
	var waypoints := PackedVector3Array()
	if not ready or not start.is_finite() or not goal.is_finite():
		return waypoints
	var a := Vector2(start.x, start.z)
	var b := Vector2(goal.x, goal.z)
	if a == b or not _inside(a) or not _inside(b):
		return waypoints
	var from := Vector2i((a / CELL).round())
	var to := Vector2i((b / CELL).round())
	if not grid.is_in_boundsv(from) or not grid.is_in_boundsv(to):
		return waypoints
	if grid.is_point_solid(from) or grid.is_point_solid(to):
		return waypoints
	var ids := grid.get_id_path(from, to)
	if ids.is_empty():
		return waypoints
	for id in ids:
		var point := Vector3(id.x * CELL, 0, id.y * CELL)
		if not point.is_equal_approx(Vector3(start.x, 0, start.z)):
			waypoints.append(point)
	var target := Vector3(goal.x, 0, goal.z)
	if waypoints.is_empty() or not waypoints[-1].is_equal_approx(target):
		waypoints.append(target)
	return waypoints

func _inside(point: Vector2) -> bool:
	return absf(point.x) <= limits.x and absf(point.y) <= limits.y
