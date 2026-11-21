"""Assess opaque color swatches, camera/HUD rectangles and a gate's cue vocabulary."""

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _integer
from .lab_interface import _luminance, _ratio


TRACK = {
    'id': 'visual-readability', 'title': 'Visual readability and player expectations',
    'roles': ['ui', 'content', 'gameplay', 'verification'],
    'workflow': [
        'At a decision point, name what the player needs to notice first, what action they can take and how '
        'the game will acknowledge it. Keep that cue and response consistent when the situation recurs.',
        'Stage the decision from the playable camera. Compare the silhouette with nearby values in shadow, '
        'backlight and motion. Leave space around the subject and check the route with effects and HUD visible.',
        'Give the main prompt more emphasis than its supporting hint. Pair state colors with a readable label '
        'and a distinct shape. Provide a text-size setting and an opaque backing where the scene changes.',
        'Repeat the approach at the widest and narrowest supported camera framing, with larger UI text and '
        'device safe-area insets. Try brightness settings, reduced motion and color-vision options independently.',
    ],
    'deliverables': [
        'An annotated playable-camera capture for each lighting extreme, with subject outline, action prompt, '
        'supporting hint, device, UI scale and brightness settings.',
        'A cue sheet mapping each state to its shape, wording, input and outcome. Include first-time players’ '
        'predictions before input and the result they observed afterward.',
    ],
    'verification': [
        'Measure declared opaque swatches and layout bounds in the fixture. Then inspect actual rendered edges, '
        'tone mapping, occlusion, text wrapping and motion on target displays at the supported viewing distances.',
        'In the build, dim or remove color cues and ask a first-time player to identify the state and predict '
        'the next input outcome. Record missed cues, surprising responses and the settings used.',
    ],
    'exercise': 'Keep a service gate and its prompts readable in two camera views as its lock state changes.',
}


_GATE = {
    'locked': {'labels': ('Locked', 'Key required'), 'icons': ('padlock', 'keyhole'), 'action': 'explain-lock'},
    'ready': {'labels': ('Unlocked', 'Open gate'), 'icons': ('open-door', 'open-lock'), 'action': 'open-gate'},
}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Read a service gate through a lighting change',
    'brief': 'Supply 2–4 views in physical pixels. Use two resolutions, at least one nonzero safe inset, '
             '100% UI scale and a 150% or larger setting. Insets are [left, top, right, bottom]. '
             'Scale the base panel width, height and font sizes by the percentage, rounding each up. Keep its '
             'top-left origin fixed in screen pixels. The two stacked lines reserve eight more scaled pixels '
             'for padding. The hint is at least 14px and the headline at least 4px larger at every setting. '
             'Supply a gate silhouette rectangle [x,y,width,height] and adjacent background sample per view. '
             'Keep the gate at least 24×24px and show one dark backdrop (linear luminance ≤0.10). Test opaque '
             '#RRGGBB samples. This exercise targets 4.5:1 for text on the panel and 3:1 for icons on the panel '
             'and silhouette against its backdrop. For this English fixture, locked uses “Locked” or “Key required”, '
             'a padlock or keyhole, and explain-lock. Ready uses “Unlocked” or “Open gate”, an open-door or '
             'open-lock, and open-gate. Visit each state at least twice across 4–16 cues. Consecutive readings '
             'of an unchanged state count as one visit. Keep its label, icon '
             'and action consistent on return. Real lighting, font rendering and player understanding require '
             'captures and a playtest.',
    'criteria': [
        {'id': 'hud-contrast', 'label': 'Measure the text and every state icon against the opaque panel swatch.'},
        {'id': 'camera-readability', 'label': 'Keep the gate in frame, clear of the HUD and distinct against each sampled backdrop.'},
        {'id': 'safe-scaling', 'label': 'Keep the scaled panel within safe bounds on both normal and enlarged layouts.'},
        {'id': 'type-hierarchy', 'label': 'Reserve room for both type sizes and keep the action more prominent than the hint.'},
        {'id': 'noncolor-cues', 'label': 'Use a state-appropriate label and icon so either can identify the gate without its tint.'},
        {'id': 'stable-response', 'label': 'Repeat each state with the same cue and its promised interaction outcome.'},
    ],
    'example': {
        'hud': {'size': [256, 56], 'headline_px': 20, 'hint_px': 16,
                'text_color': '#F3F5F4', 'panel_color': '#171B22'},
        'views': [
            {'width': 1280, 'height': 720, 'insets': [32, 24, 32, 32], 'scale_percent': 100,
             'panel_xy': [40, 620], 'gate_rect': [680, 250, 118, 202],
             'silhouette': '#9DB7BC', 'backdrop': '#232B33'},
            {'width': 854, 'height': 480, 'insets': [32, 16, 48, 24], 'scale_percent': 150,
             'panel_xy': [36, 364], 'gate_rect': [390, 110, 76, 134],
             'silhouette': '#303F42', 'backdrop': '#C5C6B3'},
        ],
        'cues': [
            {'state': state, 'label': _GATE[state]['labels'][0], 'icon': _GATE[state]['icons'][0],
             'action': _GATE[state]['action'], 'tint': tint}
            for state, tint in [('locked', '#F3C576'), ('ready', '#88D3D7')] * 2
        ],
    },
}]


def _pixels(value, length, field, low=-16384):
    _array(value, length, length, field)
    for number in value:
        _integer(number, low, 16384, field)
    return value


def _scaled(px, percent):
    return (px * percent + 99) // 100


def _view_checks(views, hud):
    _array(views, 2, 4, 'views')
    hidden, outside, cramped = [], [], []
    resolutions, scales = set(), set()
    has_inset = has_dark_view = False
    for index, view in enumerate(views, 1):
        _object(view, ('width', 'height', 'insets', 'scale_percent', 'panel_xy', 'gate_rect',
                       'silhouette', 'backdrop'), 'view')
        width, height, scale = (view[k] for k in ('width', 'height', 'scale_percent'))
        _integer(width, 1, 8192, 'width')
        _integer(height, 1, 8192, 'height')
        _integer(scale, 50, 300, 'scale_percent')
        resolutions.add((width, height))
        scales.add(scale)
        left, top, right, bottom = _pixels(view['insets'], 4, 'insets', low=0)
        has_inset |= any(view['insets'])
        x, y = _pixels(view['panel_xy'], 2, 'panel_xy')
        panel_w, panel_h = (_scaled(px, scale) for px in hud['size'])
        if x < left or y < top or x + panel_w > width - right or y + panel_h > height - bottom:
            outside.append(index)
        headline, hint = (_scaled(hud[key], scale) for key in ('headline_px', 'hint_px'))
        if hint < 14 or headline < hint + 4 or headline + hint + _scaled(8, scale) > panel_h or headline > panel_w:
            cramped.append(index)
        gx, gy, gw, gh = _pixels(view['gate_rect'], 4, 'gate_rect')
        framed = 0 <= gx and 0 <= gy and gw >= 24 and gh >= 24 and gx + gw <= width and gy + gh <= height
        occluded = gx < x + panel_w and x < gx + gw and gy < y + panel_h and y < gy + gh
        ratio = _ratio(view['silhouette'], view['backdrop'])
        has_dark_view |= _luminance(view['backdrop']) <= 0.10
        if not framed or occluded or ratio < 3:
            hidden.append(f'view {index} (in frame and at least 24px={framed}, HUD overlap={occluded}, {ratio:.3f}:1)')
    scale_coverage = 100 in scales and max(scales) >= 150
    return [
        _check('camera-readability', has_dark_view and not hidden,
               f'Dark backdrop sampled={has_dark_view}. ' + (', '.join(hidden) or 'All gate rectangles and swatches meet the fixture targets.')),
        _check('safe-scaling', len(resolutions) >= 2 and scale_coverage and has_inset and not outside,
               f'{len(resolutions)} resolutions, scales {sorted(scales)}%, nonzero inset={has_inset}, outside safe area in views {outside}.'),
        _check('type-hierarchy', not cramped, f'Checked {len(views)} scaled headline/hint pairs. Size or space fails in views {cramped}.'),
    ]


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown visual readability exercise.')
    _object(submission, ('hud', 'views', 'cues'), 'Visual readability submission')
    hud = submission['hud']
    _object(hud, ('size', 'headline_px', 'hint_px', 'text_color', 'panel_color'), 'hud')
    _pixels(hud['size'], 2, 'size', low=1)
    for key in ('headline_px', 'hint_px'):
        _integer(hud[key], 1, 256, key)
    text_ratio = _ratio(hud['text_color'], hud['panel_color'])
    views = _view_checks(submission['views'], hud)
    cues = submission['cues']
    _array(cues, 4, 16, 'cues')
    codes = {state: set() for state in _GATE}
    visits = dict.fromkeys(_GATE, 0)
    previous = None
    ambiguous, unexpected, ratios = [], [], []
    for index, cue in enumerate(cues, 1):
        _object(cue, ('state', 'label', 'icon', 'action', 'tint'), 'cue')
        for key in ('state', 'icon', 'action'):
            _identifier(cue[key], key)
        _text(cue['label'], 64, 'label')
        state = cue['state']
        if state not in _GATE:
            raise ValueError('A gate cue state must be locked or ready.')
        meaning = _GATE[state]
        if cue['label'] not in meaning['labels'] or cue['icon'] not in meaning['icons']:
            ambiguous.append(index)
        if cue['action'] != meaning['action']:
            unexpected.append(index)
        codes[state].add((cue['label'], cue['icon'], cue['action']))
        if state != previous:
            visits[state] += 1
        previous = state
        ratios.append(_ratio(cue['tint'], hud['panel_color']))
    unstable = [state for state in _GATE if visits[state] < 2 or len(codes[state]) != 1]
    return [
        _check('hud-contrast', text_ratio >= 4.5 and min(ratios) >= 3,
               f'Opaque swatches give {text_ratio:.3f}:1 for text and {min(ratios):.3f}:1 for the lowest icon ratio.'),
        *views,
        _check('noncolor-cues', not ambiguous, f'State label or icon disagrees with the gate legend in cues {ambiguous}.'),
        _check('stable-response', not unstable and not unexpected,
               f'States missing repeated consistent visits {unstable}. Unexpected action in cues {unexpected}.'),
    ]
