extends "res://vertical.gd"

const TOWER = preload("res://tower.gd")
const VEHICLE = preload("res://vehicle.gd")
const NPC = preload("res://npc_interactions.gd")
const SESSION = preload("res://session_network.gd")
const STORE = preload("res://session_store.gd")

var tower = TOWER.new()
var vehicle = VEHICLE.new()
var dialogue = NPC.new()
var session_store = STORE.new()
var tower_building: Dictionary = {}
var tower_ready := false
var advanced_ready := false
var objectives: Array[Vector3] = []
var session_path := ""
var world_id := ""
var durable_revision := -1
var session_error := false
var _request_drive := false
var _request_dialogue := false
var _request_objective := false
var _drive_test := false
var _drive_input := Vector2.ZERO
var _drive_brake := false
var _session_retry := 0.0
var _objective_labels: Array[Label3D] = []
var _last_objective_revision := -1
var _quest_marker: Label3D

func _create_network():
	return SESSION.new()

func _ready() -> void:
	super._ready()
	if not vertical_ready:
		return
	add_child(vehicle)
	var spawn := _vec(config.spawn)
	if not vehicle.configure(int(config.seed),spawn+Vector3(2.2,0.08,0),float(config.world_size)) or not dialogue.configure(int(config.seed),int(config.civilians)):
		push_error("Advanced city components rejected configuration")
		return
	# The three co-op objectives are in clear, distinct street positions near spawn.
	objectives.assign([spawn,spawn+Vector3(0,0,-8),spawn+Vector3(-8,0,0)])
	if not network.configure_objectives(objectives):
		push_error("Session objectives rejected")
		return
	world_id = JSON.stringify(config,"",true).sha256_text()
	session_path = "user://advanced_session_%s.json" % world_id.substr(0,24)
	checkpoint_path = "user://advanced_%s.json" % world_id.substr(0,24)
	if tower_ready:
		_make_sign(tower.entrance_position(),"THREE-FLOOR TOWER · E",Color("#b6e3ff"))
	for i in objectives.size():
		var label := Label3D.new()
		label.text = "CO-OP %d · Q" % (i+1)
		label.modulate = Color("#ffc85f")
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.pixel_size = 0.008
		add_child(label)
		label.global_position = objectives[i]+Vector3.UP*2.8
		_objective_labels.append(label)
	_quest_marker = Label3D.new()
	_quest_marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_quest_marker.modulate = Color("#a0ffc4")
	_quest_marker.pixel_size = 0.008
	add_child(_quest_marker)
	advanced_ready = true
	message = "Tower E · Vehicle F · Resident C · Co-op Q (online)"
	# The inherited parser may have attempted start before this scene was ready.
	_parse_network_args()
	print("STUDIO_ADVANCED_READY")

func _construct_city() -> void:
	# Avoid consuming the building selected by Vertical City for its first interior.
	var first_found := false
	for row in config.buildings:
		if not first_found and row.size[0] >= 9 and row.size[2] >= 9 and row.size[1] >= 5:
			first_found = true
			continue
		if first_found and row.size[0] >= 9 and row.size[2] >= 9 and row.size[1] >= 9:
			tower_building = row
			break
	super._construct_city()
	if not tower_building.is_empty():
		city_root.add_child(tower)
		tower_ready = tower.configure(int(config.seed),tower_building)
		if tower_ready:
			buildings[tower_building.id] = tower
		else:
			push_error("Tower failed eligible configuration")
	else:
		# Very compact custom layouts may not contain a suitable second tall lot.
		tower.free()
		tower = null

func _skip_building(row: Dictionary) -> bool:
	return super._skip_building(row) or (not tower_building.is_empty() and row.id == tower_building.id)

func _parse_network_args() -> void:
	if advanced_ready:
		super._parse_network_args()

func start_network(mode: String, port: int) -> bool:
	if not advanced_ready or network.status().mode != "offline" or not _surface_clear(player.global_position) or vehicle.status().driving or (tower_ready and tower.status().riding) or transit.status().riding:
		return false
	if mode == "host":
		var saved: Dictionary = session_store.load(session_path,world_id)
		if not saved.is_empty():
			if not network.restore_session(saved):
				return false
			durable_revision = int(saved.revision)
		elif FileAccess.file_exists(session_path) or FileAccess.file_exists(session_path+".bak"):
			message = "Session checkpoint corrupt; host not started"
			return false
		else:
			durable_revision = -1
	if not super.start_network(mode,port):
		return false
	if mode == "host":
		if not _save_session():
			network.stop()
			message = "Host could not commit its session checkpoint"
			return false
	return true

func _save_session() -> bool:
	if network.status().mode != "host":
		return false
	var state: Dictionary = network.session_snapshot()
	if state.is_empty():
		return false
	if int(state.revision) == durable_revision:
		return true
	if session_store.save(session_path,world_id,state):
		durable_revision = int(state.revision)
		session_error = false
		return true
	session_error = true
	return false

func request_nearest_objective() -> bool:
	var net: Dictionary = network.status()
	if not advanced_ready or net.mode == "offline" or not net.connected:
		return false
	var best := -1
	var distance := 2.5
	var state: Dictionary = network.session_snapshot()
	if state.is_empty():
		return false
	for i in objectives.size():
		if state.claimed[i]:
			continue
		var d: float = objectives[i].distance_to(net.local_position)
		if d <= distance:
			best = i
			distance = d
	if best < 0:
		message = "Approach an unclaimed co-op objective"
		return false
	var accepted: bool = network.request_objective(best)
	if accepted:
		message = "Objective submitted"
		if net.mode == "host":
			_save_session()
	return accepted

func interact_world() -> bool:
	if not advanced_ready or network.status().mode != "offline" or vehicle.status().driving:
		return false
	if tower_ready and tower.interact(player):
		message = "Tower interaction"
		return true
	if tower_ready and tower.status().riding:
		return false
	return super.interact_world()

func interact_vehicle() -> bool:
	if not advanced_ready or network.status().mode != "offline" or transit.status().riding or (tower_ready and tower.status().riding) or not _surface_clear(player.global_position):
		return false
	var moved: bool = vehicle.interact(player)
	if moved:
		message = "Drive WASD · Space brake · F exit" if vehicle.status().driving else "Vehicle parked"
	return moved

func interact_resident() -> Dictionary:
	if not advanced_ready or network.status().mode != "offline" or vehicle.status().driving or not _surface_clear(player.global_position):
		return {"accepted":false,"message":"Dialogue unavailable","id":"","quest_stage":dialogue.status().get("quest_stage","")}
	var result: Dictionary = dialogue.interact(player.global_position,civilians.status())
	message = result.message
	return result

func shoot_cover(direction: Vector3) -> Dictionary:
	if not advanced_ready or vehicle.status().driving or (tower_ready and tower.status().riding):
		return {"fired":false,"hit":false,"destroyed":false,"id":-1}
	return super.shoot_cover(direction)

func set_vehicle_test_input(input: Vector2,brake: bool = false) -> void:
	_drive_test = true
	_drive_input = input
	_drive_brake = brake

func _physics_process(delta: float) -> void:
	if not advanced_ready:
		return
	super._physics_process(delta)
	var net: Dictionary = network.status()
	if net.mode == "offline":
		if _request_drive:
			interact_vehicle()
		if _request_dialogue:
			interact_resident()
		if tower_ready:
			tower.step(delta,player)
		var control := Vector2.ZERO
		var brake := false
		if _drive_test:
			control = _drive_input
			brake = _drive_brake
		elif Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			control = Vector2(int(Input.is_physical_key_pressed(KEY_D))-int(Input.is_physical_key_pressed(KEY_A)),int(Input.is_physical_key_pressed(KEY_W))-int(Input.is_physical_key_pressed(KEY_S)))
			brake = Input.is_physical_key_pressed(KEY_SPACE)
		vehicle.step(delta,player,control,brake)
	else:
		if _request_objective:
			request_nearest_objective()
		if net.mode == "host":
			_session_retry = maxf(0.0,_session_retry-delta)
			if _session_retry <= 0.0 and int(network.session_snapshot().revision) != durable_revision:
				_save_session()
				_session_retry = 0.25
	_request_drive = false
	_request_dialogue = false
	_request_objective = false
	var state: Dictionary = network.session_snapshot()
	var revision := int(state.get("revision",-1))
	if revision >= 0 and revision != _last_objective_revision:
		for i in _objective_labels.size():
			_objective_labels[i].text = ("COMPLETE %d" if state.claimed[i] else "CO-OP %d · Q") % (i+1)
			_objective_labels[i].modulate = Color("#8eeaa4") if state.claimed[i] else Color("#ffc85f")
		_last_objective_revision = revision
	elif revision < 0:
		_last_objective_revision = -1
	var tower_text := "Unavailable in this layout"
	if tower_ready:
		var t: Dictionary = tower.status()
		tower_text = "Floor %d · %s · trips %d" % [t.floor,t.phase,t.trips]
	var car: Dictionary = vehicle.status()
	var q: Dictionary = dialogue.status()
	_quest_marker.visible = false
	var quest_text: String = q.objective
	if net.mode == "offline" and not q.target_id.is_empty():
		for resident in civilians.status().civilians:
			if resident.id == q.target_id:
				var p := _vec(resident.position)
				_quest_marker.global_position = p+Vector3.UP*2.1
				_quest_marker.text = q.target_name+" · C"
				_quest_marker.visible = true
				quest_text += " %.1f m" % player.global_position.distance_to(p)
				break
	for label in _objective_labels:
		label.visible = net.mode != "offline" and revision >= 0
	hud.text += "\nADVANCED CITY · Tower %s\nVehicle %s · %.1f km/h · F enter/exit\nCitizen quest: %s · C talk\nCo-op %s/%d · Q claim online%s" % [tower_text,"driving" if car.driving else "parked",absf(car.speed)*3.6,quest_text,str(revision) if revision >= 0 else "syncing",objectives.size()," · SAVE ERROR" if session_error else (" · saved" if net.mode == "host" and durable_revision == revision else "")]

func _unhandled_input(event: InputEvent) -> void:
	if not advanced_ready:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_F:
				_request_drive = true
				return
			KEY_C:
				_request_dialogue = true
				return
			KEY_Q:
				_request_objective = true
				return
	super._unhandled_input(event)

func save_world(path: String) -> bool:
	if not advanced_ready or vehicle.status().driving or (tower_ready and tower.status().riding):
		return false
	var base: Dictionary = super.vertical_snapshot()
	if base.is_empty():
		return false
	var car: Dictionary = vehicle.snapshot()
	# A saved car must also clear geometry in a freshly constructed city, before
	# the saved door and demolition states have been restored. Conservatively
	# require a parking space clear of every potentially changing collider.
	if not _vehicle_parking_safe(car) or not vehicle.valid_player_position(player.global_position,car):
		message = "Park away from buildings and the demolition lab before saving"
		return false
	return persistence.write_checkpoint(path,{"version":1,"vertical":base,"tower":tower.snapshot() if tower_ready else {},"vehicle":car,"dialogue":dialogue.snapshot()})

func _vehicle_parking_safe(car: Dictionary) -> bool:
	if not vehicle.valid_snapshot(car):
		return false
	var p := _vec(car.position)
	# Half diagonal of the 1.90 x 3.88 m chassis plus safety margin.
	const MARGIN := 2.25
	for row in [selected_building,tower_building]:
		if row.is_empty():
			continue
		var center := _vec(row.center)
		var size := _vec(row.size)
		if absf(p.x-center.x) < size.x*0.5+MARGIN and absf(p.z-center.z) < size.z*0.5+MARGIN:
			return false
	for row in demolition.status().targets:
		var position := _vec(row.position)
		if absf(p.x-position.x) < 1.3+MARGIN and absf(p.z-position.z) < 0.25+MARGIN:
			return false
	return true

func load_world(path: String) -> bool:
	if not advanced_ready or vehicle.status().driving or (tower_ready and tower.status().riding) or not _surface_clear(player.global_position):
		return false
	var data: Dictionary = persistence.read_checkpoint(path)
	if data.size() != 5 or data.get("version") != 1 or not data.get("vertical") is Dictionary or not data.get("tower") is Dictionary or not data.get("vehicle") is Dictionary or not data.get("dialogue") is Dictionary:
		return false
	if (tower_ready and (not tower.valid_snapshot(data.tower) or data.tower.get("riding",false))) or (not tower_ready and not data.tower.is_empty()) or not vehicle.valid_snapshot(data.vehicle) or data.vehicle.get("driving",false) or not dialogue.valid_snapshot(data.dialogue):
		return false
	var saved_base = data.vertical.get("base")
	if not saved_base is Dictionary or not saved_base.get("position") is Array or saved_base.position.size() != 3:
		return false
	for component in saved_base.position:
		if not (component is int or component is float) or not is_finite(float(component)):
			return false
	if not _vehicle_parking_safe(data.vehicle) or not vehicle.valid_player_position(_vec(saved_base.position),data.vehicle):
		return false
	if not super.restore_vertical(data.vertical):
		return false
	if tower_ready:
		tower.restore(data.tower,player)
	vehicle.restore(data.vehicle,player)
	dialogue.restore(data.dialogue)
	return true
