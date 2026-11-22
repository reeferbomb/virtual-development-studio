extends RefCounted

# In this stage puzzle "cover" means a marked lightproof bay. A flash pauses
# performances for a bounded number of ticks. No aiming or damage is modeled.
class Performer extends Node2D:
	var role: String
	var original_role: String
	var enabled := true
	var waypoint: int
	var next_waypoint := -1
	var slot := -1
	var readings := 0
	var chimes := 0
	var last_chimed_revision := 0

	func path_origin() -> int:
		return next_waypoint if next_waypoint != -1 else waypoint

	func travel(graph: AStar2D, destination: int, stride: float) -> void:
		# Complete the current edge even if the destination changes mid-step.
		if next_waypoint == -1:
			if destination == waypoint or destination == -1:
				return
			var route := graph.get_id_path(waypoint, destination)
			if route.size() < 2:
				return
			next_waypoint = route[1]
		var toward := graph.get_point_position(next_waypoint)
		position = position.move_toward(toward, stride)
		if position == toward:
			waypoint = next_waypoint
			next_waypoint = -1

class Ensemble extends Node2D:
	const STRIDE := 4.0
	const SIGHT_RADIUS := 15.0
	const MEMORY_TICKS := 3
	const MAX_FLASH := 16
	var graph := AStar2D.new()
	var homes := {"reader": 0, "ringer": 1, "standby": 5}
	var members: Array[Performer] = []
	var cover_points: Array[int] = []
	var curtain := Line2D.new()
	var cue := Node2D.new()
	var tick := 0
	var pressure_left := 0
	var shared: Dictionary = {}
	var _revision := 0

	func _init() -> void:
		curtain.name = "Curtain"
		add_child(curtain)
		cue.name = "StageCue"
		add_child(cue)

	func add_performer(id: String, role: String, start: int) -> Performer:
		if not homes.has(role) or not graph.has_point(start) or not graph.has_point(homes[role]):
			return null
		for peer in members:
			if peer.name == id or (peer.enabled and peer.role == role and role != "standby"):
				return null
		var performer := Performer.new()
		performer.name = id
		performer.role = role
		performer.original_role = role
		performer.waypoint = start
		add_child(performer)
		performer.position = graph.get_point_position(start)
		members.append(performer)
		return performer

	func _role_filled(role: String) -> bool:
		for member in members:
			if member.enabled and member.role == role:
				return true
		return false

	func set_enabled(member: Performer, enabled: bool) -> void:
		if member not in members or member.enabled == enabled:
			return
		member.enabled = enabled
		member.slot = -1
		if enabled:
			for role in [member.original_role, "reader", "ringer"]:
				if role != "standby" and not _role_filled(role):
					member.role = role
					break
			return
		var vacant := member.role
		member.role = "standby"
		if vacant == "standby":
			return
		for peer in members:
			if peer.enabled and peer.role == "standby":
				peer.role = vacant
				return

	func flash(duration_ticks: int) -> void:
		pressure_left = maxi(pressure_left, clampi(duration_ticks, 0, MAX_FLASH))

	func _read_signal(reader: Performer) -> void:
		if reader.position.distance_to(cue.position) > SIGHT_RADIUS:
			return
		for i in range(1, curtain.get_point_count()):
			var hit: Variant = Geometry2D.segment_intersects_segment(reader.global_position, cue.global_position,
					curtain.to_global(curtain.get_point_position(i - 1)), curtain.to_global(curtain.get_point_position(i)))
			if hit != null:
				return
		if shared.is_empty() or shared.position != cue.position:
			_revision += 1
		shared = {"position": cue.position, "source": str(reader.name), "seen_tick": tick,
				"expires_tick": tick + MEMORY_TICKS, "revision": _revision}
		reader.readings += 1

	func _reserve(member: Performer, occupied: Dictionary) -> void:
		var shortest := INF
		var best := -1
		for point in cover_points:
			if occupied.has(point) or not graph.has_point(point) or graph.is_point_disabled(point):
				continue
			var route := graph.get_point_path(member.path_origin(), point)
			if route.is_empty():
				continue
			var length := 0.0
			for i in range(1, route.size()):
				length += route[i - 1].distance_to(route[i])
			if length < shortest or (length == shortest and point < best):
				shortest = length
				best = point
		member.slot = best
		if best != -1:
			occupied[best] = true

	func advance() -> void:
		tick += 1
		if not shared.is_empty() and tick >= int(shared.expires_tick):
			shared = {}
		if pressure_left > 0:
			var occupied := {}
			for member in members:
				if member.enabled and member.slot != -1:
					occupied[member.slot] = true
			for member in members:
				if member.enabled:
					if member.slot == -1:
						_reserve(member, occupied)
					member.travel(graph, member.slot, STRIDE)
			pressure_left -= 1
			return
		for member in members:
			member.slot = -1
			if member.enabled:
				member.travel(graph, int(homes[member.role]), STRIDE)
		for member in members:
			if member.enabled and member.role == "reader":
				_read_signal(member)
		# A ringer receives the observation record. Only the reader accesses the cue.
		for member in members:
			if member.enabled and member.role == "ringer" and not shared.is_empty():
				if member.position == graph.get_point_position(homes.ringer) and member.last_chimed_revision != int(shared.revision):
					member.chimes += 1
					member.last_chimed_revision = int(shared.revision)


func _fixture() -> Ensemble:
	var show := Ensemble.new()
	var points := [Vector2(0, 0), Vector2(12, 0), Vector2(24, 0), Vector2(12, 12),
			Vector2(24, 12), Vector2(0, 12), Vector2(0, 2)]
	for id in points.size():
		show.graph.add_point(id, points[id])
	for edge in [[0, 1], [1, 2], [1, 3], [2, 4], [3, 4], [3, 5], [0, 5]]:
		show.graph.connect_points(edge[0], edge[1])
	# Point 6 is geographically close to the reader but has no walkway.
	show.cover_points.assign([6, 2, 4])
	show.curtain.points = PackedVector2Array([Vector2(6, -4), Vector2(6, 4)])
	show.add_performer("Pip", "reader", 0)
	show.add_performer("Copper", "ringer", 1)
	show.add_performer("Loop", "standby", 5)
	return show


func _check(id: String, passed: bool, detail: String) -> Dictionary:
	return {"id": id, "passed": passed, "detail": detail}


func _step(show: Ensemble, evidence: Dictionary) -> void:
	var old: Array[Vector2] = []
	for member in show.members:
		old.append(member.position)
	show.advance()
	var occupied: Array[int] = []
	for i in show.members.size():
		var member := show.members[i]
		var distance := old[i].distance_to(member.position)
		evidence.max_step = maxf(float(evidence.max_step), distance)
		if distance > 0.0:
			evidence.travel_ticks = int(evidence.travel_ticks) + 1
		var on_edge := false
		for a in show.graph.get_point_ids():
			for b in show.graph.get_point_connections(a):
				var nearest := Geometry2D.get_closest_point_to_segment(member.position,
						show.graph.get_point_position(a), show.graph.get_point_position(b))
				if member.position.distance_to(nearest) < 0.001:
					on_edge = true
		evidence.on_graph = bool(evidence.on_graph) and on_edge
		if member.slot != -1:
			if member.slot in occupied or member.slot == 6 or not member.enabled:
				evidence.unique_slots = false
			occupied.append(member.slot)


func run(tree: SceneTree) -> Dictionary:
	var show := _fixture()
	show.position = Vector2(64, -32)
	tree.root.add_child(show)
	var reader := show.members[0]
	var ringer := show.members[1]
	var spare := show.members[2]
	var evidence := {"max_step": 0.0, "travel_ticks": 0, "on_graph": true, "unique_slots": true}
	var checks: Array[Dictionary] = []
	show.cue.position = show.graph.get_point_position(1)
	await tree.process_frame
	_step(show, evidence)
	var screened := show.shared.is_empty() and reader.readings == 0 and ringer.chimes == 0
	show.cue.position = show.graph.get_point_position(5)
	_step(show, evidence)
	var receipt := show.shared.duplicate()
	var roles_ok := reader.readings == 1 and reader.chimes == 0 and ringer.readings == 0 and ringer.chimes == 1 and spare.chimes == 0 and spare.readings == 0
	var acquired: bool = not receipt.is_empty() and receipt.get("source") == "Pip" and receipt.get("position") == Vector2(0, 12)
	show.cue.position = show.graph.get_point_position(4)
	_step(show, evidence)
	_step(show, evidence)
	var remembered := show.shared == receipt and ringer.chimes == 1
	_step(show, evidence)
	var expired_tick := show.tick
	var expired := show.shared.is_empty() and expired_tick == int(receipt.get("expires_tick", -1)) and ringer.chimes == 1
	checks.append(_check("role-work", roles_ok, "Only the reader acquired the cue. The ringer issued one chime and the understudy held."))
	checks.append(_check("local-observation", screened and acquired and remembered, "The curtain blocked a nearby cue. A visible cue was shared, then its recorded position stayed fixed when it moved out of sight."))
	checks.append(_check("observation-expiry", expired, "Observation from tick %d expired at tick %d without another chime." % [int(receipt.get("seen_tick", -1)), expired_tick]))

	show.cue.position = show.graph.get_point_position(5)
	show.flash(30)
	var bounded_flash := show.pressure_left == Ensemble.MAX_FLASH
	_step(show, evidence)
	var initial_slots := [reader.slot, ringer.slot, spare.slot]
	var slot_ok := initial_slots == [2, 4, -1]
	var vacated := ringer.slot
	var disabled_at := ringer.position
	show.set_enabled(ringer, false)
	var handoff_ok := ringer.slot == -1 and ringer.role == "standby" and spare.role == "ringer" and ringer.position == disabled_at
	await tree.process_frame
	_step(show, evidence)
	handoff_ok = handoff_ok and spare.slot == vacated and spare.position != show.graph.get_point_position(vacated)
	while show.pressure_left > 0:
		_step(show, evidence)
	var before_return := show.tick
	var housed := reader.position == show.graph.get_point_position(2) and spare.position == show.graph.get_point_position(4)
	var suppressed := reader.readings == 1 and spare.chimes == 0 and show.shared.is_empty()
	handoff_ok = handoff_ok and ringer.position == disabled_at
	for i in 12:
		await tree.process_frame
		_step(show, evidence)
	var recovered := reader.slot == -1 and spare.slot == -1 and reader.readings > 1 and spare.chimes == 1
	recovered = recovered and reader.position == show.graph.get_point_position(0) and spare.position == show.graph.get_point_position(1)
	show.set_enabled(ringer, true)
	handoff_ok = handoff_ok and ringer.role == "standby" and spare.role == "ringer" and ringer.position == disabled_at
	_step(show, evidence)
	show.set_enabled(ringer, false)
	show.set_enabled(spare, false)
	show.set_enabled(ringer, true)
	handoff_ok = handoff_ok and ringer.role == "ringer"
	checks.append(_check("slot-deconfliction", slot_ok and bool(evidence.unique_slots) and housed,
			"Three performers requested two reachable bays. Initial reservations %s. A disconnected bay was never assigned." % [initial_slots]))
	var motion_ok: bool = evidence.on_graph and int(evidence.travel_ticks) > 12 and float(evidence.max_step) <= Ensemble.STRIDE
	checks.append(_check("path-continuity", motion_ok, "Godot node motion stayed on walkways across %d moving samples. Maximum displacement %.2f." % [int(evidence.travel_ticks), float(evidence.max_step)]))
	checks.append(_check("pressure-recovery", bounded_flash and suppressed and recovered,
			"The stage flash ended after %d ticks. The performers released their bays, resumed their jobs and returned to their stations." % Ensemble.MAX_FLASH))
	checks.append(_check("disabled-handoff", handoff_ok, "Disabling a moving ringer released its bay and promoted the waiting understudy. Re-enabling the former ringer preserved the assignment."))
	var metrics := {"ticks": show.tick, "initial_slots": initial_slots, "last_seen_tick": int(receipt.get("seen_tick", -1)),
			"expired_tick": expired_tick, "pressure_last_tick": before_return, "replacement_chimes": spare.chimes,
			"travel_samples": evidence.travel_ticks, "max_step": evidence.max_step, "active_cover_capacity": 2}
	show.free()
	return {"id": "squad", "checks": checks, "metrics": metrics}
