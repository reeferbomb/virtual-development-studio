"""Sample a bounded retargeted dialogue beat from declared animation curves."""

from collections import Counter
from fractions import Fraction

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _integer


_ID = 'character-performance'
_ROLES = {
    'jaw': 'percent', 'lip_seal': 'percent', 'brow': 'percent',
    'eyes': 'degrees', 'head': 'degrees', 'hand': 'degrees',
    'hips': 'mm', 'foot_x': 'mm', 'foot_z': 'mm',
}
_LIMITS = {'percent': (0, 100), 'degrees': (-180, 180), 'mm': (-10000, 10000)}
_CLOSED = ('m', 'b', 'p')

TRACK = {
    'id': _ID, 'title': 'Character performance and retargeting',
    'roles': ['content', 'gameplay', 'verification'],
    'workflow': [
        'Give the actor an intention and a change of thought. Mark the listening beat, gaze target, '
        'operative word and recovery. Block distinct poses and verify the silhouette at the gameplay camera.',
        'Work from a timed dialogue take. Mark selected closures, vowel openings, stress and pauses. '
        'Shape the jaw and lips separately. Blend neighboring mouth shapes through the word, then layer '
        'brows, cheeks and blinks to support the thought without obscuring articulation.',
        'Stage a change of attention with the eyes, then the head. Test the eyeline against the other '
        'character in both camera angles. Give gestures preparation, an accent tied to intention, and '
        'a settling pose. Track the pelvis over the support foot to check weight and ground contact.',
        'Inspect source and target joint hierarchies, rest poses, local axes, units, joint limits and '
        'facial controls. Calibrate the retarget map in a neutral pose, then try extreme shapes. Check '
        'left and right, foot planting and gaze after body, face and procedural layers are blended.',
    ],
    'deliverables': [
        'A beat sheet tied to the dialogue take, with listen, emphasis and recovery poses, eyeline, '
        'phoneme landmarks and contact frames.',
        'A source-to-target control map and a target-rig clip. Include the take and rig revisions, '
        'a synchronized facial close-up, a full-body view with foot markers, and a retake list.',
    ],
    'verification': [
        'Sample the compiled target curves at intended cue frames. Check control units and axis signs, '
        'mouth closures, vowel openings, gaze lead, accent pose and drift of the planted foot.',
        'Listen with picture at normal speed, then scrub critical frames. Inspect deformation, coarticulation, '
        'contact, expressiveness and the transition back into gameplay on the real target rig.',
    ],
    'exercise': 'Retarget and sample a short dialogue performance with a gaze shift, stressed word and planted gesture.',
}


_EXAMPLE_RIG = [
    ('jaw_drop', 'jaw', 1), ('lips_press', 'lip_seal', 1), ('brow_lift', 'brow', 1),
    ('eye_pan', 'eyes', -1), ('neck_turn', 'head', 1), ('arm_lift', 'hand', 1),
    ('pelvis_up', 'hips', 1), ('shoe_world_x', 'foot_x', 1), ('shoe_world_z', 'foot_z', 1),
]

EXERCISES = [{
    'id': _ID, 'title': 'Point out a mark to a scene partner',
    'brief': (
        'Author a beat in which a character spots a mark, says a word and lifts a hand. Supply 12–120 fps '
        'and 8–240 frames. Frame zero is rest. Set 0 < look < prepare < accent < settle < frame_count. '
        'Use a signed target yaw 15–35 degrees from straight ahead. The look must lead the accent by '
        '40–400 ms. Mark at least one m, b or p closure and one aa opening, in strict frame order from '
        'look through settle inclusive. These are selected landmarks, not a full phonetic transcription. '
        'Map the nine example roles to unique local control IDs and curves. Percent weights are 0–100 '
        'with sign +1. Degrees are −180 to 180 and millimetres −10000 to 10000. A signed control can '
        'use +1 or −1 to convert its local axis. Each curve has 2–32 ordered [frame, value] integer '
        'keys spanning zero through frame_count−1. Sample intermediate frames by linear interpolation. '
        'At closure jaw ≤20 and lip_seal ≥70. At aa jaw ≥70 and lip_seal ≤20. Brow is ≤20 at rest, ≥55 '
        'at accent and ≤20 at settle. Eyes and head each start within 3 degrees of zero. At look the head '
        'is still within 3 of zero. Combined head and relative eye yaw are within 4 degrees of target at '
        'look, accent and settle. At accent and settle the eyes are within 4 of neutral as the head follows. '
        'Hand angles are within 3 of zero at rest, ≤−5 at prepare, ≥35 at accent and within 5 of zero at '
        'settle. Hips dip at least 20 mm from rest at prepare and settle within 5 mm of rest. From rest '
        'through settle the planted foot stays within 10 mm of its starting horizontal position. These '
        'thresholds describe this staged exercise. The example is synthetic and the lab reads no audio or rigs.'
    ),
    'criteria': [
        {'id': 'retarget-map', 'label': 'Bind every semantic role to a distinct local control with the expected unit, sign and curve.'},
        {'id': 'curve-coverage', 'label': 'Supply ordered, full-span keys within the declared channel units.'},
        {'id': 'beat-sheet', 'label': 'Order the pose and speech cues, include both mouth shapes and give the eyes time to lead.'},
        {'id': 'lip-sync', 'label': 'Sample the jaw and lip seal at each selected closure and open vowel.'},
        {'id': 'expression', 'label': 'Lift the brow on the accent and recover to the low-intensity expression.'},
        {'id': 'gaze', 'label': 'Lead with the eyes, let the head take the turn and hold the target through recovery.'},
        {'id': 'gesture', 'label': 'Prepare the hand in the opposite direction, lift on the accent and settle.'},
        {'id': 'weight-contact', 'label': 'Lower and recover the hips while the planted foot stays within its drift allowance.'},
    ],
    'example': {
        'fps': 24, 'frame_count': 48,
        'beats': {'look': 8, 'prepare': 12, 'accent': 17, 'settle': 36},
        'target_yaw_deg': 24,
        'phonemes': [{'frame': 14, 'sound': 'm'}, {'frame': 17, 'sound': 'aa'}],
        'rig': [dict(id=control, role=role, unit=_ROLES[role], sign=sign) for control, role, sign in _EXAMPLE_RIG],
        'curves': {
            'jaw_drop': [[0, 0], [14, 8], [17, 82], [24, 12], [47, 0]],
            'lips_press': [[0, 0], [14, 90], [17, 6], [24, 0], [47, 0]],
            'brow_lift': [[0, 10], [16, 58], [18, 70], [36, 12], [47, 10]],
            'eye_pan': [[0, 0], [8, -23], [17, -1], [47, -1]],
            'neck_turn': [[0, 0], [8, 1], [17, 23], [47, 23]],
            'arm_lift': [[0, 0], [12, -8], [17, 44], [36, 2], [47, 0]],
            'pelvis_up': [[0, 870], [12, 842], [17, 868], [36, 872], [47, 870]],
            'shoe_world_x': [[0, 120], [12, 123], [27, 124], [47, 120]],
            'shoe_world_z': [[0, -95], [12, -93], [27, -91], [47, -95]],
        },
    },
}]


def _validate(data):
    _object(data, ('fps', 'frame_count', 'beats', 'target_yaw_deg', 'phonemes', 'rig', 'curves'), 'Performance')
    _integer(data['fps'], 12, 120, 'fps')
    _integer(data['frame_count'], 8, 240, 'frame_count')
    _integer(data['target_yaw_deg'], -180, 180, 'target_yaw_deg')
    _object(data['beats'], ('look', 'prepare', 'accent', 'settle'), 'beats')
    for frame in data['beats'].values():
        _integer(frame, -240, 480, 'Beat frame')
    _array(data['phonemes'], 0, 32, 'phonemes')
    for cue in data['phonemes']:
        _object(cue, ('frame', 'sound'), 'Speech cue')
        _integer(cue['frame'], -240, 480, 'Speech frame')
        if cue['sound'] not in (*_CLOSED, 'aa'):
            raise ValueError('Use m, b, p or aa as the speech landmark.')

    _array(data['rig'], 0, 16, 'rig')
    for control in data['rig']:
        _object(control, ('id', 'role', 'unit', 'sign'), 'Rig control')
        for field in ('id', 'role', 'unit'):
            _identifier(control[field], field)
        if control['role'] not in _ROLES or control['unit'] not in _LIMITS:
            raise ValueError('Unknown performance role or control unit.')
        _integer(control['sign'], -1, 1, 'Control sign')

    curves = data['curves']
    if type(curves) is not dict or len(curves) > 16:
        raise ValueError('Use an object of at most 16 local control curves.')
    for control, keys in curves.items():
        _identifier(control, 'Curve ID')
        _array(keys, 2, 32, 'curve keys')
        for key in keys:
            _array(key, 2, 2, 'curve key')
            _integer(key[0], -240, 480, 'Key frame')
            _integer(key[1], -10000, 10000, 'Key value')


def _sample(keys, sign):
    # Integer cue frames can lie between sparse authoring keys.
    values = []
    for (start, left), (end, right) in zip(keys, keys[1:]):
        for frame in range(start, end):
            values.append(sign * Fraction(left * (end - frame) + right * (frame - start), end - start))
    values.append(sign * keys[-1][1])
    return values


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown character performance exercise.')
    _validate(submission)
    frames, fps = submission['frame_count'], submission['fps']
    look, prepare, accent, settle = (submission['beats'][k] for k in ('look', 'prepare', 'accent', 'settle'))
    target, phonemes = submission['target_yaw_deg'], submission['phonemes']
    rig, curves = submission['rig'], submission['curves']

    by_id = {control['id']: control for control in rig}
    units_ok = all(c['unit'] == _ROLES[c['role']] and c['sign'] in ((1,) if c['unit'] == 'percent' else (-1, 1))
                   for c in rig)
    bound = (Counter(c['role'] for c in rig) == Counter(_ROLES.keys()) and len(by_id) == len(rig)
             and by_id.keys() == curves.keys() and units_ok)
    invalid = []
    for ctrl, keys in curves.items():
        lo, hi = _LIMITS[by_id[ctrl]['unit']] if ctrl in by_id else (-10000, 10000)
        if (keys[0][0] != 0 or keys[-1][0] != frames - 1 or
                any(a[0] >= b[0] for a, b in zip(keys, keys[1:])) or
                any(not lo <= value <= hi for frame, value in keys)):
            invalid.append(ctrl)
    timing = (0 < look < prepare < accent < settle < frames and 15 <= abs(target) <= 35
              and 40 * fps <= 1000 * (accent - look) <= 400 * fps)
    speech_frames = [cue['frame'] for cue in phonemes]
    sounds = {cue['sound'] for cue in phonemes}
    sheet_ok = (timing and 'aa' in sounds and not sounds.isdisjoint(_CLOSED)
                and all(look <= f <= settle for f in speech_frames)
                and all(a < b for a, b in zip(speech_frames, speech_frames[1:])))
    checks = [
        _check('retarget-map', bound, f'{len(by_id)} distinct local controls for {len(_ROLES)} required roles. '
               f'Units and axis signs compatible={units_ok}, curve IDs match={by_id.keys() == curves.keys()}.'),
        _check('curve-coverage', bool(curves) and not invalid,
               'Invalid frame span, order or value on ' + ', '.join(invalid) + '.' if invalid
               else f'{len(curves)} curves span frames 0–{frames - 1}.'),
        _check('beat-sheet', sheet_ok, f'{len(phonemes)} speech landmarks. Pose order, yaw and eye lead valid={timing}. '
               f'Look-to-accent separation {(accent - look) * 1000 / fps:.1f} ms.'),
    ]
    if not (bound and not invalid and sheet_ok):
        for criterion in EXERCISES[0]['criteria'][3:]:
            checks.append(_check(criterion['id'], False, 'Sampling requires a valid rig map, full-span curves and beat sheet.'))
        return checks

    pose = {c['role']: _sample(curves[c['id']], c['sign']) for c in rig}
    bad_mouth = []
    for cue in phonemes:
        frame = cue['frame']
        jaw, seal = pose['jaw'][frame], pose['lip_seal'][frame]
        match = jaw <= 20 and seal >= 70 if cue['sound'] in _CLOSED else jaw >= 70 and seal <= 20
        if not match:
            bad_mouth.append(frame)
    brow, hand = pose['brow'], pose['hand']
    eyes, head = pose['eyes'], pose['head']
    aim_error = max(abs(eyes[f] + head[f] - target) for f in (look, accent, settle))
    gaze_ok = (max(abs(eyes[0]), abs(head[0]), abs(head[look])) <= 3 and aim_error <= 4
               and max(abs(eyes[accent]), abs(eyes[settle])) <= 4)
    hips, x, z = pose['hips'], pose['foot_x'], pose['foot_z']
    drift_sq = max((x[f] - x[0]) ** 2 + (z[f] - z[0]) ** 2 for f in range(settle + 1))
    drop, recovery = hips[0] - hips[prepare], abs(hips[settle] - hips[0])
    checks.extend([
        _check('lip-sync', not bad_mouth, f'{len(phonemes)} phoneme landmarks sampled. Mismatched frames {bad_mouth}.'),
        _check('expression', brow[0] <= 20 and brow[accent] >= 55 and brow[settle] <= 20,
               f'Brow weights at rest, accent and settle: {brow[0]}, {brow[accent]}, {brow[settle]} percent.'),
        _check('gaze', gaze_ok, f'Head at eye lead {head[look]} degrees. Maximum aim error {float(aim_error):.2f} degrees.'),
        _check('gesture', abs(hand[0]) <= 3 and hand[prepare] <= -5 and hand[accent] >= 35 and abs(hand[settle]) <= 5,
               f'Hand angles at rest, preparation, accent and settle: {hand[0]}, {hand[prepare]}, {hand[accent]}, {hand[settle]} degrees.'),
        _check('weight-contact', drop >= 20 and recovery <= 5 and drift_sq <= 100,
               f'Hip drop {float(drop):.2f} mm, recovery error {float(recovery):.2f} mm, '
               f'maximum planted-foot drift {float(drift_sq) ** 0.5:.2f} mm.'),
    ])
    return checks
