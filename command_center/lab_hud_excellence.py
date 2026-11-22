"""Measure a synthetic contextual HUD and replay two physical input maps through its menus."""

from itertools import combinations

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer
from .lab_interface import _ratio


TRACK = {
    'id': 'hud-excellence', 'title': 'HUD hierarchy, handheld layout and controller menus',
    'roles': ['ui', 'gameplay', 'content', 'verification'],
    'workflow': [
        'Write the immediate decision for each view. A first-person player needs status near the edge of the '
        'action. A strategy player needs selection, cost and queue state together. An RPG player comparing '
        'items needs the equipped baseline, the changed attribute and the cost of committing.',
        'Distinguish persistent, contextual and interrupting information. Give warnings a label and a shape. '
        'Keep the play space visible, suppress expired prompts and retain urgent information in a compact HUD.',
        'Anchor to safe areas and test normal and enlarged type on a 1280×720 handheld layout. Allow text '
        'to wrap or reflow, and test the longest translations with actual fonts over bright and dark scenes.',
        'Design keyboard and controller navigation together. Show a visible focus indicator, own focus while '
        'a dialog is open and restore it to the opener on return. Derive prompts from the active device and '
        'binding. Test successful actions, unavailable actions, remap conflicts and restoring defaults.',
    ],
    'deliverables': [
        'A state-by-state HUD inventory, priority and visibility rules, enlarged layouts, and an annotated capture '
        'of each representative player decision.',
        'Focus map, default and remapped input tables, feedback copy, accessibility settings and an input replay.',
    ],
    'verification': [
        'Check safe bounds, text fit, panel collisions, focus contrast and reachability. Replay with a controller '
        'alone and a keyboard alone through settings, a nested menu, a failed action and recovery.',
        'Use a real handheld to inspect gameplay text, icon shapes, focus and overlay timing at viewing distance. '
        'Recheck saved preferences after restart. Declare which device, build, language and settings were used.',
    ],
    'exercise': 'Build a compact signal-station HUD and operate its display settings with remapped controls.',
}

_STATES = {
    'travel': ('status', 'route'), 'console': ('status', 'use'), 'alarm': ('status', 'route', 'warning'),
    'compact-alarm': ('status', 'warning'), 'pause': ('resume', 'settings'), 'options': ('size', 'compact', 'return'),
}
_WIDGETS = tuple(dict.fromkeys(key for group in _STATES.values() for key in group))
_ACTIONS = ('menu', 'down', 'up', 'confirm', 'back')
_DEVICES = ('keyboard', 'controller')
_INPUTS = {'keyboard': ('esc', 'tab', 'enter', 'space', 'backspace', 'up', 'down', 'w', 's', 'e', 'q'),
           'controller': ('menu', 'view', 'south', 'east', 'west', 'north', 'dpad-up', 'dpad-down', 'lb', 'rb')}
_PROFILES = ((1280, 720, 100), (1280, 720, 150), (1920, 1080, 100))
_FEEDBACK = {'applied': (('Applied', 'Settings saved'), ('check', 'tick')),
             'blocked': (('Unavailable', 'Action blocked'), ('lock', 'stop'))}


def _widget(label, corner, margin, size):
    return {'label': label, 'corner': corner, 'offset': margin, 'size': size, 'glyph_px': 16}


def _input_map(keys, alternate):
    default = dict(zip(_ACTIONS, keys, strict=True))
    active = dict(default, confirm=alternate)
    return {'default': default, 'active': active, 'confirm_prompt': alternate,
            'trace': [active[k] for k in ('menu', 'down', 'confirm', 'confirm', 'down', 'confirm', 'back', 'up', 'confirm')]}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Operate a signal station from a handheld',
    'brief': 'Use the named widget slots and visible sets in the example. The route is optional during an alarm '
             'and must disappear in compact mode; the status and warning stay. Only pause and options contain '
             'focusable controls. Each widget has a printable ASCII label (1–32 characters), physical corner, inward '
             'offset [x,y], base size [width,height] and base glyph height. Use exact pixels at 1280×720 and '
             'scale for 1920×1080 by height. At enlarged handheld type, grow the box and glyphs to 150% while '
             'retaining their anchors. Round each scaled dimension up. Leave 4% safe space per edge and '
             'reserve 8px of base padding at each edge inside the box. Each fixture character advances '
             'ceil(glyph height × 0.6). Keep base glyph height at least 14px. Test text against opaque plates '
             'at 4.5:1 (7:1 in high contrast), and focus against each plate at 3:1. Pair Applied/Settings saved '
             'with check/tick, and Unavailable/Action blocked with lock/stop. Specify Up and Down links for '
             'each menu control. Start pause on resume, start options on size, and restore settings on return. '
             'Provide unique physical bindings per device, change confirm, and name its updated prompt. Keyboard '
             'keys: esc, tab, enter, space, backspace, up, down, w, s, e, q. Controller: menu, view, south, east, '
             'west, north, dpad-up, dpad-down, lb, rb. Replay 1–32 active inputs per device. Open pause, enter '
             'settings, enable enlarged type and compact HUD, return to the opener and resume. The trace starts '
             'from play with both settings off. This measures fixture geometry, declared swatches and input state.',
    'criteria': [
        {'id': 'context', 'label': 'Keep the relevant state cues visible and remove stale or lower-priority overlays.'},
        {'id': 'layout', 'label': 'Fit each simultaneous set within the safe area without overlapping controls.'},
        {'id': 'type-fit', 'label': 'Keep the synthetic text line readable and contained at every declared scale.'},
        {'id': 'contrast-feedback', 'label': 'Meet palette targets and distinguish applied and blocked feedback without color.'},
        {'id': 'menu-focus', 'label': 'Reach every control and return within its own menu using directional navigation.'},
        {'id': 'remap', 'label': 'Provide distinct controls and display the new confirm binding on both devices.'},
        {'id': 'state-replay', 'label': 'Enable both options, restore the opener and resume via both active input maps.'},
    ],
    'example': {
        'widgets': {
            'status': _widget('Relay online', 'tl', [60, 40], [160, 40]),
            'route': _widget('West gantry', 'br', [60, 50], [160, 40]),
            'use': _widget('Open console', 'bl', [60, 50], [180, 40]),
            'warning': _widget('Pressure critical', 'tr', [60, 40], [240, 44]),
            'resume': _widget('Resume', 'tl', [100, 120], [220, 40]),
            'settings': _widget('Display settings', 'tl', [100, 210], [220, 40]),
            'size': _widget('Large text', 'tl', [100, 120], [220, 40]),
            'compact': _widget('Compact HUD', 'tl', [100, 210], [220, 40]),
            'return': _widget('Return', 'tl', [100, 300], [220, 40]),
        },
        'visible': {k: list(v) for k, v in _STATES.items()},
        'palettes': {'default': {'text': '#EDF3F5', 'plate': '#252C32', 'focus': '#F5BE67'},
                     'high-contrast': {'text': '#FFFFFF', 'plate': '#090909', 'focus': '#FFDE66'}},
        'feedback': {'applied': {'text': 'Settings saved', 'symbol': 'check'},
                     'blocked': {'text': 'Action blocked', 'symbol': 'stop'}},
        'focus': {'initial': {'pause': 'resume', 'options': 'size'}, 'restore': 'settings',
                  'links': {'resume': {'up': 'settings', 'down': 'settings'}, 'settings': {'up': 'resume', 'down': 'resume'},
                            'size': {'up': 'return', 'down': 'compact'}, 'compact': {'up': 'size', 'down': 'return'},
                            'return': {'up': 'compact', 'down': 'size'}}},
        'devices': {'keyboard': _input_map(('esc', 'down', 'up', 'enter', 'backspace'), 'space'),
                    'controller': _input_map(('menu', 'dpad-down', 'dpad-up', 'south', 'east'), 'west')},
    },
}]


def _pair(value, low, high, name):
    _array(value, 2, 2, name)
    for item in value:
        _integer(item, low, high, name)


def _label(value):
    if type(value) is not str or not 1 <= len(value) <= 32 or not value.isascii() or not value.isprintable() or not value.strip():
        raise ValueError('A fixture label needs 1–32 printable ASCII characters.')


def _scale(px, height, percent=100):
    return (px * height * percent + 71999) // 72000


def _rectangle(widget, width, height, percent):
    x, y = (_scale(px, height) for px in widget['offset'])
    w, h = (_scale(px, height, percent) for px in widget['size'])
    glyph = _scale(widget['glyph_px'], height, percent)
    padding = _scale(8, height, percent)
    advance = (glyph * 6 + 9) // 10
    fits = len(widget['label']) * advance + 2 * padding <= w and glyph + 2 * padding <= h
    if widget['corner'][1] == 'r':
        x = width - x - w
    if widget['corner'][0] == 'b':
        y = height - y - h
    return (x, y, x + w, y + h), fits


def _layout(widgets, visible):
    _object(widgets, _WIDGETS, 'widgets')
    _object(visible, _STATES, 'visible')
    for widget in widgets.values():
        _object(widget, ('label', 'corner', 'offset', 'size', 'glyph_px'), 'widget')
        _label(widget['label'])
        _choice(widget['corner'], ('tl', 'tr', 'bl', 'br'), 'corner')
        _pair(widget['offset'], 0, 4096, 'offset')
        _pair(widget['size'], 1, 4096, 'size')
        _integer(widget['glyph_px'], 1, 128, 'glyph_px')
    wrong_states = []
    for state, ids in visible.items():
        _array(ids, 0, len(widgets), 'visible widgets')
        for key in ids:
            _choice(key, widgets, 'visible widget')
        wanted = set(_STATES[state])
        correct = set(ids) == wanted or (state == 'alarm' and set(ids) == wanted - {'route'})
        if len(ids) != len(set(ids)) or not correct:
            wrong_states.append(state)
    geometry, text = [], []
    for width, height, percent in _PROFILES:
        rects = {}
        for key, widget in widgets.items():
            rects[key], fits = _rectangle(widget, width, height, percent)
            if not fits or widget['glyph_px'] < 14:
                text.append(f'{key} at {width}×{height}/{percent}%')
        for state, ids in visible.items():
            boxes = [rects[key] for key in ids]
            clipped = any(25*x < width or 25*y < height or 25*r > 24*width or 25*b > 24*height for x,y,r,b in boxes)
            overlaps = any(x < rr and xx < r and y < bb and yy < b for (x,y,r,b),(xx,yy,rr,bb) in combinations(boxes, 2))
            if clipped or overlaps:
                geometry.append(f'{state} at {width}×{height}/{percent}%')
    return [
        _check('context', not wrong_states, 'Unexpected visibility in: ' + (', '.join(wrong_states) or 'none') + '.'),
        _check('layout', not geometry, 'Safe-area or overlap failures: ' + (', '.join(geometry[:3]) or 'none') + '.'),
        _check('type-fit', not text, 'Fixture text or base glyph failures: ' + (', '.join(text[:3]) or 'none') + '.'),
    ]


def _presentation(palettes, feedback):
    _object(palettes, ('default', 'high-contrast'), 'palettes')
    details = []
    for mode, threshold in (('default', 4.5), ('high-contrast', 7)):
        swatch = palettes[mode]
        _object(swatch, ('text', 'plate', 'focus'), 'palette')
        text, focus = (_ratio(swatch[key], swatch['plate']) for key in ('text', 'focus'))
        if text < threshold or focus < 3:
            details.append(f'{mode} text {text:.3f}:1 and focus {focus:.3f}:1')
    _object(feedback, _FEEDBACK, 'feedback')
    for state, (labels, symbols) in _FEEDBACK.items():
        cue = feedback[state]
        _object(cue, ('text', 'symbol'), 'feedback cue')
        _label(cue['text'])
        _identifier(cue['symbol'], 'symbol')
        if cue['text'] not in labels or cue['symbol'] not in symbols:
            details.append(f'{state} label or symbol disagrees with its outcome')
    return _check('contrast-feedback', not details, '. '.join(details) or 'Both swatch sets and feedback pairs meet the fixture targets.')


def _menu_focus(focus, visible):
    _object(focus, ('initial', 'restore', 'links'), 'focus')
    _object(focus['initial'], ('pause', 'options'), 'initial focus')
    _identifier(focus['restore'], 'restore')
    controls = (*_STATES['pause'], *_STATES['options'])
    _object(focus['links'], controls, 'focus links')
    for links in focus['links'].values():
        _object(links, ('up', 'down'), 'directions')
        for dest in links.values():
            _identifier(dest, 'focus destination')
    failures = []
    for menu, initial in (('pause', 'resume'), ('options', 'size')):
        _identifier(focus['initial'][menu], 'initial control')
        members = set(_STATES[menu])
        if focus['initial'][menu] != initial or set(visible[menu]) != members:
            failures.append(menu)
            continue
        for start in members:
            visited, todo = set(), [start]
            while todo:
                key = todo.pop()
                if key not in members or key in visited:
                    continue
                visited.add(key)
                todo.extend(focus['links'][key].values())
            if visited != members or not set(focus['links'][start].values()) <= members:
                failures.append(menu)
                break
    return _check('menu-focus', not failures and focus['restore'] == 'settings',
                  f'Menu focus failures: {", ".join(failures) or "none"}. Return target: {focus["restore"]}.')


def _replay(device, focus, visible):
    actions = {key: action for action, key in device['active'].items()}
    screen, current = 'play', None
    large = compact = restored = resumed = False
    for key in device['trace']:
        if screen != 'play' and current not in visible[screen]:
            return False
        action = actions.get(key)
        if screen == 'play' and action == 'menu':
            screen, current = 'pause', focus['initial']['pause']
            resumed = False
        elif screen in ('pause', 'options') and action in ('up', 'down') and current in _STATES[screen]:
            current = focus['links'][current][action]
        elif screen == 'pause' and current == 'settings' and action == 'confirm':
            screen, current = 'options', focus['initial']['options']
        elif screen == 'options' and action == 'confirm' and current in ('size', 'compact'):
            if current == 'size':
                large = not large
            else:
                compact = not compact
        elif screen == 'options' and (action == 'back' or (current == 'return' and action == 'confirm')):
            screen, current = 'pause', focus['restore']
            restored |= current == 'settings'
        elif screen == 'pause' and (action == 'back' or (current == 'resume' and action == 'confirm')):
            screen, current = 'play', None
            resumed = action == 'confirm'
        else:
            return False
    return screen == 'play' and large and compact and restored and resumed


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown HUD excellence exercise.')
    _object(submission, ('widgets', 'visible', 'palettes', 'feedback', 'focus', 'devices'), 'HUD submission')
    checks = _layout(submission['widgets'], submission['visible'])
    checks.append(_presentation(submission['palettes'], submission['feedback']))
    focus = submission['focus']
    checks.append(_menu_focus(focus, submission['visible']))
    _object(submission['devices'], _DEVICES, 'devices')
    stale, incomplete = [], []
    for name in _DEVICES:
        device = submission['devices'][name]
        _object(device, ('default', 'active', 'confirm_prompt', 'trace'), name)
        distinct = True
        for mapping in (device['default'], device['active']):
            _object(mapping, _ACTIONS, 'bindings')
            for key in mapping.values():
                _choice(key, _INPUTS[name], 'physical input')
            distinct &= len(set(mapping.values())) == len(_ACTIONS)
        _choice(device['confirm_prompt'], _INPUTS[name], 'confirm prompt')
        _array(device['trace'], 1, 32, 'input trace')
        for key in device['trace']:
            _choice(key, _INPUTS[name], 'trace input')
        active = device['active']['confirm']
        if not distinct or active == device['default']['confirm'] or device['confirm_prompt'] != active:
            stale.append(name)
        if not distinct or not _replay(device, focus, submission['visible']):
            incomplete.append(name)
    return checks + [
        _check('remap', not stale, 'Conflicting bindings or stale confirm prompts: ' + (', '.join(stale) or 'none') + '.'),
        _check('state-replay', not incomplete, 'Incomplete settings-and-resume traces: ' + (', '.join(incomplete) or 'none') + '.'),
    ]
