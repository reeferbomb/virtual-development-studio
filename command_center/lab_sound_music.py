"""Schedule symbolic foley, limited effect voices and a bar-quantized original score."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'sound-music', 'title': 'Sound effects, foley and adaptive music',
    'roles': ['content', 'gameplay', 'architecture', 'ui', 'verification'],
    'workflow': [
        'Start with an event and the information it conveys. Make original foley or use clearly licensed '
        'material. For a fictional blaster, design the transient, body and room tail separately. Link '
        'footsteps to actual contacts and surface types. Compare repeated takes and the transition at a seam.',
        'Design ambience in layers and position distinctive sources. Write an original motif for the score. '
        'Try retaining its phase as a rhythmic stem enters on a bar line. Treat an in-world radio as its own '
        'source with a location and level. Check that switching it off preserves the score’s transport.',
        'Decide which sounds deserve scarce voices at the busiest moment. Meter the buses, inspect the master '
        'peak, and audition whether critical information remains legible. Supply visual access to important '
        'non-speech events and independent volume controls. Test with sound off and on the target output.',
        'Use presentation_studies/SOUND_MUSIC.md for primary implementation sources and listening prompts. '
        'Keep rights records for production media. Use invented cue IDs and symbolic music in this exercise.',
    ],
    'deliverables': [
        'An event-to-cue list with material variations, source ownership or license, mix priority and accessible equivalents.',
        'An original motif, a score-state chart, separate radio routing and a transition audition at each boundary.',
        'A worst-case scheduling trace, peak report and target-device playback notes for the actual build.',
    ],
    'verification': [
        'Compare selected material takes and audible effects during overload. Check continued motif phase '
        'on the return to quiet. Mute the radio and replay the same inputs to isolate its contribution.',
        'Inspect real rendered transitions, level, timing, mix clarity, captions and listening comfort in '
        'a separate playback review. The data exercise carries no recordings or device measurements.',
    ],
    'exercise': 'Mix a ferry platform warning over footsteps, a radio and a score that changes on the bar.',
}


_SURFACES = ('timber', 'tile')
_LEVELS = ('room', 'motif', 'drive', 'radio', 'timber', 'tile', 'pop', 'alert')
_STATES = ('quiet', 'lift')

EXERCISES = [{
    'id': 'sound-music', 'title': 'Score the ferry platform on its busiest bar',
    'brief': 'Simulate 12–32 ticks indexed from 0 with four ticks per bar. Assign two distinct original cue '
             'IDs to each material (timber, tile), unique across materials; pop and alert are reserved. '
             'Alternate each material’s takes from its first, advancing on every step request even if culled. '
             'Use sorted distinct event ticks within each lane. At each tick expire effects started two ticks '
             'ago, then combine remaining voices and new requests. Keep at most two permanently: alert first, '
             'then pop, then steps, older first within each priority. List surviving IDs in that order every '
             'tick. Demonstrate all four foot takes audibly, a pop, and an alert competing for a slot that '
             'culls a lower priority cue. Give every alert exactly one same-tick visual marker, with no extras. '
             'Keep tick 0 quiet. Apply a request before checking the current tick for a bar line. On a '
             'bar line commit the latest requested state, otherwise wait. Enter lift and return to quiet via '
             'off-bar requests. Lift adds drive to a continuously running motif. Supply 3–8 motif pitch classes '
             '(0–11) using at least two different pitches. Report the initial state and each change with the motif '
             'pitch at tick modulo motif length. Show a transition away from the opening motif index. '
             'Room and motif always sound. Each retained effect adds its cue family level. Add drive in lift '
             'and radio only from radio.start inclusive to radio.end exclusive. Levels are positive integer '
             'linear peak bounds (1–100), full scale 100. Give the summed peak, earliest peak tick and peak '
             'with radio muted. Keep the normal peak at most 80 and demonstrate a reduction on mute. '
             'Mutes do not change score timing or the visual marker lane. These are symbolic inputs only.',
    'criteria': [
        {'id': 'material-foley', 'label': 'Make both variations of each material audible across the timeline.'},
        {'id': 'voice-priority', 'label': 'Predict the surviving voices and retain the warning under competition.'},
        {'id': 'adaptive-score', 'label': 'Schedule lift and return at bar lines and preserve the original motif phase.'},
        {'id': 'mix-headroom', 'label': 'Predict the conservative peak, its earliest tick and the isolated radio contribution.'},
        {'id': 'visual-cues', 'label': 'Provide exactly one same-tick visual equivalent for each audible warning.'},
    ],
    'example': {
        'ticks': 12,
        'materials': {'timber': ['plank_heel', 'plank_toe'], 'tile': ['tile_tap', 'tile_scuff']},
        'levels': {'room': 5, 'motif': 10, 'drive': 12, 'radio': 9, 'timber': 7, 'tile': 8, 'pop': 18, 'alert': 23},
        'steps': [{'tick': t, 'surface': s} for t, s in [(0, 'timber'), (2, 'tile'), (4, 'timber'),
                                                          (6, 'tile'), (8, 'timber'), (10, 'timber')]],
        'pop': [3, 5, 9], 'alert': [4], 'markers': [4],
        'radio': {'start': 3, 'end': 7}, 'motif': [0, 3, 7],
        'requests': [{'tick': 2, 'state': 'lift'}, {'tick': 6, 'state': 'quiet'}],
        'expected': {
            'voices': [['plank_heel'], ['plank_heel'], ['tile_tap'], ['pop', 'tile_tap'], ['alert', 'pop'],
                       ['alert', 'pop'], ['pop', 'tile_scuff'], ['tile_scuff'], ['plank_heel'],
                       ['pop', 'plank_heel'], ['pop', 'plank_toe'], ['plank_toe']],
            'changes': [{'tick': 0, 'state': 'quiet', 'pitch': 0}, {'tick': 4, 'state': 'lift', 'pitch': 3},
                        {'tick': 8, 'state': 'quiet', 'pitch': 7}],
            'peak': 77, 'peak_tick': 4, 'muted_radio_peak': 68,
        },
    },
}]


def _ordered(ticks, limit, name):
    _array(ticks, 0, limit, name)
    for tick in ticks:
        _integer(tick, 0, limit - 1, name)
    if ticks != sorted(set(ticks)):
        raise ValueError(f'{name} needs distinct ticks in increasing order.')


def _read(data):
    _object(data, ('ticks', 'materials', 'levels', 'steps', 'pop', 'alert', 'markers', 'radio', 'motif',
                   'requests', 'expected'), 'sound scene')
    limit = data['ticks']
    _integer(limit, 12, 32, 'ticks')
    _object(data['materials'], _SURFACES, 'materials')
    cue_ids = {'pop', 'alert'}
    for names in data['materials'].values():
        _array(names, 2, 2, 'material takes')
        for cue in names:
            _identifier(cue, 'cue ID')
            if cue in cue_ids:
                raise ValueError('Each material take requires a unique cue ID. Pop and alert are reserved.')
            cue_ids.add(cue)
    _object(data['levels'], _LEVELS, 'levels')
    for level in data['levels'].values():
        _integer(level, 1, 100, 'linear peak bound')
    for name in ('pop', 'alert', 'markers'):
        _ordered(data[name], limit, name)
    for lane, field, choices in [('steps', 'surface', _SURFACES), ('requests', 'state', _STATES)]:
        _array(data[lane], 0, limit, lane)
        for row in data[lane]:
            _object(row, ('tick', field), lane)
            _choice(row[field], choices, field)
        _ordered([row['tick'] for row in data[lane]], limit, lane)
    _object(data['radio'], ('start', 'end'), 'radio')
    _integer(data['radio']['start'], 0, limit - 1, 'radio.start')
    _integer(data['radio']['end'], data['radio']['start'] + 1, limit, 'radio.end')
    _array(data['motif'], 3, 8, 'motif')
    for note in data['motif']:
        _integer(note, 0, 11, 'pitch class')
    expected = data['expected']
    _object(expected, ('voices', 'changes', 'peak', 'peak_tick', 'muted_radio_peak'), 'expected')
    _array(expected['voices'], limit, limit, 'expected.voices')
    for row in expected['voices']:
        _array(row, 0, 2, 'surviving voices')
        for name in row:
            _identifier(name, 'predicted cue')
    _array(expected['changes'], 0, limit, 'expected.changes')
    for row in expected['changes']:
        _object(row, ('tick', 'state', 'pitch'), 'score change')
        _integer(row['tick'], 0, limit - 1, 'change tick')
        _choice(row['state'], _STATES, 'score state')
        _integer(row['pitch'], 0, 11, 'pitch class')
    _integer(expected['peak_tick'], 0, limit - 1, 'peak tick')
    for field in ('peak', 'muted_radio_peak'):
        _integer(expected[field], 0, 600, field)


def _effects(data):
    steps = {row['tick']: row['surface'] for row in data['steps']}
    takes = {material: 0 for material in _SURFACES}
    active, voices, totals = [], [], []
    heard = set()
    contested = False
    for tick in range(data['ticks']):
        # Tuple order encodes priority, then the start tick. Each lane sends at most one cue per tick.
        active = [voice for voice in active if voice[1] + 2 > tick]
        if tick in steps:
            material = steps[tick]
            cue = data['materials'][material][takes[material] % 2]
            takes[material] += 1
            active.append((2, tick, cue, material))
        for priority, family in enumerate(('alert', 'pop')):
            if tick in data[family]:
                active.append((priority, tick, family, family))
        active.sort()
        dropped, active = active[2:], active[:2]
        if any(voice[2] == 'alert' for voice in active) and any(voice[0] > 0 for voice in dropped):
            contested = True
        names = [v[2] for v in active]
        heard.update(names)
        voices.append(names)
        totals.append(sum(data['levels'][v[3]] for v in active))
    return voices, totals, heard, contested


def _score(data):
    requests = {row['tick']: row['state'] for row in data['requests']}
    state = pending = 'quiet'
    request_tick = 0
    changes, states, delayed = [], [], set()
    for tick in range(data['ticks']):
        if tick in requests:
            pending, request_tick = requests[tick], tick
        if tick % 4 == 0 and (tick == 0 or pending != state):
            state = pending
            changes.append({'tick': tick, 'state': state, 'pitch': data['motif'][tick % len(data['motif'])]})
            if request_tick % 4 != 0:
                delayed.add(state)
        states.append(state)
    return changes, states, delayed


def assess(exercise_id, submission):
    if exercise_id != 'sound-music':
        raise ValueError('Unknown sound and music exercise.')
    _read(submission)
    expected, levels, radio = (submission[k] for k in ('expected', 'levels', 'radio'))
    voices, fx_peaks, heard, contested = _effects(submission)
    changes, states, delayed = _score(submission)
    muted = [levels['room'] + levels['motif'] + fx + (levels['drive'] if state == 'lift' else 0)
             for fx, state in zip(fx_peaks, states)]
    mix = [value + (levels['radio'] if radio['start'] <= tick < radio['end'] else 0)
           for tick, value in enumerate(muted)]
    peak, muted_peak = max(mix), max(muted)
    peak_tick = mix.index(peak)
    materials = {name for names in submission['materials'].values() for name in names}
    mismatch = next((i for i, (a, b) in enumerate(zip(voices, expected['voices'])) if a != b), None)
    motif = submission['motif']
    varied = len(set(motif)) > 1 and any(row['tick'] % len(motif) != 0 for row in changes[1:])
    return [
        _check('material-foley', materials <= heard, f'{len(materials & heard)}/4 material variations reached a voice.'),
        _check('voice-priority', contested and 'pop' in heard and mismatch is None,
               (f'First differing tick {mismatch} should play {voices[mismatch]}. ' if mismatch is not None else 'All voice traces match. ')
               + f'An alert held a slot during a lower-priority loss: {contested}.'),
        _check('adaptive-score', delayed == set(_STATES) and varied and changes == expected['changes']
               and changes[0]['state'] == 'quiet',
               f'Committed states and pitches by tick {[(c["tick"], c["state"], c["pitch"]) for c in changes]}.'),
        _check('mix-headroom', peak <= 80 and muted_peak < peak and
               (peak, peak_tick, muted_peak) == (expected['peak'], expected['peak_tick'], expected['muted_radio_peak']),
               f'Conservative peak {peak}/100 first occurs at tick {peak_tick}. Radio-muted peak {muted_peak}/100.'),
        _check('visual-cues', bool(submission['alert']) and submission['markers'] == submission['alert'],
               f'Warning ticks {submission["alert"]}. Visual marker ticks {submission["markers"]}.'),
    ]
