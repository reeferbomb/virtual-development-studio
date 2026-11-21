"""Measure bounded JSON practice assets using geometry, map headers and sampled joint offsets."""

import math
import re
from collections import Counter, defaultdict


def _criterion(identifier, label):
    return {'id': identifier, 'label': label}


def _track(name, offsets):
    return {'joint': name, 'keys': [
        {'time_s': t, 'translation': xyz}
        for t, xyz in zip([0, 0.5, 1], offsets, strict=True)
    ]}


EXERCISES = [
    {
        'id': 'modeling', 'title': 'Build two closed prop meshes',
        'brief': 'Submit two indexed triangle meshes in meters. Build a closed prop about one meter across '
                 'each axis with its bounding-box center at the origin. Use zero-based indices and consistent '
                 'winding, then simplify it for distance. These checks measure the submitted geometry. '
                 'Inspect silhouette, shading, self-intersections and imported appearance separately.',
        'criteria': [
            _criterion('geometry', 'Every triangle in both meshes has area above 0.000000005 m².'),
            _criterion('topology', 'Each mesh is one closed, consistently wound two-manifold with unique faces and no unused vertices.'),
            _criterion('bounds', 'Both meshes span 0.95–1.05 m per axis and center within 0.025 m of zero per axis.'),
            _criterion('lod-budget', 'LOD0 has 8–64 triangles. LOD1 has 4–32 and at most half the LOD0 count.'),
        ],
        'example': {
            'lod0': {
                'vertices': [[0.5, 0, 0], [0, 0.5, 0], [-0.5, 0, 0], [0, -0.5, 0],
                             [0, 0, 0.5], [0, 0, -0.5]],
                'triangles': [[4, 0, 1], [4, 1, 2], [4, 2, 3], [4, 3, 0],
                              [5, 1, 0], [5, 2, 1], [5, 3, 2], [5, 0, 3]],
            },
            'lod1': {
                'vertices': [[0.5, 0.5, 0.5], [-0.5, -0.5, 0.5],
                             [-0.5, 0.5, -0.5], [0.5, -0.5, -0.5]],
                'triangles': [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
            },
        },
    },
    {
        'id': 'textures', 'title': 'Budget a single-tile prop material',
        'brief': 'Submit indexed UV triangles and headers for three uncompressed 8-bit-per-channel material maps. '
                 'The orm map packs occlusion, roughness and metallic. The memory estimate includes every '
                 'mip level. Pixel content, UV stretch, overlap, seams and actual GPU allocation require separate inspection.',
        'criteria': [
            _criterion('uv-bounds', 'All UV coordinates lie inside the inclusive 0–1 tile.'),
            _criterion('uv-area', 'Each indexed UV triangle has area above 0.000000005 square UV units.'),
            _criterion('map-metadata', 'Supply one base_color in srgb and one normal and orm in linear, each with 3 or 4 channels.'),
            _criterion('resolution', 'All maps share a square power-of-two resolution between 128 and 1024 pixels inclusive.'),
            _criterion('memory', 'All uncompressed 8-bit mip chains together use at most 4 MiB (4,194,304 bytes).'),
        ],
        'example': {
            'uvs': [[0, 0], [1, 0], [1, 1], [0, 1]], 'triangles': [[0, 1, 2], [0, 2, 3]],
            'maps': [
                {'role': 'base_color', 'space': 'srgb', 'width': 512, 'height': 512, 'channels': 4},
                {'role': 'normal', 'space': 'linear', 'width': 512, 'height': 512, 'channels': 3},
                {'role': 'orm', 'space': 'linear', 'width': 512, 'height': 512, 'channels': 3},
            ],
        },
    },
    {
        'id': 'animation', 'title': 'Author an in-place looping rig exercise',
        'brief': 'Describe a skeleton and a linearly interpolated looping clip using joint-local translation '
                 'offsets in meters from the rest pose. Use seconds for times and null for the root parent. '
                 'These checks sample local motion. Rotations, skin deformation, foot contact and engine playback '
                 'require separate inspection.',
        'criteria': [
            _criterion('hierarchy', 'At least two uniquely named joints form one acyclic tree with a single root.'),
            _criterion('coverage', 'Provide exactly one track per declared joint and no unknown tracks.'),
            _criterion('timing', 'Each track has strictly increasing times covering zero through the clip duration.'),
            _criterion('loop', 'Each track ends within 0.01 m of its opening local offset.'),
            _criterion('root-motion', 'The root stays within 0.02 m of its rest offset at every sample.'),
            _criterion('motion', 'At least one child moves 0.02 m from its opening offset, and every segment stays at or below 2 m/s.'),
        ],
        'example': {
            'joints': [{'name': 'root', 'parent': None}, {'name': 'chest', 'parent': 'root'},
                       {'name': 'head', 'parent': 'chest'}],
            'duration_s': 1,
            'tracks': [_track('root', [[0, 0, 0], [0, 0, 0], [0, 0, 0]]),
                       _track('chest', [[0, 0, 0], [0, 0.04, 0], [0, 0, 0]]),
                       _track('head', [[0, 0, 0], [0.01, 0.02, 0], [0, 0, 0]])],
        },
    },
]


def _object(value, fields):
    if type(value) is not dict or len(value) != len(fields) or not all(k in value for k in fields):
        raise ValueError('Expected an object with fields ' + ', '.join(fields))


def _array(value, low, high, label):
    if type(value) is not list or not low <= len(value) <= high:
        raise ValueError(f'{label} must contain {low}–{high} items')
    return value


def _number(value, low, high, label, integer=False):
    types = (int,) if integer else (int, float)
    if type(value) not in types or not low <= value <= high:
        raise ValueError(f'{label} must be a finite {"integer" if integer else "number"} in [{low}, {high}]')
    return value


def _vector(value, size, limit):
    return tuple(_number(n, -limit, limit, 'Coordinate') for n in _array(value, size, size, 'Vector'))


def _indices(value, vertex_count):
    return [tuple(_number(i, 0, vertex_count - 1, 'Triangle index', integer=True)
                  for i in _array(face, 3, 3, 'Triangle'))
            for face in _array(value, 1, 256, 'Triangle list')]


def _result(identifier, measured, detail):
    return {'id': identifier, 'status': 'pass' if measured else 'fail', 'detail': detail}


def _determinant(a, b, i, j):
    return a[i] * b[j] - a[j] * b[i]


def _double_area(points, triangle):
    a, b, c = (points[i] for i in triangle)
    ab = [y - x for x, y in zip(a, b, strict=True)]
    ac = [y - x for x, y in zip(a, c, strict=True)]
    if len(a) == 2:
        return abs(_determinant(ab, ac, 0, 1))
    return math.hypot(_determinant(ab, ac, 1, 2), _determinant(ab, ac, 2, 0), _determinant(ab, ac, 0, 1))


def _connected(graph):
    pending = [next(iter(graph))]
    seen = set()
    while pending:
        vertex = pending.pop()
        if vertex not in seen:
            seen.add(vertex)
            pending.extend(graph[vertex] - seen)
    return len(seen) == len(graph)


def _mesh_topology(vertex_count, faces):
    edges = Counter()
    adjacent = defaultdict(set)
    # The link at a vertex must be connected. Edge counts alone miss pinched vertices.
    fans = defaultdict(lambda: defaultdict(set))
    for a, b, c in faces:
        for u, v, opposite in ((a, b, c), (b, c, a), (c, a, b)):
            edges[u, v] += 1
            adjacent[u].add(v)
            adjacent[v].add(u)
            fans[opposite][u].add(v)
            fans[opposite][v].add(u)
    boundary = overused = winding = 0
    for u, v in {tuple(sorted(edge)) for edge in edges}:
        count = edges[u, v] + (edges[v, u] if u != v else 0)
        boundary += count == 1
        overused += count > 2
        winding += count == 2 and (u == v or edges[u, v] != 1)
    split = sum(not _connected(fan) for fan in fans.values())
    duplicates = len(faces) - len({tuple(sorted(triangle)) for triangle in faces})
    collapsed = sum(len(set(triangle)) < 3 for triangle in faces)
    unused = vertex_count - len(adjacent)
    connected = _connected(adjacent)
    clean = connected and not any((boundary, overused, winding, split, duplicates, collapsed, unused))
    return clean, (f'{boundary} boundary edges, {overused} edges used over twice, {winding} winding conflicts, '
                   f'{split} disconnected vertex fans, {duplicates} duplicate faces, {collapsed} repeated-index faces, '
                   f'{unused} unused vertices, {"connected" if connected else "disconnected"}')


def _mesh_bounds(points, faces):
    used = {i for face in faces for i in face}
    axes = zip(*(points[i] for i in used), strict=True)
    bounds = [(min(axis), max(axis)) for axis in axes]
    spans = [high - low for low, high in bounds]
    centers = [(high + low) / 2 for low, high in bounds]
    fits = all(0.95 <= s <= 1.05 for s in spans) and all(abs(c) <= 0.025 + 1e-12 for c in centers)
    return fits, ('spans ' + ', '.join(f'{s:.4g}' for s in spans) + ' m, center ' +
                  ', '.join(f'{c:.4g}' for c in centers) + ' m')


def _modeling(submission):
    levels = ('lod0', 'lod1')
    _object(submission, levels)
    geometry, topology, bounds, counts = [], [], [], []
    for level in levels:
        mesh = submission[level]
        _object(mesh, ('vertices', 'triangles'))
        vertices = [_vector(v, 3, 1000) for v in _array(mesh['vertices'], 1, 128, 'Vertex list')]
        faces = _indices(mesh['triangles'], len(vertices))
        counts.append(len(faces))
        degenerate = sum(_double_area(vertices, t) <= 1e-8 for t in faces)
        geometry.append((degenerate == 0, f'{degenerate} degenerate of {len(faces)} triangles'))
        topology.append(_mesh_topology(len(vertices), faces))
        bounds.append(_mesh_bounds(vertices, faces))
    checks = []
    for identifier, observations in (('geometry', geometry), ('topology', topology), ('bounds', bounds)):
        checks.append(_result(identifier, all(ok for ok, _ in observations),
                              '. '.join(f'{level.upper()} {detail}' for level, (_, detail) in
                                        zip(levels, observations, strict=True)) + '.'))
    fine, coarse = counts
    checks.append(_result('lod-budget', 8 <= fine <= 64 and 4 <= coarse <= 32 and 2 * coarse <= fine,
                          f'LOD0 has {fine} triangles and LOD1 has {coarse} ({coarse / fine:.1%} of LOD0).'))
    return checks


def _mip_bytes(width, height, channels):
    total = width * height * channels
    while width != 1 or height != 1:
        width, height = max(1, width // 2), max(1, height // 2)
        total += width * height * channels
    return total


def _textures(submission):
    _object(submission, ('uvs', 'triangles', 'maps'))
    uvs = [_vector(v, 2, 16) for v in _array(submission['uvs'], 1, 128, 'UV coordinates')]
    faces = _indices(submission['triangles'], len(uvs))
    roles = {'base_color': 'srgb', 'normal': 'linear', 'orm': 'linear'}
    observed = Counter()
    wrong = []
    sizes = set()
    total = 0
    for tex in _array(submission['maps'], 1, 12, 'Map list'):
        _object(tex, ('role', 'space', 'width', 'height', 'channels'))
        role, space = tex['role'], tex['space']
        if type(role) is not str or role not in roles or space not in ('srgb', 'linear') or type(space) is not str:
            raise ValueError('Expected a base_color, normal or orm role and srgb or linear color space')
        width = _number(tex['width'], 1, 8192, 'Map width', integer=True)
        height = _number(tex['height'], 1, 8192, 'Map height', integer=True)
        channels = _number(tex['channels'], 1, 4, 'Channel count', integer=True)
        observed[role] += 1
        if roles[role] != space or channels < 3:
            wrong.append(f'{role} ({space}, {channels} channels)')
        sizes.add((width, height))
        total += _mip_bytes(width, height, channels)
    outside = sum(any(n < 0 or n > 1 for n in uv) for uv in uvs)
    degenerate = sum(_double_area(uvs, face) <= 1e-8 for face in faces)
    size_ok = len(sizes) == 1 and all(w == h and 128 <= w <= 1024 and w & (w - 1) == 0 for w, h in sizes)
    inventory = ', '.join(f'{observed[role]} {role}' for role in roles)
    return [
        _result('uv-bounds', outside == 0, f'{outside} of {len(uvs)} coordinates fall outside the unit tile.'),
        _result('uv-area', degenerate == 0, f'{degenerate} of {len(faces)} indexed UV triangles are degenerate.'),
        _result('map-metadata', not wrong and all(observed[k] == 1 for k in roles),
                f'Inventory contains {inventory}. Invalid color space or channel count on {", ".join(wrong) or "none"}.'),
        _result('resolution', size_ok, 'Submitted pixel dimensions are ' +
                ', '.join(f'{w}×{h}' for w, h in sorted(sizes)) + '.'),
        _result('memory', total <= 4 * 1024**2,
                f'Mip chains total {total} bytes against a 4194304-byte uncompressed budget.'),
    ]


def _identifier(value):
    if type(value) is not str or len(value) > 32 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', value):
        raise ValueError('Expected a joint identifier of 1–32 ASCII letters, digits, hyphens or underscores, starting with a letter')
    return value


def _animation(submission):
    _object(submission, ('joints', 'duration_s', 'tracks'))
    duration = _number(submission['duration_s'], 0.001, 60, 'Duration in seconds')
    joints = []
    for joint in _array(submission['joints'], 1, 32, 'Joint list'):
        _object(joint, ('name', 'parent'))
        parent = None if joint['parent'] is None else _identifier(joint['parent'])
        joints.append((_identifier(joint['name']), parent))
    parents = dict(joints)
    roots = [name for name, parent in joints if parent is None]
    unknown = sum(p is not None and p not in parents for _, p in joints)
    cyclic = set()
    for name in parents:
        visited = set()
        ancestor = name
        while ancestor in parents and ancestor not in visited:
            visited.add(ancestor)
            ancestor = parents[ancestor]
        if ancestor in visited:
            cyclic.add(name)
    repeated = len(joints) - len(parents)
    hierarchy_ok = len(joints) >= 2 and len(roots) == 1 and not (repeated or unknown or cyclic)
    track_counts = Counter()
    bad_timing = bad_loop = 0
    root_excursions, child_excursions, speeds = [], [], []
    unordered = False
    for track in _array(submission['tracks'], 1, 32, 'Track list'):
        _object(track, ('joint', 'keys'))
        joint = _identifier(track['joint'])
        track_counts[joint] += 1
        times, poses = [], []
        for key in _array(track['keys'], 1, 64, 'Key list'):
            _object(key, ('time_s', 'translation'))
            times.append(_number(key['time_s'], -60, 60, 'Key time in seconds'))
            poses.append(_vector(key['translation'], 3, 100))
        # Rest-relative translations are piecewise linear, so each segment has constant speed.
        ordered = True
        for i in range(1, len(times)):
            dt = times[i] - times[i - 1]
            if dt <= 0:
                ordered = False
            else:
                speeds.append(math.dist(poses[i - 1], poses[i]) / dt)
        unordered |= not ordered
        bad_timing += not (len(times) >= 2 and ordered and times[0] == 0 and times[-1] == duration)
        bad_loop += len(poses) < 2 or math.dist(poses[0], poses[-1]) > 0.01 + 1e-12
        if joint in roots:
            root_excursions.extend(math.hypot(*pose) for pose in poses)
        elif joint in parents and parents[joint] in parents:
            child_excursions.extend(math.dist(poses[0], pose) for pose in poses)
    missing = sum(name not in track_counts for name in parents)
    extra = sum(count for name, count in track_counts.items() if name not in parents)
    duplicate = sum(count - 1 for count in track_counts.values())
    peak_root = max(root_excursions, default=0)
    peak_child = max(child_excursions, default=0)
    peak_speed = max(speeds, default=0)
    root_sampled = len(roots) == 1 and track_counts[roots[0]] == 1
    return [
        _result('hierarchy', hierarchy_ok, f'{len(joints)} joints, {len(roots)} roots, {repeated} repeated names, '
                f'{unknown} unknown parents and {len(cyclic)} joints leading into a cycle.'),
        _result('coverage', not (missing or extra or duplicate),
                f'{missing} untracked joints, {extra} tracks for unknown joints and {duplicate} duplicate tracks.'),
        _result('timing', bad_timing == 0, f'{bad_timing} tracks have invalid sample order or incomplete coverage of 0–{duration:g} s.'),
        _result('loop', bad_loop == 0, f'{bad_loop} tracks lack a sample pair with matching endpoint offsets within 0.01 m.'),
        _result('root-motion', root_sampled and peak_root <= 0.02 + 1e-12,
                f'Maximum sampled root offset is {peak_root:.4g} m.' if root_sampled else 'A unique root and its single track are required.'),
        _result('motion', not unordered and peak_child + 1e-12 >= 0.02 and peak_speed <= 2 + 1e-12,
                f'Peak child excursion is {peak_child:.4g} m. Maximum measurable segment speed is {peak_speed:.4g} m/s. '
                f'{"Some time intervals are nonpositive." if unordered else "All time intervals are positive."}'),
    ]


def assess(exercise_id, submission):
    for identifier, evaluate in (('modeling', _modeling), ('textures', _textures), ('animation', _animation)):
        if exercise_id == identifier:
            return evaluate(submission)
    raise ValueError('Unknown studio asset exercise')
