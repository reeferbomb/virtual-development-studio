extends SceneTree

const Car = preload("res://shared_vehicle.gd")
const START := Vector3(30, 0, 40)
const WALL := {"center": [30, 0, 16], "size": [15, 4, 0.06]}
const DT := 1.0 / 60.0
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(ok: bool, detail: String) -> void:
	if not ok:
		printerr("FAIL shared vehicle: ", detail)
		failures += 1


func _run() -> void:
	var car := Car.new()
	var replica := Car.new()
	root.add_child(car)
	root.add_child(replica)
	var invalid := [{"center": [30, 0, 40], "size": [1, 2, 1]}]
	check(not car.configure(START, 80, invalid) and car.snapshot().is_empty(), "overlapping spawn rejected atomically")
	check(not car.configure(START, 80, [{"size": [1, 2, 1]}]), "missing building center rejected")
	check(car.configure(START, 80, [WALL]) and replica.configure(START, 80, [WALL]), "configure matching city")
	check(car.get_node("Chassis") is MeshInstance3D and car.get_node("Wheel") is MeshInstance3D, "visible pickup")
	var parked := car.snapshot()
	var peers := {1: START + Vector3.RIGHT * 8.0, 27: START + Vector3.LEFT * 2.0}
	check(not car.request(1, peers[1]) and not car.request(0, START), "distant or invalid requester rejected")
	check(car.request(27, peers[27]) and car.occupied(27), "nearby peer takes driver's seat")
	check(not car.request(27, peers[27]) and not car.request(1, START), "repeat and competing entry rejected")
	var inputs := {1: Vector2(1, 1), 27: Vector2(0, -1)}
	for i in 60:
		car.step(DT, peers, inputs)
	check(car.position.z < START.z - 3.8 and is_equal_approx(car.status().speed, 8.0), "driver accelerates along -Z")
	check(peers[27].distance_to(car.position) < 0.75 and peers[1] == START + Vector3.RIGHT * 8.0, "seat follows car and only driver moves")
	var saved: Dictionary = JSON.parse_string(JSON.stringify(car.snapshot(), "", false, true))
	check(replica.restore(saved) and replica.occupied(27) and replica.transform.is_equal_approx(car.transform), "replica restores host pose and ownership")
	var mirrored := peers.duplicate()
	inputs[27] = Vector2(0.75, -1)
	for i in 30:
		car.step(DT, peers, inputs)
		replica.step(DT, mirrored, inputs)
	check(car.position.x > START.x + 0.5 and car.rotation.y < -0.25, "right steering turns moving pickup")
	check(replica.transform.is_equal_approx(car.transform) and mirrored[27].is_equal_approx(peers[27]), "same continuation reproduces driver trajectory")
	var good := replica.snapshot()
	for entry: Array in [["driver", -1], ["driver", 9.25], ["driver", 0], ["speed", 100.0], ["yaw", NAN],
			["position", [30, 0, 16]], ["position", [0, 0, 0]], ["position", [30, 15, 32]]]:
		var bad := good.duplicate(true)
		bad[entry[0]] = entry[1]
		check(not replica.restore(bad) and replica.snapshot() == good, "invalid " + str(entry[0]) + " cannot mutate state")

	check(car.restore(saved), "return to straight approach")
	inputs[27] = Vector2(0, -1)
	for i in 35:
		car.step(0.25, peers, inputs)
	var wall_contact := 16.03 + Car.COLLISION_RADIUS
	check(car.position.z >= wall_contact and car.position.z < wall_contact + 0.012 and absf(car.status().speed) < 0.01,
			"full-speed car stops before thin wall under large tick")
	check(car.valid_snapshot(car.snapshot()), "contact pose remains valid")
	inputs[27] = Vector2(0, 1)
	for i in 75:
		car.step(DT, peers, inputs)
	check(car.position.z > wall_contact + 3.0 and is_equal_approx(car.status().speed, -Car.REVERSE_SPEED), "reverse clears contact")

	check(not car.request(27, START + Vector3.UP * 10), "remote exit rejected")
	check(car.request(27, peers[27]) and not car.occupied(27), "driver can park and dismount")
	check(not car.request(27, peers[27]), "repeat exit before landing cannot reboard")
	car.step(DT, peers, inputs)
	check(peers[27].distance_to(car.position) >= Car.DOOR_DISTANCE - 0.001 and car.status().speed == 0.0, "driver lands clear of chassis")
	check(car.request(27, peers[27]), "driver may reboard from safe landing")
	car.release_peer(1)
	check(car.occupied(27), "unrelated disconnect preserves driver")
	car.release_peer(27)
	check(car.snapshot().driver == 0 and car.status().speed == 0.0 and car.request(1, car.position), "disconnect frees seat immediately")
	peers.erase(1)
	car.step(DT, peers, {})
	check(car.snapshot().driver == 0, "missing peer is never resurrected")

	check(car.restore(parked), "reset car for boundary test")
	check(car.request(27, START), "board for reverse perimeter test")
	for i in 60:
		car.step(0.25, peers, {27: Vector2(0, 1)})
	check(car.position.z <= 80.0 - Car.COLLISION_RADIUS and car.position.z > 80.0 - Car.COLLISION_RADIUS - 0.012,
			"full footprint remains inside city perimeter")
	car.free()
	replica.free()
	if failures == 0:
		print("PASS shared vehicle authority, boarding, steering, swept collision, replica replay, safe exit and disconnect")
	quit(int(failures > 0))
