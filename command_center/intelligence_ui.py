"""Offline diagnostics for one HUD or menu state measured across device and locale profiles.

All geometry is in physical pixels. Rectangles are [x, y, width, height]; insets and
padding are [left, top, right, bottom]. measured_text is the complete shaped text
extent [width, height], including all lines, or null for a nontext widget. Supply
visible widgets and the actual directed focus moves (including any return moves)
for this state. IDs identify stable controls across profiles. Coordinates may be
fractional. Geometry uses a 0.000001px tolerance for floating-point arithmetic.
"""

from itertools import combinations
import math
import re


_EPSILON = 1e-6
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,47}')
_LOCALE = re.compile(r'[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*')
_RULES = (
    ('viewport-bounds', 'Visible widgets inside the viewport', 'fail'),
    ('safe-area', 'Visible widgets inside the safe area', 'fail'),
    ('text-fit', 'Measured text inside padded content boxes', 'fail'),
    ('required-controls', 'Required controls present and focusable', 'fail'),
    ('focus-reachability', 'Reachable focus targets and return paths', 'fail'),
    ('control-overlap', 'Overlapping focusable rectangles', 'warn'),
    ('text-coverage', 'Profiles with measured text', 'warn'),
)


def _record(value, fields, name):
    if type(value) is not dict or len(value) != len(fields) or any(field not in value for field in fields):
        raise ValueError(f'{name} requires exactly {", ".join(fields)}.')


def _list(value, low, high, name):
    if type(value) is not list or not low <= len(value) <= high:
        raise ValueError(f'{name} requires {low}–{high} items.')


def _id(value, name):
    if type(value) is not str or len(value) > 48 or not _ID.fullmatch(value):
        raise ValueError(f'{name} must be an ASCII identifier of 1–48 characters starting with a letter.')


def _pixels(value, bounds, name):
    _list(value, len(bounds), len(bounds), name)
    for v, (low, high) in zip(value, bounds):
        # Check magnitude before conversion so arbitrarily large Python ints are rejected cleanly.
        if type(v) not in (float, int) or not low <= v <= high or not math.isfinite(v):
            raise ValueError(f'{name} requires finite pixel values in its supported range.')


def _graph(start, edges):
    found, pending = set(), [start]
    while pending:
        key = pending.pop()
        if key not in found:
            found.add(key)
            pending.extend(edges[key] - found)
    return found


def _profile(profile, required, note):
    _record(profile, ('id', 'locale', 'viewport', 'safe_insets', 'widgets', 'initial_focus', 'focus_edges'), 'profile')
    key = profile['id']
    _id(key, 'profile ID')
    locale = profile['locale']
    if type(locale) is not str or len(locale) > 48 or not _LOCALE.fullmatch(locale):
        raise ValueError('locale must be a short language tag such as en, de-DE or zh_Hant_TW.')
    _pixels(profile['viewport'], [(1, 16384)] * 2, 'viewport')
    width, height = profile['viewport']
    _pixels(profile['safe_insets'], [(0, 16384)] * 4, 'safe_insets')
    left, top, right, bottom = profile['safe_insets']
    if left + right >= width or top + bottom >= height:
        raise ValueError('Safe insets must leave a nonempty area inside the viewport.')

    _list(profile['widgets'], 0, 128, 'widgets')
    all_ids, controls = set(), {}
    outside = unsafe = overflowing = text_count = 0
    max_x_overflow = max_y_overflow = 0
    for widget in profile['widgets']:
        _record(widget, ('id', 'rect', 'padding', 'measured_text', 'focusable'), 'widget')
        wid = widget['id']
        _id(wid, 'widget ID')
        if wid in all_ids:
            raise ValueError(f'Duplicate widget ID {wid} in {key}.')
        all_ids.add(wid)
        _pixels(widget['rect'], [(-65536, 65536)] * 2 + [(0, 65536)] * 2, 'rect')
        x, y, w, h = widget['rect']
        if w <= 0 or h <= 0:
            raise ValueError('Visible widgets must have positive width and height.')
        if type(widget['focusable']) is not bool:
            raise ValueError('focusable must be a boolean.')
        if widget['focusable']:
            controls[wid] = (x, y, x + w, y + h)
        name = f'{key}/{wid}'
        if x < -_EPSILON or y < -_EPSILON or x + w > width + _EPSILON or y + h > height + _EPSILON:
            note('viewport-bounds', name)
            outside += 1
        if x < left - _EPSILON or y < top - _EPSILON or x + w > width - right + _EPSILON or y + h > height - bottom + _EPSILON:
            note('safe-area', name)
            unsafe += 1
        _pixels(widget['padding'], [(0, 65536)] * 4, 'padding')
        pl, pt, pr, pb = widget['padding']
        tw = th = 0
        if widget['measured_text'] is not None:
            _pixels(widget['measured_text'], [(0, 65536)] * 2, 'measured_text')
            tw, th = widget['measured_text']
            if tw <= 0 or th <= 0:
                raise ValueError('Measured text extents must be positive. Use null for a nontext widget.')
            text_count += 1
        dx, dy = max(0, tw + pl + pr - w), max(0, th + pt + pb - h)
        if max(dx, dy) > _EPSILON:
            note('text-fit', f'{name} (+{dx:g}px width, +{dy:g}px height)')
            overflowing += 1
            max_x_overflow, max_y_overflow = max(max_x_overflow, dx), max(max_y_overflow, dy)
    if not text_count:
        note('text-coverage', key)

    needed = sorted(required - controls.keys())
    for wid in needed:
        note('required-controls', f'{key}/{wid} ' + ('is nonfocusable' if wid in all_ids else 'is missing'))
    overlaps = 0
    for (a, (ax, ay, ar, ab)), (b, (bx, by, br, bb)) in combinations(controls.items(), 2):
        if min(ar, br) - max(ax, bx) > _EPSILON and min(ab, bb) - max(ay, by) > _EPSILON:
            note('control-overlap', f'{key}/{a} & {b}')
            overlaps += 1

    _list(profile['focus_edges'], 0, 512, 'focus_edges')
    forward = {wid: set() for wid in controls}
    backward = {wid: set() for wid in controls}
    seen_edges = set()
    invalid_edges = 0
    for pair in profile['focus_edges']:
        _list(pair, 2, 2, 'focus edge')
        a, b = pair
        _id(a, 'focus source')
        _id(b, 'focus destination')
        if (a, b) in seen_edges:
            raise ValueError(f'Duplicate focus edge {a} → {b} in {key}.')
        seen_edges.add((a, b))
        if a not in controls or b not in controls:
            note('focus-reachability', f'{key} invalid link {a} → {b}')
            invalid_edges += 1
        else:
            forward[a].add(b)
            backward[b].add(a)
    initial = profile['initial_focus']
    if initial is not None:
        _id(initial, 'initial_focus')
    if initial in controls:
        reached, can_return = _graph(initial, forward), _graph(initial, backward)
    else:
        reached, can_return = set(), set()
        if controls or initial is not None:
            note('focus-reachability', f'{key} invalid initial focus')
    for wid in sorted(controls.keys() - reached):
        note('focus-reachability', f'{key}/{wid} unreachable')
    for wid in sorted(reached - can_return):
        note('focus-reachability', f'{key}/{wid} has no return path')
    return {
        'id': key, 'locale': locale, 'viewport': [width, height], 'widgets': len(all_ids), 'text_samples': text_count,
        'outside_viewport': outside, 'outside_safe_area': unsafe, 'overflowing_boxes': overflowing,
        'max_width_overflow_px': max_x_overflow, 'max_height_overflow_px': max_y_overflow,
        'missing_or_nonfocusable_required': len(needed), 'focusable': len(controls), 'invalid_focus_edges': invalid_edges,
        'unreachable_focusable': len(controls) - len(reached), 'reachable_without_return': len(reached - can_return),
        'overlapping_control_pairs': overlaps,
    }


def analyze(data: dict) -> dict:
    """Analyze 1–16 measured profiles of the same state without opening assets or rendering UI."""
    _record(data, ('required_controls', 'profiles'), 'UI input')
    _list(data['required_controls'], 0, 128, 'required_controls')
    for key in data['required_controls']:
        _id(key, 'required control')
    required = set(data['required_controls'])
    if len(required) != len(data['required_controls']):
        raise ValueError('Required control IDs must be distinct.')
    _list(data['profiles'], 1, 16, 'profiles')
    counts = dict.fromkeys((r[0] for r in _RULES), 0)
    samples = {key: [] for key in counts}

    def note(rule, detail):
        counts[rule] += 1
        if len(samples[rule]) < 4:
            samples[rule].append(detail)

    rows, ids = [], set()
    for profile in data['profiles']:
        row = _profile(profile, required, note)
        if row['id'] in ids:
            raise ValueError('Profile IDs must be unique.')
        ids.add(row['id'])
        rows.append(row)
    checks = []
    for rule, label, severity in _RULES:
        n = counts[rule]
        detail = f'{n} findings. ' + ', '.join(samples[rule]) if n else f'No findings across {len(rows)} supplied profiles.'
        checks.append({'id': rule, 'label': label, 'status': severity if n else 'pass', 'detail': detail})
    statuses = {c['status'] for c in checks}
    status = 'fail' if 'fail' in statuses else 'warn' if 'warn' in statuses else 'pass'
    return {'schema_version': 1, 'kind': 'ui', 'status': status, 'checks': checks,
            'metrics': {'profile_count': len(rows), 'locale_count': len({r['locale'] for r in rows}),
                        'required_controls': len(required), 'profiles': rows},
            'advisory': 'Results cover the supplied pixel measurements and directed focus links for one UI state. '
                        'Check shaping, translated meaning, actual focus behavior and readability in the build on target devices. '
                        'Input measurements do not establish accessibility compliance or release approval.'}


def example() -> dict:
    """A synthetic seed-cabinet menu at desktop and handheld settings with different text extents."""
    profiles = []
    for key, locale, viewport, safe, captions in (
        ('desk-en', 'en-US', [1920, 1080], [48, 32, 48, 32], [[139, 25], [127, 25]]),
        ('hand-de', 'de-DE', [1280, 720], [48, 24, 56, 32], [[236, 32], [191, 32]]),
    ):
        widgets = [{'id': 'heading', 'rect': [88, 64, 540, 66], 'padding': [12, 6, 12, 6],
                    'measured_text': [268, 40], 'focusable': False}]
        for index, (control, extent) in enumerate(zip(('inspect', 'return'), captions)):
            widgets.append({'id': control, 'rect': [88, 162 + 90 * index, 320, 64], 'padding': [16, 8, 16, 8],
                            'measured_text': extent, 'focusable': True})
        profiles.append({'id': key, 'locale': locale, 'viewport': viewport, 'safe_insets': safe, 'widgets': widgets,
                         'initial_focus': 'inspect', 'focus_edges': [['inspect', 'return'], ['return', 'inspect']]})
    return {'required_controls': ['inspect', 'return'], 'profiles': profiles}
