extends "res://city.gd"

const INTERIORS = preload("res://interiors.gd")
const TRANSIT = preload("res://transit.gd")
const DEMOLITION = preload("res://demolition.gd")
const SYNC = preload("res://world_sync.gd")

var interior = INTERIORS.new()
var transit = TRANSIT.new()
var demolition = DEMOLITION.new()
var selected_building: Dictionary = {}
var vertical_ready := false
var interior_ready := false
var interior_visited := false
var metro_trips := 0
var demolition_origin: Vector3
var _board_station := -1
var _was_riding := false
var _world_tick := 0
var _applied_world_tick := -1
var _pending_shot := Vector3.ZERO
var _pending_interact := false

func _ready() -> void:
	network.free()
	network = _create_network()
	super._ready()
	if not ready_for_play or not interior_ready:
		return
	checkpoint_path = "user://vertical_%s.json" % JSON.stringify(config,"",true).sha256_text().substr(0,24)
	add_child(transit)
	add_child(demolition)
	var block := float(config.block_size)
	demolition_origin = Vector3(block*1.5,0,block*2)
	if not transit.configure(int(config.seed),float(config.world_size),block) or not demolition.configure(int(config.seed),demolition_origin):
		push_error("Vertical components failed configuration")
		return
	if not network.set_world_validators(traffic.valid_snapshot,civilians.valid_snapshot):
		push_error("Shared-world validators unavailable")
		return
	_make_sign(interior.entrance_position(),"ENTERABLE BUILDING",Color("#4adabc"))
	_make_sign(demolition_origin+Vector3(0,0,-4),"DEMOLITION LAB",Color("#ffb06c"))
	vertical_ready = true
	message = "Explore the interior, ride the metro, and clear the demolition lab."
	# Base ready calls our overridden parser before these systems exist.
	super._parse_network_args()
	print("STUDIO_VERTICAL_READY")

func _create_network():
	return SYNC.new()

func _construct_city() -> void:
	for row in config.buildings:
		if row.size[0] >= 9 and row.size[2] >= 9 and row.size[1] >= 5:
			selected_building = row
			break
	super._construct_city()
	if selected_building.is_empty():
		push_error("No eligible enterable building")
		return
	city_root.add_child(interior)
	interior_ready = interior.configure(int(config.seed),selected_building)
	if interior_ready:
		buildings[selected_building.id] = interior

func _skip_building(row: Dictionary) -> bool:
	return not selected_building.is_empty() and row.id == selected_building.id

func _parse_network_args() -> void:
	# Delayed until all authoritative models and validators are initialized.
	if vertical_ready:
		super._parse_network_args()

func _make_sign(point: Vector3, title: String, color: Color) -> void:
	var label := Label3D.new()
	label.text = title
	label.modulate = color
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.pixel_size = 0.01
	add_child(label)
	label.global_position = point+Vector3.UP*3.0

func _step_population(delta: float) -> void:
	if network.status().mode != "client":
		super._step_population(delta)

func start_network(mode: String, port: int) -> bool:
	if not vertical_ready or not _surface_clear(player.global_position):
		return false
	_world_tick = 0
	_applied_world_tick = -1
	return super.start_network(mode,port)

func interact_world() -> bool:
	if not vertical_ready or network.status().mode != "offline":
		return false
	if transit.interact(player):
		message = "Metro interaction"
		return true
	if interior.interact(player.global_position):
		message = "Door opened" if interior.status().door_open else "Door closed"
		return true
	return false

func shoot_cover(direction: Vector3) -> Dictionary:
	if not vertical_ready or network.status().mode != "offline" or player.global_position.y < -1.0:
		return {"fired":false,"hit":false,"destroyed":false,"id":-1}
	var result: Dictionary = demolition.shoot(player.get_node("Camera3D").global_position,direction)
	if result.destroyed:
		message = "Cover segment destroyed"
	return result

func _physics_process(delta: float) -> void:
	if not vertical_ready:
		return
	super._physics_process(delta)
	var net: Dictionary = network.status()
	if net.mode == "host":
		_world_tick += 1
		if _world_tick % 10 == 1:
			network.publish_world({"tick":_world_tick,"traffic":traffic.snapshot(),"civilians":civilians.snapshot()})
	elif net.mode == "client":
		var state: Dictionary = network.latest_world()
		if not state.is_empty() and state.tick > _applied_world_tick and traffic.valid_snapshot(state.traffic) and civilians.valid_snapshot(state.civilians):
			traffic.restore(state.traffic)
			civilians.restore(state.civilians)
			_applied_world_tick = int(state.tick)
	else:
		demolition.step(delta)
		transit.step(delta,player)
		if _pending_interact:
			if not interact_world():
				message = "Approach an entrance or stopped train"
		if not _pending_shot.is_zero_approx():
			shoot_cover(_pending_shot)
		var metro: Dictionary = transit.status()
		if metro.riding and not _was_riding:
			_board_station = int(metro.station)
		elif not metro.riding and _was_riding:
			if int(metro.station) >= 0 and int(metro.station) != _board_station:
				metro_trips += 1
			_board_station = -1
		_was_riding = metro.riding
		if not interior_visited and player.global_position.distance_to(interior.room_target()) < 1.2:
			interior_visited = true
			message = "Interior explored"
	_pending_interact = false
	_pending_shot = Vector3.ZERO
	var metro: Dictionary = transit.status()
	var demo: Dictionary = demolition.status()
	var sync_text := "Offline · E door/metro · LMB cover lab"
	if net.mode != "offline":
		sync_text = "Shared world tick %d · special zones offline only" % int(network.status().get("world_tick",-1))
	hud.text += "\nVERTICAL CITY · Interior %s · Metro trips %d · Cover %d/%d\nMetro %s · %s\n%s" % ["visited" if interior_visited else "unvisited",metro_trips,demo.destroyed,demo.total,metro.phase,transit.interaction_hint(player),sync_text]

func _unhandled_input(event: InputEvent) -> void:
	if not vertical_ready:
		return
	if event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_E:
		_pending_interact = true
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_pending_shot = -player.get_node("Camera3D").global_transform.basis.z
		return
	super._unhandled_input(event)

func _surface_clear(p: Vector3) -> bool:
	if p.y < -0.25 or p.y > 5 or p.x < 0 or p.z < 0 or p.x > config.world_size or p.z > config.world_size:
		return false
	for row in config.buildings:
		var center := _vec(row.center)
		var size := _vec(row.size)
		if absf(p.x-center.x) < size.x/2+0.35 and absf(p.z-center.z) < size.z/2+0.35 and p.y < size.y:
			return false
	return true

func save_world(path: String) -> bool:
	var data := vertical_snapshot()
	return not data.is_empty() and persistence.write_checkpoint(path,data)

func vertical_snapshot() -> Dictionary:
	if not vertical_ready or network.status().mode != "offline" or not _surface_clear(player.global_position) or transit.status().riding:
		return {}
	var base: Dictionary = super.world_snapshot()
	if base.is_empty():
		return {}
	return {"version":1,"base":base,"interior":interior.snapshot(),"transit":transit.snapshot(),"demolition":demolition.snapshot(),"interior_visited":interior_visited,"metro_trips":metro_trips}

func load_world(path: String) -> bool:
	return restore_vertical(persistence.read_checkpoint(path))

func restore_vertical(data: Dictionary) -> bool:
	if not vertical_ready or network.status().mode != "offline" or not _surface_clear(player.global_position) or transit.status().riding:
		return false
	if data.size() != 7 or data.get("version") != 1 or not data.get("interior_visited") is bool:
		return false
	var trips = data.get("metro_trips")
	if not (trips is int or trips is float) or not is_finite(float(trips)) or trips < 0 or trips > 1000000 or trips != floorf(trips):
		return false
	for key in ["base","interior","transit","demolition"]:
		if not data.get(key) is Dictionary:
			return false
	if not interior.valid_snapshot(data.interior) or not transit.valid_snapshot(data.transit) or not demolition.valid_snapshot(data.demolition) or data.transit.get("riding",false):
		return false
	if not super.restore_world(data.base):
		return false
	interior.restore(data.interior)
	transit.restore(data.transit,player)
	demolition.restore(data.demolition)
	interior_visited = data.interior_visited
	metro_trips = int(trips)
	_was_riding = false
	_board_station = -1
	return true
