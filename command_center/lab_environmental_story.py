"""Check where a player can encounter evidence and which event orders it supports."""

from collections import deque
from itertools import permutations

from .lab_design import _array, _check, _identifier, _object, _text, _walk


# Developer accounts: Smith & Worch, https://www.worch.com/2010/03/11/gdc-2010/
# Gaynor & Freeman, https://www.gdcvault.com/play/1025178/Level-Design-Workshop-Designing-for
# Gaynor & Craig, https://www.gdcvault.com/play/1022112/Level-Design-in-a-Day
TRACK = {
    'id': 'environmental-storytelling', 'title': 'Environmental storytelling and non-linear discovery',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Study a scene from a game you can legitimately play. List what you saw or heard before explaining '
        'what it meant. In their Tacoma level-design talk, Steve Gaynor and Nina Freeman discuss how players '
        'discover story in different orders. Trace two approaches to a reveal and identify what each approach '
        'allows the player to know when they arrive. For Gone Home, study Gaynor and environment artist Kate '
        'Craig’s account of constructing a believable home. Ask which details establish how a room was used '
        'before asking which reveal an unusual event.',
        'Write a new question about an original place and the people who used it. Work backward from the '
        'last change. Who needed to move something, what was in their way, and what mark would their work leave? '
        'In a greenhouse, roof putty dripping across a wheel rut suggests a sequence. The motive for moving '
        'the rack can remain open.',
        'Block out the room at player eye height. Decide what reads from the doorway, what inspection adds '
        'and what can be missed. A second route can show a different consequence of the same event. Reserve '
        'a detour for detail that changes a player’s interpretation without making the main thread disappear.',
        'Borrow the question or design technique from a reference and change its setting, history, room plan, '
        'props and wording. Create original assets and dialogue. Record which observation from the reference '
        'led you to test a particular relationship in your own scene.',
        'Walk the space silently from both entrances, including the quickest exit. Check that scale, lighting, '
        'contrast and an accessible inspection method preserve the clues. In a separately authorized playtest, '
        'ask “What do you think happened?” and “What in the room suggested that?” Preserve plausible alternative '
        'interpretations of motive when the evidence only establishes an order.',
    ],
    'deliverables': [
        'A reference-analysis sheet distinguishing observations from interpretations, and an original scene '
        'brief with a core question, a chronology and a second plausible explanation of intent.',
        'A route map and clue list linking each physical trace to its location and the events it can support. '
        'Include the fast route, an optional discovery and captures from actual player viewpoints.',
    ],
    'verification': [
        'Test entry, detours, backtracking and a direct exit. Identify a concrete route when a required '
        'inference depends on a missed room or a written explanation.',
        'Inspect the authored traces in the actual build. A graph proves an opportunity to encounter evidence. '
        'Readability, accessibility and a player’s interpretation require separate observation.',
    ],
    'exercise': 'Build two routes through an original place that both support an implied event order, '
                'with a fuller history available to an observant explorer.',
}


def _clue(kind, observation, before, after):
    return {'kind': kind, 'observation': observation, 'before': before, 'after': after}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Reconstruct the glasshouse after the storm',
    'brief': 'Author 4–16 rooms and a history of 3–5 distinct event IDs, earliest first. The core fact is an '
             'ordered pair of different events. Give each room a unique ID, 0–4 distinct directed exits and '
             'one clue or null. Each clue has a brief observation (1–180 characters), kind (placement, wear, '
             'damage, residue, repair or note) and before/after event IDs. All IDs are lowercase identifiers. '
             'Visiting a room makes its annotated clue available. Entry and exit differ. Reaching the exit '
             'ends the walk, so it has no clue or outgoing edges. Every room must be on a possible entry-to-exit '
             'walk. Submit two simple complete routes, each with a room absent from the other. All annotations '
             'must agree with the history, and one actual walk must collect physical evidence for every '
             'consecutive event pair. On every possible finishing walk, physical clues must imply the core '
             'fact through intermediate events. For that test, ignore notes and direct statements of the core '
             'pair. The model checks declared evidence links. People must judge whether the observations '
             'really support them and whether those traces are noticeable in play.',
    'criteria': [
        {'id': 'exploration', 'label': 'Place every room on a walk from entry to exit.'},
        {'id': 'alternate-routes', 'label': 'Trace two legal routes with a distinct room on each.'},
        {'id': 'chronology', 'label': 'Support the full written chronology with compatible physical traces on one walk.'},
        {'id': 'core-inference', 'label': 'Support the indirect core inference on every route to the exit.'},
    ],
    'example': {
        'entry': 'mud_yard', 'exit': 'footbridge',
        'history': ['hail_fell', 'rack_moved', 'roof_patched', 'orchids_returned'],
        'core': ['hail_fell', 'roof_patched'],
        'rooms': [
            {'id': 'mud_yard', 'exits': ['tool_bay', 'glazing_bay'],
             'clue': _clue('wear', 'Glass-rack wheel ruts cut through the round hail pits in the clay.',
                           'hail_fell', 'rack_moved')},
            {'id': 'tool_bay', 'exits': ['orchid_bench', 'footbridge'],
             'clue': _clue('residue', 'A hardened drip from the roof patch crosses a wheel rut in the doorway.',
                           'rack_moved', 'roof_patched')},
            {'id': 'orchid_bench', 'exits': ['tool_bay', 'footbridge'],
             'clue': _clue('placement', 'The orchid pots leave damp rings on the cured patch compound below the roof seam.',
                           'roof_patched', 'orchids_returned')},
            {'id': 'glazing_bay', 'exits': ['footbridge'],
             'clue': _clue('repair', 'Roof putty has dripped onto the glass rack in its new bay and set around its rim.',
                           'rack_moved', 'roof_patched')},
            {'id': 'footbridge', 'exits': [], 'clue': None},
        ],
        'routes': [['mud_yard', 'tool_bay', 'orchid_bench', 'footbridge'], ['mud_yard', 'glazing_bay', 'footbridge']],
    },
}]

_KINDS = ('placement', 'wear', 'damage', 'residue', 'repair', 'note')


def _ids(rows, low, high, label):
    _array(rows, low, high, label)
    for value in rows:
        _identifier(value, label)
    if len(set(rows)) != len(rows):
        raise ValueError(f'{label} requires distinct IDs.')


def _read_rooms(rooms, history):
    _array(rooms, 4, 16, 'rooms')
    graph, physical, inconsistent = {}, {}, {}
    for room in rooms:
        _object(room, ('id', 'exits', 'clue'), 'room')
        name = room['id']
        _identifier(name, 'room ID')
        if name in graph:
            raise ValueError('Room IDs must be unique.')
        _ids(room['exits'], 0, 4, 'room exits')
        graph[name] = room['exits']
        clue = room['clue']
        if clue is None:
            continue
        _object(clue, ('kind', 'observation', 'before', 'after'), 'clue')
        if clue['kind'] not in _KINDS:
            raise ValueError('Unknown clue kind.')
        _text(clue['observation'], 180, 'clue observation')
        pair = (clue['before'], clue['after'])
        for event in pair:
            _identifier(event, 'clue event')
            if event not in history:
                raise ValueError('A clue references an unknown event.')
        if history.index(pair[0]) >= history.index(pair[1]):
            inconsistent[name] = clue['kind']
        elif clue['kind'] != 'note':
            physical[name] = pair
    if any(target not in graph for neighbors in graph.values() for target in neighbors):
        raise ValueError('A room exit references an unknown room.')
    return graph, physical, inconsistent


def _complete_history(graph, entry, exit_room, history, physical):
    # A known total order is uniquely established when each adjacent pair has
    # been observed. At five events the mask has at most sixteen possible values.
    bits = {pair: 1 << i for i, pair in enumerate(zip(history, history[1:]))}
    full = (1 << len(bits)) - 1
    initial = (entry, bits.get(physical.get(entry), 0))
    queue, seen = deque([initial]), {initial}
    while queue:
        room, mask = queue.popleft()
        if room == exit_room and mask == full:
            return True
        for nxt in graph[room]:
            state = (nxt, mask | bits.get(physical.get(nxt), 0))
            if state not in seen:
                seen.add(state)
                queue.append(state)
    return False


def _ambiguous_route(graph, entry, exit_room, history, core, physical):
    # If even one ordering with the core reversed fits an entire route, that
    # route lacks sufficient evidence. At most 60 alternative orders need a walk.
    for order in permutations(history):
        if order.index(core[0]) < order.index(core[1]):
            continue
        blocked = {room for room, pair in physical.items()
                   if pair != core and order.index(pair[0]) > order.index(pair[1])}
        if entry in blocked:
            continue
        compatible = {room: [n for n in exits if n not in blocked] for room, exits in graph.items()}
        _, parents = _walk(compatible, entry)
        if exit_room in parents:
            path = [exit_room]
            while path[-1] != entry:
                path.append(parents[path[-1]])
            return list(reversed(path))
    return None


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown environmental storytelling exercise.')
    _object(submission, ('entry', 'exit', 'history', 'core', 'rooms', 'routes'), 'story map')
    history = submission['history']
    _ids(history, 3, 5, 'history')
    _ids(submission['core'], 2, 2, 'core fact')
    core = tuple(submission['core'])
    if any(event not in history for event in core):
        raise ValueError('The core fact references an unknown event.')
    graph, physical, inconsistent = _read_rooms(submission['rooms'], history)
    entry, exit_room = submission['entry'], submission['exit']
    _ids([entry, exit_room], 2, 2, 'entry and exit')
    if entry not in graph or exit_room not in graph:
        raise ValueError('Entry and exit must name declared rooms.')
    if graph[exit_room] or any(room['id'] == exit_room and room['clue'] is not None for room in submission['rooms']):
        raise ValueError('The terminal room cannot have clues or exits.')

    reverse = {room: [] for room in graph}
    for room, neighbors in graph.items():
        for neighbor in neighbors:
            reverse[neighbor].append(room)
    reachable, _ = _walk(graph, entry)
    can_finish, _ = _walk(reverse, exit_room)
    accessible = reachable.keys() & can_finish.keys()

    routes = submission['routes']
    _array(routes, 2, 2, 'routes')
    legal = 0
    for route in routes:
        _ids(route, 2, len(graph), 'simple walkthrough')
        legal += (route[0] == entry and route[-1] == exit_room
                  and all(b in graph.get(a, ()) for a, b in zip(route, route[1:])))
    first, second = map(set, routes)
    distinct = bool(first - second and second - first)

    full = _complete_history(graph, entry, exit_room, history, physical)
    ambiguous = _ambiguous_route(graph, entry, exit_room, history, core, physical)
    conflicts = [r for r in accessible if r in inconsistent and inconsistent[r] != 'note']
    inferable = (not conflicts and exit_room in reachable and history.index(core[0]) < history.index(core[1])
                 and ambiguous is None)
    if conflicts:
        evidence = 'Physical clues on a finishing walk conflict with the history in ' + ', '.join(sorted(conflicts)) + '.'
    elif ambiguous:
        evidence = 'The core order can be reversed on this walk through ' + ' → '.join(ambiguous) + '.'
    elif inferable:
        evidence = 'Every finishing walk rules out the reverse order using indirect physical evidence.'
    else:
        evidence = 'The core order needs to match the history and the exit must be reachable.'
    return [
        _check('exploration', len(accessible) == len(graph), f'{len(accessible)}/{len(graph)} rooms lie on a finishing walk.'),
        _check('alternate-routes', legal == 2 and distinct,
               f'{legal}/2 submitted routes are legal. Each needs at least one room absent from the other.'),
        _check('chronology', not inconsistent and full, f'{len(inconsistent)} clues conflict with the history. '
               + ('A single walk gathers every adjacent physical link.' if full else 'No single walk gathers every adjacent physical link.')),
        _check('core-inference', inferable, evidence),
    ]
