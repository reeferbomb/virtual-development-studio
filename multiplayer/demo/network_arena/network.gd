extends Node3D

const LOBBY = preload("res://lobby.gd")
const GUARD = preload("res://input_guard.gd")
const COMBAT = preload("res://combat.gd")
const NAV = preload("res://navigation.gd")
const CODEC = preload("res://snapshot_codec.gd")
const SPAWNS = [Vector3(-7,0,0),Vector3(-5,0,0),Vector3(-7,0,3),Vector3(-5,0,2),Vector3(-2,0,1),Vector3(-2,0,-2),Vector3(2,0,0),Vector3(5,0,0),Vector3(7,0,0),Vector3(8,0,3),Vector3(8,0,-2),Vector3(8,0,-6),Vector3(3,0,6),Vector3(-8,0,7),Vector3(-2,0,7),Vector3(0,0,-7)]
var lobby = LOBBY.new()
var guard = GUARD.new()
var nav = NAV.new()
var actors: Dictionary = {}
var combat: Dictionary = {}
var commands: Dictionary = {}
var replicas: Dictionary = {}
var stats := {"joined":0,"started":false,"accepted":0,"rejected":0,"damage_events":0,"pvp_damage_events":0,"npc_damage_events":0,"npc_attack_events":0,"movement_m":0.0,"peak_members":0,"disconnected":0}
var options: Dictionary = {}
var world: Node3D
var npc: CharacterBody3D
var npc_hp := 150
var npc_cooldown := 0.0
var npc_path := PackedVector3Array()
var npc_replan := 0.0
var npc_patrol := 0
var host := false
var automatic := false
var duration := 8.0
var expected := 1
var seq := 0
var ticks := 0
var match_time := 0.0
var elapsed := 0.0
var snapshot: Dictionary = {}
var client_stats := {"peer_id":0,"snapshots":0,"saw_started":false,"max_members":0,"pass":false,"own_movement_m":0.0,"min_npc_health":150,"saw_player_damage":false}
var client_spawn := Vector3.ZERO
var has_client_spawn := false
var yaw := -PI/2
var pitch := 0.0
var camera: Camera3D
var hud: Label
var status := ""
var tried_bad := false
var finishing := false
var leaving := false

func _ready() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--"):
			var parts := arg.substr(2).split("=",false,1)
			options[parts[0]] = parts[1] if parts.size() > 1 else true
	host = options.has("host")
	automatic = options.has("auto")
	if options.has("duration"):
		duration = clampf(float(options.duration),2.0,60.0)
	expected = clampi(int(options.get("expect",1)),1,15)
	var port := int(options.get("port",23777))
	if port < 1024 or port > 65535 or host == options.has("join"):
		_fail("Use --host or --join=ADDRESS with a valid port")
		return
	world = load("res://world.tscn").instantiate()
	add_child(world)
	nav.configure(JSON.parse_string(FileAccess.get_file_as_string("res://level.json")))
	create_hud()
	var peer := ENetMultiplayerPeer.new()
	var err: Error
	if host:
		peer.set_bind_ip(str(options.get("bind","127.0.0.1")))
		err = peer.create_server(port,15)
	else:
		err = peer.create_client(str(options.join),port)
	if err != OK:
		_fail("ENet setup failed: %s" % error_string(err))
		return
	# Clients only communicate with the host; no automatic peer-to-peer relay.
	multiplayer.server_relay = false
	multiplayer.multiplayer_peer = peer
	if host:
		lobby.configure(16,2)
		multiplayer.peer_disconnected.connect(_left)
		lobby.join(1,"Host")
		lobby.set_ready(1,true)
		spawn_actor(1,0)
		npc = make_actor("Guard",Color(0.9,0.25,0.15),4)
		npc.position = Vector3(0,0.08,0)
		print("STUDIO_NET_HOST_READY")
	else:
		multiplayer.connected_to_server.connect(_connected)
		multiplayer.connection_failed.connect(func(): _fail("Connection failed"))
		multiplayer.server_disconnected.connect(_server_left)

func _fail(reason: String) -> void:
	printerr("STUDIO_NET_FAILURE: "+reason)
	get_tree().quit(1)

func create_hud() -> void:
	camera = Camera3D.new()
	add_child(camera)
	camera.current = true
	camera.position = Vector3(-7,1.6,0)
	camera.rotation.y = yaw
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Label.new()
	hud.position = Vector2(16,16)
	hud.add_theme_font_size_override("font_size",18)
	layer.add_child(hud)
	var cross := Label.new()
	cross.text = "+"
	layer.add_child(cross)
	cross.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func make_actor(label: String, color: Color, layer: int) -> CharacterBody3D:
	var body := CharacterBody3D.new()
	body.name = label
	body.collision_layer = layer
	body.collision_mask = 1
	var shape := CapsuleShape3D.new()
	shape.radius = 0.35
	shape.height = 1.8
	var collider := CollisionShape3D.new()
	collider.shape = shape
	collider.position.y = .9
	body.add_child(collider)
	add_mesh(body,color)
	add_child(body)
	return body

func add_mesh(node: Node3D, color: Color) -> void:
	var mesh := MeshInstance3D.new()
	var capsule := CapsuleMesh.new()
	capsule.radius = .35
	capsule.height = 1.8
	mesh.mesh = capsule
	mesh.position.y = .9
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mesh.material_override = mat
	node.add_child(mesh)

func spawn_actor(id: int, slot: int) -> void:
	var actor := make_actor("Peer_%d" % id,Color(0.2,0.55,0.85),2)
	actor.position = SPAWNS[slot] + Vector3.UP * .08
	actors[id] = actor
	combat[id] = COMBAT.new()
	if id == 1:
		actor.get_child(1).visible = false

func _connected() -> void:
	client_stats.peer_id = multiplayer.get_unique_id()
	register_player.rpc_id(1,str(options.get("name","Player")))

func _left(id: int) -> void:
	if lobby.leave(id):
		stats.disconnected += 1
	if actors.has(id):
		actors[id].queue_free()
		actors.erase(id)
	combat.erase(id)
	commands.erase(id)
	guard.forget(id)

@rpc("any_peer","call_remote","reliable")
func register_player(label: String) -> void:
	if not host:
		return
	var sender := multiplayer.get_remote_sender_id()
	if sender <= 1 or not lobby.join(sender,label):
		if sender > 1:
			multiplayer.multiplayer_peer.disconnect_peer(sender)
		return
	spawn_actor(sender,lobby.members[sender].slot)
	stats.joined += 1
	stats.peak_members = maxi(stats.peak_members,lobby.members.size())

@rpc("any_peer","call_remote","reliable")
func set_lobby_ready(value: bool) -> void:
	if host:
		lobby.set_ready(multiplayer.get_remote_sender_id(),value)

@rpc("any_peer","call_remote","reliable")
func leave_match() -> void:
	if host:
		var id := multiplayer.get_remote_sender_id()
		if lobby.members.has(id):
			_left(id)
			leave_ack.rpc_id(id)

@rpc("authority","call_remote","reliable")
func leave_ack() -> void:
	if not host and leaving:
		finish_client()

@rpc("any_peer","call_remote","unreliable_ordered",0)
func submit_command(number: int, move: Vector2, angle: float, elevation: float, fire: bool, reload: bool) -> void:
	if host:
		accept_command(multiplayer.get_remote_sender_id(),number,move,angle,elevation,fire,reload)

func accept_command(id: int, number: int, move: Vector2, angle: float, elevation: float, fire: bool, reload: bool) -> void:
	var now := Time.get_ticks_msec()
	if not is_finite(elevation) or absf(elevation) > 1.45:
		return
	if not lobby.started or not combat.has(id) or not guard.accept(id,number,move,angle,fire,reload,now):
		return
	commands[id] = {"move":move,"yaw":angle,"pitch":elevation,"fire":fire,"reload":reload,"time":now}

func fire_weapon(id: int, angle: float, elevation: float) -> void:
	var weapon = combat[id]
	if not weapon.fire():
		return
	var actor: CharacterBody3D = actors[id]
	var origin := actor.global_position + Vector3.UP * 1.2
	var direction := Vector3(-sin(angle)*cos(elevation),sin(elevation),-cos(angle)*cos(elevation))
	var ray := PhysicsRayQueryParameters3D.create(origin,origin+direction*60.0,7,[actor.get_rid()])
	var hit := get_world_3d().direct_space_state.intersect_ray(ray)
	if hit.is_empty():
		return
	if hit.collider == npc and npc_hp > 0:
		npc_hp = maxi(0,npc_hp-25)
		stats.npc_damage_events += 1
		if npc_hp == 0:
			npc.collision_layer = 0
			npc.visible = false
		return
	for other in actors:
		if other != id and hit.collider == actors[other] and combat[other].damage(25):
			stats.damage_events += 1
			stats.pvp_damage_events += 1
			if combat[other].health <= 0:
				actors[other].collision_layer = 0
				actors[other].visible = false
			break

func server_tick(delta: float) -> void:
	if not lobby.started:
		if automatic and lobby.members.size() == expected+1:
			lobby.start(1)
		if lobby.started:
			stats.started = true
		return
	match_time += delta
	for id in actors:
		var actor: CharacterBody3D = actors[id]
		var weapon = combat[id]
		weapon.tick(delta)
		var before := actor.global_position
		var move := Vector2.ZERO
		var command: Dictionary = commands.get(id,{})
		if weapon.health > 0 and not command.is_empty() and Time.get_ticks_msec()-int(command.time) < 300:
			move = command.move
			actor.rotation.y = command.yaw
			if command.reload:
				weapon.reload()
			if command.fire:
				fire_weapon(id,command.yaw,command.pitch)
		actor.velocity.x = move.x * 4.0
		actor.velocity.z = move.y * 4.0
		if not actor.is_on_floor():
			actor.velocity += actor.get_gravity() * delta
		actor.move_and_slide()
		stats.movement_m += Vector2(actor.global_position.x-before.x,actor.global_position.z-before.z).length()
	server_npc(delta)

func server_npc(delta: float) -> void:
	if npc_hp <= 0:
		return
	npc_cooldown = maxf(npc_cooldown-delta,0.0)
	npc_replan -= delta
	var target: CharacterBody3D
	var target_id := 0
	var nearest := 8.0
	for id in actors:
		var body: CharacterBody3D = actors[id]
		var distance := npc.position.distance_to(body.position)
		if combat[id].health > 0 and distance < nearest:
			var query := PhysicsRayQueryParameters3D.create(npc.position+Vector3.UP,body.position+Vector3.UP,1)
			if get_world_3d().direct_space_state.intersect_ray(query).is_empty():
				target = body
				target_id = id
				nearest = distance
	var destination := Vector3(0,0,-1) if npc_patrol == 0 else Vector3(0,0,0)
	if npc.position.distance_to(destination) < .35:
		npc_patrol = 1-npc_patrol
	if target != null:
		destination = target.position
	npc.velocity.x = 0.0
	npc.velocity.z = 0.0
	if target != null and nearest < 6.5:
		if npc_cooldown <= 0.0 and combat[target_id].damage(4):
			stats.npc_attack_events += 1
			stats.damage_events += 1
			if combat[target_id].health == 0:
				target.collision_layer = 0
				target.visible = false
			npc_cooldown = 1.0
	else:
		if npc_replan <= 0.0:
			npc_path = nav.plan(npc.position,destination)
			npc_replan = .4
		while npc_path.size() > 0:
			var step := npc_path[0]-npc.position
			step.y = 0
			if step.length() > .2:
				var movement := step.normalized()*1.5
				npc.velocity.x = movement.x
				npc.velocity.z = movement.z
				break
			npc_path.remove_at(0)
	if not npc.is_on_floor():
		npc.velocity += npc.get_gravity()*delta
	npc.move_and_slide()

func make_snapshot() -> Dictionary:
	var state := {}
	for id in actors:
		state[id] = {"position":actors[id].position,"yaw":actors[id].rotation.y,"health":combat[id].health,"ammo":combat[id].ammo,"reserve":combat[id].reserve}
	return {"members":lobby.members.duplicate(true),"started":lobby.started,"actors":state,"npc_pos":npc.position,"npc_hp":npc_hp,"time":match_time}

@rpc("authority","call_remote","unreliable_ordered",1)
func apply_snapshot(wire: Dictionary) -> void:
	if host:
		return
	var data := CODEC.unpack(wire)
	if data.is_empty():
		return
	snapshot = data
	client_stats.snapshots += 1
	client_stats.max_members = maxi(client_stats.max_members,data.members.size())
	client_stats.saw_started = client_stats.saw_started or data.started
	var id := multiplayer.get_unique_id()
	client_stats.min_npc_health = mini(client_stats.min_npc_health,data.npc_hp)
	if data.actors.has(id):
		if not has_client_spawn:
			client_spawn = data.actors[id].position
			has_client_spawn = true
		client_stats.own_movement_m = maxf(client_stats.own_movement_m,client_spawn.distance_to(data.actors[id].position))
	for row in data.actors.values():
		client_stats.saw_player_damage = client_stats.saw_player_damage or row.health < 100
	if automatic and data.members.has(id) and not data.members[id].ready and not data.started:
		set_lobby_ready.rpc_id(1,true)
	for other in data.actors:
		if other == id:
			continue
		if not replicas.has(other):
			var node := Node3D.new()
			add_mesh(node,Color(.2,.55,.85))
			add_child(node)
			replicas[other] = node
		replicas[other].position = data.actors[other].position
		replicas[other].rotation.y = data.actors[other].yaw
		replicas[other].visible = data.actors[other].health > 0
	for other in replicas.keys():
		if other != 0 and not data.actors.has(other):
			replicas[other].queue_free()
			replicas.erase(other)
	if not replicas.has(0):
		var node := Node3D.new()
		add_mesh(node,Color(.9,.25,.15))
		add_child(node)
		replicas[0] = node
	replicas[0].position = data.npc_pos
	replicas[0].visible = data.npc_hp > 0

func update_view() -> void:
	if snapshot.is_empty():
		return
	var id := 1 if host else multiplayer.get_unique_id()
	if not snapshot.actors.has(id):
		return
	var row: Dictionary = snapshot.actors[id]
	camera.position = row.position + Vector3.UP*1.6
	camera.rotation = Vector3(pitch,yaw,0)
	var lines := "NETWORK ARENA | %s | %d players | NPC HP %d\n" % ["HOST" if host else "CLIENT",snapshot.members.size(),snapshot.npc_hp]
	if snapshot.started:
		lines += "HP %d  |  AMMO %d / %d  |  WASD, mouse, LMB, R" % [row.health,row.ammo,row.reserve]
	else:
		lines += "F2 ready • host Enter start\n"
		for member in snapshot.members.values():
			lines += "%s: %s\n" % [member.name,"READY" if member.ready else "WAITING"]
	hud.text = lines

func _unhandled_input(event: InputEvent) -> void:
	if automatic or DisplayServer.get_name() == "headless":
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw = wrapf(yaw-event.relative.x*.002,-PI,PI)
		pitch = clampf(pitch-event.relative.y*.002,-1.45,1.45)
	if event is InputEventKey and event.pressed and not event.echo:
		if event.physical_keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		if event.physical_keycode == KEY_ENTER and host and lobby.start(1):
			stats.started = true
		if event.physical_keycode == KEY_F2 and not snapshot.is_empty():
			var id := 1 if host else multiplayer.get_unique_id()
			if snapshot.members.has(id):
				var value: bool = not snapshot.members[id].ready
				if host:
					lobby.set_ready(id,value)
				else:
					set_lobby_ready.rpc_id(1,value)
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func send_input() -> void:
	if snapshot.is_empty() or not snapshot.started:
		return
	var id := 1 if host else multiplayer.get_unique_id()
	if not snapshot.actors.has(id):
		return
	var move := Vector2.ZERO
	var shoot := false
	var reload := false
	if automatic:
		var row: Dictionary = snapshot.actors[id]
		if snapshot.time < .8:
			move = Vector2(.0,.5)
		else:
			var target: Vector3 = snapshot.npc_pos
			if host:
				for other in snapshot.actors:
					if other != id and snapshot.actors[other].health > 25:
						target = snapshot.actors[other].position
						break
			var diff: Vector3 = target-row.position
			yaw = atan2(-diff.x,-diff.z)
			shoot = true
			reload = row.ammo == 0
		if not host and not tried_bad:
			seq += 1
			submit_command.rpc_id(1,seq,Vector2(99,99),0.0,0.0,false,false)
			tried_bad = true
	elif Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		move = Vector2(int(Input.is_physical_key_pressed(KEY_D))-int(Input.is_physical_key_pressed(KEY_A)),int(Input.is_physical_key_pressed(KEY_S))-int(Input.is_physical_key_pressed(KEY_W))).limit_length(1.0).rotated(-yaw)
		shoot = Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT)
		reload = Input.is_physical_key_pressed(KEY_R)
	seq += 1
	if host:
		accept_command(1,seq,move,yaw,pitch,shoot,reload)
	else:
		submit_command.rpc_id(1,seq,move,yaw,pitch,shoot,reload)

func finish_client() -> void:
	if finishing:
		return
	finishing = true
	client_stats.pass = client_stats.saw_started and client_stats.snapshots >= 10 and client_stats.max_members >= 2 and client_stats.own_movement_m > .25 and client_stats.min_npc_health < 150 and client_stats.saw_player_damage
	print("STUDIO_NET_CLIENT_JSON "+JSON.stringify(client_stats))
	get_tree().quit(0 if client_stats.pass else 1)

func _server_left() -> void:
	if automatic:
		finish_client()
	else:
		_fail("Host disconnected")

func _physics_process(delta: float) -> void:
	if multiplayer.multiplayer_peer == null or finishing:
		return
	elapsed += delta
	ticks += 1
	if host:
		server_tick(delta)
		if ticks % 6 == 0:
			snapshot = make_snapshot()
			var wire := CODEC.pack(snapshot)
			for id in lobby.members:
				if id != 1 and multiplayer.get_peers().has(id):
					apply_snapshot.rpc_id(id,wire)
		if automatic and (match_time >= duration or elapsed > duration+15):
			stats.accepted = guard.accepted
			stats.rejected = guard.rejected
			stats.pass = stats.started and stats.joined == expected and stats.accepted > expected*10 and stats.rejected >= expected and stats.pvp_damage_events > 0 and stats.npc_damage_events > 0 and stats.npc_attack_events > 0 and stats.movement_m > 1.0 and stats.disconnected == expected
			print("STUDIO_NET_SERVER_JSON "+JSON.stringify(stats))
			finishing = true
			get_tree().quit(0 if stats.pass else 1)
	else:
		if automatic and not leaving and not snapshot.is_empty() and snapshot.started and snapshot.time >= duration-.5:
			leaving = true
			leave_match.rpc_id(1)
		elif automatic and elapsed > duration+18:
			finish_client()
	if ticks % 3 == 0 and not leaving:
		send_input()
	update_view()
