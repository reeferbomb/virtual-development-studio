extends Node3D

const PLAYER = preload("res://player.gd")
const STREAMING = preload("res://streaming.gd")
const POPULATION = preload("res://population.gd")
const INVENTORY = preload("res://inventory.gd")
const FACTIONS = preload("res://factions.gd")
const PERSISTENCE = preload("res://persistence.gd")
const ITEMS := ["wood", "wood", "stone", "fiber", "fiber"]
const MAX_RECORDS := 4096
const MAX_COORD := 100000.0

var config: Dictionary
var checkpoint_path: String
var stream = STREAMING.new()
var population = POPULATION.new()
var inventory = INVENTORY.new()
var factions = FACTIONS.new()
var persistence = PERSISTENCE.new()
var player: CharacterBody3D
var harvested := {}
var greeted := {}
var markers := {}
var marker_root: Node3D
var last_cell := Vector2i(999999, 999999)
var ready_for_play := false
var world_seconds := 0.0
var status: Label
var message := "Explore, gather materials and craft tools."

func _ready() -> void:
	var data = JSON.parse_string(FileAccess.get_file_as_string("res://openworld.json"))
	if not data is Dictionary:
		push_error("Missing world configuration")
		return
	config = data
	checkpoint_path = "user://frontier_%s.json" % JSON.stringify(config, "", true).sha256_text().substr(0, 24)
	add_child(stream)
	add_child(population)
	if not stream.configure(int(config.seed), float(config.chunk_size), int(config.radius)) or not population.configure(int(config.seed), float(config.chunk_size), int(config.radius)) or not inventory.configure(int(config.capacity)) or not factions.configure():
		push_error("World component configuration failed")
		return
	var environment := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#8eb6c7")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("#d2e1e8")
	env.ambient_light_energy = 0.7
	environment.environment = env
	add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 1.2
	sun.shadow_enabled = true
	add_child(sun)
	marker_root = Node3D.new()
	marker_root.name = "ResourceMarkers"
	add_child(marker_root)
	player = PLAYER.new()
	add_child(player)
	player.global_position = resource_position(Vector2i.ZERO, 0) + Vector3.UP * 0.08
	_sync_window(true)
	var canvas := CanvasLayer.new()
	add_child(canvas)
	status = Label.new()
	status.position = Vector2(20,20)
	status.add_theme_font_size_override("font_size",18)
	status.add_theme_color_override("font_outline_color", Color.BLACK)
	status.add_theme_constant_override("outline_size", 6)
	canvas.add_child(status)
	ready_for_play = true
	print("STUDIO_OPENWORLD_READY")

func resource_position(cell: Vector2i, slot: int) -> Vector3:
	var size := float(config.chunk_size)
	return Vector3((cell.x + 0.25 + 0.1 * slot) * size, 0.0, (cell.y + 0.25) * size)

func resource_id(cell: Vector2i, slot: int) -> String:
	return "%d:%d:%d" % [cell.x, cell.y, slot]

func _sync_window(force: bool = false) -> void:
	var cell: Vector2i = stream.chunk_at(player.global_position)
	if not force and cell == last_cell:
		return
	last_cell = cell
	stream.update_center(player.global_position)
	population.update_center(player.global_position)
	var wanted := {}
	var radius := int(config.radius)
	for x in range(cell.x - radius, cell.x + radius + 1):
		for z in range(cell.y - radius, cell.y + radius + 1):
			for slot in ITEMS.size():
				var id := resource_id(Vector2i(x,z), slot)
				if not harvested.has(id):
					wanted[id] = [Vector2i(x,z), slot]
	for id in markers.keys():
		if not wanted.has(id):
			markers[id].free()
			markers.erase(id)
	for id in wanted:
		if not markers.has(id):
			var row: Array = wanted[id]
			_spawn_marker(id, row[0], row[1])

func _spawn_marker(id: String, cell: Vector2i, slot: int) -> void:
	var marker := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.65, 0.55, 0.65)
	marker.mesh = mesh
	var mat := StandardMaterial3D.new()
	mat.albedo_color = {"wood":Color("#da9453"), "stone":Color("#a0b7d7"), "fiber":Color("#72cb68")}[ITEMS[slot]]
	mat.emission_enabled = true
	mat.emission = mat.albedo_color * 0.35
	marker.material_override = mat
	marker.set_meta("item", ITEMS[slot])
	marker_root.add_child(marker)
	marker.position = resource_position(cell, slot) + Vector3.UP * 0.30
	markers[id] = marker

func _nearest_resource() -> String:
	var nearest := ""
	var distance := minf(2.0, float(config.chunk_size) * 0.049)
	for id in markers:
		var marker: MeshInstance3D = markers[id]
		var point := marker.position - Vector3.UP * 0.30
		var d := point.distance_to(player.global_position)
		if d <= distance:
			distance = d
			nearest = id
	return nearest

func harvest_near() -> bool:
	if not ready_for_play or harvested.size() >= MAX_RECORDS:
		return false
	var id := _nearest_resource()
	if id.is_empty():
		return false
	var marker: MeshInstance3D = markers[id]
	var item: String = marker.get_meta("item")
	if not inventory.add(item, 1):
		message = "Inventory full"
		return false
	harvested[id] = true
	marker.free()
	markers.erase(id)
	message = "Collected " + item
	return true

func greet_near() -> bool:
	if not ready_for_play or greeted.size() >= MAX_RECORDS:
		return false
	var npc: Dictionary = population.nearest(player.global_position)
	if npc.is_empty() or npc.distance > 3.0 or greeted.has(npc.id) or not factions.adjust(npc.faction, 10):
		return false
	greeted[npc.id] = true
	message = "Greeted %s · reputation +10" % npc.faction
	return true

func _physics_process(delta: float) -> void:
	if not ready_for_play:
		return
	_sync_window()
	world_seconds += delta
	population.step(delta)
	var npc: Dictionary = population.nearest(player.global_position)
	var resource := _nearest_resource()
	status.text = "CHUNK %d, %d  |  %d loaded  |  %d NPCs\nWood %d  ·  Stone %d  ·  Fiber %d  ·  Tools %d  ·  Bandages %d\nSettlers %d (%s)  |  Rangers %d (%s)\n%s  |  %s\nWASD / Shift  ·  F gather  ·  G greet  ·  C tool  ·  B bandage  ·  F5 save / F9 load\n%s" % [last_cell.x,last_cell.y,stream.loaded_count(),population.loaded_count(),inventory.quantity("wood"),inventory.quantity("stone"),inventory.quantity("fiber"),inventory.quantity("tool"),inventory.quantity("bandage"),factions.reputation("settlers"),factions.disposition("settlers"),factions.reputation("rangers"),factions.disposition("rangers"),"Nearby resource: " + str(markers[resource].get_meta("item")) if not resource.is_empty() else "Find resources", "NPC %.1f m" % npc.distance if not npc.is_empty() else "No NPC",message]

func _unhandled_input(event: InputEvent) -> void:
	if not ready_for_play or not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.physical_keycode:
		KEY_F:
			if not harvest_near(): message = "Approach an unused resource (and ensure capacity)"
		KEY_G:
			if not greet_near(): message = "Approach an ungreeted NPC"
		KEY_C: message = "Crafted tool" if inventory.craft("tool") else "Need two wood and one stone"
		KEY_B: message = "Crafted bandage" if inventory.craft("bandage") else "Need two fiber"
		KEY_F5: message = "Checkpoint saved" if save_world(checkpoint_path) else "Save failed"
		KEY_F9: message = "Checkpoint loaded" if load_world(checkpoint_path) else "Load failed"

func save_world(path: String) -> bool:
	if not ready_for_play:
		return false
	var p := player.global_position
	return persistence.write_checkpoint(path, {"config":config, "position":[p.x,p.y,p.z], "inventory":inventory.snapshot(), "factions":factions.snapshot(), "harvested":harvested.duplicate(), "greeted":greeted.duplicate(), "world_seconds":world_seconds})

func _valid_set(value: Variant, resources: bool) -> bool:
	if not value is Dictionary or value.size() > MAX_RECORDS:
		return false
	for id in value:
		if not id is String or id.length() > 120 or not value[id] is bool or not value[id]:
			return false
		if resources:
			var parts: PackedStringArray = id.split(":")
			if parts.size() != 3 or not parts[0].is_valid_int() or not parts[1].is_valid_int() or not parts[2].is_valid_int():
				return false
			var cell := Vector2i(int(parts[0]),int(parts[1]))
			var slot := int(parts[2])
			if absf(cell.x) > MAX_COORD / float(config.chunk_size) + 2 or absf(cell.y) > MAX_COORD / float(config.chunk_size) + 2 or slot < 0 or slot >= ITEMS.size() or resource_id(cell, slot) != id:
				return false
		else:
			var parts: PackedStringArray = id.split("_")
			if parts.size() != 5 or parts[0] != "npc" or parts[1] != str(int(config.seed)) or not parts[2].is_valid_int() or not parts[3].is_valid_int() or parts[4] not in ["0", "1"]:
				return false
			if absf(int(parts[2])) > MAX_COORD / float(config.chunk_size) + 2 or absf(int(parts[3])) > MAX_COORD / float(config.chunk_size) + 2 or str(int(parts[2])) != parts[2] or str(int(parts[3])) != parts[3]:
				return false
	return true

func load_world(path: String) -> bool:
	if not ready_for_play:
		return false
	var data: Dictionary = persistence.read_checkpoint(path)
	if data.size() != 7 or data.get("config") != config or not data.get("inventory") is Dictionary or not data.get("factions") is Dictionary or not _valid_set(data.get("harvested"), true) or not _valid_set(data.get("greeted"), false):
		return false
	var elapsed = data.get("world_seconds")
	if not (elapsed is int or elapsed is float) or not is_finite(float(elapsed)) or elapsed < 0.0 or elapsed > 1000000000.0:
		return false
	var p = data.get("position")
	if not p is Array or p.size() != 3:
		return false
	for n in p:
		if not (n is int or n is float) or not is_finite(float(n)) or absf(float(n)) > MAX_COORD:
			return false
	if p[1] < -0.5 or p[1] > 10.0:
		return false
	var next_inventory = INVENTORY.new()
	var next_factions = FACTIONS.new()
	if not next_inventory.restore(data.inventory) or next_inventory.snapshot().capacity != config.capacity or not next_factions.restore(data.factions):
		return false
	inventory = next_inventory
	factions = next_factions
	harvested = data.harvested.duplicate()
	greeted = data.greeted.duplicate()
	world_seconds = float(elapsed)
	population.configure(int(config.seed), float(config.chunk_size), int(config.radius))
	population.step(world_seconds)
	player.global_position = Vector3(p[0],p[1],p[2])
	player.velocity = Vector3.ZERO
	player.clear_test_drive()
	_sync_window(true)
	return true
