extends SceneTree

const Weather = preload("res://weather.gd")
var errors: Array[String] = []


func _initialize() -> void:
	call_deferred("_run")


func _world(environment: Environment) -> Node3D:
	var world := Node3D.new()
	var sky := WorldEnvironment.new()
	sky.name = "Environment"
	sky.environment = environment
	world.add_child(sky)
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	world.add_child(sun)
	return world


func _check(condition: bool, message: String) -> void:
	if not condition:
		errors.append(message)
		printerr("FAIL ", message)


func _run() -> void:
	var resource := Environment.new()
	var world := _world(resource)
	var sky := world.get_node("Environment") as WorldEnvironment
	var sun := world.get_node("Sun") as DirectionalLight3D
	var weather := Weather.new()
	var config := {"weather": "clear", "cycle_seconds": 48.0, "start_hour": 12.0}
	_check(weather.configure(world, config), "configure a generated world")
	var noon := weather.snapshot()
	var noon_sun := sun.rotation
	var noon_sky := sky.environment.background_color
	var noon_ambient := sky.environment.ambient_light_energy
	var rain := world.get_node("Rain") as MultiMeshInstance3D
	_check(sky.environment != resource, "world owns its mutable environment")
	_check(not rain.visible and not sky.environment.fog_enabled, "clear sky has no fog or rain")
	_check(is_equal_approx(noon.hour, 12.0) and is_equal_approx(noon.light_energy, sun.light_energy),
		"snapshot reports the live noon light")
	_check(weather.set_weather("rain"), "select rain")
	var rainy := weather.snapshot()
	_check(rain.visible and rainy.rain_visible and rain.multimesh.instance_count > 0, "rain draws streaks")
	_check(rainy.visibility < noon.visibility and sun.light_energy < noon.light_energy, "rain reduces sight and sun")
	_check(sky.environment.fog_enabled and sky.environment.fog_density > 0.0, "rain creates actual mist")
	_check(weather.set_weather("fog"), "select fog")
	var foggy := weather.snapshot()
	_check(not rain.visible and foggy.fog_density > rainy.fog_density and foggy.visibility < rainy.visibility,
		"fog reduces visibility further and hides precipitation")
	_check(is_equal_approx(foggy.fog_density, sky.environment.fog_density), "snapshot tracks scene fog")
	_check(not weather.set_weather("snow") and weather.snapshot() == foggy, "invalid weather preserves state")
	_check(not weather.configure(world, {"cycle_seconds": 0.0}) and weather.snapshot() == foggy,
		"invalid config preserves state")
	_check(not weather.configure(world, {"start_hour": "noon"}), "reject malformed time")
	weather.set_weather("clear")
	weather.step(24.0)
	var midnight := weather.snapshot()
	_check(is_zero_approx(midnight.hour) and sun.light_energy < noon.light_energy, "half cycle reaches midnight")
	_check(midnight.visibility < noon.visibility and sun.rotation != noon_sun, "night changes sight and sun angle")
	_check(sky.environment.background_color != noon_sky and sky.environment.ambient_light_energy < noon_ambient,
		"night dims the actual environment")
	weather.step(-1.0)
	weather.step(INF)
	_check(weather.snapshot() == midnight, "invalid deltas preserve state")
	weather.step(48.0 * 3.0 + 24.0)
	_check(is_equal_approx(weather.snapshot().hour, noon.hour) and sun.rotation.is_equal_approx(noon_sun),
		"multiple cycles wrap to noon")

	var second := _world(resource)
	var other := Weather.new()
	_check(other.configure(second, config), "configure second world")
	weather.step(3.75)
	for i in 15:
		other.step(0.25)
	_check(is_equal_approx(weather.snapshot().hour, other.snapshot().hour)
		and is_equal_approx(weather.snapshot().light_energy, other.snapshot().light_energy),
		"elapsed time is independent of frame partition")
	weather.set_weather("fog")
	_check(not (second.get_node("Environment") as WorldEnvironment).environment.fog_enabled,
		"weather cannot bleed into another instance")
	_check(weather.configure(world, config) and world.get_node("Rain") == rain and not rain.visible,
		"reconfiguration resets state and reuses the rain mesh")
	second.free()
	other.free()
	world.free()
	weather.free()
	if errors.is_empty():
		print("WEATHER_TEST_PASS")
	quit(0 if errors.is_empty() else 1)
