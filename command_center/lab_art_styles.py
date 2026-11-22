"""Compare indexed composition studies and the modeled cost of two versions of a kit."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _integer
from .lab_interface import _luminance, _ratio


_ID = 'art-styles'
_TIERS = ('full', 'handheld')
_ROLES = {'.': 'wall', '#': 'truss', '@': 'signal'}
_LIGHTS = ('day', 'dusk')

TRACK = {
    'id': _ID, 'title': 'Art styles and a cohesive visual language',
    'roles': ['content', 'ui', 'gameplay', 'verification'],
    'workflow': [
        'Compare photorealistic and semi-realistic surfaces with stylized, painterly and cel-shaded '
        'treatments of the same landmark. Record which details establish function and which the style can simplify.',
        'Build low-poly and pixel-art silhouette studies. For retro direction, choose particular display or '
        'palette constraints. Combine an industrial setting or horror mood with the chosen rendering treatment.',
        'Set a palette with named gameplay roles, a small material library and lighting rules. Test the focal '
        'silhouette and negative space against nearby scenery in wide and close views at delivery size.',
        'Preserve the scene’s identifying features in a lower-cost kit. Project triangle and texture costs, '
        'then profile the visible scene on the target device. Read presentation_studies/ART_STYLES.md for sources.',
    ],
    'deliverables': [
        'A one-page style brief, credited reference notes, silhouette sheet and original material swatches in two lights.',
        'Matched compositions for the full and handheld kits, geometry and atlas totals, and target-device captures.',
    ],
    'verification': [
        'Compare palette roles, material response, adjacent silhouette contrasts and composition under both lights.',
        'Profile real frame time and memory. Inspect moving edges, filtering, exposure and visibility on the device.',
    ],
    'exercise': 'Reduce a cel-shaded pumping station kit for handheld while preserving its signal landmark.',
}


def _material(swatch, roughness, triangles, copies):
    return dict(swatch=swatch, bands=3, roughness=roughness, triangles=triangles, copies=copies)


EXERCISES = [{
    'id': _ID, 'title': 'Keep the pump signal visible on handheld',
    'brief': (
        'Author full and handheld versions of one industrial cel-shaded kit. Choose 2–5 shade bands for '
        'every surface. Supply 3–8 named swatches with opaque #RRGGBB colors in day and dusk. Assign distinct '
        'swatches (different day/dusk color pairs) to wall, truss and signal and preserve each assignment across tiers. In this brief the full '
        'and handheld signal finishes each have roughness at least 25 percentage points below the wall. '
        'Keep each role’s roughness within eight points of its full counterpart. Draw equal-sized 6–24 cell '
        'wide and high thumbnails using dot for wall, # for truss and @ for signal. Include all three. The '
        'signal occupies at least four four-connected cells, clears every frame edge by a cell, and its centroid '
        '(using cell centers) falls between 50% and 80% of width and in the top 65% of height. The two '
        'signal masks overlap by at least 75% of their union. Every horizontally or vertically adjoining '
        'signal/background pair needs at least 3:1 relative-luminance contrast in both lights for this '
        'fixture. Hold each role’s placed copy count constant. Sum triangles per copy × copies and compute '
        'one shared uncompressed RGBA8 atlas at width × height × 4 bytes per tier, without mipmaps. Predict '
        'both totals for both tiers. Handheld must reduce both costs and fit 6000 triangles and 262144 bytes.'
    ),
    'criteria': [
        {'id': 'palette', 'label': 'Keep three distinct swatch roles stable between the two kits.'},
        {'id': 'materials', 'label': 'Preserve shade bands, finish separation and cross-tier roughness.'},
        {'id': 'composition', 'label': 'Keep each connected signal visible in the intended part of the frame.'},
        {'id': 'silhouette', 'label': 'Preserve at least three quarters of the union of the matched signal masks.'},
        {'id': 'lighting', 'label': 'Retain the required edge contrast under both lighting conditions.'},
        {'id': 'device-budget', 'label': 'Retain the instance counts while reducing geometry and atlas cost within budget.'},
        {'id': 'cost-predictions', 'label': 'Predict triangle and resident atlas byte counts for each tier.'},
    ],
    'example': {
        'bands': 3, 'palette': {
            'slate': {'day': '#465565', 'dusk': '#263647'},
            'oxide': {'day': '#554137', 'dusk': '#3D3031'},
            'ochre': {'day': '#FFD77A', 'dusk': '#F4BD72'},
        },
        'full': {
            'kit': {'wall': _material('slate', 84, 420, 8), 'truss': _material('oxide', 64, 600, 9),
                    'signal': _material('ochre', 30, 2450, 1)},
            'atlas': [512, 512], 'triangles': 11210, 'atlas_bytes': 1048576,
            'thumbnail': ['..........', '......@@..', '..##.@@@..', '...##.@@..', '...####...', '........##'],
        },
        'handheld': {
            'kit': {'wall': _material('slate', 82, 220, 8), 'truss': _material('oxide', 65, 310, 9),
                    'signal': _material('ochre', 35, 1200, 1)},
            'atlas': [256, 256], 'triangles': 5750, 'atlas_bytes': 262144,
            'thumbnail': ['..........', '......@@..', '..##..@@..', '...##.@@..', '...####...', '........##'],
        },
    },
}]


def _read(data):
    _object(data, ('bands', 'palette', *_TIERS), 'Style study')
    _integer(data['bands'], 2, 5, 'Shade bands')
    palette = data['palette']
    if type(palette) is not dict or not 3 <= len(palette) <= 8:
        raise ValueError('Use three to eight named palette swatches.')
    for name, swatch in palette.items():
        _identifier(name, 'Swatch ID')
        _object(swatch, _LIGHTS, 'Swatch')
        for color in swatch.values():
            _luminance(color)
    for tier in _TIERS:
        variant = data[tier]
        _object(variant, ('kit', 'thumbnail', 'atlas', 'triangles', 'atlas_bytes'), tier)
        _object(variant['kit'], _ROLES.values(), 'Kit')
        for mat in variant['kit'].values():
            _object(mat, ('swatch', 'bands', 'roughness', 'triangles', 'copies'), 'Material and geometry')
            _identifier(mat['swatch'], 'Material swatch')
            if mat['swatch'] not in palette:
                raise ValueError('Unresolved material swatch.')
            for key, lo, hi in [('bands', 1, 32), ('roughness', 0, 100), ('triangles', 1, 100000), ('copies', 1, 128)]:
                _integer(mat[key], lo, hi, key)
        grid = variant['thumbnail']
        _array(grid, 6, 24, 'thumbnail')
        for row in grid:
            if (type(row) is not str or not 6 <= len(row) <= 24 or len(row) != len(grid[0])
                    or any(cell not in _ROLES for cell in row)):
                raise ValueError('Use equal-width thumbnail rows of 6–24 cells drawn from ., # and @.')
        _array(variant['atlas'], 2, 2, 'Atlas dimensions')
        for side in variant['atlas']:
            _integer(side, 1, 4096, 'Atlas side')
        _integer(variant['triangles'], 0, 38400000, 'Predicted triangles')
        _integer(variant['atlas_bytes'], 0, 67108864, 'Predicted atlas bytes')


def _neighbors(x, y):
    return ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))


def _study(grid, kit, palette):
    height, width = len(grid), len(grid[0])
    mask = {(x, y) for y, row in enumerate(grid) for x, cell in enumerate(row) if cell == '@'}
    count = len(mask)
    if not count:
        return mask, False, 0.0
    connected, pending = set(), [next(iter(mask))]
    while pending:
        point = pending.pop()
        if point not in connected:
            connected.add(point)
            pending.extend(p for p in _neighbors(*point) if p in mask and p not in connected)
    twice_x = sum(2 * x + 1 for x, y in mask)
    twice_y = sum(2 * y + 1 for x, y in mask)
    composed = (len(connected) == count and count >= 4 and set(''.join(grid)) == _ROLES.keys()
                and all(0 < x < width - 1 and 0 < y < height - 1 for x, y in mask)
                and 50 * 2 * count * width <= 100 * twice_x <= 80 * 2 * count * width
                and 100 * twice_y <= 65 * 2 * count * height)
    adjacent = {grid[ny][nx] for x, y in mask for nx, ny in _neighbors(x, y)
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in mask}
    signal = palette[kit['signal']['swatch']]
    weakest = min((_ratio(signal[light], palette[kit[_ROLES[cell]]['swatch']][light])
                   for cell in adjacent for light in _LIGHTS), default=0.0)
    return mask, composed, weakest


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown art styles exercise.')
    _read(submission)
    full, handheld = (submission[name] for name in _TIERS)
    kits = (full['kit'], handheld['kit'])
    roles = _ROLES.values()
    role_colors = {tuple(submission['palette'][kits[0][r]['swatch']][light].upper() for light in _LIGHTS)
                   for r in roles}
    palette_ok = (len(role_colors) == len(_ROLES)
                  and all(kits[0][r]['swatch'] == kits[1][r]['swatch'] for r in roles))
    gaps = [kit['wall']['roughness'] - kit['signal']['roughness'] for kit in kits]
    shifts = [abs(kits[0][r]['roughness'] - kits[1][r]['roughness']) for r in roles]
    bands_ok = all(mat['bands'] == submission['bands'] for kit in kits for mat in kit.values())
    a, b = full['thumbnail'], handheld['thumbnail']
    mask_a, composed_a, contrast_a = _study(a, kits[0], submission['palette'])
    mask_b, composed_b, contrast_b = _study(b, kits[1], submission['palette'])
    same_frame = (len(a), len(a[0])) == (len(b), len(b[0]))
    overlap, union = len(mask_a & mask_b), len(mask_a | mask_b)
    tris, resident, errors = [], [], []
    for name in _TIERS:
        tier = submission[name]
        tris.append(sum(m['copies'] * m['triangles'] for m in tier['kit'].values()))
        resident.append(tier['atlas'][0] * tier['atlas'][1] * 4)
        if (tier['triangles'], tier['atlas_bytes']) != (tris[-1], resident[-1]):
            errors.append(name)
    copies_ok = all(kits[0][r]['copies'] == kits[1][r]['copies'] for r in roles)
    costs_ok = tris[1] <= 6000 and resident[1] <= 262144 and tris[1] < tris[0] and resident[1] < resident[0]
    return [
        _check('palette', palette_ok, f'Three distinct and stable material-to-swatch assignments={palette_ok}.'),
        _check('materials', bands_ok and min(gaps) >= 25 and max(shifts) <= 8,
               f'Shade bands match={bands_ok}. Wall/signal gaps {gaps} points. Largest tier shift {max(shifts)}.'),
        _check('composition', composed_a and composed_b, f'Composed signal in full={composed_a}, handheld={composed_b}.'),
        _check('silhouette', same_frame and union > 0 and overlap * 4 >= union * 3,
               f'Matched framing={same_frame}. Signal masks share {overlap} of {union} union cells.'),
        _check('lighting', min(contrast_a, contrast_b) >= 3,
               f'Weakest signal edge across both lights is {contrast_a:.3f}:1 full and {contrast_b:.3f}:1 handheld.'),
        _check('device-budget', costs_ok and copies_ok,
               f'Triangles {tris}, RGBA8 bytes {resident}, matching placed counts={copies_ok}. Full then handheld.'),
        _check('cost-predictions', not errors, f'Incorrect geometry or atlas predictions for {errors}.'),
    ]
