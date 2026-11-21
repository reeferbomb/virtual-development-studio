extends SceneTree

const Metro = preload("res://transit.gd")
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(ok: bool, detail: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL metro: ", detail)


func _run() -> void:
	var metro := Metro.new()
	root.add_child(metro)
	check(not metro.configure(12, 64.0, 32.0) and not metro.configure(12, INF, 32.0)
		and not metro.configure(12, 97.0, 32.0), "reject unusable grids before construction")
	check(metro.configure(12, 128.0, 32.0), "create the metro")
	check(not metro.configure(12, 128.0, 32.0), "a second configure cannot duplicate the station geometry")
	var west: Dictionary = metro.status().stations[0]
	var east: Dictionary = metro.status().stations[1]
	var train := metro.get_node("Train") as Node3D
	var left_door := train.get_node("Door0") as MeshInstance3D
	var open_x := left_door.position.x
	check(west.platform.x == 32.0 and east.platform.x == 96.0 and west.platform.y < -6.0,
		"platforms serve distinct ends below street level")
	for i in 2:
		var station := metro.get_node("Station%d" % i)
		check(station.get_node("Platform") is StaticBody3D and station.get_node("Platform/Mesh") is MeshInstance3D
			and station.get_node("StreetLift/Marquee") is MeshInstance3D, "solid platform with a marked street entrance")
		var rail := metro.get_node("Tunnel/Rail%d" % i) as MeshInstance3D
		var rail_half: float = rail.mesh.size.x * 0.5
		check(rail.global_position.x - rail_half < west.platform.x and rail.global_position.x + rail_half > east.platform.x,
			"each continuous rail spans both train stops")
	var sleeper_batch := metro.get_node("Tunnel/Sleepers") as MultiMeshInstance3D
	check(sleeper_batch.multimesh.instance_count > 20, "track sleepers run through the tunnel")
	await physics_frame
	await physics_frame
	for row in [west, east]:
		var origin: Vector3 = row.platform
		var query := PhysicsRayQueryParameters3D.create(origin + Vector3.UP, origin + Vector3.DOWN, 1)
		var hit := metro.get_world_3d().direct_space_state.intersect_ray(query)
		check(not hit.is_empty() and hit.collider.name == "Platform", "a physical floor supports each boarding point")
	var passenger := CharacterBody3D.new()
	root.add_child(passenger)
	passenger.set_physics_process(true)
	passenger.position = Vector3.ZERO
	check(not metro.interact(passenger), "an unrelated street position cannot activate transit")
	passenger.position = east.platform
	check(not metro.interact(passenger), "a distant train cannot be boarded from the other station")
	passenger.position = west.entrance
	check(metro.interact(passenger) and passenger.position.is_equal_approx(west.portal), "street lift reaches the platform")
	passenger.position = west.platform
	check(metro.status().doors_open and metro.interaction_hint(passenger).contains("Board"), "open doors advertise boarding")
	check(metro.interact(passenger) and metro.status().riding and not passenger.is_physics_processing(),
		"boarding attaches the passenger and suspends walking")
	metro.step(Metro.DWELL + 2.0, passenger)
	check(metro.status().phase == "travel" and not metro.status().doors_open and left_door.position.x > open_x + 0.8,
		"train departs with physically closed doors")
	check(train.position.x > west.platform.x and train.position.x < east.platform.x and passenger.position.distance_to(train.position) < 0.1,
		"moving train carries the passenger")
	var rider_checkpoint: Dictionary = JSON.parse_string(JSON.stringify(metro.snapshot(), "", false, true))
	check(metro.valid_player_position(passenger.position, rider_checkpoint) and not metro.valid_player_position(west.platform, rider_checkpoint),
		"rider checkpoint requires a position inside the scheduled carriage")
	check(not metro.interact(passenger) and metro.status().riding, "moving train rejects an early exit")
	var stop_time: float = metro.status().seconds_remaining
	metro.step(stop_time, passenger)
	check(metro.status().station == 1 and metro.status().doors_open and is_equal_approx(open_x, left_door.position.x),
		"doors reopen at the destination")
	check(metro.interact(passenger) and passenger.position.is_equal_approx(east.platform) and passenger.is_physics_processing(),
		"passenger disembarks onto the destination platform and can walk")
	var foot_checkpoint := metro.snapshot()
	check(metro.valid_player_position(passenger.position, foot_checkpoint) and not metro.valid_player_position(train.position, foot_checkpoint),
		"on-foot underground checkpoints stay on reachable platforms")
	passenger.position = east.portal
	check(metro.interact(passenger) and passenger.position.is_equal_approx(east.entrance), "return lift reaches the surface in the same scene")
	check(metro.restore(rider_checkpoint, passenger) and metro.status().riding and not passenger.is_physics_processing(),
		"restoring a JSON checkpoint reattaches the rider")
	check(metro.valid_player_position(passenger.position, rider_checkpoint), "restored rider follows the saved train position immediately")
	metro.step(stop_time, passenger)
	check(metro.interact(passenger) and passenger.position.is_equal_approx(east.platform), "resumed ride reaches the same destination")
	var no_rider := metro.snapshot()
	metro.step(Metro.DWELL + 1.0, passenger)
	check(not metro.interact(passenger), "closed doors deny boarding from the departure platform")
	metro.step(metro.status().seconds_remaining, passenger)
	check(metro.status().station == 0 and metro.status().doors_open, "return service completes a round trip")
	check(metro.restore(no_rider), "rewind to the far station")
	var before := metro.snapshot()
	for edits in [{"clock": -1.0}, {"clock": INF}, {"clock": 10000.0}, {"clock": "0"}, {"riding": 1},
			{"seed": 41}, {"seed": "12"}, {"world_size": null}, {"block_size": {}}, {"version": true}, {"extra": true}]:
		var bad := before.duplicate()
		bad.merge(edits, true)
		check(not metro.restore(bad) and metro.snapshot() == before, "invalid checkpoint rejected without a partial restore")
	metro.step(-1.0, passenger)
	metro.step(NAN, passenger)
	check(metro.snapshot() == before, "invalid deltas leave the timetable intact")
	var twin := Metro.new()
	root.add_child(twin)
	check(twin.configure(12, 128.0, 32.0) and twin.restore(before), "same city can reconstruct the timetable")
	metro.step(14.5, passenger)
	for i in 58:
		twin.step(0.25)
	check(twin.status() == metro.status(), "irregular stepping reproduces the same timetable, train and doors")
	twin.free()
	passenger.free()
	metro.free()
	if failures == 0:
		print("PASS transit: underground geometry, continuous rails, lift access, boarding, full round trip and checkpoint replay")
	quit(int(failures > 0))
