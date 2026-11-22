extends Node2D

const ORIGIN := Vector2(32, 112)
const TILE := 72
const COLUMNS := 10
const ROWS := 7
const PLATFORM := Vector2i(4, 2)
const STAIRS := Vector2i(4, 5)
const INK := Color("#182f30")
const PAPER := Color("#f1e8ce")
const STONE := Color("#e5d9b9")
const GROUT := Color("#cec2a4")
const BOTTLE := Color("#275957")
const GLASS := Color("#91c5b6")
const BRASS := Color("#d6a657")
const BRICK := Color("#aa5c48")

var worker_positions: Array[Vector2] = []
var crossing_open := false
var wet := false
var shipment_count := 0
var receipt_visible := false
var rack_covered := false
var _blocked: Array[Vector2i] = []
var _discovered := false
var _cart_position := Vector2.ZERO
var _cart_warning := false
var _cart_arrived := false


func cell_center(cell: Vector2i) -> Vector2:
	return ORIGIN + Vector2(cell) * TILE + Vector2.ONE * TILE * 0.5


func sync(snapshot: Dictionary, blocked: Array[Vector2i]) -> void:
	_blocked.assign(blocked)
	crossing_open = not blocked.has(PLATFORM)
	wet = snapshot.rain
	shipment_count = snapshot.shipments
	receipt_visible = snapshot.delivered
	rack_covered = snapshot.optional_done
	_discovered = snapshot.discovered
	worker_positions.clear()
	for cell in snapshot.workers:
		worker_positions.append(cell_center(Vector2i(cell[0], cell[1])))
	var cart_cell: Array = snapshot.get("cart_cell", [3, 3])
	_cart_position = cell_center(Vector2i(cart_cell[0], cart_cell[1]))
	_cart_warning = snapshot.get("cart_state", "idle") == "warning"
	_cart_arrived = (snapshot.get("cart_last_result", "none") == "arrival"
		and snapshot.get("cart_resolved_tick", -1) == snapshot.tick)
	queue_redraw()


func _box(at: Vector2, size: Vector2, color: Color) -> void:
	draw_rect(Rect2(at, size), color)


func _label(at: Vector2, value: String, size: int, color: Color) -> void:
	draw_string(ThemeDB.fallback_font, at, value, HORIZONTAL_ALIGNMENT_LEFT, -1, size, color)


func _plate(center: Vector2, title: String) -> void:
	var width := ThemeDB.fallback_font.get_string_size(title, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x + 10
	_box(center - Vector2(width / 2, 0), Vector2(width, 17), INK)
	_label(center + Vector2(5 - width / 2, 13), title, 12, PAPER)


func _draw() -> void:
	_box(Vector2(16, 16), Vector2(752, 688), PAPER)
	_box(Vector2(26, 26), Vector2(732, 678), STONE)
	_box(Vector2(26, 26), Vector2(732, 78), PAPER)
	draw_line(Vector2(32, 98), Vector2(752, 98), INK, 2)
	_header()
	_box(ORIGIN - Vector2(2, 2), Vector2(COLUMNS, ROWS) * TILE + Vector2(4, 4), INK)
	_box(ORIGIN, Vector2(COLUMNS, ROWS) * TILE, STONE)
	for x in range(COLUMNS):
		for y in range(ROWS):
			var corner := ORIGIN + Vector2(x, y) * TILE
			if _blocked.has(Vector2i(x, y)) and x != PLATFORM.x:
				_wall(corner, x, y)
			else:
				draw_rect(Rect2(corner, Vector2(TILE, TILE)), GROUT, false, 1)
	_waterway()
	_bridge(cell_center(PLATFORM), crossing_open)
	_stair_bridge(cell_center(STAIRS))
	_winch(cell_center(Vector2i(3, 2)))
	_stairhead(cell_center(Vector2i(3, 5)))
	_chart_board(cell_center(Vector2i(3, 3)))
	_rack(cell_center(Vector2i(6, 5)))
	_dispatch(cell_center(Vector2i(7, 3)))
	if wet:
		_rain()
	if _cart_warning or _cart_arrived:
		_cart(_cart_position)
	for index in worker_positions.size():
		# A small fixed left/right offset keeps both aprons visible on a shared tile.
		var side := -1 if index % 2 == 0 else 1
		_worker(worker_positions[index] + Vector2(15 * side, -11), side)
	_footer()


func _header() -> void:
	_box(Vector2(42, 38), Vector2(46, 46), BOTTLE)
	# Maker's stamp: three cut panes with an unglazed diamond at their centre.
	for offset in [Vector2(0, -9), Vector2(-8, 4), Vector2(8, 4)]:
		var c: Vector2 = Vector2(65, 61) + offset
		draw_colored_polygon(PackedVector2Array([c + Vector2(0, -8), c + Vector2(6, 0),
			c + Vector2(0, 8), c + Vector2(-6, 0)]), GLASS)
	_label(Vector2(103, 70), "Millrace Glassworks", 33, INK)
	_label(Vector2(105, 89), "DISPATCH YARD", 12, BOTTLE)
	var weather := "Rain on the race" if wet else "Clear morning"
	if wet:
		for offset in [0, 7, 14]:
			draw_line(Vector2(563 + offset, 46), Vector2(558 + offset, 58), BOTTLE, 2)
	else:
		draw_arc(Vector2(566, 53), 8, 0, TAU, 20, BRICK, 3, true)
	_label(Vector2(588, 60), weather, 18, INK)


func _wall(corner: Vector2, x: int, y: int) -> void:
	_box(corner, Vector2(TILE, TILE), BOTTLE)
	if y == 0 or y == ROWS - 1:
		# Clerestory strip with leaded panes and spouts facing the yard.
		_box(corner + Vector2(3, 12), Vector2(66, 40), INK)
		for i in 3:
			var pane := corner + Vector2(6 + 21 * i, 15)
			_box(pane, Vector2(18, 34), GLASS)
			draw_line(pane + Vector2(1, 25), pane + Vector2(16, 8), BOTTLE, 2)
		_box(corner + Vector2(0, 58), Vector2(TILE, 7), BRASS)
	else:
		var inset := 22 if x == 0 else 12
		_box(corner + Vector2(inset, 8), Vector2(38, 53), INK)
		for i in 4:
			_box(corner + Vector2(inset + 4, 14 + i * 11), Vector2(30, 4), BOTTLE)


func _waterway() -> void:
	var top := ORIGIN + Vector2(PLATFORM.x * TILE, 0)
	_box(top, Vector2(TILE, ROWS * TILE), INK)
	_box(top + Vector2(5, 0), Vector2(TILE - 10, ROWS * TILE), BOTTLE)
	for i in 23:
		var c := top + Vector2(9 + (i * 19) % 37, 5 + i * 22)
		draw_polyline(PackedVector2Array([c, c + Vector2(4, 5), c + Vector2(4, 12)]),
			GLASS, 1.5, true)
	# The gauge and mineral tide marks remain after the rain passes.
	var gauge := top + Vector2(4, 3 * TILE + 10)
	_box(gauge, Vector2(9, 45), PAPER)
	for i in 5:
		draw_line(gauge + Vector2(1, 5 + 8 * i), gauge + Vector2(6, 5 + 8 * i), INK, 2)
	draw_line(gauge + Vector2(1, 12 if wet else 35), gauge + Vector2(9, 12 if wet else 35), BRICK, 3)


func _bridge(c: Vector2, open: bool) -> void:
	if open:
		_box(c + Vector2(-38, -22), Vector2(76, 42), INK)
		for i in 7:
			_box(c + Vector2(-36 + i * 10, -19), Vector2(9, 36), BRASS)
		draw_line(c + Vector2(-36, -23), c + Vector2(36, -23), PAPER, 3)
	else:
		for side in [-1, 1]:
			var pivot := c + Vector2(side * 29, 0)
			_box(pivot + Vector2(-5, -20), Vector2(10, 40), BRASS)
			draw_line(pivot + Vector2(0, -16), pivot + Vector2(-side * 9, -8), PAPER, 3)
			draw_line(pivot + Vector2(0, 16), pivot + Vector2(-side * 9, 8), PAPER, 3)
		draw_line(c + Vector2(-6, -6), c + Vector2(6, 6), PAPER, 3)
		draw_line(c + Vector2(-6, 6), c + Vector2(6, -6), PAPER, 3)
	_plate(c + Vector2(0, 17), "OPEN" if open else "CLOSED")


func _stair_bridge(c: Vector2) -> void:
	_box(c + Vector2(-37, -16), Vector2(74, 35), INK)
	for i in 8:
		_box(c + Vector2(-35 + 9 * i, -14), Vector2(8, 29), PAPER if i % 2 == 0 else GROUT)
	for side in [-1, 1]:
		draw_line(c + Vector2(-36, side * 19), c + Vector2(36, side * 19), BRASS, 3)


func _winch(c: Vector2) -> void:
	var h := c + Vector2(2, -7)
	draw_line(h, h + Vector2(30, 4), INK, 3)
	draw_circle(h, 17, INK)
	draw_arc(h, 13, 0, TAU, 28, BRASS, 4, true)
	for angle in [0.0, TAU / 3.0, TAU * 2.0 / 3.0]:
		draw_line(h, h + Vector2.from_angle(angle) * 12, BRASS, 3)
	draw_circle(h, 4, PAPER)
	_plate(c + Vector2(0, 15), "WINCH")


func _stairhead(c: Vector2) -> void:
	for i in 3:
		draw_polyline(PackedVector2Array([c + Vector2(-18 + i * 11, -16),
			c + Vector2(-11 + i * 11, -8), c + Vector2(-18 + i * 11, 0)]), BOTTLE, 3)
	_plate(c + Vector2(0, 15), "STAIRS")


func _chart_board(c: Vector2) -> void:
	# Chipped route board and tack holes left by previous dispatch slips.
	var board := c + Vector2(-27, -28)
	_box(board, Vector2(34, 18), BRICK)
	_box(board + Vector2(3, 3), Vector2(28, 12), INK)
	if _discovered:
		for x in [5, 25]:
			draw_circle(board + Vector2(x, 6), 1.5, PAPER)
	else:
		_box(board + Vector2(7, 3), Vector2(14, 16), PAPER)
		draw_line(board + Vector2(10, 8), board + Vector2(18, 8), BOTTLE, 2)
	_plate(c + Vector2(0, 15), "JUNCTION")


func _rack(c: Vector2) -> void:
	var top := c + Vector2(-26, -26)
	_box(top + Vector2(2, 7), Vector2(48, 29), INK)
	for i in 3:
		_box(top + Vector2(6 + i * 14, 12), Vector2(11, 15), GLASS)
		draw_line(top + Vector2(8 + i * 14, 24), top + Vector2(14 + i * 14, 14), PAPER, 1)
	if rack_covered:
		draw_colored_polygon(PackedVector2Array([top, top + Vector2(52, 0), top + Vector2(48, 25),
			top + Vector2(37, 21), top + Vector2(25, 26), top + Vector2(11, 21), top + Vector2(1, 25)]), BRASS)
		draw_line(top + Vector2(4, 6), top + Vector2(46, 6), INK, 2)
	else:
		_box(top, Vector2(52, 7), BRASS)
	_plate(c + Vector2(0, 15), "DRY RACK")


func _dispatch(c: Vector2) -> void:
	_box(c + Vector2(-21, -27), Vector2(42, 33), INK)
	_box(c + Vector2(-17, -23), Vector2(34, 25), BRICK)
	if receipt_visible:
		_box(c + Vector2(-11, -22), Vector2(22, 21), PAPER)
		draw_polyline(PackedVector2Array([c + Vector2(-8, -12), c + Vector2(-3, -7),
			c + Vector2(7, -17)]), BOTTLE, 3, true)
	else:
		_box(c + Vector2(-12, -14), Vector2(24, 5), INK)
	_plate(c + Vector2(0, 15), "DISPATCH")


func _rain() -> void:
	for cell in [Vector2i(1, 2), Vector2i(2, 4), Vector2i(5, 1), Vector2i(6, 3), Vector2i(8, 4)]:
		var c := cell_center(cell)
		draw_arc(c + Vector2(0, 7), 13, 0.3, 2.7, 12, BOTTLE, 2, true)
		for n in 3:
			draw_line(c + Vector2(-6 + 8 * n, -11), c + Vector2(-11 + 8 * n, -1), BOTTLE, 2)


func _cart(c: Vector2) -> void:
	var p := c + Vector2(20, -14)
	if _cart_warning:
		draw_colored_polygon(PackedVector2Array([p + Vector2(0, -12), p + Vector2(12, 10),
			p + Vector2(-12, 10)]), INK)
		_label(p + Vector2(-3, 7), "!", 15, PAPER)
	elif _cart_arrived:
		_box(p + Vector2(-12, -8), Vector2(23, 14), BRASS)
		draw_line(p + Vector2(-12, 6), p + Vector2(13, 6), INK, 3)
		draw_circle(p + Vector2(-8, 9), 3, INK)
		draw_circle(p + Vector2(8, 9), 3, INK)


func _worker(c: Vector2, side: int) -> void:
	# Worker's apron, shoulder sash and cap stay readable without animation.
	draw_circle(c, 9, INK)
	draw_colored_polygon(PackedVector2Array([c + Vector2(-5, 1), c + Vector2(5, 1),
		c + Vector2(7, 10), c + Vector2(-7, 10)]), BRICK if side < 0 else BOTTLE)
	draw_line(c + Vector2(-4, 2), c + Vector2(4, 8), PAPER, 2)
	draw_circle(c + Vector2(0, -5), 5, BRASS)
	_box(c + Vector2(-6, -11), Vector2(12, 4), INK)


func _footer() -> void:
	draw_line(Vector2(42, 635), Vector2(742, 635), INK, 1)
	_label(Vector2(44, 658), "Outbound glass", 17, INK)
	_label(Vector2(45, 680), "Crates dispatched   %d" % shipment_count, 14, BOTTLE)
	for i in mini(shipment_count, 6):
		var p := Vector2(216 + i * 26, 650)
		_box(p, Vector2(23, 22), INK)
		_box(p + Vector2(2, 2), Vector2(19, 18), BRASS)
		draw_line(p + Vector2(4, 17), p + Vector2(18, 5), INK, 2)
	_worker(Vector2(521, 665), -1)
	_label(Vector2(541, 670), "Glassworks crew", 15, INK)
