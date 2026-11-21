"""Assess a small, declarative HUD layout and interaction map, not a rendered UI."""

import re
import unicodedata


EXERCISES = [{
    'id': 'interface', 'title': 'Accessible inventory HUD',
    'brief': 'Provide two target-resolution HUD layouts, focus navigation, keyboard and controller mappings, and feedback for empty/full/error inventory states. This checks declared geometry and colors, not rendered pixels or actual input devices.',
    'criteria': [
        {'id': 'layout', 'label': 'Widgets fit both declared screens without overlap'},
        {'id': 'contrast', 'label': 'Text reaches 4.5:1 contrast and 14px minimum'},
        {'id': 'focus', 'label': 'Every widget is reachable in both directions from initial focus'},
        {'id': 'controls', 'label': 'Each device has distinct required action bindings'},
        {'id': 'feedback', 'label': 'Empty, full and error states have distinct text feedback'},
    ],
    'example': {
        'screens': [
            {'width': 1280, 'height': 720, 'widgets': [
                {'id': 'items', 'rect': [40, 80, 560, 500], 'foreground': '#F5F5F5', 'background': '#222222', 'text_px': 18},
                {'id': 'close', 'rect': [40, 600, 170, 50], 'foreground': '#FFFFFF', 'background': '#254048', 'text_px': 18},
            ]},
            {'width': 640, 'height': 360, 'widgets': [
                {'id': 'items', 'rect': [20, 20, 600, 250], 'foreground': '#F5F5F5', 'background': '#222222', 'text_px': 16},
                {'id': 'close', 'rect': [20, 290, 150, 50], 'foreground': '#FFFFFF', 'background': '#254048', 'text_px': 16},
            ]},
        ],
        'navigation': {'start': 'items', 'edges': [['items', 'close'], ['close', 'items']]},
        'actions': {'keyboard': {'move': 'arrows', 'select': 'enter', 'back': 'escape', 'inventory': 'i'},
                    'controller': {'move': 'dpad', 'select': 'a', 'back': 'b', 'inventory': 'y'}},
        'states': {'empty': 'Inventory empty', 'full': 'Inventory full', 'error': 'Cannot use this item'},
    },
}]


def _obj(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError('Unexpected HUD object fields')
    return value


def _array(value, low, high):
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise ValueError('Invalid HUD array size')
    return value


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid HUD integer')
    return value


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value):
        raise ValueError('Invalid HUD identifier')
    return value


def _text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 120:
        raise ValueError('Invalid HUD feedback or binding')
    text = unicodedata.normalize('NFKC', value).strip().casefold()
    if not any(char.isprintable() and not char.isspace() and unicodedata.category(char)[0] not in ('M', 'C')
               for char in text):
        raise ValueError('HUD feedback and bindings must contain visible text')
    return text


def _luminance(hex_color):
    if not isinstance(hex_color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', hex_color):
        raise ValueError('Expected #RRGGBB color')
    channels = [int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722), strict=True))


def _ratio(foreground, background):
    a, b = sorted((_luminance(foreground), _luminance(background)))
    return (b + .05) / (a + .05)


def _reachable(start, adjacency):
    seen, pending = set(), [start]
    while pending:
        node = pending.pop()
        if node not in seen:
            seen.add(node)
            pending.extend(adjacency[node] - seen)
    return seen


def assess(exercise_id, submission):
    if exercise_id != 'interface':
        raise ValueError('Unknown HUD exercise')
    _obj(submission, ('screens', 'navigation', 'actions', 'states'))
    layouts, widget_sets, ratios, sizes, resolutions = [], [], [], [], set()
    for screen in _array(submission['screens'], 2, 4):
        _obj(screen, ('width', 'height', 'widgets'))
        width, height = (_integer(screen[k], 1, 8192) for k in ('width', 'height'))
        resolutions.add((width, height))
        ids, rects, text_fits = set(), [], []
        for widget in _array(screen['widgets'], 2, 40):
            _obj(widget, ('id', 'rect', 'foreground', 'background', 'text_px'))
            identifier = _name(widget['id'])
            if identifier in ids:
                raise ValueError('Duplicate HUD widget ID')
            ids.add(identifier)
            x, y, w, h = (_integer(v, -8192, 16384) for v in _array(widget['rect'], 4, 4))
            rects.append((x, y, w, h))
            ratios.append(_ratio(widget['foreground'], widget['background']))
            size = _integer(widget['text_px'], 1, 256)
            sizes.append(size)
            text_fits.append(w >= size and h >= size)
        widget_sets.append(ids)
        fit = all(x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height for x,y,w,h in rects)
        overlaps = any(x < u + a and u < x + w and y < v + b and v < y + h
                       for index, (x,y,w,h) in enumerate(rects) for u,v,a,b in rects[index+1:])
        layouts.append(fit and not overlaps and all(text_fits))
    consistent = all(ids == widget_sets[0] for ids in widget_sets)
    valid_layout = all(layouts) and len(resolutions) == len(layouts) and consistent

    navigation = _obj(submission['navigation'], ('start', 'edges'))
    start = _name(navigation['start'])
    widgets = widget_sets[0]
    edges = [tuple(_name(x) for x in _array(edge, 2, 2)) for edge in _array(navigation['edges'], 0, 160)]
    linked = start in widgets and all(a in widgets and b in widgets for a, b in edges)
    reachable = set()
    if linked:
        forward = {node: set() for node in widgets}
        backward = {node: set() for node in widgets}
        for a, b in edges:
            forward[a].add(b)
            backward[b].add(a)
        reachable = _reachable(start, forward) & _reachable(start, backward)
    actions = _obj(submission['actions'], ('keyboard', 'controller'))
    unique = []
    for device in actions.values():
        _obj(device, ('move', 'select', 'back', 'inventory'))
        unique.append(len({_text(binding) for binding in device.values()}) == 4)
    states = submission['states']
    if not isinstance(states, dict) or not set(states) <= {'empty', 'full', 'error'}:
        raise ValueError('Invalid inventory states')
    feedback = {_text(value) for value in states.values()}
    return [
        dict(id='layout', status='pass' if valid_layout else 'fail',
             detail=f'{sum(layouts)}/{len(layouts)} layouts fit without overlap and with room for text; {len(resolutions)} unique resolutions; consistent widget IDs: {consistent}.'),
        dict(id='contrast', status='pass' if min(ratios) >= 4.5 and min(sizes) >= 14 else 'fail',
             detail=f'Minimum declared contrast {min(ratios):.2f}:1; smallest text {min(sizes)}px.'),
        dict(id='focus', status='pass' if consistent and reachable == widgets else 'fail',
             detail=f'{len(reachable)}/{len(widgets)} widgets reachable from and back to initial focus.'),
        dict(id='controls', status='pass' if all(unique) else 'fail',
             detail=f'{sum(unique)}/2 devices have four distinct required bindings.'),
        dict(id='feedback', status='pass' if len(feedback) == 3 else 'fail',
             detail=f'{len(feedback)}/3 distinct required feedback messages.'),
    ]
