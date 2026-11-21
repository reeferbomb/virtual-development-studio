"""Procedural freight-yard props. Coordinates are metres before uniform scaling."""

import math

import bpy


def create(spec: dict) -> None:
    identifier = spec["id"]
    variant = spec["variant"]
    scale = float(spec.get("size_m", 1.0))
    tint = tuple(spec.get("color", (0.17, 0.46, 0.40)))
    if variant not in ("crate", "barrel", "barricade"):
        raise ValueError(f"Unknown prop variant: {variant}")
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("size_m must be finite and positive")

    def material(name, rgb, metal, roughness):
        mat = bpy.data.materials.new(f"{identifier}.{name}")
        mat.diffuse_color = (*rgb, 1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        for key, value in (("Base Color", (*rgb, 1)), ("Metallic", metal),
                           ("Roughness", roughness)):
            shader.inputs[key].default_value = value
        return mat

    paint = material("enamel", tint, 0.32, 0.48)
    steel = material("gunmetal", (0.075, 0.093, 0.099), 0.72, 0.38)
    signal = material("amber", (0.98, 0.54, 0.055), 0.18, 0.40)

    def finish(name, mat, bevel=0):
        obj = bpy.context.object
        obj.name = f"{identifier}.{name}"
        obj.data.name = obj.name
        obj.data.materials.append(mat)
        if bevel:
            mod = obj.modifiers.new("Chamfer", "BEVEL")
            mod.width = bevel * scale
            mod.segments = 1
            mod = obj.modifiers.new("Face normals", "WEIGHTED_NORMAL")
            mod.keep_sharp = True
        return obj

    def box(name, xyz, dims, mat, bevel=0.012):
        bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(v * scale for v in xyz))
        obj = bpy.context.object
        for vert in obj.data.vertices:
            for axis, dim in enumerate(dims):
                vert.co[axis] *= dim * scale
        obj.data.update()
        return finish(name, mat, bevel)

    def disc(name, xyz, radius, depth, mat, segments=20):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=segments, radius=radius * scale, depth=depth * scale,
            location=tuple(v * scale for v in xyz))
        return finish(name, mat, 0.005)

    if variant == "crate":
        box("shell", (0, 0, 0.50), (0.92, 0.84, 0.92), paint, 0.045)
        for n, z in enumerate((0.06, 0.94)):
            box(f"rim{n}", (0, 0, z), (1, 0.92, 0.12), steel, 0.03)
        for i, x in enumerate((-0.42, 0.42)):
            for j, y in enumerate((-0.38, 0.38)):
                box(f"post{i}{j}", (x, y, 0.50), (0.14, 0.14, 0.84), steel, 0.022)
        for j, y in enumerate((-0.43, 0.43)):
            for i, z in enumerate((0.25, 0.49, 0.73)):
                box(f"rib{j}{i}", (0, y, z), (0.64, 0.035, 0.065), paint)
            box(f"latch{j}", (0, 1.065 * y, 0.88), (0.16, 0.035, 0.12), signal)
        for i, x in enumerate((-0.27, 0, 0.27)):
            box(f"lid{i}", (x, 0, 0.998), (0.24, 0.70, 0.018), paint, 0.006)

    elif variant == "barrel":
        disc("drum", (0, 0, 0.50), 0.355, 0.96, paint)
        for i, z in enumerate((0.025, 0.27, 0.73, 0.975)):
            disc(f"hoop{i}", (0, 0, z), 0.375, 0.05, steel)
        disc("lid", (0, 0, 0.999), 0.327, 0.014, paint)
        disc("bung-seat", (0.145, 0.11, 1.012), 0.064, 0.017, steel, 12)
        disc("bung", (0.145, 0.11, 1.025), 0.045, 0.021, signal, 6)
        for i, z in enumerate((0.34, 0.66)):
            disc(f"band{i}", (0, 0, z), 0.358, 0.019, signal)

    else:
        for i, x in enumerate((-0.56, 0.56)):
            box(f"foot{i}", (x, 0, 0.057), (0.18, 0.62, 0.114), steel, 0.024)
            box(f"upright{i}", (x, 0, 0.48), (0.105, 0.115, 0.84), steel)
        box("board", (0, 0, 0.68), (1.54, 0.14, 0.37), paint, 0.032)
        box("lower-rail", (0, 0, 0.32), (1.33, 0.10, 0.075), paint)
        for j, y in enumerate((-0.072, 0.072)):
            for i, x in enumerate((-0.54, -0.27, 0, 0.27, 0.54)):
                stripe = box(f"stripe{j}{i}", (x, y, 0.68), (0.088, 0.012, 0.313),
                             signal, 0.003)
                stripe.rotation_euler.y = 0.45
