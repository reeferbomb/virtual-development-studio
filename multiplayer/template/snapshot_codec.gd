extends RefCounted

# Compact fixed-width state fields; maximum 16 actors and 24 ASCII name bytes.
static func pack(state: Dictionary) -> Dictionary:
	var ids := PackedInt32Array()
	var names := PackedStringArray()
	var flags := PackedByteArray()
	var poses := PackedFloat32Array()
	for id in state.members:
		var member: Dictionary = state.members[id]
		var actor: Dictionary = state.actors[id]
		ids.append(id)
		names.append(member.name)
		flags.append_array(PackedByteArray([int(member.ready),member.slot,actor.health,actor.ammo,actor.reserve]))
		poses.append_array(PackedFloat32Array([actor.position.x,actor.position.y,actor.position.z,actor.yaw]))
	return {"i":ids,"n":names,"f":flags,"p":poses,"s":state.started,"v":state.npc_pos,"h":state.npc_hp,"t":state.time}

static func unpack(data: Dictionary) -> Dictionary:
	if not data.has_all(["i","n","f","p","s","v","h","t"]):
		return {}
	if not (data.i is PackedInt32Array and data.n is PackedStringArray and data.f is PackedByteArray and data.p is PackedFloat32Array and data.s is bool and data.v is Vector3 and data.h is int and data.t is float):
		return {}
	var count: int = data.i.size()
	if count < 1 or count > 16 or data.n.size() != count or data.f.size() != count*5 or data.p.size() != count*4:
		return {}
	if not data.v.is_finite() or not is_finite(data.t) or data.h < 0 or data.h > 150:
		return {}
	var members := {}
	var actors := {}
	for index in count:
		var id: int = data.i[index]
		var name: String = data.n[index]
		var f := index*5
		var p := index*4
		var position := Vector3(data.p[p],data.p[p+1],data.p[p+2])
		var yaw: float = data.p[p+3]
		if id < 1 or members.has(id) or name.length() < 1 or name.length() > 24 or data.f[f] > 1 or data.f[f+1] > 15 or data.f[f+2] > 100 or data.f[f+3] > 6 or not position.is_finite() or not is_finite(yaw):
			return {}
		members[id] = {"name":name,"ready":bool(data.f[f]),"slot":int(data.f[f+1])}
		actors[id] = {"position":position,"yaw":yaw,"health":int(data.f[f+2]),"ammo":int(data.f[f+3]),"reserve":int(data.f[f+4])}
	return {"members":members,"actors":actors,"started":data.s,"npc_pos":data.v,"npc_hp":data.h,"time":data.t}
