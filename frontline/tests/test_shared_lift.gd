extends SceneTree

const Lift = preload("res://shared_lift.gd")
const ORIGIN := Vector3(12, 0.25, 9)
var failures := 0


func _initialize() -> void:
	call_deferred("_run")


func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		printerr("FAIL shared lift: ", message)


func _run() -> void:
	var host := Lift.new()
	var replica := Lift.new()
	root.add_child(host)
	root.add_child(replica)
	check(host.configure(ORIGIN) and replica.configure(ORIGIN), "configure both peers")
	var initial := host.snapshot()
	var positions: Dictionary[int, Vector3] = {17: ORIGIN + Vector3(0, 0, 1.5), 23: ORIGIN}
	var directions: Dictionary[int, Vector2] = {17: Vector2.RIGHT, 23: Vector2.ZERO}
	check(not host.request(0, ORIGIN) and not host.request(17, ORIGIN + Vector3(8, 0, 0)), "unassigned and distant requests denied")
	check(not host.request(17, ORIGIN + Vector3.UP * Lift.HEIGHT), "cannot board from upper landing")
	check(host.request(17, positions[17]) and host.occupied(17), "board from street")
	check(not host.request(23, positions[23]) and not host.occupied(23), "capacity limited to one rider")
	host.step(0.1, positions, directions)
	check(positions[17] == ORIGIN and positions[23] == ORIGIN, "onboard player standing on car")
	check(host.request(17, positions[17]), "occupant starts trip up")
	check(host.get_node("StreetGate").visible and host.get_node("Cab/CabGate").visible, "street and cab gates close before travel")
	for frame in 12:
		var before := positions[17]
		host.step(0.1, positions, directions)
		var expected_height := (frame + 1) * Lift.SPEED * 0.1
		check(is_equal_approx(positions[17].y - before.y, 0.1 * Lift.SPEED), "continuous ascent")
		check(positions[17].is_equal_approx(ORIGIN + Vector3.UP * expected_height), "rider fixed to cab despite walk input")
		check(host.get_node("Cab").position.is_equal_approx(Vector3.UP * expected_height), "visible cab follows rider")
	check(positions[23] == ORIGIN and not host.request(17, positions[17]), "travel interlock and uninvolved peer")
	var mid: Dictionary = JSON.parse_string(JSON.stringify(host.snapshot()))
	check(replica.restore(mid) and replica.occupied(17), "JSON snapshot reattaches rider on replica")
	check(replica.get_node("Cab").position.is_equal_approx(host.get_node("Cab").position), "replica renders moving platform at same height")
	check(replica.get_node("StreetGate").visible and replica.get_node("Cab/CabGate").visible, "replica renders closed gates")
	var before_rejection := replica.snapshot()
	for patch: Dictionary in [{"version": true}, {"phase": "missing"}, {"rider": -1}, {"rider": 1.5}, {"rider": 2147483648}, {"height": NAN}, {"height": "2"}, {"height": 8}, {"rider": 0}, {"phase": "ground"}, {"extra": 7}]:
		var bad := mid.duplicate()
		bad.merge(patch, true)
		check(not replica.valid_snapshot(bad) and not replica.restore(bad) and replica.snapshot() == before_rejection, "invalid snapshot rejected atomically: %s" % str(patch))
	var missing := mid.duplicate()
	missing.erase("height")
	check(not replica.restore(missing) and not replica.restore(null), "incomplete and non-dictionary snapshot rejected")
	host.step(10.0, positions, directions)
	check(host.snapshot().phase == "upper" and positions[17] == ORIGIN + Vector3.UP * Lift.HEIGHT, "large final step docks at 6 m")
	check(host.occupied(17) and host.get_node("Cab/CabGate").visible, "upper observation stop retains rider")
	check(not host.request(17, ORIGIN) and not host.request(23, positions[17]), "only the onboard rider can request return")
	check(host.request(17, positions[17]), "rider commands return from observation stop")
	host.step(0.25, positions, directions)
	check(positions[17] == ORIGIN + Vector3.UP * (Lift.HEIGHT - 0.25 * Lift.SPEED), "descending player moves with cab")
	check(not host.request(17, positions[17]), "descending rider cannot exit")
	host.step(10.0, positions, directions)
	check(host.snapshot().phase == "returned" and host.occupied(17) and positions[17] == ORIGIN, "arrived at ground ready to exit")
	check(not host.get_node("StreetGate").visible and not host.get_node("Cab/CabGate").visible, "street and cab gates open on return")
	check(host.request(17, positions[17]) and host.snapshot() == initial, "exit frees cab at street level")
	# Disconnect mid-ascent, at the top, or just after boarding.
	for seconds: float in [0.6, 4.0, 0.0]:
		check(host.request(17, ORIGIN), "board for disconnect case")
		if seconds > 0.0:
			check(host.request(17, ORIGIN), "start trip before disconnect")
			host.step(seconds, positions, directions)
		var at_height: float = host.snapshot().height
		host.release_peer(23)
		check(host.occupied(17), "another member leaving leaves passenger seated")
		positions.erase(17)
		if seconds == 0.6:
			# The tick also recovers when membership disappears before cleanup.
			host.step(0.1, positions, directions)
			check(is_equal_approx(host.snapshot().height, at_height - 0.1 * Lift.SPEED), "unoccupied cab returns continuously")
		else:
			host.release_peer(17)
		check(host.valid_snapshot(host.snapshot()) and not host.occupied(17), "disconnect produces valid recoverable state")
		if at_height > 0.0:
			check(not host.request(23, ORIGIN), "unoccupied cab must dock before boarding")
		host.step(4.0, positions, directions)
		check(host.snapshot() == initial and not positions.has(17), "returns to ground without reviving disconnected peer")
		positions[17] = ORIGIN
	check(host.configure(ORIGIN) and host.snapshot() == initial, "reset lift for a new session")
	check(not host.configure(Vector3(NAN, 0, 0)) and host.position == ORIGIN, "reject nonfinite origin")
	host.free()
	replica.free()
	if failures == 0:
		print("PASS shared observation lift")
	quit(1 if failures else 0)
