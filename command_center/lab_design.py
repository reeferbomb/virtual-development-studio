"""Deterministic, data-only practical assessments for three academy design tracks."""

from collections import defaultdict, deque
import re


EXERCISES = [
    {
        'id': 'game-design',
        'title': 'Balance a five-trip scavenging loop',
        'brief': 'Tune five trips with an integer fuel cost (1–20) and salvage (0–20). '
                 'Pay the cost before collecting salvage. A player who cannot pay stops immediately. '
                 'Test the same schedule with 8, 6 and 2 units of starting fuel.',
        'criteria': [
            {'id': 'standard', 'label': 'Finish all five trips from 8 fuel with 6–10 fuel left.'},
            {'id': 'lean', 'label': 'Finish all five trips from 6 fuel with at least 1 left.'},
            {'id': 'stranded', 'label': 'A player starting with 2 fuel cannot pay for trip 1 or trip 2.'},
            {'id': 'pacing', 'label': 'Include at least one net gain and one net loss.'},
        ],
        'example': {'rounds': [
            {'cost': 3, 'salvage': 4}, {'cost': 4, 'salvage': 3}, {'cost': 5, 'salvage': 7},
            {'cost': 4, 'salvage': 2}, {'cost': 3, 'salvage': 3},
        ]},
    },
    {
        'id': 'storytelling',
        'title': 'Trace a branching salvage quest',
        'brief': 'Write 1–24 dialogue nodes with unique IDs. Each node has a line, required facts, '
                 'facts it grants and up to four labeled choices leading to other node IDs. '
                 'IDs and facts use 1–32 lowercase letters, digits, hyphens or underscores, '
                 'starting with a letter. Limit lines to 240 characters, labels to 100 and the quest to '
                 'eight distinct facts. The player starts '
                 'with no facts, checks requirements on entry, then keeps all granted facts. '
                 'A node with no choices is an ending.',
        'criteria': [
            {'id': 'reachability', 'label': 'Resolve every destination and make every written node playable.'},
            {'id': 'continuity', 'label': 'Use a fact-dependent line and establish its facts on every offered path.'},
            {'id': 'agency', 'label': 'Offer a choice whose playable options lead to different sets of endings.'},
            {'id': 'resolution', 'label': 'Keep an ending within reach from every playable story state.'},
        ],
        'example': {'start': 'arrival', 'nodes': [
            {'id': 'arrival', 'line': 'The ferryman bars the sluice. A bell rings below.',
             'requires': [], 'grants': [], 'choices': [
                 {'label': 'Pull the ferryman from the breach', 'to': 'rescue'},
                 {'label': 'Slip through the floodgate', 'to': 'escape'}]},
            {'id': 'rescue', 'line': 'He gives you his bell and asks you to call the fleet.',
             'requires': [], 'grants': ['bell'], 'choices': [
                 {'label': 'Ring the bell', 'to': 'harbor'}]},
            {'id': 'harbor', 'line': 'Your bell guides the first hull home.',
             'requires': ['bell'], 'grants': [], 'choices': []},
            {'id': 'escape', 'line': 'You reach dry land alone as the last lantern gutters.',
             'requires': [], 'grants': [], 'choices': []},
        ]},
    },
    {
        'id': 'level-design',
        'title': 'Block out a two-route arena',
        'brief': 'Submit 3–24 equally wide grid rows, each 3–24 tiles wide. Use one S for spawn, '
                 'one G for goal, # for walls, . for floor and C for walkable cover positions. '
                 'Each horizontal or vertical move takes one step.',
        'criteria': [
            {'id': 'reachability', 'label': 'Reach the goal and every walkable tile from spawn.'},
            {'id': 'alternate-routes', 'label': 'Connect spawn and goal with two routes sharing no interior tile.'},
            {'id': 'spacing', 'label': 'Measure 6–18 steps on the shortest spawn-to-goal route.'},
            {'id': 'cover', 'label': 'Place at least two cover positions, each 3+ steps from spawn, '
                                    '2+ from goal and 3+ from every other cover position.'},
        ],
        'example': {'grid': ['###########', '#...C.....#', '#S#######G#', '#.....C...#', '###########']},
    },
]


def _object(value, keys, name):
    if type(value) is not dict or len(value) != len(keys) or not all(key in value for key in keys):
        raise ValueError(f'{name} must contain exactly {", ".join(keys)}.')


def _array(value, low, high, name):
    if type(value) is not list or not low <= len(value) <= high:
        raise ValueError(f'{name} must be an array with {low}–{high} items.')


def _text(value, limit, name):
    if type(value) is not str or not 1 <= len(value) <= limit or not value.strip():
        raise ValueError(f'{name} must be nonblank text of at most {limit} characters.')


def _identifier(value, name):
    if type(value) is not str or len(value) > 32 or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', value):
        raise ValueError(f'{name} must be a lowercase identifier of at most 32 characters.')


def _check(name, passed, detail):
    return {'id': name, 'status': 'pass' if passed else 'fail', 'detail': detail}


def _scavenge(rounds, fuel):
    for index, trip in enumerate(rounds):
        if fuel < trip['cost']:
            return index, fuel, f'Stopped before trip {index + 1} with {fuel} fuel against a cost of {trip["cost"]}.'
        fuel += trip['salvage'] - trip['cost']
    return len(rounds), fuel, f'Finished {len(rounds)} trips with {fuel} fuel.'


def _economy(artifact):
    _object(artifact, ('rounds',), 'Submission')
    rounds = artifact['rounds']
    _array(rounds, 5, 5, 'rounds')
    for trip in rounds:
        _object(trip, ('cost', 'salvage'), 'Each trip')
        for key, low in (('cost', 1), ('salvage', 0)):
            if type(trip[key]) is not int or not low <= trip[key] <= 20:
                raise ValueError(f'{key} must be an integer from {low} to 20.')
    standard, balance, standard_detail = _scavenge(rounds, 8)
    lean, reserve, lean_detail = _scavenge(rounds, 6)
    stranded, _, stranded_detail = _scavenge(rounds, 2)
    gains = sum(trip['salvage'] > trip['cost'] for trip in rounds)
    losses = sum(trip['salvage'] < trip['cost'] for trip in rounds)
    return [
        _check('standard', standard == 5 and 6 <= balance <= 10, standard_detail),
        _check('lean', lean == 5 and reserve >= 1, lean_detail),
        _check('stranded', stranded < 2, stranded_detail),
        _check('pacing', gains > 0 and losses > 0, f'{gains} gain trips and {losses} loss trips.'),
    ]


def _quest_nodes(artifact):
    _object(artifact, ('start', 'nodes'), 'Submission')
    _identifier(artifact['start'], 'start')
    _array(artifact['nodes'], 1, 24, 'nodes')
    nodes = {}
    facts = set()
    for node in artifact['nodes']:
        _object(node, ('id', 'line', 'requires', 'grants', 'choices'), 'Each node')
        _identifier(node['id'], 'Node ID')
        if node['id'] in nodes:
            raise ValueError('Each node must have a unique ID.')
        nodes[node['id']] = node
        _text(node['line'], 240, 'Dialogue line')
        for key in ('requires', 'grants'):
            _array(node[key], 0, 8, key)
            for fact in node[key]:
                _identifier(fact, 'Fact')
                facts.add(fact)
            if len(node[key]) != len(set(node[key])) or len(facts) > 8:
                raise ValueError('Use unique facts in each list and at most eight facts in the quest.')
        _array(node['choices'], 0, 4, 'choices')
        for choice in node['choices']:
            _object(choice, ('label', 'to'), 'Each choice')
            _text(choice['label'], 100, 'Choice label')
            _identifier(choice['to'], 'Choice destination')
    return nodes


def _quest(artifact):
    nodes = _quest_nodes(artifact)
    start = artifact['start']
    queue = deque()
    if start in nodes and not nodes[start]['requires']:
        queue.append((start, frozenset(nodes[start]['grants'])))
    visited = set(queue)
    next_states = {}
    parents = defaultdict(set)
    continuity_error = None
    if not queue:
        continuity_error = f'Start node {start} is missing or requires unavailable starting facts.'
    while queue:
        state = queue.popleft()
        name, facts = state
        successors = set()
        for choice in nodes[name]['choices']:
            target = choice['to']
            if target not in nodes:
                continue
            missing = set(nodes[target]['requires']) - facts
            if missing:
                if continuity_error is None:
                    continuity_error = f'{name} offers {target} before establishing {", ".join(sorted(missing))}.'
                continue
            child = (target, facts.union(nodes[target]['grants']))
            successors.add(child)
            parents[child].add(state)
            if child not in visited:
                visited.add(child)
                queue.append(child)
        next_states[state] = successors

    played = {name for name, _ in visited}
    dangling = sorted({choice['to'] for node in nodes.values() for choice in node['choices']
                       if choice['to'] not in nodes})
    absent = sorted(nodes.keys() - played)
    reach_detail = f'{len(played)} of {len(nodes)} nodes playable.'
    if absent:
        reach_detail += ' Unreached: ' + ', '.join(absent) + '.'
    if dangling:
        reach_detail += ' Missing destinations: ' + ', '.join(dangling) + '.'

    # Propagate ending identities backwards, even through revisitable branches.
    endings = defaultdict(set)
    for state in next_states:
        if not nodes[state[0]]['choices']:
            endings[state].add(state[0])
            queue.append(state)
    while queue:
        state = queue.popleft()
        for parent in parents[state]:
            if not endings[state] <= endings[parent]:
                endings[parent].update(endings[state])
                queue.append(parent)
    consequential = sorted({state[0] for state, children in next_states.items()
                            if len({frozenset(endings[c]) for c in children if endings[c]}) >= 2})
    resolved = sum(bool(endings[state]) for state in next_states)
    gated = sum(bool(nodes[name]['requires']) for name in played)
    return [
        _check('reachability', not absent and not dangling, reach_detail),
        _check('continuity', not continuity_error and gated > 0,
               continuity_error or f'{gated} playable fact-dependent lines.'),
        _check('agency', bool(consequential), 'Ending-changing choices at ' + ', '.join(consequential) + '.'
               if consequential else 'No playable choice changes the set of reachable endings.'),
        _check('resolution', bool(visited) and resolved == len(visited),
               f'{resolved} of {len(visited)} playable story states can reach an ending.'),
    ]


def _grid_graph(artifact):
    _object(artifact, ('grid',), 'Submission')
    rows = artifact['grid']
    _array(rows, 3, 24, 'grid')
    for row in rows:
        if (type(row) is not str or not 3 <= len(row) <= 24 or len(row) != len(rows[0])
                or any(tile not in '#.CSG' for tile in row)):
            raise ValueError('Use equal widths of 3–24 tiles and only #, ., C, S and G.')
    tiles = {(x, y): char for y, row in enumerate(rows) for x, char in enumerate(row) if char != '#'}
    if list(tiles.values()).count('S') != 1 or list(tiles.values()).count('G') != 1:
        raise ValueError('Include exactly one spawn (S) and one goal (G).')
    graph = {(x, y): [p for p in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)) if p in tiles]
             for x, y in tiles}
    markers = {tile: pos for pos, tile in tiles.items() if tile in 'SG'}
    return graph, markers['S'], markers['G'], [pos for pos, tile in tiles.items() if tile == 'C']


def _walk(graph, start, blocked=None, skip_edge=None):
    parents = {start: None}
    distances = {start: 0}
    queue = deque([start])
    while queue:
        pos = queue.popleft()
        for neighbor in graph[pos]:
            if neighbor in distances or neighbor == blocked or (pos, neighbor) == skip_edge:
                continue
            parents[neighbor] = pos
            distances[neighbor] = distances[pos] + 1
            queue.append(neighbor)
    return distances, parents


def _two_routes(graph, start, goal, parents):
    if goal not in parents:
        return False, 'The goal is unreachable.'
    if parents[goal] == start:
        alternate = goal in _walk(graph, start, skip_edge=(start, goal))[0]
        return alternate, 'A detour connects the adjacent endpoints.' if alternate else 'Only the direct step connects the endpoints.'
    # Any single-tile cut must lie on this route. For nonadjacent endpoints,
    # the absence of a single-tile cut implies two internally disjoint paths.
    tile = parents[goal]
    while tile != start:
        if goal not in _walk(graph, start, blocked=tile)[0]:
            return False, f'Every route crosses column {tile[0]+1}, row {tile[1]+1}.'
        tile = parents[tile]
    return True, 'Two routes share only the spawn and goal.'


def _arena(artifact):
    graph, start, goal, cover = _grid_graph(artifact)
    distances, parents = _walk(graph, start)
    length = distances.get(goal)
    alternate, route_detail = _two_routes(graph, start, goal, parents)
    goal_distances, _ = _walk(graph, goal)
    well_placed = [pos for pos in cover if distances.get(pos, -1) >= 3 and goal_distances.get(pos, -1) >= 2]
    # Two cover tiles are too close if one occurs in the other's 1- or 2-step neighborhood.
    cover_set = set(cover)
    crowded = set()
    for pos in cover:
        nearby = set(graph[pos])
        for neighbor in graph[pos]:
            nearby.update(graph[neighbor])
        if (nearby - {pos}) & cover_set:
            crowded.add(pos)
    return [
        _check('reachability', len(distances) == len(graph), f'{len(distances)} of {len(graph)} walkable tiles reached.'),
        _check('alternate-routes', alternate, route_detail),
        _check('spacing', length is not None and 6 <= length <= 18,
               'Goal unreachable.' if length is None else f'Shortest route takes {length} steps.'),
        _check('cover', len(cover) >= 2 and len(well_placed) == len(cover) and not crowded,
               f'{len(well_placed)} of {len(cover)} cover positions meet endpoint spacing. '
               f'{len(crowded)} have another cover position within two steps.'),
    ]


def assess(exercise_id, submission):
    """Assess one JSON artifact. Structural errors raise ValueError."""
    handlers = {'game-design': _economy, 'storytelling': _quest, 'level-design': _arena}
    if type(exercise_id) is not str or exercise_id not in handlers:
        raise ValueError('Unknown design exercise.')
    return handlers[exercise_id](submission)
