extends RefCounted

const SAMPLE_COUNT := 120
const TIME_LIMIT_US := 4_500_000


# The courier moves one unit per process callback so every capture exercises
# the same two checkpoints. Its movement never supplies the measured time.
class Courier extends Node2D:
	func _process(_delta: float) -> void:
		position.x += 1.0


class Recorder extends RefCounted:
	var active := false
	var intervals: Array[int] = []
	var events: Array[Dictionary] = []
	var first_us := 0
	var last_us := 0
	var last_frame := -1
	var consecutive := true
	var rejected_intervals: Array[int] = []

	func start(now_us: int, frame: int) -> bool:
		if active or not events.is_empty():
			return false
		active = true
		first_us = now_us
		last_us = now_us
		last_frame = frame
		mark("started")
		return true

	func sample(now_us: int, frame: int) -> bool:
		if not active or intervals.size() >= SAMPLE_COUNT:
			return false
		var interval_us := now_us - last_us
		if interval_us < 1 or interval_us > 10_000_000:
			rejected_intervals.append(interval_us)
			return false
		intervals.append(interval_us)
		consecutive = consecutive and frame == last_frame + 1
		last_us = now_us
		last_frame = frame
		return true

	func mark(id: String) -> void:
		events.append({
			"id": id, "sample_count": intervals.size(),
			"elapsed_us": last_us - first_us, "process_frame": last_frame,
		})

	func stop() -> bool:
		if not active:
			return false
		mark("stopped")
		active = false
		return true

	func reset() -> bool:
		if active:
			return false
		intervals.clear()
		events.clear()
		rejected_intervals.clear()
		first_us = 0
		last_us = 0
		last_frame = -1
		consecutive = true
		return true


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func _timeline_valid(recorder: Recorder) -> bool:
	var ids := ["started", "first_checkpoint", "second_checkpoint", "stopped"]
	var counts := [0, 30, 90, SAMPLE_COUNT]
	if recorder.events.size() != ids.size():
		return false
	var elapsed := 0
	var interval := 0
	for i in ids.size():
		var event := recorder.events[i]
		if event.id != ids[i] or event.sample_count != counts[i]:
			return false
		while interval < event.sample_count:
			elapsed += recorder.intervals[interval]
			interval += 1
		if event.elapsed_us != elapsed or event.process_frame != recorder.events[0].process_frame + interval:
			return false
	return true


func run(tree: SceneTree) -> Dictionary:
	var recorder := Recorder.new()
	var courier := Courier.new()
	tree.root.add_child(courier)
	courier.set_process(false)
	var checks: Array[Dictionary] = []

	# Anchor and sample at the same point in each process cycle. Engine delta
	# can be smoothed or fixed, so only the monotonic wall clock is differenced.
	await tree.process_frame
	var anchor_us := Time.get_ticks_usec()
	var frame := Engine.get_process_frames()
	var idle_rejected := not recorder.sample(anchor_us, frame) and not recorder.stop()
	var started := recorder.start(anchor_us, frame)
	var protected_start := not recorder.start(anchor_us, frame) and not recorder.reset()
	checks.append(_check("lifecycle-start", idle_rejected and started and protected_start,
		"Inactive sampling, duplicate start and reset during a capture were exercised."))
	courier.set_process(true)
	for i in SAMPLE_COUNT:
		await tree.process_frame
		var now_us := Time.get_ticks_usec()
		if not recorder.sample(now_us, Engine.get_process_frames()):
			break
		if courier.position.x == 30.0:
			recorder.mark("first_checkpoint")
		elif courier.position.x == 90.0:
			recorder.mark("second_checkpoint")
		if now_us - anchor_us >= TIME_LIMIT_US:
			break
	courier.set_process(false)
	var stopped := recorder.stop()
	var count := recorder.intervals.size()
	var duration := recorder.last_us - anchor_us
	var clock_ok := count > 0 and recorder.consecutive and recorder.rejected_intervals.is_empty()
	checks.append(_check("frame-coverage", count == SAMPLE_COUNT,
		"Captured %d of %d requested intervals in %d wall-clock microseconds." % [count, SAMPLE_COUNT, duration]))
	checks.append(_check("frame-clock", clock_ok,
		"Checked each interval for positive integer microseconds within analyzer bounds and each process frame for adjacency."))
	checks.append(_check("gameplay-timeline", _timeline_valid(recorder) and courier.position.x == SAMPLE_COUNT,
		"Checked both courier checkpoints and capture boundaries against cumulative interval times and process frame IDs."))

	# A subsequent real callback must leave a stopped recorder unchanged.
	var event_count := recorder.events.size()
	await tree.process_frame
	var rejected := not recorder.sample(Time.get_ticks_usec(), Engine.get_process_frames()) and not recorder.stop()
	checks.append(_check("lifecycle-stop", stopped and rejected and recorder.intervals.size() == count and recorder.events.size() == event_count,
		"Checked that an extra callback and repeated stop preserve the finished capture."))
	var metrics := {
		"capture": {"scenarios": [{
			"name": "Courier checkpoint traversal", "target_fps": 60,
			"frame_times_us": recorder.intervals.duplicate(), "budget": {"min_samples": SAMPLE_COUNT},
		}]},
		"sample_count": count, "elapsed_us": duration, "events": recorder.events.duplicate(true),
		"rejected_intervals_us": recorder.rejected_intervals.duplicate(),
		"clock": "Time.get_ticks_usec at consecutive SceneTree.process_frame signals",
		"scope": "Wall-clock process cadence for the owned courier scene. Headless timing cannot establish GPU or target-device performance.",
	}
	var reset := recorder.reset()
	var empty := recorder.intervals.is_empty() and recorder.events.is_empty() and recorder.last_frame == -1
	var restarted := recorder.start(Time.get_ticks_usec(), Engine.get_process_frames()) and recorder.stop()
	checks.append(_check("lifecycle-reset", reset and empty and restarted and recorder.reset(),
		"Cleared the completed capture and started a fresh recording with an independent event history."))
	courier.free()
	return {"id": "capture", "checks": checks, "metrics": metrics}
