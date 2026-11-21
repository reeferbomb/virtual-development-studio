extends SceneTree

func _initialize() -> void:
	if not ResourceLoader.exists("res://network.tscn"):
		printerr("FAIL: multiplayer scene is missing")
		quit(1)
		return
	var scene = load("res://network.tscn").instantiate()
	if not scene.has_method("submit_command") or not scene.has_method("apply_snapshot"):
		printerr("FAIL: multiplayer authority interface missing")
		scene.free()
		quit(1)
		return
	scene.free()
	print("PASS multiplayer scene contract")
	quit(0)
