"""Score an editorial cut list and a declarative gameplay handoff without running an engine."""

from collections import Counter
from unicodedata import category

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _integer


TRACK = {
    'id': 'cutscenes', 'title': 'Cutscene direction and cinematic implementation',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Mark the trigger, dramatic turn and player objective in the script. Give each spoken line a stable ID '
        'before recording scratch dialogue. Draw storyboard panels with subject, screen direction and eyeline.',
        'Time a previz animatic against scratch sound at the delivery frame rate. Choose where to cut on action '
        'or hold for a reaction. Keep panel, line and shot IDs in the edit notes so revisions can be traced.',
        'Block actors and props at scene scale. Place and bind cameras in the engine timeline, check lens and '
        'axis continuity, then key blocking, performance and focus. Light faces and silhouettes for each angle.',
        'Edit camera cuts with picture and dialogue together. Place voice, ambience, music transitions and '
        'subtitles against the locked edit. Preview the mix, speaker attribution and caption readability.',
        'Bind the sequence to a guarded gameplay trigger. Coordinate camera and input ownership, story-state '
        'changes and audio/UI cleanup on completion, skip and interruption. Hand off the sequence and bindings '
        'to gameplay, the caption sheet to UI and representative playback cases to verification.',
    ],
    'deliverables': [
        'Annotated script, numbered storyboard panels, timed animatic and shot list with the target frame rate.',
        'Engine timeline with camera cuts, actor bindings, blocking clips, lighting notes, voice cues and caption sheet.',
        'Entry and exit-state table, playback captures and a handoff naming the sequence revision and outstanding retakes.',
    ],
    'verification': [
        'Check edit coverage frame by frame and reconcile cue windows with the edit. In a separate playback pass, '
        'inspect composition, exposure, eyelines, clipping, edit rhythm, lip sync, mix and caption legibility.',
        'In the actual build, trigger from gameplay, skip during a voiced line, interrupt at a cut, retry and '
        'finish normally. Check camera/input return, subtitle and audio cleanup, plus the resulting story flag.',
    ],
    'exercise': 'Cut a short voiced encounter with continuous camera coverage and hand control back to the player on three exit paths.',
}


_RESTORE = ('camera', 'input', 'voice', 'subtitles')
_PATHS = ('complete', 'skip', 'interrupt')

EXERCISES = [{
    'id': 'cutscenes', 'title': 'Edit a voiced reveal and return control to gameplay',
    'brief': 'Use a fixed integer fps (1–120) and whole-frame start/end indices; start is inclusive and end exclusive. '
             'Round the frame count divided by fps to the nearest millisecond, rounding ties up. List camera cuts '
             'in edit order and declare camera and actor bindings by ID. Include blocking clips and spoken lines '
             'with one verbatim subtitle per line for this single-language edit. The trigger requires the initial '
             'story state. Complete and skip advance it; interruption returns to it for retry. Each path restores '
             'camera, input, voice and subtitles. These checks inspect timeline and handoff data only.',
    'criteria': [
        {'id': 'timebase', 'label': 'Match the declared duration to the frame count and playback rate.'},
        {'id': 'shot-coverage', 'label': 'Cut between at least two cameras with continuous, ordered coverage from frame zero to the end.'},
        {'id': 'cue-bounds', 'label': 'Keep each cut, blocking clip, spoken line and subtitle in a positive frame window inside the sequence.'},
        {'id': 'bindings', 'label': 'Resolve every camera and actor reference and start each spoken line during a blocking clip for its speaker.'},
        {'id': 'subtitle-sync', 'label': 'Match each unique spoken line to exactly one verbatim subtitle with the same frame window.'},
        {'id': 'restoration', 'label': 'Explicitly restore the camera, input, voice and subtitle channels on all three exit paths.'},
        {'id': 'story-state', 'label': 'Advance the guarded story state on completion and skip, and preserve it for retry after interruption.'},
    ],
    'example': {
        'fps': 24, 'frame_count': 144, 'duration_ms': 6000,
        'cameras': ['dock_wide', 'mira_close'], 'actors': ['mira', 'keeper'],
        'shots': [
            {'camera': 'dock_wide', 'start_frame': 0, 'end_frame': 48},
            {'camera': 'mira_close', 'start_frame': 48, 'end_frame': 108},
            {'camera': 'dock_wide', 'start_frame': 108, 'end_frame': 144},
        ],
        'blocking': [
            {'actor': 'keeper', 'clip': 'raise_lantern', 'start_frame': 0, 'end_frame': 48},
            {'actor': 'mira', 'clip': 'turn_to_channel', 'start_frame': 44, 'end_frame': 112},
        ],
        'dialogue': [
            {'line': 'signal', 'speaker': 'keeper', 'text': 'One light left.', 'start_frame': 6, 'end_frame': 42},
            {'line': 'reply', 'speaker': 'mira', 'text': 'Then we keep it burning.', 'start_frame': 54, 'end_frame': 104},
        ],
        'subtitles': [
            {'line': 'signal', 'text': 'One light left.', 'start_frame': 6, 'end_frame': 42},
            {'line': 'reply', 'text': 'Then we keep it burning.', 'start_frame': 54, 'end_frame': 104},
        ],
        'trigger': {'event': 'enter_dock', 'requires': 'signal_dark', 'advances_to': 'signal_lit'},
        'exits': {
            'complete': {'restore': list(_RESTORE), 'next_state': 'signal_lit'},
            'skip': {'restore': list(_RESTORE), 'next_state': 'signal_lit'},
            'interrupt': {'restore': list(_RESTORE), 'next_state': 'signal_dark'},
        },
    },
}]


_LANES = {
    'shots': ('camera',),
    'blocking': ('actor', 'clip'),
    'dialogue': ('line', 'speaker', 'text'),
    'subtitles': ('line', 'text'),
}


def _bindings_list(data, name):
    values = data[name]
    _array(values, 1, 32, name)
    for value in values:
        _identifier(value, name)
    if len(set(values)) != len(values):
        raise ValueError(f'{name} contains a duplicate binding ID.')
    return set(values)


def _validate_cues(data):
    for lane, properties in _LANES.items():
        _array(data[lane], 0, 64, lane)
        for cue in data[lane]:
            _object(cue, ('start_frame', 'end_frame', *properties), lane)
            for field in ('start_frame', 'end_frame'):
                _integer(cue[field], -72000, 144000, field)
            for field in properties:
                if field == 'text':
                    _text(cue[field], 240, field)
                    if not any(category(char)[0] in 'LNPS' for char in cue[field]):
                        raise ValueError(f'{lane} needs visible text.')
                else:
                    _identifier(cue[field], field)


def _shot_coverage(shots, frames):
    camera_count = len({cut['camera'] for cut in shots})
    cursor = invalid_cuts = 0
    for cut in shots:
        start, end = cut['start_frame'], cut['end_frame']
        if start != cursor or end <= start:
            invalid_cuts += 1
        cursor = end
    return _check('shot-coverage', camera_count >= 2 and invalid_cuts == 0 and cursor == frames,
                  f'{len(shots)} shots use {camera_count} cameras. {invalid_cuts} shots start away from the '
                  f'previous end or have nonpositive length. Final cut ends at frame {cursor} of {frames}.')


def _cue_bounds(data, frames):
    bad = {lane: sum(not 0 <= cue['start_frame'] < cue['end_frame'] <= frames for cue in data[lane])
           for lane in _LANES}
    counts = ', '.join(f'{count} {lane}' for lane, count in bad.items())
    return _check('cue-bounds', not any(bad.values()),
                  f'Invalid windows in the {frames}-frame timeline: {counts}.')


def _binding_check(data, cameras, actors):
    blocking = data['blocking']
    missing_camera = sum(cut['camera'] not in cameras for cut in data['shots'])
    missing_actor = sum(clip['actor'] not in actors for clip in blocking)
    uncovered_lines = 0
    for line in data['dialogue']:
        speaker, start = line['speaker'], line['start_frame']
        if speaker not in actors or not any(clip['actor'] == speaker and
                                            clip['start_frame'] <= start < clip['end_frame'] for clip in blocking):
            uncovered_lines += 1
    return _check('bindings', bool(blocking) and not any((missing_camera, missing_actor, uncovered_lines)),
                  f'{missing_camera} unbound camera cuts, {missing_actor} unbound clips in {len(blocking)} '
                  f'blocking cues, {uncovered_lines} spoken lines without a bound actor clip at entry.')


def _subtitle_sync(lines, captions):
    line_counts = Counter(row['line'] for row in lines)
    caption_counts = Counter(row['line'] for row in captions)
    by_line = {row['line']: row for row in captions}
    matched = 0
    for row in lines:
        key = row['line']
        if line_counts[key] == caption_counts[key] == 1:
            matched += all(row[field] == by_line[key][field] for field in ('text', 'start_frame', 'end_frame'))
    return _check('subtitle-sync', matched > 0 and matched == len(lines) == len(captions),
                  f'{matched} unique line/caption pairs agree on text and frames across '
                  f'{len(lines)} spoken lines and {len(captions)} subtitles.')


def _exit_checks(trigger, exits):
    _object(trigger, ('event', 'requires', 'advances_to'), 'trigger')
    for key, value in trigger.items():
        _identifier(value, key)
    _object(exits, _PATHS, 'exits')
    unclean, wrong_state = [], []
    for path in _PATHS:
        result = exits[path]
        _object(result, ('restore', 'next_state'), path)
        _identifier(result['next_state'], 'next_state')
        restore = result['restore']
        _array(restore, 0, len(_RESTORE), 'restore')
        if any(type(resource) is not str or resource not in _RESTORE for resource in restore):
            raise ValueError('Unknown channel in restore list.')
        missing = [resource for resource in _RESTORE if resource not in restore]
        if missing:
            unclean.append(f'{path} missing {", ".join(missing)}')
        target = trigger['requires'] if path == 'interrupt' else trigger['advances_to']
        if result['next_state'] != target:
            wrong_state.append(f'{path} targets {result["next_state"]}, expected {target}')
    advances = trigger['requires'] != trigger['advances_to']
    return [
        _check('restoration', not unclean, '. '.join(unclean) or 'All four channels restored on all three planned exits.'),
        _check('story-state', advances and not wrong_state,
               f'Trigger {trigger["event"]} guards {trigger["requires"]} and advances to {trigger["advances_to"]}. '
               + ('. '.join(wrong_state) or 'All three exits target their expected state.')),
    ]


def assess(exercise_id, submission):
    if exercise_id != 'cutscenes':
        raise ValueError('Unknown cutscene exercise.')
    _object(submission, ('fps', 'frame_count', 'duration_ms', 'cameras', 'actors', *_LANES, 'trigger', 'exits'),
            'Cutscene submission')
    fps, frames, duration = (submission[key] for key in ('fps', 'frame_count', 'duration_ms'))
    _integer(fps, 1, 120, 'fps')
    _integer(frames, 1, 72000, 'frame_count')
    _integer(duration, 1, 72000000, 'duration_ms')
    cameras = _bindings_list(submission, 'cameras')
    actors = _bindings_list(submission, 'actors')
    _validate_cues(submission)
    expected_ms = (2000 * frames + fps) // (2 * fps)
    return [
        _check('timebase', duration == expected_ms,
               f'{frames} frames at {fps} fps round to {expected_ms} ms; the edit declares {duration} ms.'),
        _shot_coverage(submission['shots'], frames),
        _cue_bounds(submission, frames),
        _binding_check(submission, cameras, actors),
        _subtitle_sync(submission['dialogue'], submission['subtitles']),
        *_exit_checks(submission['trigger'], submission['exits']),
    ]
