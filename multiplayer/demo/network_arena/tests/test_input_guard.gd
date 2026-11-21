extends SceneTree

const Guard = preload("res://input_guard.gd")
var failures := 0

func check(condition: bool, label: String) -> void:
	if not condition:
		push_error(label)
		failures += 1

func _initialize() -> void:
	var guard = Guard.new()
	for peer in [-1, 0]:
		check(not guard.accept(peer, 0, Vector2.ZERO, 0, false, false, 0), "invalid peer")
	for axis in [Vector2(NAN, 0), Vector2(0, INF), Vector2.ONE]:
		check(not guard.accept(1, 0, axis, 0, false, false, 0), "invalid axis")
	for yaw in [NAN, INF, -INF, TAU + 0.001, -TAU - 0.001]:
		check(not guard.accept(1, 0, Vector2.ZERO, yaw, false, false, 0), "invalid yaw")
	for seq in [-1, 2147483648]:
		check(not guard.accept(1, seq, Vector2.ZERO, 0, false, false, 0), "invalid sequence")
	check(not guard.accept(1, 0, Vector2.ZERO, 0, false, false, -1), "invalid time")
	for i in range(40):
		check(guard.accept(1, i, Vector2.RIGHT, TAU, true, true, 10 + i), "burst allowance")
	check(not guard.accept(1, 40, Vector2.ZERO, 0, false, false, 1009), "rolling window")
	check(guard.accept(1, 40, Vector2.ZERO, -TAU, false, false, 1010), "oldest expires")
	check(not guard.accept(1, 41, Vector2.ZERO, 0, false, false, 1008), "clock regression")
	check(not guard.accept(1, 40, Vector2.ZERO, 0, false, false, 2010), "duplicate")
	check(not guard.accept(1, 39, Vector2.ZERO, 0, false, false, 2010), "stale")
	for peer in range(2, 17):
		check(guard.accept(peer, 2147483647, Vector2.ZERO, 0, false, false, 2010), "independent peer")
	check(not guard.accept(17, 0, Vector2.ZERO, 0, false, false, 2010), "peer capacity")
	guard.forget(1)
	check(guard.accept(17, 0, Vector2.ZERO, 0, false, false, 2010), "released slot")
	guard.forget(17)
	check(guard.accept(1, 0, Vector2.ZERO, 0, false, false, 2010), "reconnect resets sequence")
	check(guard.accepted == 58 and guard.rejected == 18, "independent counters")
	print("input guard failures: ", failures)
	quit(1 if failures else 0)
