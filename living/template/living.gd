extends "res://unified.gd"

const ENCOUNTERS = preload("res://encounters.gd")
const DIPLOMACY = preload("res://diplomacy.gd")
const CONTRACTS = preload("res://contracts.gd")
const ANIMATOR = preload("res://character_animator.gd")

var encounters = ENCOUNTERS.new()
var diplomacy = DIPLOMACY.new()
var contracts = CONTRACTS.new()
var scout = ANIMATOR.new()
var living_ready := false
var encounter_origin: Vector3
var scout_origin: Vector3
var _at_checkpoint := false
var _scout_time := 0.0
var _scout_last: Vector3
var _scout_label: Label3D

func _ready() -> void:
	super._ready()
	if not unified_ready:
		return
	checkpoint_path = "user://living_%s.json" % JSON.stringify(config,"",true).sha256_text().substr(0,24)
	var size := float(config.chunk_size)
	encounter_origin = Vector3(size*0.75,0,-size*3.5)
	scout_origin = Vector3(size*0.35,0,size*0.5)
	add_child(encounters)
	add_child(scout)
	if not encounters.configure(int(config.seed),encounter_origin) or not diplomacy.configure(int(config.seed)) or not contracts.configure(int(config.seed)) or not scout.configure():
		push_error("Living component configuration failed")
		return
	encounters.step(0.001,player.global_position)
	scout.position = scout_origin
	_scout_last = scout.position
	_scout_label = Label3D.new()
	_scout_label.text = "RANGER SCOUT"
	_scout_label.position = Vector3(0,2.15,0)
	_scout_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_scout_label.pixel_size = 0.006
	scout.add_child(_scout_label)
	_add_landmark(encounter_origin, Color("#ff5754"),true)
	living_ready = true
	print("STUDIO_LIVING_READY")

func alive() -> bool:
	return living_ready and encounters.status().health > 0

func accept_contract(slot: int) -> bool:
	if not alive() or transport.driving:
		return false
	var offers: Array = contracts.board()
	if slot < 0 or slot >= offers.size() or not contracts.accept(offers[slot].id):
		return false
	message = "Accepted: " + str(offers[slot].title)
	return true

func claim_contract() -> bool:
	if not alive() or transport.driving:
		return false
	var state: Dictionary = contracts.status()
	if not state.complete or not economy.credit(int(state.reward)):
		return false
	var reward: int = contracts.claim()
	message = "Contract reward +%d credits" % reward
	return reward == int(state.reward)

func use_bandage() -> bool:
	if not alive() or transport.driving or encounters.status().health >= encounters.MAX_HEALTH:
		return false
	if not inventory.remove("bandage",1):
		return false
	encounters.heal(24)
	message = "Used bandage · restored up to 24 HP"
	return true

func harvest_near() -> bool:
	if not alive():
		return false
	var id := _nearest_resource()
	if id.is_empty():
		return false
	var item: String = markers[id].get_meta("item")
	if not super.harvest_near():
		return false
	contracts.record("gather",item)
	return true

func greet_near() -> bool:
	if not alive():
		return false
	var npc: Dictionary = population.nearest(player.global_position)
	if not super.greet_near():
		return false
	contracts.record("greet",npc.faction)
	diplomacy.record("greet",npc.faction)
	return true

func craft_item(item: String) -> bool:
	if not alive() or not super.craft_item(item):
		return false
	contracts.record("craft",item)
	return true

func trade(action: String, item: String, count: int = 1) -> bool:
	if not alive() or not super.trade(action,item,count):
		return false
	diplomacy.record("trade","traders")
	if action == "sell":
		for i in count:
			contracts.record("sell",item)
	return true

func shoot_target(direction: Vector3) -> Dictionary:
	var empty := {"fired":false,"hit":false,"defeated":false,"id":""}
	if not alive() or transport.driving:
		return empty
	if not quests.completed:
		return super.shoot_target(direction)
	if combat_range.ammo <= 0 or combat_range.cooldown > 0.0:
		return empty
	var result: Dictionary = encounters.shoot(player.get_node("Camera3D").global_position,direction)
	if result.fired:
		combat_range.ammo -= 1
		combat_range.cooldown = combat_range.SHOT_INTERVAL
	if result.defeated:
		diplomacy.record("aid","rangers")
		message = "Hostile patrol neutralized"
	return result

func _physics_process(delta: float) -> void:
	if not living_ready:
		return
	super._physics_process(delta)
	diplomacy.step(delta)
	# The training expedition unlocks hostile combat. Without it, the player can
	# still explore and complete non-combat contracts without being attacked.
	if quests.completed:
		encounters.step(delta,player.global_position)
	var health: int = encounters.status().health
	if health <= 0:
		player.walk_speed = 0.0
		player.sprint_speed = 0.0
		if transport.driving:
			transport.set_drive(0,0,true)
	var reached: bool = transport.driving and transport.vehicle.global_position.distance_to(drive_checkpoint) <= 2.5
	if reached and not _at_checkpoint and health > 0:
		contracts.record("drive","checkpoint")
	_at_checkpoint = reached
	_scout_time = world_seconds
	var angle := _scout_time*0.45
	var next_position := scout_origin + Vector3(cos(angle)*3.0,0,sin(angle)*3.0)
	var velocity := (next_position-_scout_last)/maxf(delta,0.0001)
	scout.position = next_position
	_scout_last = next_position
	if velocity.length_squared() > 0.01:
		scout.rotation.y = atan2(-velocity.x,-velocity.z)
	scout.step(delta,velocity.limit_length(2.0),false,false,false,false)
	var board_state: Dictionary = contracts.status()
	var faction_state: Dictionary = diplomacy.status()
	var line := ""
	if board_state.active_id == "":
		var offers: Array = contracts.board()
		for i in offers.size():
			line += "%d:%s (%dc)  " % [i+1,offers[i].title,offers[i].reward]
	elif board_state.complete:
		line = "Contract finished · H claim %dc" % board_state.reward
	else:
		line = "%s · %s %s (%d/%d)" % [board_state.title,board_state.current.action,board_state.current.target,board_state.progress,board_state.current.count]
	status.text += "\nLIVING WORLD · HP %d · Diplomacy tick %d · Encounters %d\nSettlers %d · Rangers %d · Traders %d\n%s\n1/2/3 accept · H claim · J bandage · Patrols unlock after training" % [health,faction_state.tick,encounters.status().active_count,faction_state.standings.settlers,faction_state.standings.rangers,faction_state.standings.traders,line]
	if health <= 0:
		status.text += "\nINCAPACITATED · F9 restore checkpoint"

func _unhandled_input(event: InputEvent) -> void:
	if not living_ready:
		return
	if event is InputEventKey and event.pressed and not event.echo:
		match event.physical_keycode:
			KEY_1, KEY_2, KEY_3:
				accept_contract(int(event.physical_keycode-KEY_1))
				return
			KEY_H:
				claim_contract()
				return
			KEY_J:
				use_bandage()
				return
			KEY_F9:
				message = "Checkpoint loaded" if load_world(checkpoint_path) else "Load failed"
				return
			KEY_E:
				if not alive() and transport.driving:
					message = "Exited vehicle · F9 restore" if transport.exit() else "Waiting for vehicle to stop"
					return
	if alive():
		super._unhandled_input(event)

func save_world(path: String) -> bool:
	if not alive():
		return false
	var base: Dictionary = super.world_snapshot()
	if base.is_empty():
		return false
	return persistence.write_checkpoint(path,{"version":1,"base":base,"encounters":encounters.snapshot(),"diplomacy":diplomacy.snapshot(),"contracts":contracts.snapshot()})

func load_world(path: String) -> bool:
	if not living_ready or transport.driving:
		return false
	var data: Dictionary = persistence.read_checkpoint(path)
	if data.size() != 5 or data.get("version") != 1:
		return false
	for key in ["base","encounters","diplomacy","contracts"]:
		if not data.get(key) is Dictionary:
			return false
	var next_diplomacy = DIPLOMACY.new()
	var next_contracts = CONTRACTS.new()
	next_diplomacy.configure(int(config.seed))
	next_contracts.configure(int(config.seed))
	if not next_diplomacy.restore(data.diplomacy) or not next_contracts.restore(data.contracts) or not encounters.valid_snapshot(data.encounters):
		return false
	if not super.restore_world(data.base):
		return false
	diplomacy = next_diplomacy
	contracts = next_contracts
	encounters.restore(data.encounters)
	_at_checkpoint = false
	player.walk_speed = 4.0 if alive() else 0.0
	player.sprint_speed = 7.0 if alive() else 0.0
	return true
