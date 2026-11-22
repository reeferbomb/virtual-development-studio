extends Node2D

const ORIGIN := Vector2(32, 112)
const TILE_SIZE := 72.0
const KEY_BINDINGS := {
	KEY_W: Vector2i.UP, KEY_UP: Vector2i.UP,
	KEY_A: Vector2i.LEFT, KEY_LEFT: Vector2i.LEFT,
	KEY_S: Vector2i.DOWN, KEY_DOWN: Vector2i.DOWN,
	KEY_D: Vector2i.RIGHT, KEY_RIGHT: Vector2i.RIGHT,
	KEY_E: "interact", KEY_SPACE: "interact", KEY_Q: "wait",
}
const PAD_BINDINGS := {
	JOY_BUTTON_DPAD_UP: Vector2i.UP, JOY_BUTTON_DPAD_LEFT: Vector2i.LEFT,
	JOY_BUTTON_DPAD_DOWN: Vector2i.DOWN, JOY_BUTTON_DPAD_RIGHT: Vector2i.RIGHT,
	JOY_BUTTON_A: "interact", JOY_BUTTON_X: "wait",
}

const INK := Color("#172b34")
const COAT := Color("#197d83")
const CAP := Color("#f2b54e")
const PAPER := Color("#fff0bf")

var _session: RefCounted
var _epoch := -1
var _cell := Vector2i.ZERO
var _facing := 1


func _init() -> void:
	z_index = 10
	hide()


func configure(session: RefCounted) -> void:
	_session = session
	_epoch = -1
	_facing = 1
	if _session == null:
		hide()
		return
	sync(_session.call("snapshot"))


func sync(snapshot: Dictionary) -> void:
	var cell := Vector2i(snapshot.player[0], snapshot.player[1])
	var epoch := int(snapshot.epoch)
	if epoch != _epoch:
		_facing = 1
	elif cell.x != _cell.x:
		_facing = signi(cell.x - _cell.x)
	_epoch = epoch
	_cell = cell
	position = ORIGIN + (Vector2(cell) + Vector2(0.5, 0.5)) * TILE_SIZE
	show()
	queue_redraw()


# Main routes fresh events here only while the world owns input. The visible
# snapshot's epoch travels with the command so old views cannot act after retry.
func handle(event: InputEvent) -> bool:
	if _session == null or _epoch < 0:
		return false
	var binding: Variant
	if event is InputEventKey and event.pressed and not event.echo:
		var key: Key = event.physical_keycode if event.physical_keycode != KEY_NONE else event.keycode
		binding = KEY_BINDINGS.get(key)
	elif event is InputEventJoypadButton and event.pressed:
		binding = PAD_BINDINGS.get(event.button_index)
	if binding == null:
		return false
	if binding is Vector2i:
		_session.call("command", _epoch, "move", binding)
	else:
		_session.call("command", _epoch, binding, null)
	sync(_session.call("snapshot"))
	return true


func _draw() -> void:
	# A chart courier with a brass-billed cap, rolled chart and work boots.
	draw_set_transform(Vector2(0, 17), 0.0, Vector2(1, 0.28))
	draw_circle(Vector2.ZERO, 21, Color(0.06, 0.10, 0.12, 0.36), true, -1.0, true)
	draw_set_transform(Vector2.ZERO, 0.0, Vector2(_facing, 1))
	draw_rect(Rect2(-10, 7, 7, 12), INK)
	draw_rect(Rect2(2, 7, 7, 12), INK)
	draw_line(Vector2(-11, 18), Vector2(-3, 18), Color("#644536"), 4, true)
	draw_line(Vector2(1, 18), Vector2(11, 18), Color("#644536"), 4, true)
	var coat := PackedVector2Array([Vector2(-8, -5), Vector2(6, -5), Vector2(12, 2),
			Vector2(10, 12), Vector2(-12, 12), Vector2(-14, 3)])
	draw_colored_polygon(coat, COAT)
	var hem := coat.duplicate()
	hem.append(coat[0])
	draw_polyline(hem, INK, 2.0, true)
	draw_circle(Vector2(0, -10), 8, INK, true, -1.0, true)
	draw_circle(Vector2(1, -10), 6.5, Color("#e3ac85"), true, -1.0, true)
	draw_circle(Vector2(0, -16), 7.5, CAP, true, -1.0, true)
	draw_line(Vector2(-8, -14), Vector2(11, -14), INK, 4, true)
	draw_line(Vector2(-7, -15), Vector2(11, -15), CAP, 2, true)
	draw_circle(Vector2(5, -10), 1.2, INK, true, -1.0, true)
	draw_line(Vector2(-12, 8), Vector2(4, -3), INK, 7, true)
	draw_line(Vector2(-12, 8), Vector2(4, -3), PAPER, 4, true)
	draw_line(Vector2(-5, 2), Vector2(-3, 5), CAP, 2, true)
