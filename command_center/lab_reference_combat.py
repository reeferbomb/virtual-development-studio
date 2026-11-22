"""Replay an original two-player arcade encounter and a limited-knowledge NPC variant."""

from .lab_design import _array, _check, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'reference-combat', 'title': 'Combat reference study and responsive action systems',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Read the 2009 Modern Warfare 2 manual’s HUD and Special Ops sections. Distinguish a readable input '
        'opportunity, acknowledgment, the eventual effect and the opportunity to retry. Mark those moments '
        'in an original short challenge and predict how a second input during recovery is handled.',
        'Compare Battlefield’s squad roles and changing geometry. Trace how one player changes a shared '
        'object, how a teammate acts on the new state and when both learn the outcome. Distinguish the 2004 '
        'standalone Vietnam game from the 2010 Bad Company 2 Vietnam expansion when attributing mechanics.',
        'Study the original Naughty Bear designers’ account of a witness reacting to a changed prop. Give an '
        'original NPC local knowledge and a remembered event. Replay the same actions with the event hidden '
        'and identify the first moment when the two reaction histories diverge.',
        'Stage the combined rules with simple shapes and two input lanes. Keep model results, instrumented '
        'engine timing and what players actually noticed as separate evidence. Source notes and original '
        'design hypotheses are in command_center/reference_studies/COMBAT.md.',
    ],
    'deliverables': [
        'A primary-source observation and a distinct original design hypothesis for command feedback, shared '
        'world state and witness memory.',
        'A reusable challenge with command receipts, contact outcomes, a cooperative scoring rule and two '
        'witness traces under identical player inputs.',
    ],
    'verification': [
        'Probe the earliest legal repeat, a busy tap, an empty contact frame, the opening of a panel, '
        'and a teammate attempting to bank before and after the objective is ready.',
        'Mask the NPC’s view of only the opening. Confirm the score and physical events still resolve, then '
        'check the predicted change in reaction. Review perceived responsiveness and causality in a playable build.',
    ],
    'exercise': 'Ring the glasshouse bell through a changing panel and predict what a clockwork usher learns.',
}


def _event(frame, kind):
    return {'frame': frame, 'kind': kind}


_IMPACTS = ('miss', 'chip', 'open', 'chime')
_REACTIONS = ('work', 'inspect', 'cheer', 'search')
_LANES = ('tap', 'spark', 'bank', 'watch')
_RECEIPTS = ('accepted', 'busy', 'deposits', 'refused')

EXERCISES = [{
    'id': 'reference-combat', 'title': 'Catch a spark in the chime arcade',
    'brief': 'Simulate frames 0 through frames−1 (8–48 total). Each input lane lists its distinct frames in '
             'increasing order. Start with a two-hit glass panel, an unlit bell, the usher at work, and a ready '
             'ringer. Each frame first process tap. Accept if ready, schedule impact delay frames later (1–6), '
             'and become ready again recovery frames after impact (1–6). Reject earlier taps as busy. For this '
             'challenge set delay to at most 2, demonstrate a busy press and accept a repeat on its first legal '
             'frame. Next resolve any scheduled impact. No spark gives miss. With a spark, a panel of 2 becomes '
             '1 (chip), 1 becomes 0 (open), and at 0 the bell lights (chime). Finish all accepted actions and '
             'demonstrate all four impacts. The usher sees impacts only on watch frames. A seen open causes '
             'inspect. A seen chime causes cheer if already inspecting or cheering, otherwise search. On '
             'the same frame, after impact and witness processing, the second player can bank a lit bell once, '
             'extinguishing it, restoring panel 2, and returning the usher to work. An unlit bank is refused. '
             'Demonstrate both bank outcomes. Record only changes of usher state, in order, including two '
             'changes if a chime and a deposit share a frame. Predict accepted, busy, deposits and refused frame '
             'lists, every impact, final_panel, and the keeper changes. Repeat as hidden_opening with the same '
             'inputs and only the view of open events removed. Demonstrate a witnessed opening that changes '
             'a later reaction from search to cheer. All timings and scoring rules belong to this original arcade.',
    'criteria': [
        {'id': 'command-timing', 'label': 'Predict immediate input receipts, a busy press and an earliest legal repeat.'},
        {'id': 'changing-scene', 'label': 'Resolve each accepted tap and show a miss, a chip, an opening and a chime.'},
        {'id': 'team-objective', 'label': 'Use the second role to bank a lit bell and reject premature or repeated banking.'},
        {'id': 'witness-memory', 'label': 'Reproduce both usher histories and demonstrate a chime reaction changed by prior knowledge.'},
    ],
    'example': {
        'frames': 10, 'delay': 1, 'recovery': 1,
        'inputs': {'tap': [0, 1, 2, 4, 6], 'spark': [3, 5, 7], 'bank': [1, 8, 9], 'watch': [5, 7]},
        'expected': {
            'accepted': [0, 2, 4, 6], 'busy': [1],
            'impacts': [_event(1, 'miss'), _event(3, 'chip'), _event(5, 'open'), _event(7, 'chime')],
            'deposits': [8], 'refused': [1, 9], 'final_panel': 2,
            'keeper': [_event(5, 'inspect'), _event(7, 'cheer'), _event(8, 'work')],
            'hidden_opening': [_event(7, 'search'), _event(8, 'work')],
        },
    },
}]


def _frame_list(items, frames, name):
    _array(items, 0, frames, name)
    for frame in items:
        _integer(frame, 0, frames - 1, name)
    if items != sorted(set(items)):
        raise ValueError(f'{name} requires distinct frames in increasing order.')


def _read(data):
    _object(data, ('frames', 'delay', 'recovery', 'inputs', 'expected'), 'arcade submission')
    frames = data['frames']
    _integer(frames, 8, 48, 'frames')
    for field in ('delay', 'recovery'):
        _integer(data[field], 1, 6, field)
    _object(data['inputs'], _LANES, 'inputs')
    for name, lane in data['inputs'].items():
        _frame_list(lane, frames, name)
    expected = data['expected']
    _object(expected, (*_RECEIPTS, 'impacts', 'final_panel', 'keeper', 'hidden_opening'), 'expected')
    for name in _RECEIPTS:
        _frame_list(expected[name], frames, name)
    _integer(expected['final_panel'], 0, 2, 'final_panel')
    for name in ('impacts', 'keeper', 'hidden_opening'):
        _array(expected[name], 0, frames if name == 'impacts' else frames * 2, name)
        for event in expected[name]:
            _object(event, ('frame', 'kind'), name)
            _integer(event['frame'], 0, frames - 1, 'event frame')
            _choice(event['kind'], _IMPACTS if name == 'impacts' else _REACTIONS, 'event kind')


def _play(data):
    lanes = {name: set(times) for name, times in data['inputs'].items()}
    ready = 0
    due = None
    panel = 2
    lit = False
    result = {name: [] for name in _RECEIPTS}
    impacts = []
    for frame in range(data['frames']):
        if frame in lanes['tap']:
            if frame < ready:
                result['busy'].append(frame)
            else:
                result['accepted'].append(frame)
                due = frame + data['delay']
                ready = due + data['recovery']
        if frame == due:
            if frame not in lanes['spark']:
                kind = 'miss'
            elif panel:
                panel -= 1
                kind = 'chip' if panel else 'open'
            else:
                kind = 'chime'
                lit = True
            impacts.append(_event(frame, kind))
            due = None
        if frame in lanes['bank']:
            if lit:
                result['deposits'].append(frame)
                lit = False
                panel = 2
            else:
                result['refused'].append(frame)
    return dict(result, impacts=impacts, final_panel=panel)


def _witnesses(impacts, deposits, watching, hide_open):
    state = 'work'
    reactions = []
    chimes = {}
    events = {event['frame']: event['kind'] for event in impacts}
    for frame in sorted(set(events) | set(deposits)):
        kind = events.get(frame)
        if frame in watching:
            after = state
            if kind == 'open' and not hide_open:
                after = 'inspect'
            elif kind == 'chime':
                after = 'cheer' if state in ('inspect', 'cheer') else 'search'
                chimes[frame] = after
            if after != state:
                reactions.append(_event(frame, after))
                state = after
        if frame in deposits and state != 'work':
            reactions.append(_event(frame, 'work'))
            state = 'work'
    return reactions, chimes


def assess(exercise_id, submission):
    if exercise_id != 'reference-combat':
        raise ValueError('Unknown combat reference exercise.')
    _read(submission)
    actual = _play(submission)
    expected = submission['expected']
    accepted = actual['accepted']
    interval = submission['delay'] + submission['recovery']
    boundary = any(b - a == interval for a, b in zip(accepted, accepted[1:]))
    timed = bool(actual['busy']) and boundary and submission['delay'] <= 2
    impact_kinds = {row['kind'] for row in actual['impacts']}
    resolved = len(actual['impacts']) == len(accepted)
    changed = impact_kinds == set(_IMPACTS) and resolved
    banked = bool(actual['deposits'] and actual['refused'])
    watch = set(submission['inputs']['watch'])
    visible, informed = _witnesses(actual['impacts'], actual['deposits'], watch, False)
    hidden, unaware = _witnesses(actual['impacts'], actual['deposits'], watch, True)
    differences = [frame for frame in informed if informed[frame] == 'cheer' and unaware[frame] == 'search']
    return [
        _check('command-timing', timed and all(expected[k] == actual[k] for k in ('accepted', 'busy')),
               f'Accepted {accepted}, busy {actual["busy"]}. First-legal-frame repeat {boundary}. '
               f'Impact delay {submission["delay"]} frames.'),
        _check('changing-scene', changed and all(expected[k] == actual[k] for k in ('impacts', 'final_panel')),
               f'{len(actual["impacts"])}/{len(accepted)} taps resolved. Impact types {sorted(impact_kinds)}. '
               f'Final panel {actual["final_panel"]}.'),
        _check('team-objective', banked and all(expected[k] == actual[k] for k in ('deposits', 'refused')),
               f'Deposits {actual["deposits"]}. Refused bank requests {actual["refused"]}.'),
        _check('witness-memory', bool(differences) and expected['keeper'] == visible and expected['hidden_opening'] == hidden,
               f'Hiding the opening changed the chime reaction on frames {differences}. '
               f'Usher changed state {len(visible)} times in view and {len(hidden)} times with opening hidden.'),
    ]
