extends Node3D

const PLAYER = preload("res://player.gd")
const COMBAT = preload("res://combat.gd")
const MISSION = preload("res://mission.gd")
const NAV = preload("res://navigation.gd")
const ENEMY = preload("res://enemy.gd")
const SAVE_PATH = "user://studio_checkpoint.json"

var player: CharacterBody3D
var world: Node3D
var combat = COMBAT.new()
var mission = MISSION.new()
var nav = NAV.new()
var spec: Dictionary
var config: Dictionary
var enemies: Dictionary = {}
var status: Label
var message := ""
var goal: Marker3D

func vec(row: Array) -> Vector3:
	return Vector3(float(row[0]),float(row[1]),float(row[2]))

func xyz(p: Vector3) -> Array:
	return [p.x,p.y,p.z]

func _ready() -> void:
	spec = JSON.parse_string(FileAccess.get_file_as_string("res://level.json"))
	config = JSON.parse_string(FileAccess.get_file_as_string("res://gameplay.json"))
	world = load("res://world.tscn").instantiate()
	add_child(world)
	player = PLAYER.new()
	add_child(player)
	player.global_position = world.get_node("Spawn").global_position + Vector3.UP * 0.08
	goal = world.get_node("Goal")
	nav.configure(spec)
	var ids: Array[String] = []
	for row in config.enemies:
		ids.append(row.id)
		var enemy = ENEMY.new()
		enemy.name = row.id
		enemy.game = self
		enemy.target = player
		enemy.navigator = nav
		for point in row.patrol:
			enemy.patrol.append(vec(point))
		add_child(enemy)
		enemy.global_position = vec(row.position) + Vector3.UP * 0.08
		enemies[row.id] = enemy
	mission.configure(int(config.seed),ids)
	var canvas := CanvasLayer.new()
	add_child(canvas)
	status = Label.new()
	status.position = Vector2(20,20)
	status.add_theme_font_size_override("font_size",20)
	canvas.add_child(status)
	var cross := Label.new()
	cross.text = "+"
	cross.add_theme_font_size_override("font_size",24)
	canvas.add_child(cross)
	cross.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	cross.position -= Vector2(8,12)
	print("STUDIO_GAMEPLAY_READY")

func shoot(direction: Vector3) -> bool:
	if mission.completed or direction.length_squared() < 0.99 or not combat.fire():
		return false
	var origin: Vector3 = player.get_node("Camera3D").global_position
	var ray := PhysicsRayQueryParameters3D.create(origin, origin + direction.normalized() * 60.0, 5)
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	if not hit.is_empty() and hit.collider.has_method("take_damage"):
		hit.collider.take_damage(25)
		message = "Target hit"
	else:
		message = "Shot missed or blocked"
	return true

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		shoot(-player.get_node("Camera3D").global_transform.basis.z)
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_R:
				combat.reload()
			KEY_F5:
				message = "Checkpoint saved" if save_game(SAVE_PATH) else "Save failed"
			KEY_F9:
				message = "Checkpoint loaded" if load_game(SAVE_PATH) else "Load failed"

func _physics_process(delta: float) -> void:
	combat.tick(delta)
	if player == null:
		return
	if combat.health <= 0:
		player.set_test_drive(Vector2.ZERO)
		status.text = "MISSION FAILED | F9 to load a saved checkpoint"
		return
	var diff := player.global_position - goal.global_position
	if Vector2(diff.x,diff.z).length() <= 1.0 and absf(diff.y) < 1.2:
		mission.extract()
	status.text = "HP %d  |  AMMO %d / %d  |  TARGETS %d\n%s\nWASD / Shift / Space  •  Mouse / LMB  •  R reload  •  F5 save / F9 load\n%s" % [combat.health,combat.ammo,combat.reserve,mission.remaining.size(),"MISSION COMPLETE" if mission.completed else ("REACH EXTRACTION" if mission.remaining.is_empty() else "ELIMINATE GUARDS"),message]

func save_game(path: String) -> bool:
	var rows := {}
	for id in enemies:
		rows[id] = {"health":enemies[id].health,"position":xyz(enemies[id].global_position)}
	return MISSION.write_checkpoint(path,{"schema":1,"level":spec.id,"seed":config.seed,"player":xyz(player.global_position),"yaw":player.rotation.y,"combat":combat.snapshot(),"mission":mission.snapshot(),"enemies":rows})

func valid_position(p: Variant) -> bool:
	if not p is Array or p.size() != 3:
		return false
	for n in p:
		if not (n is int or n is float) or not is_finite(float(n)):
			return false
	return absf(p[0]) < float(spec.terrain.width)/2 - .35 and absf(p[2]) < float(spec.terrain.depth)/2 - .35 and p[1] >= -2 and p[1] < 10

func load_game(path: String) -> bool:
	var data: Dictionary = MISSION.read_checkpoint(path)
	if data.get("schema") != 1 or data.get("level") != spec.id or data.get("seed") != config.seed or not valid_position(data.get("player")):
		return false
	var yaw = data.get("yaw")
	if not (yaw is int or yaw is float) or not is_finite(float(yaw)):
		return false
	if not data.get("combat") is Dictionary or not data.get("mission") is Dictionary or not data.get("enemies") is Dictionary or data.enemies.size() != enemies.size():
		return false
	var next_combat = COMBAT.new()
	var next_mission = MISSION.new()
	var ids: Array[String] = []
	for id in enemies:
		ids.append(id)
	next_mission.configure(int(config.seed),ids)
	if not next_combat.restore(data.combat) or not next_mission.restore(data.mission):
		return false
	for id in enemies:
		var row = data.enemies.get(id)
		if not row is Dictionary or not valid_position(row.get("position")):
			return false
		var hp = row.get("health")
		if not (hp is int or hp is float) or hp != int(hp) or hp < 0 or hp > 50 or (hp > 0) != next_mission.remaining.has(id):
			return false
	combat = next_combat
	mission = next_mission
	player.global_position = vec(data.player)
	player.rotation.y = float(yaw)
	player.velocity = Vector3.ZERO
	player.clear_test_drive()
	for id in enemies:
		enemies[id].global_position = vec(data.enemies[id].position)
		enemies[id].velocity = Vector3.ZERO
		enemies[id].set_health(int(data.enemies[id].health))
	return true
