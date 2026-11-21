extends "res://openworld.gd"

const TRANSPORT = preload("res://transport.gd")
const RANGE = preload("res://range_combat.gd")
const SCHEDULES = preload("res://scheduled_population.gd")
const QUESTS = preload("res://quests.gd")
const ECONOMY = preload("res://economy.gd")

var transport = TRANSPORT.new()
var combat_range = RANGE.new()
var quests = QUESTS.new()
var economy = ECONOMY.new()
var drive_checkpoint: Vector3
var shop_position: Vector3
var target_position: Vector3
var unified_ready := false

func _ready() -> void:
	population.free()
	population = SCHEDULES.new()
	super._ready()
	if not ready_for_play:
		return
	checkpoint_path = "user://unified_%s.json" % JSON.stringify(config,"",true).sha256_text().substr(0,24)
	var s := float(config.chunk_size)
	drive_checkpoint = Vector3(s*0.625,0,-s*1.25)
	shop_position = Vector3(s*0.75,0,-s*1.25)
	target_position = Vector3(s*0.75,1.5,-s*1.5625)
	add_child(transport)
	add_child(combat_range)
	if not transport.configure(player, Vector3(s*0.625,0.08,s*0.3125)) or not combat_range.configure([{"id":"drone","position":[target_position.x,target_position.y,target_position.z]}]) or not quests.configure(int(config.seed)) or not economy.configure(int(config.seed),30):
		push_error("Unified component configuration failed")
		return
	_add_landmark(drive_checkpoint, Color("#43d7df"), true)
	_add_landmark(shop_position, Color("#f3be52"), false)
	message = "Gather two wood and one stone, then craft a tool."
	unified_ready = true
	print("STUDIO_UNIFIED_READY")

func _add_landmark(p: Vector3, color: Color, ring: bool) -> void:
	var marker := MeshInstance3D.new()
	if ring:
		var mesh := TorusMesh.new()
		mesh.inner_radius = 1.9
		mesh.outer_radius = 2.4
		marker.mesh = mesh
	else:
		var mesh := CylinderMesh.new()
		mesh.top_radius = 0.7
		mesh.bottom_radius = 0.9
		mesh.height = 1.35
		marker.mesh = mesh
	var paint := StandardMaterial3D.new()
	paint.albedo_color = color
	paint.emission_enabled = true
	paint.emission = color * 0.4
	marker.material_override = paint
	add_child(marker)
	marker.position = p + Vector3.UP * (0.16 if ring else 0.675)

func _advance(action: String, target: String) -> void:
	if quests.record(action,target) and quests.completed:
		economy.credit(quests.reward())
		message = "Contract complete · +%d credits" % quests.reward()

func craft_item(item: String) -> bool:
	if not unified_ready or transport.driving or not inventory.craft(item):
		return false
	message = "Crafted " + item
	_advance("craft",item)
	return true

func harvest_near() -> bool:
	return unified_ready and not transport.driving and super.harvest_near()

func greet_near() -> bool:
	return unified_ready and not transport.driving and super.greet_near()

func trade(action: String, item: String, count: int = 1) -> bool:
	if not unified_ready or transport.driving or player.global_position.distance_to(shop_position) > 3.0 or not economy.trade(inventory,action,item,count):
		return false
	message = "%s %d × %s" % [action.capitalize(),count,item]
	if action == "sell":
		_advance("trade",item)
	return true

func shoot_target(direction: Vector3) -> Dictionary:
	var empty := {"fired":false,"hit":false,"defeated":false,"id":""}
	if not unified_ready or transport.driving or quests.current() != {"action":"defeat","target":"drone"}:
		return empty
	var camera: Camera3D = player.get_node("Camera3D")
	var result: Dictionary = combat_range.shoot(camera.global_position,direction)
	if result.get("defeated"):
		_advance("defeat",result.id)
	return result

func _physics_process(delta: float) -> void:
	if not unified_ready:
		return
	transport.step(delta)
	super._physics_process(delta)
	combat_range.tick(delta)
	if transport.driving and transport.vehicle.global_position.distance_to(drive_checkpoint) <= 2.5:
		_advance("drive","checkpoint")
	var clock: Dictionary = population.clock_snapshot()
	var stage: Dictionary = quests.current()
	var objective := "CONTRACT COMPLETE" if quests.completed else "%s %s" % [str(stage.get("action", "")).to_upper(),stage.get("target", "")]
	status.text += "\n%s  |  %s  |  Credits %d  |  Ammo %d/%d\nDay %d · %.1f h · %s  |  Shop %.1f m  |  Checkpoint %.1f m\nE enter/exit · Space brake · V sell tool (%d) · T buy bandage (%d) · LMB shoot · R reload" % [objective,"DRIVING" if transport.driving else "ON FOOT",economy.credits,combat_range.ammo,combat_range.reserve,clock.day,clock.hour,clock.phase,player.global_position.distance_to(shop_position),player.global_position.distance_to(drive_checkpoint),economy.price("tool","sell"),economy.price("bandage","buy")]

func _unhandled_input(event: InputEvent) -> void:
	if not unified_ready:
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		shoot_target(-player.get_node("Camera3D").global_transform.basis.z)
		return
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.physical_keycode:
		KEY_E:
			if transport.driving:
				message = "Exited vehicle" if transport.exit() else "Stop and find clear ground to exit"
			else:
				message = "Entered vehicle" if transport.enter() else "Approach the parked vehicle"
		KEY_C:
			if not craft_item("tool"): message = "Need two wood and one stone"
		KEY_B:
			if not craft_item("bandage"): message = "Need two fiber"
		KEY_V:
			if not trade("sell","tool"): message = "Approach the outpost with a tool"
		KEY_T:
			if not trade("buy","bandage"): message = "Approach the outpost with credits and inventory space"
		KEY_R:
			if not transport.driving: combat_range.reload()
		_:
			if not transport.driving: super._unhandled_input(event)

func save_world(path: String) -> bool:
	if not unified_ready or transport.driving:
		return false
	var p := player.global_position
	var parked: Dictionary = transport.snapshot()
	if parked.is_empty():
		return false
	return persistence.write_checkpoint(path,{"config":config,"position":[p.x,p.y,p.z],"inventory":inventory.snapshot(),"factions":factions.snapshot(),"harvested":harvested.duplicate(),"greeted":greeted.duplicate(),"world_seconds":world_seconds,"transport":parked,"combat":combat_range.snapshot(),"quest":quests.snapshot(),"economy":economy.snapshot()})

func load_world(path: String) -> bool:
	if not unified_ready or transport.driving:
		return false
	var data: Dictionary = persistence.read_checkpoint(path)
	if data.size() != 11 or data.get("config") != config or not _valid_set(data.get("harvested"),true) or not _valid_set(data.get("greeted"),false):
		return false
	for key in ["inventory","factions","transport","combat","quest","economy"]:
		if not data.get(key) is Dictionary:
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
	var next_quests = QUESTS.new()
	var next_economy = ECONOMY.new()
	next_quests.configure(int(config.seed))
	next_economy.configure(int(config.seed),30)
	if not next_inventory.restore(data.inventory) or next_inventory.snapshot().capacity != config.capacity or not next_factions.restore(data.factions) or not next_quests.restore(data.quest) or not next_economy.restore(data.economy) or not TRANSPORT.valid_snapshot(data.transport) or not combat_range.valid_snapshot(data.combat):
		return false
	if next_quests.completed != (data.combat.targets.get("drone") == 0) or (next_quests.index < 3 and data.combat.targets.get("drone") != 2):
		return false
	inventory = next_inventory
	factions = next_factions
	quests = next_quests
	economy = next_economy
	harvested = data.harvested.duplicate()
	greeted = data.greeted.duplicate()
	world_seconds = float(elapsed)
	population.configure(int(config.seed),float(config.chunk_size),int(config.radius))
	population.step(world_seconds)
	player.global_position = Vector3(p[0],p[1],p[2])
	player.velocity = Vector3.ZERO
	player.clear_test_drive()
	_sync_window(true)
	transport.restore(data.transport)
	combat_range.restore(data.combat)
	return true
