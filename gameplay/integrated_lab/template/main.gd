extends Node2D

const Session = preload("res://session.gd")
const Player = preload("res://player.gd")
const Yard = preload("res://yard.gd")
const Hud = preload("res://hud.gd")

var session = Session.new()
var player
var yard
var hud

func _ready() -> void:
	yard = Yard.new()
	yard.name = "Glassworks"
	add_child(yard)
	player = Player.new()
	player.name = "Courier"
	add_child(player)
	player.configure(session)
	var overlay := CanvasLayer.new()
	add_child(overlay)
	hud = Hud.new()
	hud.name = "MissionHUD"
	overlay.add_child(hud)
	hud.retry_requested.connect(_retry)
	_sync()

func _retry() -> void:
	session.command(session.snapshot().epoch, "retry")
	_sync()

func snapshot() -> Dictionary:
	return session.snapshot()

func _sync() -> void:
	var state := snapshot()
	yard.sync(state, session.blocked_cells())
	player.sync(state)
	hud.sync(state)

# The real input path and QA both use this method. Modal input cannot leak
# through to the world, even for an unmapped button or a rejected move.
func dispatch(event: InputEvent) -> bool:
	if hud == null:
		return false
	if hud.handle(event):
		_sync()
		return true
	if hud.modal_open:
		# Pointer events go to native GUI controls, never to the player.
		return not event is InputEventMouse
	if player.handle(event):
		_sync()
		return true
	return false

func _input(event: InputEvent) -> void:
	if dispatch(event):
		get_viewport().set_input_as_handled()
