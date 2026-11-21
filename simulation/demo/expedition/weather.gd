extends Node

const WEATHER := {
	"clear": {"sun": 1.0, "visibility": 1.0, "fog": 0.0, "sky": Color(0.57, 0.73, 0.80)},
	"rain": {"sun": 0.48, "visibility": 0.70, "fog": 0.024, "sky": Color(0.39, 0.48, 0.56)},
	"fog": {"sun": 0.60, "visibility": 0.40, "fog": 0.085, "sky": Color(0.66, 0.71, 0.73)},
}
const RAIN_DROPS := 320
const RAIN_HEIGHT := 9.0
const RAIN_PERIOD := 0.75

var _environment: Environment
var _sun: DirectionalLight3D
var _rain: MultiMeshInstance3D
var _drop_origins := PackedVector3Array()
var _mode := "clear"
var _cycle_seconds := 120.0
var _hour := 12.0
var _rain_phase := 0.0
var _visibility := 1.0


func configure(world: Node3D, config: Dictionary) -> bool:
	if not is_instance_valid(world):
		return false
	var sky := world.get_node_or_null("Environment") as WorldEnvironment
	var sun := world.get_node_or_null("Sun") as DirectionalLight3D
	var mode = config.get("weather", "clear")
	var cycle = config.get("cycle_seconds", 120.0)
	var hour = config.get("start_hour", 12.0)
	if not sky or not sky.environment or not sun or not mode is String or not WEATHER.has(mode):
		return false
	if not _finite_number(cycle) or cycle <= 0.0 or not _finite_number(hour) or hour < 0.0 or hour >= 24.0:
		return false

	if not is_instance_valid(_rain) or _rain.get_parent() != world:
		if is_instance_valid(_rain):
			_rain.free()
		# PackedScene instances can share Environment resources. Keep weather local.
		sky.environment = sky.environment.duplicate() as Environment
		_create_rain(world)
	_environment = sky.environment
	_sun = sun
	_mode = mode
	_cycle_seconds = cycle
	_hour = hour
	_rain_phase = 0.0
	_apply()
	return true


func _finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func step(delta: float) -> void:
	if not is_instance_valid(_sun) or not is_finite(delta) or delta <= 0.0:
		return
	_hour = fposmod(_hour + fmod(delta, _cycle_seconds) / _cycle_seconds * 24.0, 24.0)
	_rain_phase = fposmod(_rain_phase + fmod(delta, RAIN_PERIOD) / RAIN_PERIOD, 1.0)
	_apply()


func set_weather(mode: String) -> bool:
	if not is_instance_valid(_sun) or not WEATHER.has(mode):
		return false
	_mode = mode
	_apply()
	return true


func snapshot() -> Dictionary:
	if not is_instance_valid(_sun):
		return {}
	return {"hour": _hour, "weather": _mode, "visibility": _visibility,
		"light_energy": _sun.light_energy, "fog_density": _environment.fog_density,
		"rain_visible": _rain.visible}


func _apply() -> void:
	var profile: Dictionary = WEATHER[_mode]
	# Sunrise is 06:00 and sunset is 18:00. Ambient twilight extends beyond both.
	var elevation := sin((_hour - 6.0) * TAU / 24.0)
	var daylight := smoothstep(-0.12, 0.90, elevation)
	var sky_color := Color(0.034, 0.052, 0.105).lerp(profile.sky, daylight)
	_environment.background_mode = Environment.BG_COLOR
	_environment.background_color = sky_color
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_environment.ambient_light_color = Color(0.45, 0.53, 0.72).lerp(Color(0.83, 0.89, 1.0), daylight)
	_environment.ambient_light_energy = lerpf(0.26, 0.73, daylight) * lerpf(0.7, 1.0, profile.sun)
	_environment.fog_enabled = profile.fog > 0.0
	_environment.fog_density = profile.fog
	_environment.fog_light_color = sky_color
	_sun.rotation_degrees = Vector3(-65.0 * elevation, -35.0 + (_hour - 12.0) * 15.0, 0.0)
	_sun.light_color = Color(1.0, 0.57, 0.31).lerp(Color(1.0, 0.95, 0.85), daylight)
	_sun.light_energy = maxf(0.0, elevation) * 1.2 * float(profile.sun)
	_visibility = lerpf(0.40, 1.0, daylight) * float(profile.visibility)
	_rain.visible = _mode == "rain"
	if _rain.visible:
		_position_drops()


func _create_rain(world: Node3D) -> void:
	# Batch the streaks in a single mesh. Their positions depend only on simulation time.
	var terrain := world.get_node_or_null("Terrain") as MeshInstance3D
	var area := AABB(Vector3(-16, 0, -12), Vector3(32, 0, 24))
	if terrain and terrain.mesh:
		area = terrain.transform * terrain.mesh.get_aabb()
	var streak := BoxMesh.new()
	streak.size = Vector3(0.022, 0.30, 0.022)
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = Color(0.55, 0.67, 0.74)
	streak.material = material
	var mesh := MultiMesh.new()
	mesh.transform_format = MultiMesh.TRANSFORM_3D
	mesh.mesh = streak
	mesh.instance_count = RAIN_DROPS
	_rain = MultiMeshInstance3D.new()
	_rain.name = "Rain"
	_rain.multimesh = mesh
	_rain.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	world.add_child(_rain)
	_drop_origins.resize(RAIN_DROPS)
	var random := RandomNumberGenerator.new()
	random.seed = 1701
	for i in RAIN_DROPS:
		_drop_origins[i] = Vector3(random.randf_range(area.position.x, area.end.x),
			random.randf() * RAIN_HEIGHT, random.randf_range(area.position.z, area.end.z))


func _position_drops() -> void:
	var tilt := Basis(Vector3.FORWARD, 0.09)
	for i in _drop_origins.size():
		var point := _drop_origins[i]
		point.y = fposmod(point.y - _rain_phase * RAIN_HEIGHT, RAIN_HEIGHT)
		point.x -= point.y * 0.09
		_rain.multimesh.set_instance_transform(i, Transform3D(tilt, point))
