extends "res://session_network.gd"

# Host-only commands and bounded snapshots, independent of earlier channels.
const ACTION_PACKET := 6
const FEATURE_PACKET := 7
const FEATURE_VERSION := 1
const FEATURE_CHANNEL := 3
const FEATURE_MAX_BYTES := 16384
const FEATURE_PERIOD := 0.10

var feature_car
var feature_lift
var feature_cover
var feature_mission
var feature_squads
var feature_identity := ""
var feature_ready := false
var feature_tick := 0
var feature_received := 0
var feature_rejected := 0
var feature_accepted := 0
var _feature_until := 0.0
var _feature_peer_cooldown: Dictionary[int,float] = {}

func configure_features(identity: String,car,lift,cover,mission,squads) -> bool:
	if _mode != "offline" or identity.length() != 64:
		return false
	feature_identity = identity
	feature_car = car
	feature_lift = lift
	feature_cover = cover
	feature_mission = mission
	feature_squads = squads
	feature_ready = true
	return true

func feature_snapshot() -> Dictionary:
	if not feature_ready or (_mode == "client" and feature_received == 0):
		return {}
	return {"version":FEATURE_VERSION,"identity":feature_identity,"tick":feature_tick,"car":feature_car.snapshot(),"lift":feature_lift.snapshot(),"cover":feature_cover.snapshot(),"mission":feature_mission.snapshot(),"squads":feature_squads.snapshot()}

func valid_feature_snapshot(data: Variant) -> bool:
	if not feature_ready or not data is Dictionary or data.size() != 8 or not data.has_all(["version","identity","tick","car","lift","cover","mission","squads"]):
		return false
	if data.version != FEATURE_VERSION or data.identity != feature_identity or not (data.tick is int or data.tick is float) or not is_finite(float(data.tick)) or data.tick < 0 or data.tick != floorf(data.tick) or data.tick > 2147483647:
		return false
	return feature_car.valid_snapshot(data.car) and feature_lift.valid_snapshot(data.lift) and feature_cover.valid_snapshot(data.cover) and feature_mission.valid_snapshot(data.mission) and feature_squads.valid_snapshot(data.squads)

func _apply_features(data: Dictionary) -> bool:
	if not valid_feature_snapshot(data):
		return false
	feature_car.restore(data.car)
	feature_lift.restore(data.lift)
	feature_cover.restore(data.cover)
	feature_mission.restore(data.mission)
	feature_squads.restore(data.squads)
	feature_tick = int(data.tick)
	return true

func request_feature(kind: int,index: int = 0) -> bool:
	if not feature_ready or kind < 0 or kind > 3 or index < 0 or index > 2:
		return false
	if _mode == "host":
		return _feature_action(1,kind,index)
	if _mode != "client" or feature_received == 0 or not _positions.has(_local_id):
		return false
	return _api.send_bytes(PackedByteArray([ACTION_PACKET,FEATURE_VERSION,kind,index]),1,MultiplayerPeer.TRANSFER_MODE_RELIABLE,FEATURE_CHANNEL) == OK

func _feature_action(peer: int,kind: int,index: int) -> bool:
	if not feature_ready or not _positions.has(peer) or _feature_peer_cooldown.get(peer,0.0) > 0.0:
		return false
	_feature_peer_cooldown[peer] = 0.1
	var pos: Vector3 = _positions[peer]
	var accepted := false
	if kind == 0 and index == 0 and not feature_lift.occupied(peer):
		accepted = feature_car.request(peer,pos)
	elif kind == 1 and index == 0 and not feature_car.occupied(peer):
		accepted = feature_lift.request(peer,pos)
	elif not feature_car.occupied(peer) and not feature_lift.occupied(peer):
		if kind == 2:
			accepted = feature_cover.request(peer,pos,index)
		elif kind == 3 and index == 0:
			accepted = feature_mission.request(peer,pos)
	if accepted:
		feature_accepted += 1
	return accepted

func _member_move(id: int,dt: float) -> Vector3:
	if not feature_ready:
		return super._member_move(id,dt)
	if feature_car.occupied(id) or feature_lift.occupied(id):
		return _positions[id]
	return feature_cover.move(_positions[id],super._member_move(id,dt))

func _after_members_moved(dt: float) -> void:
	if not feature_ready:
		return
	for id in _feature_peer_cooldown.keys():
		_feature_peer_cooldown[id] = maxf(0.0,_feature_peer_cooldown[id]-dt)
	feature_car.step(dt,_positions,_directions)
	feature_lift.step(dt,_positions,_directions)
	feature_cover.step(dt)
	feature_mission.step(dt)
	feature_squads.step(dt)
	feature_tick = mini(feature_tick+1,2147483647)

func _remove_member(id: int) -> void:
	if feature_ready and _mode == "host" and is_instance_valid(feature_car) and is_instance_valid(feature_lift) and is_instance_valid(feature_cover):
		feature_car.release_peer(id)
		feature_lift.release_peer(id)
		feature_cover.release_peer(id)
	_feature_peer_cooldown.erase(id)
	super._remove_member(id)

func step(delta: float,input: Vector2) -> void:
	super.step(delta,input)
	if _mode != "host" or not feature_ready or not is_finite(delta) or delta <= 0.0:
		return
	_feature_until -= minf(delta,0.1)
	if _feature_until <= 0.0:
		_feature_until = FEATURE_PERIOD
		if _positions.size() > 1:
			var payload := JSON.stringify(feature_snapshot()).to_utf8_buffer()
			if payload.size() <= FEATURE_MAX_BYTES:
				var packet := PackedByteArray([FEATURE_PACKET])
				packet.append_array(payload)
				_api.send_bytes(packet,0,MultiplayerPeer.TRANSFER_MODE_UNRELIABLE_ORDERED,FEATURE_CHANNEL)

func _receive(sender: int,packet: PackedByteArray) -> void:
	if packet.is_empty() or packet[0] not in [ACTION_PACKET,FEATURE_PACKET]:
		super._receive(sender,packet)
		return
	if packet[0] == ACTION_PACKET:
		if _mode == "host" and sender > 1 and packet.size() == 4 and packet[1] == FEATURE_VERSION and packet[2] <= 3 and packet[3] <= 2 and _feature_action(sender,int(packet[2]),int(packet[3])):
			return
	elif _mode == "client" and sender == 1 and packet.size() <= FEATURE_MAX_BYTES+1 and packet.size() > 1:
		var body := packet.slice(1).get_string_from_utf8()
		var data = JSON.parse_string(body)
		if valid_feature_snapshot(data) and int(data.tick) > feature_tick and _apply_features(data):
			feature_received += 1
			return
	feature_rejected += 1

func status() -> Dictionary:
	var result := super.status()
	result.merge({"feature_tick":feature_tick,"feature_received":feature_received,"feature_accepted":feature_accepted,"feature_rejected":feature_rejected})
	return result

func stop() -> void:
	if feature_ready and _mode == "host" and is_instance_valid(feature_car) and is_instance_valid(feature_lift) and is_instance_valid(feature_cover):
		for id in _positions:
			feature_car.release_peer(id)
			feature_lift.release_peer(id)
			feature_cover.release_peer(id)
	super.stop()
	_feature_peer_cooldown.clear()
	feature_tick = 0
	feature_received = 0
	feature_rejected = 0
	feature_accepted = 0
	_feature_until = 0.0
