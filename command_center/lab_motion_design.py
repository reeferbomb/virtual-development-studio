"""Evaluate a one-dimensional walk-to-guard animation at fixed simulation frames."""

from itertools import groupby

from .lab_design import _array, _check, _object
from .lab_gameplay import _choice, _integer


# Godot, Using AnimationTree: https://docs.godotengine.org/en/stable/tutorials/animation/animation_tree.html
# Simon Clavet, Ubisoft Montreal, Motion Matching and The Road to Next-Gen Animation (GDC 2016):
# https://www.gdcvault.com/play/1022985/Motion-Matching-and-The-Road
TRACK = {
    'id': 'motion-design', 'title': 'Gameplay animation, contact and responsiveness',
    'roles': ['gameplay', 'content', 'architecture', 'verification'],
    'workflow': [
        'Study a walk, pivot or guard from a credited game presentation. Mark the anticipation, planted foot, '
        'first visible response, contact and recovery. In his GDC motion-matching talk, Simon Clavet describes '
        'selecting frames against both the current pose and intended path. Use those two questions to critique '
        'a transition, then block an original move with your own poses and timing.',
        'Block the weight shift and support foot first. Sample the same sole point in world space while it '
        'carries weight. Include the loop seam. A foot can move backward relative to the hips while staying '
        'still on the ground. Review swing clearance, toe roll and balance separately in front and side views.',
        'Choose a movement owner. With extracted root motion, feed the blended motion delta to the controller '
        'once and let collision resolve the move. With in-place clips, match the stride to controller speed. '
        'Inspect the body and skeleton together while starting, turning, stopping and changing speed.',
        'Mark input, the first readable pose, the gameplay event and return to control on the same clock. '
        'Crossfade outgoing and incoming poses and inspect the blended result at the event. Define what '
        'happens to pending and already-issued events when an incoming command interrupts the action.',
    ],
    'deliverables': [
        'An original pose sheet with support contacts, movement ownership and the intended gameplay timing.',
        'A transition trace showing blend weights, input latency, extracted movement and gameplay events.',
        'Capture lists for natural completion and both sides of a cancel boundary, including the first frame back in locomotion.',
    ],
    'verification': [
        'Check contact drift against a ground mark at the target speed. Scrub through the transition and compare '
        'camera-visible motion with collision and gameplay event timing. Check interrupted playback for duplicate '
        'events, delayed control, residual movement or an abrupt pose change.',
        'Repeat in a running build under different render rates, with an obstacle and on a slope. Compare '
        'input and simulation timing with the displayed frame. Review weight, silhouette and responsiveness '
        'at play speed with an observer. The simplified frame exercise only verifies its numeric model.',
    ],
    'exercise': 'Crossfade a walking sentinel into a shield guard and predict what survives an interruption.',
}


_CASES = ('complete', 'cancel_on_marker', 'cancel_after_marker')
EXERCISES = [{
    'id': 'motion-design', 'title': 'Keep a clockwork sentinel’s shield and gameplay in step',
    'brief': 'Work in fixed 60 Hz frames, forward millimetres and degrees. Walk loops over 4–24 samples. '
             'Each sample advances the body by dx_mm (1–100) and supplies the planted foot (left or right) '
             'and its signed sole_mm (−3000 to 3000) relative to the body. On each continuous support, including across the '
             'loop seam, keep body position plus sole_mm within a 2 mm range for at least two frames. Use both feet. '
             'The guard button is pressed at frame 0. After delay_frames (0–8), start guard sample 0. Guard has '
             '4–24 samples of dx_mm (−100 to 100) and shield_deg (0–90). Walk holds the shield at 0 degrees. '
             'Provide 2–8 incoming blend_pct values, rising from implicit 0 to 100 by at most 50 points per frame. '
             'Hold the last weight through the remaining guard samples. The first blended shield pose at or above '
             '5 degrees must arrive by global frame 2. Set marker to the first guard-local frame whose blended '
             'shield reaches 60 degrees. Raise through the threshold once and lower below it before returning. '
             'Keep at least one guard sample after the marker. '
             'Walk phase always uses global frame modulo walk length. Starting from body position 0, add exactly '
             'one blended delta per frame using (walk_dx × (100 − weight) + guard_dx × weight) / 100, rounded to '
             'the nearest mm with ties away from zero. Demonstrate nonzero guard travel and an actual change from '
             'pure walking. Return to pure walk at the first frame after the guard, or immediately on cancel. '
             'A cancel at the start of a frame suppresses that frame’s guard movement and event. '
             'For complete, cancel_on_marker and cancel_after_marker (one frame later), give the global walk_frame '
             'of return, cumulative body_mm at every frame from 0 through that return inclusive, and a list of '
             'global event_frames. These tolerances are specific to the synthetic fixture.',
    'criteria': [
        {'id': 'foot-contacts', 'label': 'Keep both support feet planted in world space, including across the loop seam.'},
        {'id': 'crossfade', 'label': 'Transfer weight to the guard progressively and finish the blend within the clip.'},
        {'id': 'response', 'label': 'Show the first readable shield movement within two frames of the input.'},
        {'id': 'event-sync', 'label': 'Match the gameplay marker to the single visible guard raise and recover below threshold.'},
        {'id': 'root-motion', 'label': 'Predict the single blended displacement on every sample of all three takes.'},
        {'id': 'interruption', 'label': 'Predict return of locomotion and preserve only events issued before the cancel.'},
    ],
    'example': {
        'walk': [{'dx_mm': 12, 'foot': 'left', 'sole_mm': 16}, {'dx_mm': 12, 'foot': 'left', 'sole_mm': 4},
                 {'dx_mm': 12, 'foot': 'right', 'sole_mm': 20}, {'dx_mm': 12, 'foot': 'right', 'sole_mm': 8}],
        'guard': [{'dx_mm': 4, 'shield_deg': 25}, {'dx_mm': 12, 'shield_deg': 50},
                  {'dx_mm': 20, 'shield_deg': 75}, {'dx_mm': 4, 'shield_deg': 80},
                  {'dx_mm': -4, 'shield_deg': 35}, {'dx_mm': 0, 'shield_deg': 0}],
        'delay_frames': 1, 'blend_pct': [25, 60, 100], 'marker': 2,
        'takes': {
            'complete': {'walk_frame': 7, 'body_mm': [12, 22, 34, 54, 58, 54, 54, 66], 'event_frames': [3]},
            'cancel_on_marker': {'walk_frame': 3, 'body_mm': [12, 22, 34, 46], 'event_frames': []},
            'cancel_after_marker': {'walk_frame': 4, 'body_mm': [12, 22, 34, 54, 66], 'event_frames': [3]},
        },
    },
}]


def _read(data):
    _object(data, ('walk', 'guard', 'delay_frames', 'blend_pct', 'marker', 'takes'), 'motion submission')
    _array(data['walk'], 4, 24, 'walk')
    for sample in data['walk']:
        _object(sample, ('dx_mm', 'foot', 'sole_mm'), 'walk sample')
        _integer(sample['dx_mm'], 1, 100, 'walk dx_mm')
        _choice(sample['foot'], ('left', 'right'), 'foot')
        _integer(sample['sole_mm'], -3000, 3000, 'sole_mm')
    _array(data['guard'], 4, 24, 'guard')
    for sample in data['guard']:
        _object(sample, ('dx_mm', 'shield_deg'), 'guard sample')
        _integer(sample['dx_mm'], -100, 100, 'guard dx_mm')
        _integer(sample['shield_deg'], 0, 90, 'shield_deg')
    _integer(data['delay_frames'], 0, 8, 'delay_frames')
    _integer(data['marker'], 0, 23, 'marker')
    _array(data['blend_pct'], 2, 8, 'blend_pct')
    for weight in data['blend_pct']:
        _integer(weight, 0, 100, 'blend percentage')
    _object(data['takes'], _CASES, 'takes')
    for take in data['takes'].values():
        _object(take, ('walk_frame', 'body_mm', 'event_frames'), 'take')
        _integer(take['walk_frame'], 0, 32, 'walk_frame')
        _array(take['body_mm'], 1, 33, 'body_mm')
        for position in take['body_mm']:
            _integer(position, -3300, 3300, 'body position')
        _array(take['event_frames'], 0, 33, 'event_frames')
        for frame in take['event_frames']:
            _integer(frame, 0, 32, 'event frame')


def _contacts(walk):
    # Start at a change of foot so each complete stance is measured once, even if it wraps.
    boundary = next((i for i, row in enumerate(walk) if row['foot'] != walk[i - 1]['foot']), None)
    if boundary is None:
        return _check('foot-contacts', False, 'The walking cycle never changes support foot.')
    ordered = walk[boundary:] + walk[:boundary]
    body = max_drift = 0
    shortest = len(walk)
    for _, stance in groupby(ordered, key=lambda sample: sample['foot']):
        soles = []
        for sample in stance:
            body += sample['dx_mm']
            soles.append(body + sample['sole_mm'])
        shortest = min(shortest, len(soles))
        max_drift = max(max_drift, max(soles) - min(soles))
    return _check('foot-contacts', shortest >= 2 and max_drift <= 2,
                  f'Shortest support was {shortest} frames. Largest world-space sole drift was {max_drift} mm.')


def _blended_delta(walk_dx, guard_dx, weight):
    numerator = walk_dx * (100 - weight) + guard_dx * weight
    magnitude = (abs(numerator) + 50) // 100
    return -magnitude if numerator < 0 else magnitude


def _take(data, weights, end):
    positions, events = [], []
    body = 0
    return_frame = data['delay_frames'] + end
    for frame in range(return_frame + 1):
        delta = data['walk'][frame % len(data['walk'])]['dx_mm']
        local = frame - data['delay_frames']
        if 0 <= local < end:
            delta = _blended_delta(delta, data['guard'][local]['dx_mm'], weights[local])
            if local == data['marker']:
                events.append(frame)
        body += delta
        positions.append(body)
    return {'body_mm': positions, 'event_frames': events, 'walk_frame': return_frame}


def assess(exercise_id, submission):
    if exercise_id != 'motion-design':
        raise ValueError('Unknown motion-design exercise.')
    _read(submission)
    walk, guard, curve = (submission[key] for key in ('walk', 'guard', 'blend_pct'))
    delay, marker = submission['delay_frames'], submission['marker']
    weights = [curve[min(i, len(curve) - 1)] for i in range(len(guard))]
    increments = [b - a for a, b in zip([0] + curve, curve)]
    smooth = len(curve) <= len(guard) and curve[-1] == 100 and all(0 < step <= 50 for step in increments)
    # Keep angles in hundredths of a degree so the visible thresholds are exact.
    angles = [weight * sample['shield_deg'] for weight, sample in zip(weights, guard)]
    response = next((delay + i for i, angle in enumerate(angles) if angle >= 500), None)
    edges = [i for i, angle in enumerate(angles) if angle >= 6000 and (i == 0 or angles[i - 1] < 6000)]
    synchronized = edges == [marker] and angles[-1] < 6000
    ends = [len(guard), min(marker, len(guard)), min(marker + 1, len(guard))]
    expected = {case: _take(submission, weights, end) for case, end in zip(_CASES, ends)}
    travel = any(weight > 0 and sample['dx_mm'] != 0 for weight, sample in zip(weights, guard))
    pure_walk = 0
    deviates = False
    for i, position in enumerate(expected['complete']['body_mm']):
        pure_walk += walk[i % len(walk)]['dx_mm']
        deviates |= pure_walk != position
    position_errors = []
    if not travel:
        position_errors.append('The weighted guard contributes no authored travel.')
    if not deviates:
        position_errors.append('Every body position matches pure walking.')
    handoff_errors = []
    for case, calculated in expected.items():
        submitted = submission['takes'][case]
        positions = calculated['body_mm']
        if len(submitted['body_mm']) != len(positions):
            position_errors.append(f'{case} needs {len(positions)} body samples.')
        else:
            for frame, (actual, target) in enumerate(zip(submitted['body_mm'], positions)):
                if actual != target:
                    position_errors.append(f'{case} frame {frame} expected {target} mm and received {actual} mm.')
                    break
        if (submitted['event_frames'] != calculated['event_frames']
                or submitted['walk_frame'] != calculated['walk_frame']):
            handoff_errors.append(f'{case} should return at {calculated["walk_frame"]} with events {calculated["event_frames"]}.')
    return [
        _contacts(walk),
        _check('crossfade', smooth, f'Transfer steps were {increments} percentage points over a {len(guard)}-frame guard.'),
        _check('response', response is not None and response <= 2,
               f'First pose at or above 5 degrees was on global frame {response}.' if response is not None
               else 'The shield never reached 5 degrees.'),
        _check('event-sync', synchronized, f'Visible 60-degree upcrossings were {edges}, marker {marker}. '
               f'The final blended shield angle was {angles[-1] / 100:g} degrees.'),
        _check('root-motion', not position_errors, ' '.join(position_errors)
               or 'All three body traces match the integrated, blended root motion.'),
        _check('interruption', marker + 1 < len(guard) and not handoff_errors,
               ' '.join(handoff_errors) or (f'Complete, on-marker and after-marker returns were '
               f'{[take["walk_frame"] for take in expected.values()]}. '
               f'The clip has {max(0, len(guard) - marker - 1)} guard samples after the marker.')),
    ]
