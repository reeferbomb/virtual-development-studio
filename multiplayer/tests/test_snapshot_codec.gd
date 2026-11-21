extends SceneTree

func _initialize() -> void:
	if not ResourceLoader.exists("res://snapshot_codec.gd"):
		printerr("FAIL: snapshot codec absent")
		quit(1)
		return
	var codec = load("res://snapshot_codec.gd")
	var members := {}
	var actors := {}
	for i in range(1,17):
		members[i] = {"name":"abcdefghijklmnopqrstuvwx","ready":true,"slot":i-1}
		actors[i] = {"position":Vector3(i,0,-i),"yaw":0.5,"health":75,"ammo":2,"reserve":6}
	var snapshot := {"members":members,"actors":actors,"started":true,"npc_pos":Vector3(2,0,1),"npc_hp":125,"time":3.0}
	var packed: Dictionary = codec.pack(snapshot)
	var bytes := var_to_bytes(packed).size()
	if bytes > 1200 or codec.unpack(packed) != snapshot or not codec.unpack({}).is_empty():
		printerr("FAIL: codec round trip, malformed input or packet budget: ",bytes)
		quit(1)
		return
	print("PASS snapshot codec, 16-player serialized bytes: ",bytes)
	quit(0)
