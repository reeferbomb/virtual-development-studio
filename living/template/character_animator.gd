extends Node3D

## Procedural scout rig. The origin is at the soles and local -Z faces forward.
## The caller owns position/yaw and supplies seconds and velocity in metres/sec.

const ATTACK_SECONDS := 0.42
const HIT_SECONDS := 0.36
const FALL_SECONDS := 0.62
const GAITS := ["idle", "walk", "run", "sprint"]

class Limbs:
	var side: float
	var hip: Node3D
	var knee: Node3D
	var ankle: Node3D
	var shoulder: Node3D
	var elbow: Node3D

var _pelvis: Node3D
var _chest: Node3D
var _head: Node3D
var _limbs: Array[Limbs] = []
var _gaits := Vector4(1, 0, 0, 0)
var _speed := 0.0
var _phase := 0.0
var _breath := 0.0
var _crouch := 0.0
var _aim := 0.0
var _attack_time := ATTACK_SECONDS
var _attack_held := false
var _hit_time := 0.0
var _hit_strength := 0.0
var _fall := 0.0
var _dead := false

func configure() -> bool:
	if is_instance_valid(_pelvis):
		return true
	_limbs.clear()
	var fabric := _material(Color("#278982"))
	var trim := _material(Color("#243b47"))
	var plate := _material(Color("#d4d5c4"))
	var signal_color := _material(Color("#ffae48"))
	var visor := _material(Color("#254c5e"))
	visor.metallic = 0.45

	_pelvis = _joint(self, "Pelvis", Vector3(0, 0.87, 0))
	_box(_pelvis, "Belt", Vector3(0, 0.015, 0), Vector3(0.4, 0.16, 0.24), trim)
	_chest = _joint(_pelvis, "Chest", Vector3(0, 0.07, 0))
	_shell(_chest, "Jacket", Vector3(0, 0.24, 0), 0.26, 0.19, 0.5, 0.64, fabric)
	_box(_chest, "ChestPlate", Vector3(0, 0.31, -0.135), Vector3(0.32, 0.2, 0.065), plate)
	_box(_chest, "ChestStripe", Vector3(0.09, 0.31, -0.175), Vector3(0.055, 0.18, 0.015), signal_color)
	_box(_chest, "Pack", Vector3(0, 0.25, 0.14), Vector3(0.29, 0.32, 0.13), trim)
	_head = _joint(_chest, "Head", Vector3(0, 0.5, 0))
	_shell(_head, "Helmet", Vector3(0, 0.14, 0), 0.14, 0.135, 0.27, 0.94, plate)
	_box(_head, "Visor", Vector3(0, 0.155, -0.109), Vector3(0.223, 0.095, 0.067), visor)

	for side: int in [-1, 1]:
		var limb := Limbs.new()
		limb.side = float(side)
		var prefix := "Left" if side < 0 else "Right"
		limb.hip = _joint(_pelvis, prefix + "Hip", Vector3(side * 0.119, 0, 0))
		_shell(limb.hip, "Thigh", Vector3(0, -0.18, 0), 0.105, 0.081, 0.36, 1.05, fabric)
		limb.knee = _joint(limb.hip, "Knee", Vector3(0, -0.38, 0))
		_shell(limb.knee, "Shin", Vector3(0, -0.17, 0), 0.086, 0.065, 0.35, 1.0, trim)
		_box(limb.knee, "Kneepad", Vector3(0, -0.036, -0.064), Vector3(0.13, 0.135, 0.057), plate)
		limb.ankle = _joint(limb.knee, "Ankle", Vector3(0, -0.37, 0))
		_box(limb.ankle, "Boot", Vector3(0, -0.04, -0.044), Vector3(0.145, 0.16, 0.255), trim)
		limb.shoulder = _joint(_chest, prefix + "Shoulder", Vector3(side * 0.255, 0.417, 0))
		_shell(limb.shoulder, "Sleeve", Vector3(0, -0.12, 0), 0.099, 0.072, 0.25, 1.0, fabric)
		_shell(limb.shoulder, "ShoulderGuard", Vector3(0, -0.025, 0), 0.096, 0.105, 0.098, 1.05, plate)
		limb.elbow = _joint(limb.shoulder, "Elbow", Vector3(0, -0.265, 0))
		_shell(limb.elbow, "Bracer", Vector3(0, -0.104, 0), 0.076, 0.058, 0.215, 1.0, trim)
		_box(limb.elbow, "Glove", Vector3(0, -0.238, 0), Vector3(0.112, 0.108, 0.12), signal_color)
		_limbs.append(limb)
	_apply_pose()
	return true

## Reapplying configure preserves the current pose. Invalid samples have no effect.
func step(delta: float, velocity: Vector3, aiming: bool, attacking: bool, crouching: bool, dead: bool) -> void:
	if not is_instance_valid(_pelvis) or not is_finite(delta) or delta <= 0 or not velocity.is_finite():
		return
	# Clamp before squaring to avoid overflow on extreme but finite input.
	_speed = minf(12.0, Vector2(clampf(velocity.x, -12, 12), clampf(velocity.z, -12, 12)).length())
	_dead = dead
	var target_speed := 0.0 if dead else _speed
	var moving := smoothstep(0.05, 0.95, target_speed)
	var running := smoothstep(2.0, 4.0, target_speed)
	var sprinting := smoothstep(4.8, 6.8, target_speed)
	var target := Vector4(1.0 - moving, moving - running, running - sprinting, sprinting)
	var blend := 1.0 - exp(-10.0 * delta)
	_gaits = _gaits.lerp(target, blend)
	_crouch = lerpf(_crouch, float(crouching and not dead), blend)
	_aim = lerpf(_aim, float(aiming and not dead), blend)
	var cadence := moving * (0.78 + 0.18 * target_speed)
	if cadence > 0.0:
		_phase = fposmod(_phase + TAU * cadence * fmod(delta, 1.0 / cadence), TAU)
	_breath = fposmod(_breath + TAU * fmod(delta, 4.0) / 4.0, TAU)
	_fall = move_toward(_fall, float(dead), delta / FALL_SECONDS)
	_hit_time = maxf(0.0, _hit_time - delta) if not dead else 0.0
	if attacking and not dead:
		if not _attack_held:
			_attack_time = 0.0
		_attack_time = fmod(_attack_time + fmod(delta, ATTACK_SECONDS), ATTACK_SECONDS)
	elif dead:
		_attack_time = ATTACK_SECONDS
	else:
		_attack_time = minf(ATTACK_SECONDS, _attack_time + delta)
	_attack_held = attacking and not dead
	_apply_pose()

## Trigger a short upper-body flinch independent of locomotion.
func hit(intensity: float = 1.0) -> void:
	if not is_instance_valid(_pelvis) or _dead or not is_finite(intensity) or intensity <= 0.0:
		return
	_hit_strength = minf(intensity, 1.0)
	_hit_time = HIT_SECONDS
	_apply_pose()

func status() -> Dictionary:
	var gait: String = GAITS[_gaits.max_axis_index()]
	var state := gait
	if _dead:
		state = "death"
	elif _hit_time > 0.0:
		state = "hit"
	elif _attack_time < ATTACK_SECONDS:
		state = "attack"
	elif _aim >= 0.5:
		state = "aim"
	elif _crouch >= 0.5:
		state = "crouch"
	return {
		"configured": is_instance_valid(_pelvis), "state": state, "locomotion": gait,
		"speed": _speed, "phase": _phase,
		"weights": {"idle": _gaits.x, "walk": _gaits.y, "run": _gaits.z, "sprint": _gaits.w,
			"crouch": _crouch, "aim": _aim, "attack": _strike(), "hit": _flinch(), "death": _fall}
	}

func _strike() -> float:
	var progress := _attack_time / ATTACK_SECONDS
	return smoothstep(0.0, 0.22, progress) * (1.0 - smoothstep(0.25, 1.0, progress))

func _flinch() -> float:
	return _hit_strength * smoothstep(0.0, 1.0, _hit_time / HIT_SECONDS)

func _apply_pose() -> void:
	var stride := _gaits.y * 0.42 + _gaits.z * 0.77 + _gaits.w * 1.02
	stride *= 1.0 - 0.43 * _crouch
	var gait_wave := sin(_phase)
	var bob := stride * 0.04 * (1.0 - absf(gait_wave))
	var breath := 0.007 * cos(_breath) * _gaits.x
	var fall := smoothstep(0.0, 1.0, _fall)
	var flinch := _flinch()
	var strike := _strike()
	_pelvis.position.y = lerpf(0.87 - 0.205 * _crouch + bob, 0.224, fall)
	_pelvis.rotation = Vector3(lerpf(0.0, 1.53, fall), 0, 0)
	var lean := -0.11 * _gaits.z - 0.20 * _gaits.w - 0.17 * _crouch
	var twist := 0.16 * stride * gait_wave - 0.13 * _aim + 0.32 * strike
	_chest.position.y = 0.07 + breath * (1.0 - fall)
	_chest.rotation = Vector3(lean + 0.30 * flinch, twist, 0.19 * flinch).lerp(Vector3.ZERO, fall)
	_head.rotation = Vector3(-lean * 0.55 - 0.22 * flinch, -twist * 0.6, -0.15 * flinch).lerp(Vector3(0.06, -0.15, 0.08), fall)
	for limb in _limbs:
		var swing := limb.side * gait_wave
		var thigh := stride * swing + 0.78 * _crouch
		var knee := -stride * maxf(0.0, limb.side * cos(_phase)) * 0.9 - 1.50 * _crouch
		limb.hip.rotation.x = lerpf(thigh, 0.03 + 0.055 * limb.side, fall)
		limb.knee.rotation.x = lerpf(knee, 0.0, fall)
		limb.ankle.rotation.x = lerpf(-0.87 * (thigh + knee), -0.05, fall)
		var shoulder := -0.65 * stride * swing + 0.10 * _crouch
		var elbow := 0.11 + 0.45 * stride + 0.22 * _crouch
		shoulder = lerpf(shoulder, 1.12 + 0.13 * limb.side, _aim)
		elbow = lerpf(elbow, 0.54 - 0.19 * limb.side, _aim)
		var action := strike if limb.side > 0 else strike * 0.42
		shoulder = lerpf(shoulder, 1.63, action) - 0.21 * flinch
		elbow = lerpf(elbow, 0.05, action) + 0.27 * flinch
		var spread := 0.062 - 0.36 * _aim + 0.17 * flinch
		limb.shoulder.rotation = Vector3(shoulder, 0, limb.side * spread).lerp(Vector3(0.10, 0, limb.side * 0.46), fall)
		limb.elbow.rotation.x = lerpf(elbow, 0.10, fall)

func _joint(parent: Node3D, label: String, offset: Vector3) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = label
	pivot.position = offset
	parent.add_child(pivot)
	return pivot

func _material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.68
	return material

func _box(parent: Node3D, label: String, offset: Vector3, size: Vector3, material: Material) -> void:
	var box := BoxMesh.new()
	box.size = size
	_visual(parent, label, offset, box, material)

func _shell(parent: Node3D, label: String, offset: Vector3, top: float, bottom: float, height: float, depth: float, material: Material) -> void:
	var shell := CylinderMesh.new()
	shell.top_radius = top
	shell.bottom_radius = bottom
	shell.height = height
	shell.radial_segments = 10
	shell.rings = 0
	var visual := _visual(parent, label, offset, shell, material)
	visual.scale.z = depth

func _visual(parent: Node3D, label: String, offset: Vector3, mesh: Mesh, material: Material) -> MeshInstance3D:
	var visual := MeshInstance3D.new()
	visual.name = label
	visual.position = offset
	visual.mesh = mesh
	visual.material_override = material
	parent.add_child(visual)
	return visual
