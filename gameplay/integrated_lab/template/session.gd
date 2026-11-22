extends RefCounted

const SIZE := Vector2i(10, 7)
const START := Vector2i(2, 3)
const JUNCTION := Vector2i(3, 3)
const WINCH := Vector2i(3, 2)
const STAIRHEAD := Vector2i(3, 5)
const PLATFORM := Vector2i(4, 2)
const STAIRS := Vector2i(4, 5)
const DELIVERY := Vector2i(7, 3)
const SHELTER := Vector2i(6, 5)
const HOMES := [Vector2i(2, 2), Vector2i(2, 4)]
const RACKS := [Vector2i(7, 2), Vector2i(7, 4)]
const DIRECTIONS := [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]
const MAX_TRACE := 256

var _epoch := 1
var _tick := 0
var _player := START
var _entry_bank := WINCH
var _discovered := false
var _route := "none"
var _delivered := false
var _optional := false
var _workers: Array[Vector2i] = []
var _eastbound: Array[bool] = []
var _worker_banks: Array[Vector2i] = []
var _shipments := 0
var _platform_steps := 0
var _stair_steps := 0
var _cart_state := "idle"
var _cart_due := -1
var _cart_result := "none"
var _cart_resolved := -1
var _cart_arrivals := 0
var _cart_cancellations := 0
var _trace: Array[Dictionary] = []
var _grid := AStarGrid2D.new()


func _init() -> void:
	_reset()


func _reset() -> void:
	_tick = 0
	_player = START
	_entry_bank = WINCH
	_discovered = false
	_route = "none"
	_delivered = false
	_optional = false
	_workers.assign(HOMES)
	_eastbound.assign([true, true])
	_worker_banks.assign([WINCH, WINCH])
	_shipments = 0
	_platform_steps = 0
	_stair_steps = 0
	_cart_state = "idle"
	_cart_due = -1
	_cart_result = "none"
	_cart_resolved = -1
	_cart_arrivals = 0
	_cart_cancellations = 0
	_trace.clear()
	_grid.region = Rect2i(Vector2i.ZERO, SIZE)
	_grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER
	_grid.default_compute_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	_grid.default_estimate_heuristic = AStarGrid2D.HEURISTIC_MANHATTAN
	_grid.update()
	for y in range(SIZE.y):
		for x in range(SIZE.x):
			var p := Vector2i(x, y)
			var boundary := x == 0 or y == 0 or x == SIZE.x - 1 or y == SIZE.y - 1
			_grid.set_point_solid(p, boundary or (x == 4 and p != STAIRS))
	_record("session-start")


func _rain_at(turn: int) -> bool:
	return turn % 12 >= 8


func _xy(p: Vector2i) -> Array:
	return [p.x, p.y]


func _record(event: String, data: Dictionary = {}) -> void:
	if _trace.size() == MAX_TRACE:
		_trace.pop_front()
	_trace.append({"tick": _tick, "event": event, "data": data})


func blocked_cells() -> Array[Vector2i]:
	var cells: Array[Vector2i] = []
	for y in range(SIZE.y):
		for x in range(SIZE.x):
			var cell := Vector2i(x, y)
			if _grid.is_point_solid(cell):
				cells.append(cell)
	return cells


func snapshot() -> Dictionary:
	return {"epoch": _epoch, "tick": _tick, "player": _xy(_player), "discovered": _discovered,
		"route": _route, "platform_open": not _grid.is_point_solid(PLATFORM), "rain": _rain_at(_tick),
		"delivered": _delivered, "reward": (10 if _delivered else 0) + (3 if _optional else 0),
		"optional_done": _optional, "workers": [_xy(_workers[0]), _xy(_workers[1])],
		"shipments": _shipments, "worker_platform_steps": _platform_steps, "worker_stair_steps": _stair_steps,
		"cart_state": _cart_state, "cart_cell": _xy(JUNCTION), "cart_due_tick": _cart_due,
		"cart_last_result": _cart_result, "cart_resolved_tick": _cart_resolved,
		"cart_arrivals": _cart_arrivals, "cart_cancellations": _cart_cancellations, "trace": _trace.duplicate(true)}


func _interaction() -> String:
	if _player == JUNCTION and not _discovered:
		return "discover"
	if _discovered and _route == "none":
		if _player == WINCH:
			return "platform"
		if _player == STAIRHEAD:
			return "stairs"
	if _route != "none":
		if _player == DELIVERY and not _delivered:
			return "deliver"
		if _player == SHELTER and not _optional:
			return "optional-complete"
	return ""


func command(epoch: int, action: String, value: Variant = null) -> bool:
	if epoch != _epoch or (action != "move" and typeof(value) != TYPE_NIL):
		return false
	var interaction := ""
	var destination := _player
	match action:
		"retry":
			_epoch += 1
			_reset()
			return true
		"move":
			if typeof(value) != TYPE_VECTOR2I or value not in DIRECTIONS:
				return false
			destination = _player + value
			if not _grid.is_in_boundsv(destination) or _grid.is_point_solid(destination):
				return false
			if destination == PLATFORM and _rain_at(_tick + 1):
				return false
		"interact":
			interaction = _interaction()
			if interaction.is_empty():
				return false
		"wait":
			pass
		_:
			return false
	_tick += 1
	if action == "move":
		_record("move", {"from": _xy(_player), "to": _xy(destination)})
		if destination == PLATFORM:
			_entry_bank = _player
		_player = destination
	elif action == "wait":
		_record("wait")
	else:
		match interaction:
			"discover":
				_discovered = true
				_record("discover")
			"platform", "stairs":
				_route = interaction
				_record("choose-route", {"route": _route})
			"deliver":
				_delivered = true
				_record("deliver", {"amount": 10})
			"optional-complete":
				_optional = true
				_record("optional-complete", {"amount": 3})
	var rain := _rain_at(_tick)
	_grid.set_point_solid(PLATFORM, _route != "platform" or rain)
	if rain != _rain_at(_tick - 1):
		_record("rain-start" if rain else "rain-end")
	if rain and _player == PLATFORM:
		_player = _entry_bank
		_record("platform-return", {"to": _xy(_player)})
	_advance_workers()
	_advance_cart()
	return true


func _advance_workers() -> void:
	if _route == "none":
		return
	var next: Array[Vector2i] = _workers.duplicate()
	for i in range(_workers.size()):
		if _workers[i] == PLATFORM and _grid.is_point_solid(PLATFORM):
			next[i] = _worker_banks[i]
			continue
		var destination: Vector2i = RACKS[i] if _eastbound[i] else HOMES[i]
		var path := _grid.get_id_path(_workers[i], destination)
		if path.size() > 1:
			next[i] = path[1]
	# Reserve distinct destinations before committing either movement. On a
	# closure the platform passenger always takes a bank cell.
	if next[0] == next[1]:
		var winner := _tick % 2
		for i in range(2):
			if _workers[i] == next[i]:
				winner = i
		var loser := 1 - winner
		next[loser] = _workers[loser]
		if next[loser] == PLATFORM and _grid.is_point_solid(PLATFORM):
			next[loser] = PLATFORM * 2 - next[winner]
	for i in range(_workers.size()):
		if next[i] == _workers[i]:
			continue
		if next[i] == PLATFORM:
			_worker_banks[i] = _workers[i]
			_platform_steps += 1
		elif next[i] == STAIRS:
			_stair_steps += 1
		_workers[i] = next[i]
		if _eastbound[i] and next[i] == RACKS[i]:
			_shipments += 1
			_eastbound[i] = false
			_record("shipment", {"worker": i})
		elif not _eastbound[i] and next[i] == HOMES[i]:
			_eastbound[i] = true


func _advance_cart() -> void:
	if not _discovered:
		return
	if _cart_state == "idle" or (_cart_state == "cooldown" and _tick >= _cart_due):
		_cart_state = "warning"
		_cart_due = _tick + 2
		_record("cart-warning")
	elif _cart_state == "warning" and _tick >= _cart_due:
		if _player == JUNCTION or JUNCTION in _workers:
			_cart_cancellations += 1
			_cart_result = "occupied"
			_record("cart-cancel")
		else:
			_cart_arrivals += 1
			_cart_result = "arrival"
			_record("cart-arrival")
		_cart_resolved = _tick
		_cart_state = "cooldown"
		_cart_due = _tick + 4
