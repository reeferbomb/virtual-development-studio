"""Simulate a layered one-shot effect under two quality and two motion settings."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


_ID = 'vfx-design'
_QUALITY = ('low', 'high')
_MODES = ('standard', 'reduced')
_STYLES = ('still', 'motion', 'flash', 'shake')
_BUDGETS = {'low': (24, 4), 'high': (96, 8)}

TRACK = {
    'id': _ID, 'title': 'Real-time visual effects and gameplay feedback',
    'roles': ['content', 'gameplay', 'ui', 'verification', 'build_operations'],
    'workflow': [
        'Name the decision the effect supports. For an impact, identify the contact point and surface. For a '
        'magic effect, show the active area before the state changes. Sketch the warning, contact and residue '
        'in silhouette at the intended camera distance. Give confirmation a different shape from anticipation.',
        'Build one layer at a time. Time a brief contact accent against the simulation event. Use a longer '
        'particle tail for direction or material. Ground a destruction event with a surface mark and a few '
        'large fragments, then add secondary debris only where it helps the read.',
        'For ambient pollen or rain, anchor emission to a bounded region and check indoor transitions and '
        'camera cuts. For decals, verify projection, receivers and fade distance. Inspect every layer over '
        'bright and dark backgrounds, near the reticle and during overlapping events.',
        'Keep the essential warning and feedback on low quality. Offer stable shapes when motion, camera shake '
        'or flashes are reduced. Test the rendered sequence including overlapping effects and the rest of the '
        'frame. Review final captures for flashes and patterns with suitable analysis tools.',
        'Budget emitter instances, particles, transparent screen coverage and lighting per target device. '
        'Return instances to a pool after their last visible output. Reset transforms, random seeds when needed, '
        'material state and old trails on reuse. Test interruption, rapid retriggering and scene unload.',
    ],
    'deliverables': [
        'An original warning/contact/decay sheet, per-layer production notes, quality settings and reduced-motion alternatives.',
        'A burst-overlap test with peak demand, per-layer pool capacity and a verified release timeline.',
        'Matched target-device captures and separate readability, flash-pattern and performance review notes.',
    ],
    'verification': [
        'Replay dense bursts at both quality tiers and both motion settings. Check every required cue frame, '
        'particle survival after emission stops, same-frame slot reuse and complete teardown.',
        'Inspect silhouettes and visibility in the real build and profile the worst camera angle. A synthetic '
        'particle count or an absence of authored flash layers cannot establish GPU time or photosensitivity safety.',
    ],
    'exercise': 'Stage an opening floodgate with a stable warning, a contact confirmation and a pooled spray effect.',
}


def _layer(key, role, form, offset, emit, life, release, pool, low, high, standard, reduced):
    return {'id': key, 'role': role, 'form': form, 'offset': offset, 'emit': emit, 'life': life,
            'release': release, 'pool': pool, 'low': low, 'high': high, 'standard': standard, 'reduced': reduced}


EXERCISES = [{
    'id': _ID, 'title': 'Keep a floodgate signal readable through overlapping bursts',
    'brief': 'Create a synthetic scene of 12–360 frames with 2–8 distinct contact frames in rising order. '
             'Every contact triggers every enabled layer. Frame intervals include their start and exclude their end. '
             'For each contact t, visible warning outlines cover exactly [t−lead,t) and impact glyphs or decals '
             'cover exactly [t,t+hold). Each must belong to that event. A cover from any event masks all signals '
             'while its geometry is visible. Particles alone cannot carry these cues. Support 1–30 frames for '
             'each of lead and hold, and 3–12 layers. Each layer starts at t+offset (−60 to 60). Its geometry '
             'shows for emit frames (1–60). Each emission frame births low or high particles (0–32) that '
             'survive life frames (1–60), including birth. Null low disables the entire layer on low quality. '
             'Release the instance release frames after start (1–180), after geometry and all particles finish. '
             'Each layer owns 1–8 pooled slots. A slot returned on a frame can be reused immediately. All work '
             'must end by the scene boundary. Standard style is still, motion, flash or shake. Reduced adds off '
             'and must use still or off. A still layer keeps its rate and geometry but removes movement. '
             'Roles are warning, impact and detail. Forms are outline, glyph, decal, particles and cover. '
             'Predict [peak live particles, peak occupied slots] for each quality/mode. Low budgets are [24,4] '
             'and high [96,8]. Use fewer live particles on low than high standard, positive on both. '
             'Counts measure demand before any capacity-based dropping and say nothing about a rendered frame.',
    'criteria': [
        {'id': 'cue-timing', 'label': 'Cover each warning and contact interval with the correct event-local shapes.'},
        {'id': 'visibility', 'label': 'Keep the shared focus area clear during required signals in every setting.'},
        {'id': 'reduced-motion', 'label': 'Provide stable or disabled layers throughout reduced playback.'},
        {'id': 'pool-cleanup', 'label': 'Reserve sufficient per-layer slots and release them after all live work.'},
        {'id': 'quality-budgets', 'label': 'Meet both quality budgets and reduce live particle demand on low.'},
        {'id': 'peak-predictions', 'label': 'Reproduce particle and instance peaks in all four combinations.'},
    ],
    'example': {
        'frames': 32, 'lead': 3, 'hold': 2, 'contacts': [8, 14, 20],
        'layers': [
            _layer('rim', 'warning', 'outline', -3, 3, 1, 3, 1, 0, 0, 'motion', 'still'),
            _layer('latch_mark', 'impact', 'decal', 0, 2, 1, 2, 1, 0, 0, 'still', 'still'),
            _layer('water_fan', 'detail', 'particles', 0, 2, 5, 6, 1, 1, 3, 'motion', 'off'),
            _layer('foam_beads', 'detail', 'particles', 1, 3, 5, 7, 2, None, 4, 'motion', 'off'),
        ],
        'peaks': {'low': {'standard': [2, 2], 'reduced': [0, 1]},
                  'high': {'standard': [18, 4], 'reduced': [0, 1]}},
    },
}]


def _validate(data):
    _object(data, ('frames', 'lead', 'hold', 'contacts', 'layers', 'peaks'), 'VFX sequence')
    _integer(data['frames'], 12, 360, 'frames')
    for key in ('lead', 'hold'):
        _integer(data[key], 1, 30, key)
    _array(data['contacts'], 2, 8, 'contacts')
    for contact in data['contacts']:
        _integer(contact, 0, data['frames'] - 1, 'contact frame')
    if data['contacts'] != sorted(set(data['contacts'])):
        raise ValueError('Contacts must be distinct and ordered.')
    _array(data['layers'], 3, 12, 'layers')
    names = set()
    for layer in data['layers']:
        _object(layer, ('id', 'role', 'form', 'offset', 'emit', 'life', 'release', 'pool', 'low', 'high',
                        'standard', 'reduced'), 'layer')
        _identifier(layer['id'], 'layer ID')
        if layer['id'] in names:
            raise ValueError('Layer IDs must be unique.')
        names.add(layer['id'])
        _choice(layer['role'], ('warning', 'impact', 'detail'), 'role')
        _choice(layer['form'], ('outline', 'glyph', 'decal', 'particles', 'cover'), 'form')
        _choice(layer['standard'], _STYLES, 'standard style')
        _choice(layer['reduced'], (*_STYLES, 'off'), 'reduced style')
        for key, low, high in (('offset', -60, 60), ('emit', 1, 60), ('life', 1, 60),
                               ('release', 1, 180), ('pool', 1, 8), ('high', 0, 32)):
            _integer(layer[key], low, high, key)
        if layer['low'] is not None:
            _integer(layer['low'], 0, 32, 'low')
    _object(data['peaks'], _QUALITY, 'peaks')
    for quality in _QUALITY:
        _object(data['peaks'][quality], _MODES, 'quality peaks')
        for pair in data['peaks'][quality].values():
            _array(pair, 2, 2, 'peak pair')
            for number in pair:
                _integer(number, 0, 200000, 'predicted peak')


def _simulate(data, quality, mode):
    frames = data['frames']
    particles, slots = [0] * frames, [0] * frames
    occupied_focus = set()
    signals = {contact: {'warning': set(), 'impact': set()} for contact in data['contacts']}
    cleanup, motion = [], []
    for layer in data['layers']:
        rate, style = layer[quality], layer[mode]
        if rate is None or style == 'off':
            continue
        if mode == 'reduced' and style != 'still':
            motion.append(layer['id'])
        occupied = [0] * frames
        emit, life, release = layer['emit'], layer['life'], layer['release']
        end_of_work = emit + life - 1 if rate else emit
        valid_release = release >= end_of_work
        for contact in data['contacts']:
            start = contact + layer['offset']
            valid_release &= start >= 0 and start + max(release, end_of_work) <= frames
            visible = range(max(0, start), min(frames, start + emit))
            form, role = layer['form'], layer['role']
            if form == 'cover':
                occupied_focus.update(visible)
            elif ((role == 'warning' and form == 'outline')
                  or (role == 'impact' and form in ('glyph', 'decal'))):
                signals[contact][role].update(visible)
            for frame in range(max(0, start), min(frames, start + release)):
                occupied[frame] += 1
                slots[frame] += 1
            # The surviving cohorts were born no earlier than frame-life+1 or later than the last emission.
            for frame in range(max(0, start), min(frames, start + end_of_work)):
                first_birth = max(start, frame - life + 1)
                last_birth = min(frame, start + emit - 1)
                particles[frame] += rate * (last_birth - first_birth + 1)
        if not valid_release or max(occupied) > layer['pool']:
            cleanup.append(layer['id'])

    timing_ok, blocked = True, set()
    for contact, actual in signals.items():
        windows = {'warning': set(range(contact - data['lead'], contact)),
                   'impact': set(range(contact, contact + data['hold']))}
        timing_ok &= actual == windows
        for window in windows.values():
            blocked.update(window & occupied_focus)
    return {'peaks': [max(particles), max(slots)], 'timing': timing_ok, 'blocked': sorted(blocked),
            'cleanup': cleanup, 'motion': motion}


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown visual effects exercise.')
    _validate(submission)
    results = {(quality, mode): _simulate(submission, quality, mode) for quality in _QUALITY for mode in _MODES}
    over_budget, incorrect = [], []
    for (quality, mode), row in results.items():
        if any(peak > cap for peak, cap in zip(row['peaks'], _BUDGETS[quality])):
            over_budget.append(f'{quality}/{mode}')
        if submission['peaks'][quality][mode] != row['peaks']:
            incorrect.append(f'{quality}/{mode}')
    low = results['low', 'standard']['peaks'][0]
    high = results['high', 'standard']['peaks'][0]
    obscured = sorted({frame for row in results.values() for frame in row['blocked']})
    cleanup = sorted({name for row in results.values() for name in row['cleanup']})
    motion = sorted({name for row in results.values() for name in row['motion']})
    timing = [f'{q}/{m}' for (q, m), row in results.items() if not row['timing']]
    peaks = ', '.join(f'{q}/{m} {row["peaks"]}' for (q, m), row in results.items())
    return [
        _check('cue-timing', not timing, f'Settings with missing or mistimed geometry: {", ".join(timing) or "none"}.'),
        _check('visibility', not obscured, f'Signal frames covered by foreground geometry: {obscured[:12]}.'),
        _check('reduced-motion', not motion, f'Enabled reduced layers with movement or flashes: {motion}.'),
        _check('pool-cleanup', not cleanup, f'Layers with clipped lifetimes, missed scene limits or insufficient slots: {cleanup}.'),
        _check('quality-budgets', not over_budget and 0 < low < high,
               f'Standard particle demand is {low} on low and {high} on high. Over-budget settings: {over_budget}.'),
        _check('peak-predictions', not incorrect, f'Measured peak particles and occupied slots: {peaks}.'),
    ]
