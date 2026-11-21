extends "res://advanced.gd"

const FRONT_NET = preload("res://frontline_network.gd")
const SHARED_CAR = preload("res://shared_vehicle.gd")
const SHARED_LIFT = preload("res://shared_lift.gd")
const SHARED_COVER = preload("res://shared_cover.gd")
const MISSIONS = preload("res://mission_director.gd")
const SQUADS = preload("res://squad_ai.gd")

var shared_car = SHARED_CAR.new()
var shared_lift = SHARED_LIFT.new()
var shared_cover = SHARED_COVER.new()
var missions = MISSIONS.new()
var squads = SQUADS.new()
var frontline_ready := false
var feature_root: Node3D
var initial_features: Array = []
var _feature_input := Vector2i(-1,0)
var _features_visible := false

func _create_network():
	return FRONT_NET.new()

func _ready() -> void:
	super._ready()
	if not advanced_ready:
		return
	feature_root = Node3D.new()
	add_child(feature_root)
	for model in [shared_car,shared_lift,shared_cover,missions,squads]:
		feature_root.add_child(model)
	var spawn := _vec(config.spawn)
	var extent := float(config.world_size)
	var block := float(config.block_size)
	if not shared_car.configure(spawn+Vector3(3,0,0),extent,config.buildings) or not shared_lift.configure(spawn+Vector3(-4,0,5)) or not shared_cover.configure(spawn+Vector3(0,0,-7)) or not missions.configure(int(config.seed),spawn,extent,block) or not squads.configure(int(config.seed),spawn+Vector3(block,0,block),5.0):
		push_error("Frontline feature construction failed")
		return
	if not network.configure_features(world_id,shared_car,shared_lift,shared_cover,missions,squads):
		push_error("Frontline network features rejected")
		return
	shared_car.set_cover(shared_cover)
	_feature_label(shared_car,Vector3(0,2.1,0),"SHARED CAR · F")
	for i in 3:
		_feature_label(feature_root,shared_cover.panel_center(i)+Vector3.UP*1.8,"COVER %d" % (i+1))
	_feature_label(feature_root,spawn+Vector3(block,3,block),"AI ARENA")
	for model in [shared_car,shared_lift,shared_cover,missions,squads]:
		initial_features.append(model.snapshot())
	feature_root.visible = false
	shared_cover.set_active(false)
	session_path = "user://frontline_session_%s.json" % world_id.substr(0,24)
	checkpoint_path = "user://frontline_%s.json" % world_id.substr(0,24)
	frontline_ready = true
	message = "Frontline: host/join to access shared vehicle, lift, cover, missions and AI arena"
	_parse_network_args()
	print("STUDIO_FRONTLINE_READY")

func _feature_label(parent: Node3D,at: Vector3,caption: String) -> void:
	var label := Label3D.new()
	label.text = caption
	label.position = at
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.pixel_size = 0.008
	label.modulate = Color("#ffc875")
	parent.add_child(label)

func _parse_network_args() -> void:
	if frontline_ready:
		super._parse_network_args()

func start_network(mode: String,port: int) -> bool:
	if not frontline_ready or network.status().mode != "offline":
		return false
	var models = [shared_car,shared_lift,shared_cover,missions,squads]
	for i in models.size():
		if not models[i].restore(initial_features[i]):
			return false
	if not super.start_network(mode,port):
		return false
	feature_root.visible = true
	shared_cover.set_active(true)
	_features_visible = true
	vehicle.visible = false
	return true

func request_frontline(kind: int,index: int = 0) -> bool:
	if not frontline_ready:
		return false
	return network.request_feature(kind,index)

func _network_input(local: Vector3) -> Vector2:
	if shared_car.occupied(int(network.status().peer_id)):
		return Vector2(local.x,local.z).limit_length(1.0)
	return super._network_input(local)

func _physics_process(delta: float) -> void:
	if not frontline_ready:
		return
	super._physics_process(delta)
	var net: Dictionary = network.status()
	var online: bool = net.mode != "offline"
	if online != _features_visible:
		feature_root.visible = online
		shared_cover.set_active(online)
		_features_visible = online
	vehicle.visible = not online
	if not online:
		_feature_input = Vector2i(-1,0)
		return
	if _feature_input.x >= 0:
		message = "Frontline request queued/accepted" if request_frontline(_feature_input.x,_feature_input.y) else "Action unavailable; approach the marked feature"
		_feature_input = Vector2i(-1,0)
	var state: Dictionary = network.feature_snapshot()
	if state.is_empty():
		hud.text += "\nFRONTLINE · synchronizing world features"
		return
	var mission: Dictionary = missions.status()
	var team: Dictionary = squads.status()
	var car: Dictionary = shared_car.snapshot()
	var lift: Dictionary = shared_lift.snapshot()
	var cover: Dictionary = shared_cover.snapshot()
	hud.text += "\nFRONTLINE · tick %d · F car / E lift / 1–3 cover / R mission\nShared car %.1f km/h · lift %s (%.1fm) · cover %s\nMission: %s · %.1fs · %d points · %.1fm\nAI arena: %s · cyan/amber %s · %d shots" % [net.feature_tick,absf(car.speed)*3.6,lift.phase,lift.height,str(cover.health),mission.objective,mission.time_left,mission.score,player.global_position.distance_to(mission.target),team.phase,str(team.alive),team.shots]

func _unhandled_input(event: InputEvent) -> void:
	if frontline_ready and network.status().mode != "offline" and event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_F: _feature_input = Vector2i(0,0); return
			KEY_E: _feature_input = Vector2i(1,0); return
			KEY_1: _feature_input = Vector2i(2,0); return
			KEY_2: _feature_input = Vector2i(2,1); return
			KEY_3: _feature_input = Vector2i(2,2); return
			KEY_R: _feature_input = Vector2i(3,0); return
	super._unhandled_input(event)
