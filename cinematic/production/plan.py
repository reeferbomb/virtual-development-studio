"""Compile a Cutscene Lab submission and scene bindings to data for Godot.

The unmodified submission must pass the current cutscenes rubric. Production
supports at most 7,200 frames and 120 seconds, eight actors and sixteen
cameras. The camera ID gameplay is reserved for the player's camera. Blocking uses
the lowercase Lab IDs idle, walk, run, aim, crouch and reload for the matching
title-case actor animations. Dialogue shares one voice and subtitle channel.
Blocking shares one animation channel per actor. On each channel, half-open
frame intervals may meet at an edit point but must not overlap.

Bindings have exactly two objects keyed by the corresponding declared IDs:
    cameras: {id: {position: [x,y,z], look_at: [x,y,z], fov: degrees}}
    actors:  {id: {position: [x,y,z], rotation_y: degrees}}
Coordinates are Godot world meters in [-1000, 1000], with Y up. The camera
needs at least 0.1 m of horizontal separation from its target. FOV is in
[1, 179] degrees and actor yaw is in [-360, 360] degrees.

The result has exactly schema_version (1), plan and bindings. Caller-owned
data is copied after validation. This function only reads JSON values.
"""

from collections import defaultdict
from copy import deepcopy
from math import hypot

from command_center.lab_design import _array, _object
from command_center.training_lab import _validate_data, assess_submission


_CLIPS = frozenset(('idle', 'walk', 'run', 'aim', 'crouch', 'reload'))


def _number(value, low, high, field):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f'{field} must be a finite number from {low} to {high}.')


def _position(value, field):
    _array(value, 3, 3, field)
    for coordinate in value:
        _number(coordinate, -1000, 1000, field)


def _validate_bindings(plan, bindings):
    _validate_data(bindings)
    _object(bindings, ('cameras', 'actors'), 'bindings')
    for group in ('cameras', 'actors'):
        _object(bindings[group], plan[group], f'bindings.{group}')

    for camera, binding in bindings['cameras'].items():
        _object(binding, ('position', 'look_at', 'fov'), camera)
        eye, target = binding['position'], binding['look_at']
        _position(eye, f'{camera}.position')
        _position(target, f'{camera}.look_at')
        if hypot(eye[0] - target[0], eye[2] - target[2]) < 0.1:
            raise ValueError(f'{camera}.look_at needs 0.1 m of horizontal separation.')
        _number(binding['fov'], 1, 179, f'{camera}.fov')

    for actor, binding in bindings['actors'].items():
        _object(binding, ('position', 'rotation_y'), actor)
        _position(binding['position'], f'{actor}.position')
        _number(binding['rotation_y'], -360, 360, f'{actor}.rotation_y')


def _check_overlaps(cues, channel):
    previous_end = 0
    for cue in sorted(cues, key=lambda row: row['start_frame']):
        if cue['start_frame'] < previous_end:
            raise ValueError(f'Overlapping {channel} at frame {cue["start_frame"]}.')
        previous_end = cue['end_frame']


def compile_plan(submission, bindings):
    """Return a validated v1 runtime document, or raise ValueError."""
    report = assess_submission('cutscenes', submission)
    failures = [check['id'] for check in report['checks'] if check['status'] != 'pass']
    if failures:
        raise ValueError(f'Cutscene Lab checks failed: {", ".join(failures)}.')
    if submission['frame_count'] > 7200:
        raise ValueError('Production supports at most 7200 frames.')
    if submission['frame_count'] > 120 * submission['fps']:
        raise ValueError('Production supports at most 120 seconds.')
    if len(submission['actors']) > 8 or len(submission['cameras']) > 16:
        raise ValueError('Production supports at most 8 actors and 16 cameras.')
    if 'gameplay' in submission['cameras']:
        raise ValueError('The camera ID gameplay is reserved for the player.')
    _validate_bindings(submission, bindings)
    _check_overlaps(submission['dialogue'], 'dialogue')
    by_actor = defaultdict(list)
    for cue in submission['blocking']:
        if cue['clip'] not in _CLIPS:
            raise ValueError(f'Unsupported production animation clip: {cue["clip"]}.')
        by_actor[cue['actor']].append(cue)
    for actor, cues in by_actor.items():
        _check_overlaps(cues, f'blocking for {actor}')

    return {'schema_version': 1, 'plan': deepcopy(submission), 'bindings': deepcopy(bindings)}
