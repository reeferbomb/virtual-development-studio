"""Replay an original freight yard under two inherited promises and two bridge layouts."""

from collections import deque

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'reference-narrative', 'title': 'Narrative choices, contextual abilities and changing places',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Use reference_studies/NARRATIVE.md to study each Mass Effect game separately. Examine how the first '
        'game communicates a reply, how the second accounts for a companion’s history, and how the third '
        'carries preparation into a shared outcome. Name the edition when comparing readiness systems.',
        'Study what the surroundings tell a player about their ability in The Darkness (2007), and which '
        'landmarks and connections change between the realms of Soul Reaver (1999). Record the documented '
        'mechanic and write a separate hypothesis about what a player might understand or feel.',
        'Author a new setting, cast and spatial layout. Write one early commitment and two later scenes '
        'that use it. Show each consequence through an available action, an identifiable character or '
        'a changed part of the environment. Include the case where a promised helper is absent.',
        'Sketch a location in two playable states. Mark where a change can be requested, what it costs and '
        'what happens when the request fails. Use a stable landmark for orientation and distinct feedback '
        'for a wrong location, an inaccessible route and insufficient resources.',
    ],
    'deliverables': [
        'Credited reference notes, a new scene brief and a map of the two layouts with commitment-dependent handoffs.',
        'A continuity table and replay traces for both histories, including refused requests and the exact final outcome.',
    ],
    'verification': [
        'Replay the same map with opposite histories. Search alternate legal paths for an unintended handoff '
        'or a shortcut that bypasses the layout change. Check that a refused action leaves resources intact.',
        'In the playable build, ask an authorized tester what they committed to, why a route opened and '
        'which action would work after a refusal. An abstract trace establishes rule behavior.',
    ],
    'exercise': 'Route a freight lift for two earlier promises using a shared switching yard and a limited pressure supply.',
}

_PLEDGES = ('bindery', 'pottery')
_LAYOUTS = ('low', 'high')
_RESULTS = ('moved', 'shifted', 'no_valve', 'pressure_low', 'no_link', 'other_pledge', 'wrong_layout', 'closed')


def _link(to, layout, pledge='either'):
    return {'to': to, 'layout': layout, 'pledge': pledge}


def _step(action, room, layout, charge, result):
    return {'action': action, 'room': room, 'layout': layout, 'charge': charge, 'result': result}


def _example_run(recipient):
    other = 'pottery_dock' if recipient == 'bindery_dock' else 'bindery_dock'
    return [
        _step('shift', 'yard', 'low', 2, 'no_valve'),
        _step('gantry', 'gantry', 'low', 2, 'moved'),
        _step('junction', 'gantry', 'low', 2, 'wrong_layout'),
        _step('shift', 'gantry', 'high', 0, 'shifted'),
        _step('shift', 'gantry', 'high', 0, 'pressure_low'),
        _step('junction', 'junction', 'high', 0, 'moved'),
        _step(other, 'junction', 'high', 0, 'other_pledge'),
        _step(recipient, recipient, 'high', 0, 'moved'),
    ]


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Keep yesterday’s freight promise',
    'brief': 'Author 4–16 rooms with unique lowercase IDs (reserve shift for the control). Give each a boolean '
             'valve and up to four directed links to distinct rooms. Each link names a layout (low, high or both) '
             'and a pledge (bindery, pottery or either). Design distinct terminal docks, one per pledge, with no '
             'links or valves. Both runs inherit the named pledge and start in the same nonterminal entry, in low '
             'layout with 1–12 charge. At a valve, shift toggles the layout and spends cost (1–6 charge). '
             'Without a valve it returns no_valve. At a valve with too little charge it returns pressure_low. '
             'A room-ID command moves along its link. Test missing link, pledge and layout in that order; the '
             'corresponding refusals are no_link, other_pledge and wrong_layout. All refusals preserve state. '
             'Arrival at either dock ends the run. Later commands return closed. Predict action result, room, '
             'layout and remaining charge after each of 1–32 commands per pledge. End both traces on their '
             'promised delivery, use low-only and high-only links in each, and demonstrate a paid shift in each. '
             'Across the traces demonstrate both shift refusals, a wrong-layout link and an opposite-pledge gate. '
             'Across all possible paths, only the promised dock may be reachable and every delivery must require a shift.',
    'criteria': [
        {'id': 'continuity', 'label': 'Keep only the promised dock reachable for each inherited choice.'},
        {'id': 'layouts', 'label': 'Make a shift necessary and demonstrate both layouts through restricted links.'},
        {'id': 'ability', 'label': 'Use pressure at a valve in both traces and demonstrate both reasons for refusal.'},
        {'id': 'handoffs', 'label': 'End each observed run on its promised dock and demonstrate the opposite-pledge gate.'},
        {'id': 'predictions', 'label': 'Match the simulated room, layout, charge and result after every command.'},
    ],
    'example': {
        'entry': 'yard', 'charge': 2, 'cost': 2, 'docks': {'bindery': 'bindery_dock', 'pottery': 'pottery_dock'},
        'rooms': [
            {'id': 'yard', 'valve': False, 'links': [_link('gantry', 'low')]},
            {'id': 'gantry', 'valve': True, 'links': [_link('junction', 'high')]},
            {'id': 'junction', 'valve': False,
             'links': [_link('bindery_dock', 'both', 'bindery'), _link('pottery_dock', 'both', 'pottery')]},
            {'id': 'bindery_dock', 'valve': False, 'links': []},
            {'id': 'pottery_dock', 'valve': False, 'links': []},
        ],
        'runs': {'bindery': _example_run('bindery_dock'), 'pottery': _example_run('pottery_dock')},
    },
}]


def _read(data):
    _object(data, ('entry', 'charge', 'cost', 'docks', 'rooms', 'runs'), 'dispatch yard')
    _integer(data['charge'], 1, 12, 'charge')
    _integer(data['cost'], 1, 6, 'cost')
    _array(data['rooms'], 4, 16, 'rooms')
    links, valves = {}, set()
    for row in data['rooms']:
        _object(row, ('id', 'valve', 'links'), 'room')
        name = row['id']
        _identifier(name, 'room ID')
        if name in links or name == 'shift':
            raise ValueError('Use unique room IDs and reserve shift for the control.')
        if type(row['valve']) is not bool:
            raise ValueError('valve must be boolean.')
        if row['valve']:
            valves.add(name)
        _array(row['links'], 0, 4, 'links')
        links[name] = {}
        for edge in row['links']:
            _object(edge, ('to', 'layout', 'pledge'), 'link')
            target = edge['to']
            _identifier(target, 'destination')
            _choice(edge['layout'], (*_LAYOUTS, 'both'), 'link layout')
            _choice(edge['pledge'], (*_PLEDGES, 'either'), 'link pledge')
            if target in links[name]:
                raise ValueError('A room cannot have two links to the same destination.')
            links[name][target] = edge
    if any(target not in links for neighbors in links.values() for target in neighbors):
        raise ValueError('Each link must name a declared room.')
    docks = data['docks']
    _object(docks, _PLEDGES, 'docks')
    for dock in docks.values():
        _identifier(dock, 'dock')
        if dock not in links or links[dock] or dock in valves:
            raise ValueError('Each dock must be a declared terminal room without a valve.')
    _identifier(data['entry'], 'entry')
    if len(set(docks.values())) != 2 or data['entry'] in docks.values() or data['entry'] not in links:
        raise ValueError('Use a declared entry and two distinct docks, all different.')
    _object(data['runs'], _PLEDGES, 'runs')
    for steps in data['runs'].values():
        _array(steps, 1, 32, 'run steps')
        for step in steps:
            _object(step, ('action', 'room', 'layout', 'charge', 'result'), 'prediction')
            _identifier(step['action'], 'action')
            _identifier(step['room'], 'predicted room')
            _choice(step['layout'], _LAYOUTS, 'predicted layout')
            _integer(step['charge'], 0, 12, 'predicted charge')
            _choice(step['result'], _RESULTS, 'predicted result')
    return links, valves


def _advance(state, action, pledge, data, links, valves):
    room, layout, charge = state
    if room in data['docks'].values():
        return state, 'closed'
    if action == 'shift':
        if room not in valves:
            return state, 'no_valve'
        if charge < data['cost']:
            return state, 'pressure_low'
        return (room, 'high' if layout == 'low' else 'low', charge - data['cost']), 'shifted'
    edge = links[room].get(action)
    if edge is None:
        return state, 'no_link'
    if edge['pledge'] not in ('either', pledge):
        return state, 'other_pledge'
    if edge['layout'] not in ('both', layout):
        return state, 'wrong_layout'
    return (action, layout, charge), 'moved'


def _reachable(pledge, data, links, valves):
    start = (data['entry'], 'low', data['charge'])
    pending, seen = deque([start]), {start}
    while pending:
        state = pending.popleft()
        for action in (*links[state[0]], 'shift'):
            nxt, _ = _advance(state, action, pledge, data, links, valves)
            if nxt not in seen:
                seen.add(nxt)
                pending.append(nxt)
    return {(room, charge) for room, _, charge in seen if room in data['docks'].values()}


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown narrative reference exercise.')
    links, valves = _read(submission)
    continuity = layout_runs = paid_runs = deliveries = predictions = commands = 0
    results = set()
    reach_details = []
    first_error = ''
    for pledge in _PLEDGES:
        dock = submission['docks'][pledge]
        reachable = _reachable(pledge, submission, links, valves)
        reachable_docks = {room for room, _ in reachable}
        continuity += reachable_docks == {dock}
        reach_details.append(f'{pledge} can reach {", ".join(sorted(reachable_docks)) or "no dock"}')
        state = (submission['entry'], 'low', submission['charge'])
        moved_layouts, local_results = set(), set()
        for i, step in enumerate(submission['runs'][pledge], 1):
            previous = state
            action = step['action']
            state, result = _advance(state, action, pledge, submission, links, valves)
            local_results.add(result)
            commands += 1
            if result == 'moved':
                moved_layouts.add(links[previous[0]][action]['layout'])
            if (step['room'], step['layout'], step['charge'], step['result']) == (*state, result):
                predictions += 1
            elif not first_error:
                first_error = f' {pledge} step {i} ends at {state[0]} in {state[1]} with {state[2]} charge ({result}).'
        paid_runs += 'shifted' in local_results
        # Charge can only fall on a shift, so a terminal visit at full charge is a bypass.
        needs_shift = reachable and all(charge < submission['charge'] for _, charge in reachable)
        layout_runs += bool(needs_shift and set(_LAYOUTS) <= moved_layouts)
        deliveries += state[0] == dock and 'closed' not in local_results
        results.update(local_results)

    refusals = len(results & {'no_valve', 'pressure_low'})
    return [
        _check('continuity', continuity == 2, '. '.join(reach_details) + '.'),
        _check('layouts', layout_runs == 2 and 'wrong_layout' in results,
               f'{layout_runs}/2 histories require a shift and traverse low-only and high-only links. '
               + ('Observed a layout refusal.' if 'wrong_layout' in results else 'Missing a layout refusal.')),
        _check('ability', paid_runs == 2 and refusals == 2,
               f'{paid_runs}/2 histories paid for a shift and {refusals}/2 distinct shift refusals were demonstrated.'),
        _check('handoffs', deliveries == 2 and 'other_pledge' in results,
               f'{deliveries}/2 traces stop upon the promised arrival. '
               + ('Observed the opposite-pledge gate.' if 'other_pledge' in results else 'Missing an opposite-pledge refusal.')),
        _check('predictions', predictions == commands, f'{predictions}/{commands} post-command predictions match.' + first_error),
    ]
