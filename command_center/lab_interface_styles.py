"""Compare two original HUD compositions and replay a timed profile preview."""

from itertools import combinations

from .lab_design import _array, _check, _object
from .lab_gameplay import _choice, _integer
from .lab_hud_excellence import _label
from .lab_interface import _ratio


TRACK = {
    'id': 'interface-styles', 'title': 'HUD and menu art direction across play styles',
    'roles': ['ui', 'content', 'gameplay', 'verification'],
    'workflow': [
        'Start from the player’s decision. In a minimal HUD, reveal ordinary status on request and interrupt for '
        'urgent changes. On a diegetic instrument, check its angle and occlusion, then supply an equivalent '
        'screen-space or spoken reading when the player cannot see the instrument.',
        'Compose a tactical panel around a small group of related readings. For strategy, bind costs and queues '
        'to the current selection. For an RPG comparison, keep the equipped baseline and candidate changes '
        'side by side. Write down what can be collapsed without losing the next decision.',
        'Choose how a menu looks and how it reads. A retro grid needs legible pixel lettering and distinguishable '
        'selected, unavailable and focused states. A modern card layout needs clear grouping and enough space '
        'for long labels. Keep semantic names consistent across presentations.',
        'Build two deliberately different compositions. Measure their footprints and hierarchy at handheld size. '
        'Derive directional navigation from visible arrangement. Preview a style, cancel during its transition, '
        'apply it, then reopen with a controller. Provide a reduced-motion path with the same actions.',
    ],
    'deliverables': [
        'Two original HUD and menu studies for the same task, annotated with information priority, visibility '
        'rules, fallback channels, grouping and handheld measurements.',
        'Normal and reduced-motion transition traces, focus order for each layout, and real-device views of '
        'the resting, critical, preview, canceled and applied states.',
    ],
    'verification': [
        'Check the urgent message in both layouts and when the world object leaves view. Compare control '
        'order with screen positions. Test changing styles with enlargement, remapped input and motion reduced.',
        'Inspect the rendered type, real palette over gameplay, readability in motion, sound or narration '
        'alternatives and return focus on hardware. Keep those observations separate from the fixture results.',
    ],
    'exercise': 'Present one balloon survey as a wearable dial and a dispatch chart, then preview and switch between them.',
}

_STYLES = ('dial', 'chart')
_PICKER = ('dial', 'chart', 'exit')
_FRAMES = {
    'dial': {'survey': ('charge',), 'critical': ('charge', 'alert'), 'obscured': ('backup',), 'picker': _PICKER},
    'chart': {'survey': ('charge', 'route', 'queue'), 'critical': ('charge', 'route', 'alert'),
              'obscured': ('alert',), 'picker': _PICKER},
}
_ACTIONS = ('menu', 'up', 'down', 'left', 'right', 'confirm', 'back', 'wait')


def _card(x, y, w, h, glyph, mount='screen'):
    return {'rect': [x, y, w, h], 'glyph_px': glyph, 'mount': mount}


def _profile(style, cards, plate, text, focus):
    return {'cards': cards, 'order': list(_PICKER), 'states': {s: list(v) for s, v in _FRAMES[style].items()},
            'palette': {'plate': plate, 'text': text, 'focus': focus}}


def _step(delay, key, screen, style, focus, moving=False):
    return {'dt_ms': delay, 'key': key, 'after': [screen, style, focus, moving]}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Change the balloon survey display in flight',
    'brief': 'Compose two 1280×720 profiles using integer [x,y,width,height] rectangles and the example’s '
             'named label slots and state inventories. The dial mounts charge and alert on the instrument, '
             'within the left third; its obscured backup repeats the alert on screen. The chart groups its '
             'survey and critical readings in the bottom third. All picker controls use screen space. Leave '
             '32px horizontal and 24px vertical safe margins. Permit touching edges and reuse regions across '
             'exclusive states. Fit each single-line ASCII label at 14px or larger with 8px padding on every '
             'side and fixed character advance ceil(0.6 × glyph height). Use a warning at least 4px larger '
             'than charge, including the dial backup. Chart charge must be at least as large as route and queue. '
             'Text/plate contrast must reach 4.5:1 and focus/plate 3:1. Pair Heat critical or Vent needed with '
             'thermometer or vent-alert. Stack the dial picker vertically and lay out the chart picker '
             'horizontally; their perpendicular spans must share a common interval. Declare the visible focus '
             'order. D-pad arrows move one item on the corresponding axis and wrap. Confirm on a style opens '
             'its preview. Back cancels to the opener; confirm applies immediately. Back or confirming exit '
             'closes the picker. Menu reopens on the applied style. Each trace starts in play on dial. '
             'Each after tuple predicts screen, applied style, focus (none in play, apply in preview), and '
             'whether the preview is still animating. Elapse dt_ms before applying that input. Standard glide '
             'lasts 1–500ms; reduced motion has zero duration. In standard mode cancel during a moving '
             'preview, revisit it, wait to the end, apply chart, navigate both axes and reopen to verify it. '
             'In reduced mode immediately apply chart with zero delay after opening the preview. Finish both '
             'traces back in play. Unsupported inputs fail the trace.',
    'criteria': [
        {'id': 'composition', 'label': 'Give the two styles different information density, placement and mount behavior.'},
        {'id': 'fit', 'label': 'Fit visible cards and their label lines inside handheld bounds without overlap.'},
        {'id': 'hierarchy', 'label': 'Keep the urgent reading prominent, legible and meaningful when the dial leaves view.'},
        {'id': 'picker-order', 'label': 'Match controller traversal order to a vertical column and a horizontal row.'},
        {'id': 'preview', 'label': 'Predict cancel, settle, apply and restored focus through the animated style switch.'},
        {'id': 'reduced-motion', 'label': 'Apply the same choice immediately with the preview motion disabled.'},
    ],
    'example': {
        'labels': {'charge': 'Lift charge', 'alert': 'Vent needed', 'route': 'North ridge', 'queue': '3 surveys',
                   'dial': 'Pocket dial', 'chart': 'Survey chart', 'exit': 'Return to flight'},
        'alert_symbol': 'vent-alert',
        'profiles': {
            'dial': _profile('dial', {
                'charge': _card(52, 94, 180, 46, 17, 'instrument'), 'alert': _card(52, 156, 260, 54, 23, 'instrument'),
                'backup': _card(850, 40, 310, 54, 23), 'dial': _card(64, 170, 250, 50, 18),
                'chart': _card(64, 245, 250, 50, 18), 'exit': _card(64, 320, 250, 50, 18),
            }, '#1E2E30', '#E5F3EF', '#F8D888'),
            'chart': _profile('chart', {
                'charge': _card(56, 520, 230, 56, 20), 'route': _card(318, 520, 250, 56, 17),
                'queue': _card(602, 520, 212, 56, 17), 'alert': _card(602, 520, 285, 56, 25),
                'dial': _card(84, 272, 245, 54, 18), 'chart': _card(376, 272, 245, 54, 18),
                'exit': _card(668, 272, 245, 54, 18),
            }, '#222337', '#F3EEE6', '#A8F2EC'),
        },
        'motion_ms': {'standard': 180, 'reduced': 0},
        'traces': {
            'standard': [
                _step(0, 'menu', 'picker', 'dial', 'dial'), _step(10, 'down', 'picker', 'dial', 'chart'),
                _step(10, 'confirm', 'preview', 'dial', 'apply', True), _step(20, 'back', 'picker', 'dial', 'chart'),
                _step(10, 'confirm', 'preview', 'dial', 'apply', True), _step(180, 'wait', 'preview', 'dial', 'apply'),
                _step(0, 'confirm', 'picker', 'chart', 'chart'), _step(5, 'left', 'picker', 'chart', 'dial'),
                _step(5, 'back', 'play', 'chart', 'none'), _step(5, 'menu', 'picker', 'chart', 'chart'),
                _step(5, 'back', 'play', 'chart', 'none'),
            ],
            'reduced': [
                _step(0, 'menu', 'picker', 'dial', 'dial'), _step(10, 'down', 'picker', 'dial', 'chart'),
                _step(10, 'confirm', 'preview', 'dial', 'apply'), _step(0, 'confirm', 'picker', 'chart', 'chart'),
                _step(0, 'back', 'play', 'chart', 'none'),
            ],
        },
    },
}]


def _overlap(a, b):
    x, y, w, h = a
    xx, yy, ww, hh = b
    return x < xx + ww and xx < x + w and y < yy + hh and yy < y + h


def _profile_checks(style, profile, labels):
    _object(profile, ('cards', 'order', 'states', 'palette'), style)
    cards, frames = profile['cards'], _FRAMES[style]
    required = tuple(dict.fromkeys(key for ids in frames.values() for key in ids))
    _object(cards, required, 'cards')
    _object(profile['states'], frames, 'states')
    composition = fit = True
    for key, card in cards.items():
        _object(card, ('rect', 'glyph_px', 'mount'), 'card')
        _array(card['rect'], 4, 4, 'rect')
        for i, value in enumerate(card['rect']):
            _integer(value, -4096 if i < 2 else 1, 4096, 'rect value')
        x, y, w, h = card['rect']
        glyph = card['glyph_px']
        _integer(glyph, 1, 128, 'glyph_px')
        _choice(card['mount'], ('instrument', 'screen'), 'mount')
        instrument = style == 'dial' and key in ('charge', 'alert')
        composition &= (card['mount'] == 'instrument') == instrument
        if instrument:
            composition &= 3 * (x + w) <= 1280
        if style == 'chart' and key not in _PICKER:
            composition &= y >= 480
        label = labels['alert' if key == 'backup' else key]
        fit &= 32 <= x and x + w <= 1248 and 24 <= y and y + h <= 696
        fit &= glyph >= 14 and len(label) * ((6 * glyph + 9) // 10) + 16 <= w and glyph + 16 <= h

    for state, wanted in frames.items():
        ids = profile['states'][state]
        _array(ids, 0, len(required), state)
        for key in ids:
            _choice(key, cards, 'visible card')
        composition &= len(ids) == len(wanted) and set(ids) == set(wanted)
        fit &= not any(_overlap(cards[a]['rect'], cards[b]['rect']) for a, b in combinations(ids, 2))

    palette = profile['palette']
    _object(palette, ('text', 'focus', 'plate'), 'palette')
    hierarchy = _ratio(palette['text'], palette['plate']) >= 4.5
    focus_ratio = _ratio(palette['focus'], palette['plate'])
    hierarchy &= focus_ratio >= 3
    size = cards['charge']['glyph_px']
    hierarchy &= cards['alert']['glyph_px'] >= size + 4
    if style == 'dial':
        hierarchy &= cards['backup']['glyph_px'] >= size + 4
    else:
        hierarchy &= all(size >= cards[key]['glyph_px'] for key in ('queue', 'route'))

    order = profile['order']
    _array(order, 3, 3, 'order')
    for key in order:
        _choice(key, _PICKER, 'focus choice')
    axis = 1 if style == 'dial' else 0
    cross = 1 - axis
    rects = {key: cards[key]['rect'] for key in _PICKER}
    physical = sorted(rects, key=lambda key: rects[key][axis])
    common_line = max(r[cross] for r in rects.values()) < min(r[cross] + r[cross + 2] for r in rects.values())
    separated = all(rects[a][axis] + rects[a][axis+2] <= rects[b][axis] for a, b in zip(physical, physical[1:]))
    navigation = order == physical and common_line and separated and set(profile['states']['picker']) == set(_PICKER)
    return composition, fit, hierarchy, navigation


def _trace(mode, rows, duration, profiles):
    _array(rows, 1, 32, 'trace')
    screen, applied, focus = 'play', 'dial', 'none'
    pending = None
    now = opened = 0
    stages, mismatches = set(), []
    for index, step in enumerate(rows, 1):
        _object(step, ('dt_ms', 'key', 'after'), 'trace step')
        _integer(step['dt_ms'], 0, 3000, 'dt_ms')
        key, after = step['key'], step['after']
        _choice(key, _ACTIONS, 'input')
        _array(after, 4, 4, 'after')
        _choice(after[0], ('play', 'picker', 'preview'), 'screen')
        _choice(after[1], _STYLES, 'applied style')
        _choice(after[2], (*_PICKER, 'apply', 'none'), 'focus')
        if type(after[3]) is not bool:
            raise ValueError('Moving must be a boolean.')
        now += step['dt_ms']
        moving = screen == 'preview' and now - opened < duration
        valid = True
        if screen == 'play' and key == 'menu':
            screen, focus = 'picker', applied
            if applied == 'chart':
                stages.add('reopen')
        elif screen == 'picker':
            order = profiles[applied]['order']
            axes = ('up', 'down') if applied == 'dial' else ('left', 'right')
            if key in axes and focus in order:
                delta = 1 if key == axes[1] else -1
                focus = order[(order.index(focus) + delta) % len(order)]
                stages.add(applied)
            elif key == 'back' or (key == 'confirm' and focus == 'exit'):
                screen, focus = 'play', 'none'
            elif key == 'confirm' and focus in _STYLES:
                pending, opened = focus, now
                screen, focus = 'preview', 'apply'
            else:
                valid = False
        elif screen == 'preview' and key in ('confirm', 'back', 'wait'):
            if key == 'wait' and not moving and pending != applied:
                stages.add('settle')
            if key == 'back' and moving and pending != applied:
                stages.add('cancel')
            if key == 'confirm' and pending != applied:
                stages.add('immediate' if now == opened else 'commit')
            if key != 'wait':
                if key == 'confirm':
                    applied = pending
                screen, focus = 'picker', pending
        else:
            valid = False
        if screen == 'picker' and focus not in profiles[applied]['states']['picker']:
            valid = False
        actual = [screen, applied, focus, screen == 'preview' and now - opened < duration]
        if not valid or after != actual:
            mismatches.append(index)
    required = {'dial', 'chart', 'cancel', 'settle', 'reopen'} if mode == 'standard' else {'immediate'}
    passed = required <= stages and not mismatches and screen == 'play' and applied == 'chart'
    timing_ok = 1 <= duration <= 500 if mode == 'standard' else duration == 0
    return passed and timing_ok, (f'{mode} transition {duration}ms. Ended in {screen} on {applied}. '
                                  f'Missing milestones {sorted(required - stages)}, incorrect steps {mismatches[:6]}.')


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown interface styles exercise.')
    _object(submission, ('labels', 'alert_symbol', 'profiles', 'motion_ms', 'traces'), 'Style study')
    labels = submission['labels']
    _object(labels, ('charge', 'alert', 'route', 'queue', *_PICKER), 'labels')
    for label in labels.values():
        _label(label)
    _choice(submission['alert_symbol'], ('thermometer', 'vent-alert', 'dot', 'none'), 'alert symbol')
    profiles = submission['profiles']
    _object(profiles, _STYLES, 'profiles')
    measurements = {style: _profile_checks(style, profiles[style], labels) for style in _STYLES}
    results = []
    for i, criterion in enumerate(('composition', 'fit', 'hierarchy', 'picker-order')):
        bad = [style for style in _STYLES if not measurements[style][i]]
        if criterion == 'hierarchy' and (labels['alert'] not in ('Heat critical', 'Vent needed')
                                         or submission['alert_symbol'] not in ('thermometer', 'vent-alert')):
            bad.append('shared warning')
        results.append(_check(criterion, not bad, f'Checked dial and chart for {criterion}. Rework: {", ".join(bad) or "none"}.'))
    modes = ('standard', 'reduced')
    _object(submission['motion_ms'], modes, 'motion durations')
    _object(submission['traces'], modes, 'traces')
    for mode, criterion in zip(modes, ('preview', 'reduced-motion'), strict=True):
        duration = submission['motion_ms'][mode]
        _integer(duration, 0, 2000, 'motion duration')
        passed, detail = _trace(mode, submission['traces'][mode], duration, profiles)
        results.append(_check(criterion, passed, detail))
    return results
