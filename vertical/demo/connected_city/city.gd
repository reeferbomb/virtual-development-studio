extends Node3D

const PLAYER = preload("res://player.gd")
const TRAFFIC = preload("res://traffic.gd")
const CIVILIANS = preload("res://civilians.gd")
const NETWORK = preload("res://city_network.gd")
const PERSISTENCE = preload("res://persistence.gd")

const PALETTE := {"downtown":Color("#7a899b"),"residential":Color("#ae917a"),"industrial":Color("#60756e")}
var config: Dictionary
var ready_for_play := false
var player: CharacterBody3D
var traffic = TRAFFIC.new()
var civilians = CIVILIANS.new()
var network = NETWORK.new()
var persistence = PERSISTENCE.new()
var city_root: Node3D
var remote_root: Node3D
var remote_meshes := {}
var buildings := {}
var landmarks: Array = []
var landmark_markers: Array = []
var greeted := {}
var tour_index := 0
var checkpoint_path := ""
var message := "Visit the marked district landmarks."
var hud: Label
var _window_transforms: Array[Transform3D] = []
var _paint_transforms: Array[Transform3D] = []
var _materials := {}
var _test_network_input := Vector2.ZERO
var _test_network_enabled := false
var simulation_usec := 0

func _ready() -> void:
	var raw = JSON.parse_string(FileAccess.get_file_as_string("res://city.json"))
	if not raw is Dictionary:
		push_error("City layout missing")
		return
	config = raw
	checkpoint_path = "user://metropolis_%s.json" % JSON.stringify(config,"",true).sha256_text().substr(0,24)
	city_root = Node3D.new()
	city_root.name = "StaticCity"
	add_child(city_root)
	remote_root = Node3D.new()
	remote_root.name = "RemotePlayers"
	add_child(remote_root)
	_make_environment()
	_construct_city()
	player = PLAYER.new()
	add_child(player)
	player.position = _vec(config.spawn) + Vector3.UP * 0.08
	add_child(traffic)
	add_child(civilians)
	add_child(network)
	network.visible = false  # the containing city owns its replica visuals
	if not traffic.configure(int(config.seed),int(config.blocks),float(config.block_size),int(config.traffic)) or not civilians.configure(int(config.seed),int(config.blocks),float(config.block_size),int(config.civilians)) or not network.configure(float(config.world_size),_vec(config.spawn)):
		push_error("City subsystem configuration failed")
		return
	if network.has_method("set_obstacles") and not network.set_obstacles(config.buildings):
		push_error("City network geometry rejected")
		return
	_make_tour()
	var canvas := CanvasLayer.new()
	add_child(canvas)
	hud = Label.new()
	hud.position = Vector2(16,16)
	hud.add_theme_color_override("font_outline_color",Color.BLACK)
	hud.add_theme_constant_override("outline_size",6)
	hud.add_theme_font_size_override("font_size",18)
	canvas.add_child(hud)
	ready_for_play = true
	_parse_network_args()
	print("STUDIO_CITY_READY")

func _vec(values: Array) -> Vector3:
	return Vector3(values[0],values[1],values[2])

func _make_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("#a4bdcf")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("#c4dcec")
	env.ambient_light_energy = 0.65
	var world_env := WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52,-38,0)
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	add_child(sun)

func _material(color: Color) -> StandardMaterial3D:
	var key := color.to_html()
	if not _materials.has(key):
		var material := StandardMaterial3D.new()
		material.albedo_color = color
		material.roughness = 0.86
		_materials[key] = material
	return _materials[key]

func _visual(parent: Node3D, position: Vector3, size: Vector3, color: Color) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	node.mesh = mesh
	node.material_override = _material(color)
	parent.add_child(node)
	node.position = position
	return node

func _solid(parent: Node3D, position: Vector3, size: Vector3, color: Color, visible_mesh: bool = true) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	body.collision_mask = 0
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	collision.shape = shape
	body.add_child(collision)
	if visible_mesh:
		_visual(body,Vector3.ZERO,size,color)
	parent.add_child(body)
	body.position = position
	return body

func _batch_transform(storage: Array[Transform3D], position: Vector3, size: Vector3) -> void:
	storage.append(Transform3D(Basis.IDENTITY.scaled(size),position))

func _batch(storage: Array[Transform3D], color: Color) -> void:
	if storage.is_empty():
		return
	var instances := MultiMesh.new()
	instances.transform_format = MultiMesh.TRANSFORM_3D
	var mesh := BoxMesh.new()
	mesh.size = Vector3.ONE
	mesh.material = _material(color)
	instances.mesh = mesh
	instances.instance_count = storage.size()
	for i in storage.size():
		instances.set_instance_transform(i,storage[i])
	var node := MultiMeshInstance3D.new()
	node.multimesh = instances
	city_root.add_child(node)

func _construct_city() -> void:
	var extent := float(config.world_size)
	var block := float(config.block_size)
	var count := int(config.blocks)
	var road := float(config.road_width)
	_solid(city_root,Vector3(extent/2,-0.4,extent/2),Vector3(extent+road,0.8,extent+road),Color("#6c7771"))
	for line in count+1:
		var pos := line*block
		_visual(city_root,Vector3(pos,0.012,extent*0.5),Vector3(road,0.024,extent+road),Color("#383e48"))
		_visual(city_root,Vector3(extent*0.5,0.016,pos),Vector3(extent+road,0.025,road),Color("#383e48"))
		for section in count:
			var start := section*block
			for dash in range(2,int(block)-2,6):
				if dash < 9 or dash > block-9:
					continue
				_batch_transform(_paint_transforms,Vector3(pos,0.038,start+dash),Vector3(0.17,0.018,2))
				_batch_transform(_paint_transforms,Vector3(start+dash,0.039,pos),Vector3(2,0.018,0.17))
			for side in [-1,1]:
				var off: float = side*7.25
				_visual(city_root,Vector3(pos+off,0.018,start+block/2),Vector3(2.5,0.034,block-13),Color("#a4a8a6"))
				_visual(city_root,Vector3(start+block/2,0.018,pos+off),Vector3(block-13,0.034,2.5),Color("#a4a8a6"))
			for stripe in range(-4,5,2):
				_batch_transform(_paint_transforms,Vector3(pos+stripe,0.042,start+7),Vector3(1.0,0.018,2))
				_batch_transform(_paint_transforms,Vector3(start+7,0.043,pos+stripe),Vector3(2,0.018,1.0))
				_batch_transform(_paint_transforms,Vector3(pos+stripe,0.042,start+block-7),Vector3(1.0,0.018,2))
				_batch_transform(_paint_transforms,Vector3(start+block-7,0.043,pos+stripe),Vector3(2,0.018,1.0))
	for row in config.buildings:
		if _skip_building(row):
			continue
		var center := _vec(row.center)
		var size := _vec(row.size)
		var district: String = row.district
		var color: Color = PALETTE.get(district,Color("#999999"))
		var body := _solid(city_root,center+Vector3.UP*size.y/2,size,color)
		body.name = str(row.id)
		body.set_meta("building_id",row.id)
		buildings[row.id] = body
		_visual(body,Vector3(0,size.y/2-0.15,0),Vector3(size.x+0.25,0.3,size.z+0.25),color.darkened(0.2))
		for y in range(2,int(size.y)-1,3):
			for x in range(2,int(size.x)-1,3):
				for face in [-1,1]:
					_batch_transform(_window_transforms,Vector3(center.x-size.x/2+x,y,center.z+face*(size.z/2+0.012)),Vector3(1.25,1.55,0.05))
			for z in range(2,int(size.z)-1,3):
				for face in [-1,1]:
					_batch_transform(_window_transforms,Vector3(center.x+face*(size.x/2+0.012),y,center.z-size.z/2+z),Vector3(0.05,1.55,1.25))
	_batch(_window_transforms,Color("#31485b"))
	_batch(_paint_transforms,Color("#e0d9bd"))
	# Preserve a bounded open playable map while the roads continue visually to its edge.
	for side in [0,1]:
		var edge: float = -0.25 if side == 0 else extent+0.25
		_solid(city_root,Vector3(edge,3,extent/2),Vector3(0.5,6,extent+1),Color.BLACK,false)
		_solid(city_root,Vector3(extent/2,3,edge),Vector3(extent+1,6,0.5),Color.BLACK,false)

func _skip_building(_row: Dictionary) -> bool:
	return false

func _make_tour() -> void:
	var seen := {}
	var block := float(config.block_size)
	for row in config.zoning:
		var id: String = row.district
		if seen.has(id):
			continue
		seen[id] = true
		var cell: Array = row.block
		var position := Vector3((float(cell[0])+0.5)*block,0,float(cell[1])*block)
		landmarks.append({"id":id,"position":position})
		var marker := MeshInstance3D.new()
		var mesh := TorusMesh.new()
		mesh.inner_radius = 1.5
		mesh.outer_radius = 2.0
		marker.mesh = mesh
		var material := StandardMaterial3D.new()
		material.albedo_color = Color("#f4c355")
		material.emission_enabled = true
		material.emission = Color("#b58b24")
		marker.material_override = material
		add_child(marker)
		marker.position = position+Vector3.UP*0.15
		var label := Label3D.new()
		label.text = id.capitalize()
		label.position.y = 2.8
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.pixel_size = 0.009
		marker.add_child(label)
		landmark_markers.append(marker)
	_update_tour()

func _update_tour() -> void:
	for i in landmark_markers.size():
		landmark_markers[i].visible = i == tour_index

func greet_near() -> bool:
	var npc: Dictionary = civilians.nearest(player.global_position)
	if npc.is_empty() or npc.distance > 3.0 or greeted.has(npc.id):
		return false
	greeted[npc.id] = true
	message = "Greeted %s · %s" % [npc.id,str(npc.activity)]
	return true

func start_network(mode: String, port: int) -> bool:
	if network.status().mode != "offline":
		return false
	var ok: bool = network.host(port) if mode == "host" else network.join(port) if mode == "client" else false
	if ok:
		player.set_physics_process(false)
		player.velocity = Vector3.ZERO
		message = "Loopback multiplayer: " + mode
	return ok

func _parse_network_args() -> void:
	var args := OS.get_cmdline_user_args()
	for i in args.size()-1:
		if args[i] in ["--host","--join"] and args[i+1].is_valid_int():
			start_network("host" if args[i] == "--host" else "client",int(args[i+1]))

func set_network_test_input(input: Vector2) -> void:
	_test_network_enabled = true
	_test_network_input = input

func _remote_update(peers: Dictionary, local_id: int) -> void:
	for id in remote_meshes.keys():
		if not peers.has(id) or id == local_id:
			remote_meshes[id].queue_free()
			remote_meshes.erase(id)
	for id in peers:
		if int(id) == local_id or not peers[id] is Vector3:
			continue
		if not remote_meshes.has(id):
			remote_meshes[id] = _visual(remote_root,Vector3.ZERO,Vector3(0.6,1.6,0.6),Color("#2fd2dc"))
		remote_meshes[id].position = peers[id]+Vector3.UP*0.8

func _physics_process(delta: float) -> void:
	if not ready_for_play:
		return
	var start := Time.get_ticks_usec()
	_step_population(delta)
	var net: Dictionary = network.status()
	if net.mode != "offline":
		var raw := Vector2.ZERO
		if _test_network_enabled:
			raw = _test_network_input
		elif Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			var local := Vector3(int(Input.is_physical_key_pressed(KEY_D))-int(Input.is_physical_key_pressed(KEY_A)),0,int(Input.is_physical_key_pressed(KEY_S))-int(Input.is_physical_key_pressed(KEY_W)))
			var direction := player.global_transform.basis*local.normalized()
			raw = Vector2(direction.x,direction.z)
		network.step(delta,raw)
		net = network.status()
		if net.connected:
			player.global_position = net.local_position + Vector3.UP*0.08
		_remote_update(net.peers,int(net.get("peer_id",1 if net.mode=="host" else -1)))
	else:
		if not player.is_physics_processing():
			player.set_physics_process(true)
		_remote_update({},-1)
	if tour_index < landmarks.size() and player.global_position.distance_to(landmarks[tour_index].position) < 2.7:
		message = "District visited: " + str(landmarks[tour_index].id)
		tour_index += 1
		_update_tour()
	var traffic_state: Dictionary = traffic.status()
	var civ: Dictionary = civilians.status()
	var objective := "CITY TOUR COMPLETE"
	if tour_index < landmarks.size():
		var target: Dictionary = landmarks[tour_index]
		objective = "%s · %.1f m" % [str(target.id).capitalize(),player.global_position.distance_to(target.position)]
	hud.text = "METROPOLIS · %d m × %d m · seed %d\n%d buildings · %d vehicles · %d residents · %.1fh\nTour %d/%d · %s\n%s · peers %d\nWASD / Shift · G greet · F5/F9 checkpoint (offline)\n%s" % [int(config.world_size),int(config.world_size),int(config.seed),buildings.size(),traffic_state.cars.size(),civ.count,civ.hour,tour_index,landmarks.size(),objective,str(net.mode),net.peers.size(),message]
	simulation_usec = Time.get_ticks_usec()-start

func _step_population(delta: float) -> void:
	traffic.step(delta)
	civilians.step(delta)

func _unhandled_input(event: InputEvent) -> void:
	if not ready_for_play or not event is InputEventKey or not event.pressed or event.echo:
		return
	match event.physical_keycode:
		KEY_G: message = message if greet_near() else "Approach an ungreeted resident"
		KEY_F5: message = "City checkpoint saved" if save_world(checkpoint_path) else "Save unavailable"
		KEY_F9: message = "City checkpoint restored" if load_world(checkpoint_path) else "Load unavailable"

func save_world(path: String) -> bool:
	var payload := world_snapshot()
	return not payload.is_empty() and persistence.write_checkpoint(path,payload)

func world_snapshot() -> Dictionary:
	if not ready_for_play or network.status().mode != "offline":
		return {}
	var p := player.global_position
	return {"version":1,"spec":_identity(),"position":[p.x,p.y,p.z],"tour_index":tour_index,"greeted":greeted.duplicate(),"traffic":traffic.snapshot(),"civilians":civilians.snapshot()}

func _identity() -> Dictionary:
	return {"seed":config.seed,"blocks":config.blocks,"block_size":config.block_size,"traffic":config.traffic,"civilians":config.civilians}

func load_world(path: String) -> bool:
	return restore_world(persistence.read_checkpoint(path))

func restore_world(data: Dictionary) -> bool:
	if not ready_for_play or network.status().mode != "offline":
		return false
	if data.size() != 7 or data.get("version") != 1 or data.get("spec") != _identity():
		return false
	var p = data.get("position")
	if not p is Array or p.size() != 3:
		return false
	for value in p:
		if not (value is int or value is float) or not is_finite(float(value)):
			return false
	var position := _vec(p)
	if position.x < 0 or position.z < 0 or position.x > config.world_size or position.z > config.world_size or position.y < -0.25 or position.y > 5.0:
		return false
	for row in config.buildings:
		var center := _vec(row.center)
		var size := _vec(row.size)
		if absf(position.x-center.x) < size.x/2+0.35 and absf(position.z-center.z) < size.z/2+0.35 and position.y < size.y:
			return false
	var index = data.get("tour_index")
	if not (index is int or index is float) or index != floorf(index) or index < 0 or index > landmarks.size():
		return false
	var ids = data.get("greeted")
	if not ids is Dictionary or ids.size() > int(config.civilians):
		return false
	var valid_ids := {}
	for row in civilians.status().civilians:
		valid_ids[row.id] = true
	for id in ids:
		if not valid_ids.has(id) or ids[id] != true:
			return false
	if not data.get("traffic") is Dictionary or not data.get("civilians") is Dictionary or not traffic.valid_snapshot(data.traffic) or not civilians.valid_snapshot(data.civilians):
		return false
	traffic.restore(data.traffic)
	civilians.restore(data.civilians)
	player.global_position = position
	player.velocity = Vector3.ZERO
	player.clear_test_drive()
	tour_index = int(index)
	greeted = ids.duplicate()
	_update_tour()
	return true
