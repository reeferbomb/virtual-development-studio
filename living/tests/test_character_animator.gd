extends SceneTree

const Animator = preload("res://character_animator.gd")
var failures := 0

func check(condition: bool, label: String) -> void:
	if not condition:
		failures += 1
		printerr("FAIL ", label)

func _initialize() -> void:
	call_deferred("_run")

func _rig() -> Animator:
	var actor := Animator.new()
	root.add_child(actor)
	check(actor.configure(), "configure")
	return actor

func _same_pose(a: Node3D, b: Node3D) -> bool:
	if a.get_child_count() != b.get_child_count() or not a.transform.is_equal_approx(b.transform):
		return false
	for i in a.get_child_count():
		if not _same_pose(a.get_child(i), b.get_child(i)):
			return false
	return true

func _run() -> void:
	var actor := Animator.new()
	actor.step(0.25, Vector3.RIGHT, true, true, true, true)
	actor.hit()
	check(not actor.status().configured and actor.get_child_count() == 0, "safe before configure")
	root.add_child(actor)
	check(actor.configure(), "build rig")
	check(actor.status().state == "idle" and actor.find_children("*", "MeshInstance3D", true, false).size() >= 16, "visible articulated mesh pieces")
	var chest: Node3D = actor.get_node("Pelvis/Chest")
	var shoulder: Node3D = chest.get_node("RightShoulder")
	var glove: Node3D = shoulder.get_node("Elbow/Glove")
	var left_hip: Node3D = actor.get_node("Pelvis/LeftHip")
	var right_hip: Node3D = actor.get_node("Pelvis/RightHip")
	var head: Node3D = chest.get_node("Head")
	var y_start := chest.position.y
	actor.step(1.0, Vector3.UP * 10, false, false, false, false)
	check(actor.status().state == "idle" and chest.position.y < y_start, "idle breath and vertical velocity exclusion")
	for sample in [[1.5, "walk"], [4.0, "run"], [7.0, "sprint"]]:
		actor.step(1.1, Vector3.FORWARD * sample[0], false, false, false, false)
		var state := actor.status()
		check(state.locomotion == sample[1] and state.state == sample[1], "select " + sample[1])
		check(absf(left_hip.rotation.x) > 0.025 and signf(left_hip.rotation.x) == -signf(right_hip.rotation.x), "opposing stride " + sample[1])
	var fast_pose := right_hip.rotation.x
	actor.step(0.01, Vector3.FORWARD * 2, false, false, false, false)
	check(actor.status().weights.walk > 0.0 and actor.status().weights.sprint > 0.0 and absf(fast_pose - right_hip.rotation.x) < 0.3, "gait crossfade")
	var upright_y := actor.get_node("Pelvis").position.y as float
	actor.step(1, Vector3.ZERO, false, false, true, false)
	check(actor.status().state == "crouch" and actor.get_node("Pelvis").position.y < upright_y - 0.18 and right_hip.rotation.x > 0.7, "lower pelvis and flex knees")
	var rest_hand := glove.global_position
	actor.step(1, Vector3.ZERO, true, false, true, false)
	check(actor.status().state == "aim" and actor.status().weights.crouch > 0.9 and glove.global_position.z < rest_hand.z - 0.25, "aim moves hands forward while crouched")
	var aim_arm := shoulder.rotation.x
	actor.step(0.10, Vector3.ZERO, true, true, true, false)
	check(actor.status().state == "attack" and shoulder.rotation.x > aim_arm + 0.25, "attack overlays aim")
	actor.step(0.05, Vector3.ZERO, true, false, false, false)
	check(actor.status().state == "attack", "release preserves attack follow-through")
	var before_hit := chest.rotation
	actor.hit()
	check(actor.status().state == "hit" and chest.rotation.distance_to(before_hit) > 0.25, "damage flinch rotates body")
	actor.step(0.75, Vector3.ZERO, false, false, false, false)
	check(actor.status().state == "idle" and actor.status().weights.hit == 0.0, "attack and damage recover")
	var standing_height := head.global_position.y
	actor.step(0.12, Vector3.RIGHT * 8, true, true, true, true)
	check(actor.status().state == "death" and actor.status().weights.death > 0.0 and actor.status().weights.death < 1.0, "death begins an interpolated fall")
	actor.step(1, Vector3.RIGHT * 8, true, true, true, true)
	check(head.global_position.y < standing_height * 0.3 and actor.get_node("Pelvis").rotation.x > 1.5, "fall reaches ground")
	var fallen_pose := head.global_transform
	actor.hit()
	actor.step(1, Vector3.ZERO, false, false, false, true)
	check(actor.status().state == "death" and fallen_pose.is_equal_approx(head.global_transform), "dead body stays still")
	actor.step(1, Vector3.ZERO, false, false, false, false)
	check(actor.status().state == "idle" and head.global_position.y > standing_height * 0.95, "revive")
	var valid := actor.status()
	for sample in [[-1.0, Vector3.ZERO], [0.0, Vector3.ZERO], [NAN, Vector3.ZERO], [INF, Vector3.ZERO], [1.0, Vector3(0, INF, 0)], [1.0, Vector3(NAN, 0, 0)]]:
		actor.step(sample[0], sample[1], true, true, true, true)
	for strength in [0.0, -1.0, NAN, INF]:
		actor.hit(strength)
	check(valid == actor.status(), "invalid samples leave phase, pose state and weights unchanged")
	check(actor.configure() and valid == actor.status() and actor.get_child_count() == 1, "configure is idempotent")
	var coarse := _rig()
	var fine := _rig()
	coarse.step(0.625, Vector3.FORWARD * 4.75, true, true, true, false)
	for i in 40:
		fine.step(0.625 / 40, Vector3.FORWARD * 4.75, true, true, true, false)
	check(_same_pose(coarse, fine), "pose independent of frame subdivision")
	var weights: Dictionary = fine.status().weights
	check(is_equal_approx(weights.idle + weights.walk + weights.run + weights.sprint, 1.0), "locomotion weights sum to one")
	for rig in [actor, fine, coarse]:
		rig.free()
	if failures == 0:
		print("PASS living character animator")
	quit(1 if failures else 0)
