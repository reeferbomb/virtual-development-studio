"""Replay original platform routes with bounded integer momentum and a targeted tool gate."""

from collections import defaultdict, deque

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _integer


_ID = 'reference-traversal'

TRACK = {
    'id': _ID, 'title': 'Reference study in platforming, momentum and dungeon navigation',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Compare a side-view jump with a depth-view jump in Super Mario Bros. and Super Mario 3D Land. '
        'Identify the information available before commitment, at the apex and at landing. Sketch an original '
        'destination silhouette and ground cue, then test the camera with stereoscopic depth disabled.',
        'Study how a prepared launch in Sonic and an alternate route change the next decision. Block out '
        'a recovery route with more landing tolerance and a shorter route that rewards carried speed. Measure '
        'both from the same start and include the time spent setting up a jump.',
        'Study camera targeting, equipment and floor maps in The Legend of Zelda: Ocarina of Time. In an original '
        'room, show an inactive mechanism early, provide a tool elsewhere and let the player return. Give the '
        'target a unique silhouette and keep a visible landmark when the camera disengages.',
        'Record the work, edition, source and observed behavior separately from the proposed design. Test your '
        'own geometry, controller and camera in a build. Check restarts, wrong-target feedback and routes '
        'through earlier rooms after the tool becomes available.',
    ],
    'deliverables': [
        'Source-linked observations and three original design hypotheses. See command_center/reference_studies/TRAVERSAL.md.',
        'Jump envelope, alternate-route traces, target interaction and map of the tool pickup and gate.',
        'Recorded camera and input tests with landing errors, commitment points, wrong targets and recovery notes.',
    ],
    'verification': [
        'Recompute each launch speed, horizontal landing margin and route time from the same start state. '
        'Test both under- and overshooting the landing surface.',
        'Search reachable movement states without issuing the tool. Separately verify that the intended routes '
        'work when the tool and correct target are available. Verify depth perception and input feel in live play.',
    ],
    'exercise': 'Deliver a barometer through a weather station by a forgiving route and a quicker precision route.',
}


def _edge(key, origin, destination, ground, accel, air, landing, target=None):
    return {'id': key, 'from': origin, 'to': destination, 'ground': ground, 'accel': accel,
            'air': air, 'landing': landing, 'target': target}


EXERCISES = [{
    'id': _ID, 'title': 'Cross a wind station and focus its pressure relay',
    'brief': 'Build a directed course with 4–32 uniquely named edges. Start, tool_room and goal are distinct. '
             'Each fresh run begins at start with speed 1 and no tool. On an edge, spend ground ticks (0–12) '
             'changing speed by accel (−2 to 2) per tick. Clamp speed to 1–8, then keep it for air ticks (1–12) '
             'and carry it onto the next edge. Horizontal landing distance is speed × air. The integer landing '
             'interval [near, far] includes both endpoints (0–128). Margin is the smaller distance to either '
             'edge of this interval. Outside the interval the jump misses. Every successful jump costs ground + air '
             'ticks. Gain the tool on arrival at tool_room. Entering an edge with a named target requires the '
             'tool before launch and focus on that exact target. Use null focus on ordinary edges. Supply steady '
             'and swift runs with 1–32 distinct edge IDs per route, their predicted total ticks and minimum '
             'landing margin. Each run ends at its first arrival at goal. Swift must finish sooner with less '
             'minimum margin and use a different route. Both must carry the tool through a gate. The goal must '
             'be unreachable if the pickup is withheld. This is a discrete, one-axis exercise with original geometry.',
    'criteria': [
        {'id': 'course', 'label': 'Bind distinct start, pickup and destination rooms to the course.'},
        {'id': 'landings', 'label': 'Complete two continuous routes with carried speed and valid landings.'},
        {'id': 'tool-gate', 'label': 'Use the correct target after pickup and exclude a feasible bypass.'},
        {'id': 'route-tradeoff', 'label': 'Trade landing tolerance for a faster path from the same starting state.'},
        {'id': 'predictions', 'label': 'Reconcile total ground and air time and the narrowest landing on each route.'},
    ],
    'example': {
        'start': 'wheelhouse', 'tool_room': 'gauge_bench', 'goal': 'wind_clock',
        'edges': [
            _edge('shelter_ramp', 'wheelhouse', 'lee_shelf', 2, 1, 2, [4, 8]),
            _edge('survey_steps', 'lee_shelf', 'gauge_bench', 3, -1, 3, [2, 5]),
            _edge('draft_chute', 'wheelhouse', 'gust_rail', 2, 2, 2, [9, 12]),
            _edge('sail_gap', 'gust_rail', 'gauge_bench', 0, 0, 2, [10, 11]),
            _edge('relay_span', 'gauge_bench', 'wind_clock', 1, 0, 2, [1, 11], 'pressure_socket'),
        ],
        'runs': {
            'steady': {'steps': [{'edge': 'shelter_ramp', 'focus': None}, {'edge': 'survey_steps', 'focus': None},
                                 {'edge': 'relay_span', 'focus': 'pressure_socket'}], 'ticks': 13, 'margin': 1},
            'swift': {'steps': [{'edge': 'draft_chute', 'focus': None}, {'edge': 'sail_gap', 'focus': None},
                                {'edge': 'relay_span', 'focus': 'pressure_socket'}], 'ticks': 9, 'margin': 0},
        },
    },
}]


def _optional_id(value, field):
    if value is not None:
        _identifier(value, field)


def _parse(data):
    _object(data, ('start', 'tool_room', 'goal', 'edges', 'runs'), 'Traversal course')
    for field in ('start', 'tool_room', 'goal'):
        _identifier(data[field], field)
    _array(data['edges'], 4, 32, 'edges')
    edges = {}
    for edge in data['edges']:
        _object(edge, ('id', 'from', 'to', 'ground', 'accel', 'air', 'landing', 'target'), 'edge')
        for field in ('id', 'from', 'to'):
            _identifier(edge[field], field)
        if edge['id'] in edges:
            raise ValueError('Each course edge needs a unique ID.')
        _optional_id(edge['target'], 'target')
        for field, low, high in [('ground', 0, 12), ('accel', -2, 2), ('air', 1, 12)]:
            _integer(edge[field], low, high, field)
        _array(edge['landing'], 2, 2, 'landing')
        for endpoint in edge['landing']:
            _integer(endpoint, 0, 128, 'landing endpoint')
        if edge['landing'][0] > edge['landing'][1]:
            raise ValueError('Landing endpoints must be ordered from near to far.')
        edges[edge['id']] = edge
    _object(data['runs'], ('steady', 'swift'), 'runs')
    for run in data['runs'].values():
        _object(run, ('steps', 'ticks', 'margin'), 'run')
        _array(run['steps'], 1, 32, 'steps')
        _integer(run['ticks'], 0, 768, 'predicted ticks')
        _integer(run['margin'], 0, 64, 'predicted minimum margin')
        used = set()
        for step in run['steps']:
            _object(step, ('edge', 'focus'), 'step')
            _identifier(step['edge'], 'edge ID')
            _optional_id(step['focus'], 'focus')
            if step['edge'] not in edges or step['edge'] in used:
                raise ValueError('A run must use existing, distinct edge IDs.')
            used.add(step['edge'])
    return edges


def _jump(speed, edge):
    launch = min(8, max(1, speed + edge['ground'] * edge['accel']))
    distance = launch * edge['air']
    near, far = edge['landing']
    return launch, min(distance - near, far - distance)


def _trace(data, edges, run):
    room, speed = data['start'], 1
    tool = used_gate = False
    ticks, margins = 0, []
    issue = ''
    for step in run['steps']:
        edge = edges[step['edge']]
        if room == data['goal'] or edge['from'] != room:
            issue = f'{edge["id"]} does not continue the course.'
            break
        if edge['target'] != step['focus'] or (edge['target'] is not None and not tool):
            issue = f'{edge["id"]} has an unavailable tool or incorrect focus.'
            break
        speed, margin = _jump(speed, edge)
        if margin < 0:
            issue = f'{edge["id"]} misses its landing by {-margin} units.'
            break
        ticks += edge['ground'] + edge['air']
        margins.append(margin)
        room = edge['to']
        tool |= room == data['tool_room']
        used_gate |= edge['target'] is not None
    if not issue and room != data['goal']:
        issue = 'The route ends before the destination.'
    return {'issue': issue, 'ticks': ticks, 'margin': min(margins) if margins else None, 'gate': used_gate}


def _bypass(data, edges):
    # Without the pickup, reachable states differ only by room and carried speed.
    exits = defaultdict(list)
    for edge in edges.values():
        if edge['target'] is None:
            exits[edge['from']].append(edge)
    initial = (data['start'], 1)
    pending, seen = deque([initial]), {initial}
    while pending:
        room, speed = pending.popleft()
        if room == data['goal']:
            return True
        for edge in exits[room]:
            launch, margin = _jump(speed, edge)
            state = (edge['to'], launch)
            if margin >= 0 and state not in seen:
                pending.append(state)
                seen.add(state)
    return False


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown traversal reference exercise.')
    edges = _parse(submission)
    endpoints = {room for edge in edges.values() for room in (edge['from'], edge['to'])}
    landmarks = {submission['start'], submission['tool_room'], submission['goal']}
    course_ok = len(landmarks) == 3 and landmarks <= endpoints
    runs = submission['runs']
    results = {name: _trace(submission, edges, run) for name, run in runs.items()}
    steady, swift = results['steady'], results['swift']
    complete = not steady['issue'] and not swift['issue']
    bypass = _bypass(submission, edges)
    predictions = all(result['ticks'] == runs[name]['ticks'] and result['margin'] == runs[name]['margin']
                      for name, result in results.items())
    details = ' '.join(f'{name} {result["issue"] or "reached the destination."}' for name, result in results.items())
    return [
        _check('course', course_ok, f'{len(landmarks)} distinct named landmarks for {len(endpoints)} course rooms.'),
        _check('landings', course_ok and complete, details),
        _check('tool-gate', course_ok and complete and steady['gate'] and swift['gate'] and not bypass,
               f'{sum(result["gate"] for result in results.values())} runs used a gate. '
               f'Goal reachable with the pickup withheld: {bypass}.'),
        _check('route-tradeoff', complete and swift['ticks'] < steady['ticks'] and swift['margin'] < steady['margin'],
               f'Steady and swift measured {steady["ticks"]}/{swift["ticks"]} ticks with minimum landing margins '
               f'{steady["margin"]}/{swift["margin"]}.'),
        _check('predictions', complete and predictions, 'Compared the reported ticks and minimum margin '
               'against the successful transitions on each route.'),
    ]
