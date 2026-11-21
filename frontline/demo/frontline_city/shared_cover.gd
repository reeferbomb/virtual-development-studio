extends Node3D

## The host passes its own stored peer position into request(). Only the bounded
## health vector is replicated. Cooldowns belong to the current host session.
const Workshop = preload("res://demolition.gd")
const PANEL_COUNT := Workshop.PANEL_COUNT
const MAX_HEALTH := Workshop.MAX_HEALTH
const REACH := 8.0
const COOLDOWN := 0.25
const PLAYER_RADIUS := 0.35

class PanelRow extends "res://demolition.gd":
	func health_at(index: int) -> int:
		return _health[index]

	func apply_health(index: int, value: int, active: bool) -> void:
		_set_health(index, value)
		if not active:
			_panels[index].collision_layer = 0

var _row: PanelRow
var _origin := Vector3.ZERO
var _active := true
var _cooldowns: Dictionary[int, float] = {}


func configure(origin: Vector3) -> bool:
	if not origin.is_finite():
		return false
	if _row == null:
		_row = PanelRow.new()
		_row.name = "SharedCoverRow"
		_row.top_level = true
		add_child(_row)
	_row.configure(18, origin)
	_origin = origin
	_cooldowns.clear()
	set_active(true)
	return true


func panel_center(index: int) -> Vector3:
	return _origin + Vector3((index - 1) * Workshop.SPACING, Workshop.SIZE.y * 0.5, 0.0)


func set_active(enabled: bool) -> void:
	_active = enabled
	visible = enabled
	if _row != null:
		for i in PANEL_COUNT:
			_row.apply_health(i, _row.health_at(i), enabled)


func request(peer: int, position: Vector3, index: int) -> bool:
	if not _active or _row == null or peer <= 0 or peer > 2147483647 or not position.is_finite():
		return false
	if index < 0 or index >= PANEL_COUNT or _cooldowns.has(peer):
		return false
	var health := _row.health_at(index)
	if health <= 0 or position.distance_squared_to(panel_center(index)) > REACH * REACH:
		return false
	_row.apply_health(index, health - 1, true)
	_cooldowns[peer] = COOLDOWN
	return true


func step(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0:
		return
	for peer: int in _cooldowns.keys():
		var remaining := _cooldowns[peer] - delta
		if remaining <= 0.0:
			_cooldowns.erase(peer)
		else:
			_cooldowns[peer] = remaining


func release_peer(peer: int) -> void:
	_cooldowns.erase(peer)


func snapshot() -> Dictionary:
	if _row == null:
		return {}
	var health: Array[int] = []
	for i in PANEL_COUNT:
		health.append(_row.health_at(i))
	return {"version": 1, "health": health}


func _integer_in(value: Variant, low: int, high: int) -> bool:
	return (value is int or value is float) and is_finite(value) and value >= low and value <= high and floorf(value) == value


func valid_snapshot(data: Variant) -> bool:
	if _row == null or not data is Dictionary or data.size() != 2 or not data.has_all(["version", "health"]):
		return false
	if not _integer_in(data.version, 1, 1) or not data.health is Array or data.health.size() != PANEL_COUNT:
		return false
	for value in data.health:
		if not _integer_in(value, 0, MAX_HEALTH):
			return false
	return true


func restore(data: Variant) -> bool:
	if not valid_snapshot(data):
		return false
	for i in PANEL_COUNT:
		var value := int(data.health[i])
		if value != _row.health_at(i):
			_row.apply_health(i, value, _active)
	return true


# Entry and exit times along one slab, expressed as fractions of the requested
# movement. A path along the outside face remains free to slide on that face.
func _interval(start: float, motion: float, low: float, high: float) -> Vector2:
	if motion == 0.0:
		if start <= low or start >= high:
			return Vector2(INF, -INF)
		return Vector2(-INF, INF)
	var a := (low - start) / motion
	var b := (high - start) / motion
	return Vector2(minf(a, b), maxf(a, b))


func _first_contact(start: Vector2, motion: Vector2, radius: float) -> Dictionary:
	var first := {}
	var nearest := INF
	for i in PANEL_COUNT:
		if _row.health_at(i) == 0:
			continue
		var center := panel_center(i)
		var half := Vector2(Workshop.SIZE.x, Workshop.SIZE.z) * 0.5 + Vector2.ONE * radius
		var low := Vector2(center.x, center.z) - half
		var high := Vector2(center.x, center.z) + half
		var x := _interval(start.x, motion.x, low.x, high.x)
		var z := _interval(start.y, motion.y, low.y, high.y)
		var entry := maxf(x.x, z.x)
		if entry < 0.0 or entry > 1.0 or entry >= minf(x.y, z.y) or entry >= nearest:
			continue
		var point := start + motion * entry
		var blocks_x := x.x >= z.x
		var blocks_z := z.x >= x.x
		if blocks_x:
			point.x = low.x if motion.x > 0.0 else high.x
		if blocks_z:
			point.y = low.y if motion.y > 0.0 else high.y
		first = {"point": point, "blocks_x": blocks_x, "blocks_z": blocks_z}
		nearest = entry
	return first


func move(from: Vector3, to: Vector3, radius: float = PLAYER_RADIUS) -> Vector3:
	if not from.is_finite() or not to.is_finite() or not is_finite(radius) or radius < 0.0:
		return from
	if not _active or _row == null or minf(from.y, to.y) >= _origin.y + Workshop.SIZE.y:
		return to
	if maxf(from.y, to.y) + 1.7 <= _origin.y:
		return to
	var point := Vector2(from.x, from.z)
	var goal := Vector2(to.x, to.z)
	# After one hit we slide along the remaining axis. A second hit stops it.
	for _axis in 2:
		if point == goal:
			break
		var hit := _first_contact(point, goal - point, radius)
		if hit.is_empty():
			point = goal
			break
		point = hit.point
		if hit.blocks_x:
			goal.x = point.x
		if hit.blocks_z:
			goal.y = point.y
	return Vector3(point.x, to.y, point.y)
