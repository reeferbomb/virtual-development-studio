extends RefCounted

static func _v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


static func _material(color: Color, roughness: float = 0.85) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	return material


static func _group(parent: Node3D, label: String) -> Node3D:
	var group := Node3D.new()
	group.name = label
	parent.add_child(group)
	return group


static func _collider(parent: Node3D, size: Vector3, offset := Vector3.ZERO) -> void:
	var body := StaticBody3D.new()
	body.name = "Body"
	parent.add_child(body)
	var shape := BoxShape3D.new()
	shape.size = size
	var collision := CollisionShape3D.new()
	collision.name = "Collision"
	collision.shape = shape
	collision.position = offset
	body.add_child(collision)


static func _box(parent: Node3D, label: String, center: Vector3, size: Vector3, mat: Material) -> void:
	var item := MeshInstance3D.new()
	item.name = label
	var mesh := BoxMesh.new()
	mesh.size = size
	item.mesh = mesh
	item.material_override = mat
	item.position = center
	parent.add_child(item)
	_collider(item, size)


static func _height(x: float, z: float, flat: float) -> float:
	var outside := maxf(absf(x), absf(z)) - flat
	var fade := smoothstep(0.0, 5.0, outside)
	return fade * (0.48 * sin(x * 0.27 + z * 0.17) + 0.32 * cos(z * 0.32) + 0.20 * sin(x * 0.51 - z * 0.12))


static func _terrain(parent: Node3D, t: Dictionary) -> void:
	var width := float(t["width"])
	var depth := float(t["depth"])
	var segments := int(t["segments"])
	var flat := float(t["flat_radius"])
	var amplitude := float(t["amplitude"])
	# Insert exact transition lines so triangles cannot slope into the flat square.
	var xs := _axis(width, segments, flat)
	var zs := _axis(depth, segments, flat)
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for z in zs:
		for x in xs:
			var y := amplitude * _height(x, z, flat)
			var shade := 0.5 + 0.5 * sin(x * 0.38 + z * 0.25) * cos(z * 0.42)
			surface.set_color(Color(0.20, 0.31, 0.25).lerp(Color(0.32, 0.42, 0.30), shade))
			surface.add_vertex(Vector3(x, y, z))
	for row in range(zs.size() - 1):
		for col in range(xs.size() - 1):
			var i := row * xs.size() + col
			var next := i + xs.size()
			for index: int in [i, i + 1, next, i + 1, next + 1, next]:
				surface.add_index(index)
	surface.generate_normals()
	var ground := MeshInstance3D.new()
	ground.name = "Terrain"
	ground.mesh = surface.commit()
	var mat := _material(Color.WHITE)
	mat.vertex_color_use_as_albedo = true
	ground.material_override = mat
	parent.add_child(ground)
	ground.create_trimesh_collision()


static func _axis(length_m: float, segments: int, flat: float) -> PackedFloat32Array:
	var axis := PackedFloat32Array()
	for i in range(segments + 1):
		axis.append(length_m * (float(i) / segments - 0.5))
	for split: float in [-flat, flat]:
		if absf(split) < length_m * 0.5:
			var present := false
			for point in axis:
				if is_equal_approx(point, split):
					present = true
					break
			if not present:
				axis.append(split)
	axis.sort()
	return axis


static func _lighting(world: Node3D) -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.57, 0.73, 0.80)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.83, 0.89, 1.0)
	env.ambient_light_energy = 0.68
	var sky := WorldEnvironment.new()
	sky.name = "Environment"
	sky.environment = env
	world.add_child(sky)
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_color = Color(1.0, 0.91, 0.76)
	sun.light_energy = 1.2
	sun.shadow_enabled = true
	world.add_child(sun)


static func build(spec: Dictionary) -> Node3D:
	var world := Node3D.new()
	world.name = "World"
	_lighting(world)
	var terrain: Dictionary = spec["terrain"]
	_terrain(world, terrain)
	var blocks := _group(world, "Blocks")
	for data: Dictionary in spec["blocks"]:
		var rgb: Array = data["color"]
		_box(blocks, str(data["id"]), _v3(data["position"]), _v3(data["size"]), _material(Color(rgb[0], rgb[1], rgb[2])))
	var bounds := _group(world, "Bounds")
	var w := float(terrain["width"])
	var d := float(terrain["depth"])
	var amp := absf(float(terrain["amplitude"]))
	var h := 2.0 * amp + 2.5
	var wall_mat := _material(Color(0.23, 0.29, 0.31))
	for sign_dir: int in [-1, 1]:
		_box(bounds, "West" if sign_dir < 0 else "East", Vector3(sign_dir * (w * 0.5 + 0.15), 1.25, 0), Vector3(0.3, h, d + 0.6), wall_mat)
		_box(bounds, "North" if sign_dir < 0 else "South", Vector3(0, 1.25, sign_dir * (d * 0.5 + 0.15)), Vector3(w, h, 0.3), wall_mat)
	var props := _group(world, "Props")
	for data: Dictionary in spec["placements"]:
		var anchor := _group(props, str(data["id"]))
		anchor.add_to_group("studio_prop", true)
		anchor.position = _v3(data["position"])
		anchor.rotation.y = deg_to_rad(float(data["yaw_deg"]))
		var scene := load("res://assets/%s.glb" % data["asset"]) as PackedScene
		if scene:
			anchor.add_child(scene.instantiate())
		if data.has("collider_size"):
			var size := _v3(data["collider_size"])
			_collider(anchor, size, Vector3.UP * size.y * 0.5)
	for label: String in ["Spawn", "Goal"]:
		var marker := Marker3D.new()
		marker.name = label
		marker.position = _v3(spec[label.to_lower()])
		world.add_child(marker)
		if label == "Goal":
			var ring := TorusMesh.new()
			ring.inner_radius = 0.60
			ring.outer_radius = 0.75
			ring.rings = 32
			ring.ring_segments = 8
			var visual := MeshInstance3D.new()
			visual.name = "BeaconRing"
			visual.mesh = ring
			visual.position.y = 0.10
			var mat := _material(Color(0.10, 0.94, 0.76), 0.35)
			mat.emission_enabled = true
			mat.emission = Color(0.05, 0.64, 0.46)
			visual.material_override = mat
			marker.add_child(visual)
	return world
