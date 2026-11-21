extends Node3D
## The world calls step once per physics tick, before updating its streamed terrain.

const VEHICLE = preload("res://vehicle.gd")
const ENTER_DISTANCE := 3.0
const STOP_SPEED := 0.05
const DOOR_OFFSET := 2.0
const SEAT_HEIGHT := 0.65
const MAX_COORD := 100000.0

var vehicle: CharacterBody3D
var driving := false
var _player: CharacterBody3D
var _walk_layer: int
var _walk_mask: int
var _walk_processing: bool
var _test_drive := false
var _settling := false


func configure(player: CharacterBody3D, spawn: Vector3) -> bool:
	if vehicle != null or not is_inside_tree() or not is_instance_valid(player):
		return false
	if not player.is_inside_tree() or player.get_world_3d() != get_world_3d() or not spawn.is_finite():
		return false
	_player = player
	vehicle = VEHICLE.new()
	vehicle.name = "Vehicle"
	add_child(vehicle)
	vehicle.global_position = spawn
	# The world owns the tick order, including synchronizing the passenger after motion.
	vehicle.set_physics_process(false)
	_settling = true
	return true


func enter() -> bool:
	if driving or not is_instance_valid(_player) or not is_instance_valid(vehicle):
		return false
	if _player.global_position.distance_to(vehicle.global_position) > ENTER_DISTANCE or absf(vehicle.speed) > STOP_SPEED:
		return false
	_walk_layer = _player.collision_layer
	_walk_mask = _player.collision_mask
	_walk_processing = _player.is_physics_processing()
	_player.set_physics_process(false)
	_player.collision_layer = 0
	_player.collision_mask = 0
	_player.velocity = Vector3.ZERO
	if _player.has_method("clear_test_drive"):
		_player.call("clear_test_drive")
	_settling = false
	driving = true
	_follow_vehicle()
	return true


func exit() -> bool:
	if not driving or absf(vehicle.speed) > STOP_SPEED or not vehicle.is_on_floor():
		return false
	for side in [1.0, -1.0]:
		var landing: Variant = _door_landing(side)
		if landing == null:
			continue
		driving = false
		clear_test_drive()
		vehicle.stop()
		_player.global_position = landing
		_player.velocity = Vector3.ZERO
		_player.collision_layer = _walk_layer
		_player.collision_mask = _walk_mask
		if _player.has_method("clear_test_drive"):
			_player.call("clear_test_drive")
		_player.set_physics_process(_walk_processing)
		return true
	return false


func _door_landing(side: float) -> Variant:
	var space := get_world_3d().direct_space_state
	var origin := vehicle.global_position
	var door := origin + vehicle.global_basis.x.normalized() * DOOR_OFFSET * side
	var ignored: Array[RID] = [_player.get_rid(), vehicle.get_rid()]
	var floor_query := PhysicsRayQueryParameters3D.create(
			door + Vector3.UP * 0.45, door + Vector3.DOWN * 0.5, _walk_mask, ignored)
	var floor_hit := space.intersect_ray(floor_query)
	if floor_hit.is_empty() or floor_hit.normal.y < cos(_player.floor_max_angle):
		return null
	var landing: Vector3 = floor_hit.position + Vector3.UP * 0.08
	var door_path := PhysicsRayQueryParameters3D.create(
			origin + Vector3.UP * 0.9, landing + Vector3.UP * 0.9, _walk_mask, ignored)
	if not space.intersect_ray(door_path).is_empty():
		return null
	var standing := Transform3D(_player.global_basis, landing)
	var clearance := PhysicsShapeQueryParameters3D.new()
	clearance.collision_mask = _walk_mask | vehicle.collision_layer
	clearance.exclude = [_player.get_rid()]
	var checked_shape := false
	for owner in _player.get_shape_owners():
		if _player.is_shape_owner_disabled(owner):
			continue
		clearance.transform = standing * _player.shape_owner_get_transform(owner)
		for index in _player.shape_owner_get_shape_count(owner):
			clearance.shape = _player.shape_owner_get_shape(owner, index)
			if not space.intersect_shape(clearance, 1).is_empty():
				return null
			checked_shape = true
	return landing if checked_shape else null


func set_drive(throttle: float, steer: float, brake: bool = false) -> void:
	if driving:
		_test_drive = true
		vehicle.set_drive(throttle, steer, brake)


func clear_test_drive() -> void:
	_test_drive = false
	if is_instance_valid(vehicle):
		vehicle.set_drive(0.0, 0.0)


func step(delta: float) -> void:
	if not is_instance_valid(vehicle) or not is_finite(delta) or delta <= 0.0:
		return
	if not driving:
		# A newly spawned vehicle settles onto loaded ground. Once parked, its
		# transform survives terrain eviction and restoration outside the window.
		if _settling:
			var point := vehicle.global_position
			var ground := PhysicsRayQueryParameters3D.create(
					point + Vector3.UP * 0.1, point + Vector3.DOWN * 10.0, vehicle.collision_mask)
			if not get_world_3d().direct_space_state.intersect_ray(ground).is_empty():
				vehicle._physics_process(delta)
				_settling = not vehicle.is_on_floor()
		return
	if not _test_drive:
		var throttle := 0.0
		var steer := 0.0
		var brake := false
		if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			throttle = float(Input.is_physical_key_pressed(KEY_W)) - float(Input.is_physical_key_pressed(KEY_S))
			steer = float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
			brake = Input.is_physical_key_pressed(KEY_SPACE)
		vehicle.set_drive(throttle, steer, brake)
	vehicle._physics_process(delta)
	_follow_vehicle()


func _follow_vehicle() -> void:
	_player.global_position = vehicle.global_position + Vector3.UP * SEAT_HEIGHT
	_player.global_rotation = Vector3(0.0, vehicle.global_rotation.y, 0.0)


func snapshot() -> Dictionary:
	if driving or not is_instance_valid(vehicle):
		return {}
	var p := vehicle.global_position
	return {"position": [p.x, p.y, p.z], "yaw": wrapf(vehicle.global_rotation.y, -PI, PI)}


static func valid_snapshot(state: Variant) -> bool:
	if not state is Dictionary or state.size() != 2:
		return false
	var p: Variant = state.get("position")
	var yaw: Variant = state.get("yaw")
	if not p is Array or p.size() != 3 or not (yaw is int or yaw is float):
		return false
	if not is_finite(float(yaw)) or absf(float(yaw)) > PI:
		return false
	for n in p:
		if not (n is int or n is float) or not is_finite(float(n)) or absf(float(n)) > MAX_COORD:
			return false
	return p[1] >= -0.5 and p[1] <= 10.0


func restore(state: Variant) -> bool:
	if driving or not is_instance_valid(vehicle) or not valid_snapshot(state):
		return false
	var p: Array = state.position
	clear_test_drive()
	vehicle.stop()
	vehicle.global_position = Vector3(p[0], p[1], p[2])
	vehicle.global_rotation = Vector3(0.0, state.yaw, 0.0)
	_settling = false
	return true
