"""A bounded, deterministic garden-sprite encounter exercise. All coordinates are tiles."""

from collections import deque

from .lab_gameplay import _array, _choice, _criterion, _integer, _object, _result
from .studio_curriculum import _track


TRACK = _track('ai-encounters', 'Game AI and encounter design', 'architecture gameplay content verification', [
    'Define what each NPC can sense, its decisions, and what the player can observe before it acts. Draw the state machine or behavior tree with explicit transition priority, interruption and recovery.',
    'Block out spawn gates and navigation routes at gameplay scale. Test occlusion, sensor range, disconnected regions and a fallback when a destination cannot be reached.',
    'Allocate an active encounter budget by actor cost and lifetime. Reserve and release that budget at explicit ticks and tune spawn distance, line of sight, warnings and recovery windows.',
    'Replay a fixed seed and input trace. Inspect the navigation overlay and log positions, sensor results, transitions, spawn choices and active cost at each divergence before tuning the encounter.'
], [
    'Annotated arena, perception rules, NPC state diagram and a wave schedule with actor costs and lifetimes.',
    'Seed, build and fixture identifiers, tick-by-tick debug evidence and a human playtest record of warning readability and perceived fairness.'
], [
    'Check all gates for reachability, sight lines and distance. Replay warning, loss of sight, interruption, normal action, cooldown and recovery on the same build.',
    'Compare measured peak active cost to the encounter budget, including coincident arrivals and expirations. Verify presentation, response time and navigation in the game.'
], 'Plan a garden-sprite tag encounter and reproduce a seeded movement, perception and budget trace.')


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Garden sprite tag encounter',
    'brief': 'Build a rectangular arena (2–12 rows and columns) using floor (.), walls (#), one stationary player (P) '
             'and 2–8 gates (G), numbered from 0 in row-major order. All gates must have a four-direction walk '
             'to P at least three moves long by the shortest route, and start out of sight. The sprite sees P '
             'on the same tile or along a clear row or column up to three moves away. '
             'Submit 1–32 spawns starting at tick 0, ordered by tick (0–63; ties use list order), with cost '
             '1–4 and life 1–64 ticks. Cost is active from arrival until, but excluding, tick + life. '
             'Demonstrate overlapping actors and a later spawn after a reservation expires, with peak cost at most 4. '
             'Predict peak and each gate index. Start s at seed (1–2147483646); for each spawn update '
             's = (48271 × s) modulo 2147483647 and choose gate s modulo gate count. '
             'Trace the first sprite for 1–32 ticks within its lifetime. Start on its selected gate at tick 0, '
             'then stay or walk one open cardinal tile per tick. Give cell [x,y] from the top left, boolean '
             'interrupt, and predicted state after each tick. Start ready. Ready signals when P is seen. '
             'From signal, interrupt takes priority and enters recover; otherwise seeing P tags, and losing sight '
             'returns to ready. Tag always enters recover; recover always enters ready. Interrupt is ignored '
             'outside signal. Show a canceled warning from lost sight, an interrupted warning, and a completed '
             'tag with a full recovery. Check the reported tick when a prediction diverges.',
    'criteria': [_criterion('routes', 'All gates have a reachable, concealed approach with adequate distance'),
                 _criterion('budget', 'Reuse the four-point budget across overlapping sprite lifetimes'),
                 _criterion('behavior', 'Exercise loss of sight, interruption, tagging and recovery on a valid path'),
                 _criterion('replay', 'Predict seeded gates, active peak and every state on the first sprite’s path')],
    'example': {'arena': ['G...P..', '.##.#..', '.......', '..##..G'], 'seed': 3,
                'spawns': [{'tick': 0, 'cost': 2, 'life': 16, 'gate': 1},
                           {'tick': 1, 'cost': 2, 'life': 2, 'gate': 0},
                           {'tick': 3, 'cost': 2, 'life': 2, 'gate': 1}], 'peak': 4,
                'steps': [{'cell': [6, 3], 'interrupt': False, 'state': 'ready'},
                          {'cell': [6, 2], 'interrupt': False, 'state': 'ready'},
                          {'cell': [6, 1], 'interrupt': False, 'state': 'ready'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'signal'},
                          {'cell': [6, 1], 'interrupt': False, 'state': 'ready'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'signal'},
                          {'cell': [6, 0], 'interrupt': True, 'state': 'recover'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'ready'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'signal'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'tag'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'recover'},
                          {'cell': [6, 0], 'interrupt': False, 'state': 'ready'}]},
}]


def _arena(rows):
    _array(rows, 12, 'arena', minimum=2)
    floor, gates, players = set(), [], []
    for y, row in enumerate(rows):
        if (type(row) is not str or not 2 <= len(row) <= 12 or len(row) != len(rows[0])
                or any(tile not in '.#GP' for tile in row)):
            raise ValueError('arena requires equal-width rows of 2–12 tiles using . # G P')
        for x, tile in enumerate(row):
            if tile != '#':
                floor.add((x, y))
            if tile == 'G':
                gates.append((x, y))
            if tile == 'P':
                players.append((x, y))
    if len(players) != 1 or not 2 <= len(gates) <= 8:
        raise ValueError('arena requires one player and 2–8 gates')
    return floor, gates, players[0]


def _visible(cell, player, floor):
    x, y = cell
    dx, dy = player[0] - x, player[1] - y
    distance = abs(dx) + abs(dy)
    if (dx and dy) or distance > 3:
        return False
    step_x, step_y = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    return all((x + step_x * n, y + step_y * n) in floor for n in range(distance + 1))


def _routes(floor, gates, player):
    distance = {player: 0}
    queue = deque([player])
    while queue:
        x, y = queue.popleft()
        for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbor in floor and neighbor not in distance:
                distance[neighbor] = distance[x, y] + 1
                queue.append(neighbor)
    failures = []
    for index, gate in enumerate(gates):
        if gate not in distance:
            failures.append(f'Gate {index} is unreachable')
        elif distance[gate] < 3 or _visible(gate, player, floor):
            failures.append(f'Gate {index} is {distance[gate]} moves away, visible={_visible(gate, player, floor)}')
    return _result('routes', not failures, '. '.join(failures) or f'Checked all {len(gates)} gates. Shortest routes in moves: {[distance[g] for g in gates]}.')


def _schedule(spawns, seed, gate_count):
    _array(spawns, 32, 'spawns', minimum=1)
    choices, active = [], []
    peak = peak_tick = previous_tick = 0
    overlap = reused = False
    for index, spawn in enumerate(spawns):
        name = f'spawns[{index}]'
        _object(spawn, ('tick', 'cost', 'life', 'gate'), name)
        _integer(spawn['tick'], previous_tick, 63 if index else 0, name + '.tick')
        _integer(spawn['cost'], 1, 4, name + '.cost')
        _integer(spawn['life'], 1, 64, name + '.life')
        _integer(spawn['gate'], 0, gate_count - 1, name + '.gate')
        tick = previous_tick = spawn['tick']
        seed = 48271 * seed % 2147483647
        choices.append(seed % gate_count)
        continuing = [(end, cost) for end, cost in active if end > tick]
        reused |= len(continuing) < len(active)
        overlap |= bool(continuing)
        active = [*continuing, (tick + spawn['life'], spawn['cost'])]
        cost_now = sum(cost for end, cost in active)
        if cost_now > peak:
            peak, peak_tick = cost_now, tick
    detail = f'Peak active cost {peak}/4 at tick {peak_tick}. Overlap: {overlap}. Spawn after expiry: {reused}.'
    return choices, peak, _result('budget', peak <= 4 and overlap and reused, detail)


def _next_state(state, seen, interrupt):
    if state == 'signal':
        if interrupt:
            return 'recover'
        return 'tag' if seen else 'ready'
    if state == 'tag':
        return 'recover'
    if state == 'ready' and seen:
        return 'signal'
    return 'ready'


def _trace(submission, gate, player, floor):
    steps = submission['steps']
    _array(steps, 32, 'steps', minimum=1)
    previous_cell = gate
    state = 'ready'
    previous_state = None
    covered = set()
    completed_tag = False
    path_error = state_error = ''
    for tick, step in enumerate(steps):
        name = f'steps[{tick}]'
        _object(step, ('cell', 'interrupt', 'state'), name)
        _array(step['cell'], 2, name + '.cell', minimum=2)
        _integer(step['cell'][0], 0, len(submission['arena'][0]) - 1, name + '.cell[0]')
        _integer(step['cell'][1], 0, len(submission['arena']) - 1, name + '.cell[1]')
        if type(step['interrupt']) is not bool:
            raise ValueError(f'{name}.interrupt requires a boolean')
        _choice(step['state'], ('ready', 'signal', 'tag', 'recover'), name + '.state')
        cell = tuple(step['cell'])
        distance = abs(cell[0] - previous_cell[0]) + abs(cell[1] - previous_cell[1])
        if not path_error:
            if tick == 0 and cell != gate:
                path_error = f'Tick 0 must start at seeded gate {gate}, found {cell}.'
            elif cell not in floor or distance > 1:
                path_error = f'Tick {tick} cannot move from {previous_cell} to {cell}.'
            elif tick >= submission['spawns'][0]['life']:
                path_error = f'Tick {tick} is outside the first sprite’s lifetime.'
        seen = _visible(cell, player, floor)
        after = _next_state(state, seen, step['interrupt'])
        covered.add((state, after))
        if (previous_state, state, after) == ('tag', 'recover', 'ready'):
            completed_tag = True
        if not state_error and step['state'] != after:
            state_error = f'Tick {tick}, cell {cell}, sight={seen}, interrupt={step["interrupt"]}: {state} → {after}, predicted {step["state"]}.'
        previous_cell = cell
        previous_state, state = state, after
    required = {('signal', 'ready'), ('signal', 'recover')}
    missing = [f'{a} → {b}' for a, b in sorted(required - covered)]
    if not completed_tag:
        missing.append('tag → recover → ready')
    detail = f'All required transitions occurred across {len(steps)} ticks.'
    if missing:
        detail = 'Missing transitions include ' + ', '.join(missing) + '.'
    return _result('behavior', not (path_error or missing), path_error or detail), path_error or state_error


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown encounter exercise')
    _object(submission, ('arena', 'seed', 'spawns', 'peak', 'steps'), 'Encounter')
    _integer(submission['seed'], 1, 2147483646, 'seed')
    _integer(submission['peak'], 0, 128, 'peak')
    floor, gates, player = _arena(submission['arena'])
    choices, peak, budget = _schedule(submission['spawns'], submission['seed'], len(gates))
    behavior, error = _trace(submission, gates[choices[0]], player, floor)
    for index, (spawn, gate) in enumerate(zip(submission['spawns'], choices, strict=True)):
        if spawn['gate'] != gate:
            error = f'Spawn {index} at tick {spawn["tick"]} selected gate {gate}; predicted {spawn["gate"]}.'
            break
    if not error and submission['peak'] != peak:
        error = f'Predicted cost peak {submission["peak"]}, measured {peak}.'
    detail = error or f'Seed {submission["seed"]} selected gates {choices}. Peak {peak} and all {len(submission["steps"])} state predictions match.'
    return [_routes(floor, gates, player), budget, behavior, _result('replay', not error, detail)]
