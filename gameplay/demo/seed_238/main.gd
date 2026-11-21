extends Node3D

const PLAYER = preload("res://player.gd")
var world: Node3D
var player: CharacterBody3D
var spec: Dictionary
var goal_reached := false
var goal: Marker3D
var status: Label

func _ready() -> void:
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://level.json"))
	if not parsed is Dictionary:
		push_error("Level JSON is invalid")
		return
	spec = parsed
	var packed = load("res://world.tscn") as PackedScene
	if packed == null:
		push_error("Baked world scene missing")
		return
	world = packed.instantiate() as Node3D
	add_child(world)
	var spawn = world.get_node("Spawn") as Marker3D
	goal = world.get_node("Goal") as Marker3D
	player = PLAYER.new()
	player.name = "Player"
	add_child(player)
	player.global_position = spawn.global_position + Vector3(0, 0.08, 0)
	_create_hud()
	print("STUDIO_WORLD_READY")

func _create_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	status = Label.new()
	status.position = Vector2(20, 20)
	status.text = "TRAINING YARD  |  Reach the marked goal.\nWASD move  •  Mouse look  •  Shift sprint  •  Space jump"
	status.add_theme_font_size_override("font_size", 18)
	layer.add_child(status)
	var cross := Label.new()
	cross.text = "+"
	cross.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	cross.position -= Vector2(7, 10)
	cross.add_theme_font_size_override("font_size", 24)
	layer.add_child(cross)

func _physics_process(_dt: float) -> void:
	if player == null or goal == null or goal_reached:
		return
	var diff := player.global_position - goal.global_position
	if Vector2(diff.x, diff.z).length() <= 1.0 and abs(diff.y) <= 1.2:
		goal_reached = true
		status.text = "MISSION COMPLETE  |  You reached the goal."
		print("STUDIO_GOAL_REACHED")
