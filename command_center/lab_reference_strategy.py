"""Replay a synthetic watershed and crew-allocation strategy exercise."""

from .lab_gameplay import _array, _choice, _integer, _object, _result


TRACK = {
    'id': 'reference-strategy', 'title': 'Strategy reference study and terrain-driven tradeoffs',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification', 'build_operations'],
    'workflow': [
        'Study a developer or publisher source. Record the actual rule, the choice it creates and how the player '
        'sees its consequences. Check the exact title and edition before transferring a design lesson.',
        'Prototype an original terrain system with explicit flow, storage and erosion. Keep a material ledger '
        'so engineering transfers, natural movement and loss are visible in the turn trace.',
        'Give the player limited work per turn and distinct objectives with readable progress. Model how the same '
        'terrain supports one objective while creating costs or risks for another.',
        'Replay two plans with identical starting conditions, then remove one intervention from a successful plan '
        'and trace the changed environment and outcomes. Preview the affected sites and test where a plan breaks.',
    ],
    'deliverables': [
        'Source-backed notes connecting a documented rule to a transferable design lesson.',
        'Original turn rules, initial terrain and material inventory, and two successful plans with different objectives.',
        'A matched single-action counterfactual with predicted consequences and a plan for in-engine UX review.',
    ],
    'verification': [
        'Check boundary values, water carryover, erosion, rejected work, resource accounting and the effects on both objectives.',
        'In the prototype, inspect the same state transitions and ask playtesters to predict where runoff will go '
        'and explain what their crew choice leaves undone.',
    ],
    'exercise': 'Plan work on two terraces under one storm sequence, then remove one decisive terrain intervention.',
}


_GOALS = ('nursery', 'freight')
_TOTALS = ('seedlings', 'deliveries')
_ACTIONS = ('raise', 'lower', 'recover', 'grow', 'ship', 'wait')
_TERRAIN = ('diverted', 'overflow', 'bed_water', 'yard_water', 'eroded')
_MATERIAL = ('barrier', 'spares', 'sediment')
_MAX_BARRIER = 5


def _turn(action, flow, water, materials, output, *, accepted=True, eroded=0):
    return {'action': action, 'expected': {'accepted': accepted, 'eroded': eroded,
                                          **dict(zip(_TERRAIN[:2], flow, strict=True)),
                                          **dict(zip(_TERRAIN[2:4], water, strict=True)),
                                          **dict(zip(_MATERIAL, materials, strict=True)),
                                          **dict(zip(_TOTALS, output, strict=True))}}


EXERCISES = [{
    'id': 'reference-strategy', 'title': 'Allocate a storm crew at the rain terraces',
    'brief': 'The nursery and freight yard share one rain-fed diversion. Submit 4–8 turns with 0–12 rain '
             'units per turn. Start with a barrier of 0–5 blocks, 0–6 spare blocks, no sediment, no stored '
             'water and zero output. Set separate nursery seedling and freight delivery targets (2–16). '
             'One crew picks one action per turn. Raise moves a spare block to the barrier up to height 5. '
             'Lower returns one barrier block to spares. Recover returns one sediment block to spares. '
             'Reject these moves if the required block or barrier capacity is unavailable. '
             'After earthworks, divert up to the barrier height from this turn’s rain to the nursery and send '
             'the rest to the freight yard. Add each inflow to the site’s existing water. Drain up to 1 from '
             'the bed and 2 from the yard. Overflow of at least 4 erodes one barrier block into sediment if '
             'a block remains. The erosion affects the next turn’s split. Grow yields two seedlings if bed '
             'water is 1–3 after drainage. Ship yields two deliveries if post-drain yard water is at most 2. '
             'Wait always succeeds. A rejected action still uses the turn and weather advances. '
             'Record acceptance, water split, post-drain water, erosion, block counts and cumulative output '
             'for every turn. Each named plan must meet its own target and miss the other. For a counterfactual, '
             'repeat one plan, replacing exactly one raise or lower with wait. Show an immediate difference '
             'in water and eventual loss of its target. This exercise uses a synthetic turn model.',
    'criteria': [
        {'id': 'terrain-trace', 'label': 'Trace the runoff split, carried water, drainage and erosion on every turn.'},
        {'id': 'material-budget', 'label': 'Conserve barrier material and match each transfer between barrier, spares and sediment.'},
        {'id': 'resource-trace', 'label': 'Apply the crew and water constraints and predict acceptance and output.'},
        {'id': 'strategic-choice', 'label': 'Meet separate objectives with two plans that trade off the other target.'},
        {'id': 'counterfactual', 'label': 'Isolate one terrain decision that changes water and loses its plan’s objective.'},
    ],
    'example': {
        'start': {'barrier': 1, 'spares': 2}, 'rain': [2, 4, 4, 7, 3, 2],
        'goals': {'nursery': 4, 'freight': 4},
        'plans': {
            'nursery': [
                _turn('raise', (2, 0), (1, 0), (2, 1, 0), (0, 0)),
                _turn('grow', (2, 2), (2, 0), (2, 1, 0), (2, 0)),
                _turn('grow', (2, 2), (3, 0), (2, 1, 0), (4, 0)),
                _turn('wait', (2, 5), (4, 3), (1, 1, 1), (4, 0), eroded=1),
                _turn('recover', (1, 2), (4, 3), (1, 2, 0), (4, 0)),
                _turn('ship', (1, 1), (4, 2), (1, 2, 0), (4, 2)),
            ],
            'freight': [
                _turn('ship', (1, 1), (0, 0), (1, 2, 0), (0, 2)),
                _turn('raise', (2, 2), (1, 0), (2, 1, 0), (0, 2)),
                _turn('ship', (2, 2), (2, 0), (2, 1, 0), (0, 4)),
                _turn('ship', (2, 5), (3, 3), (1, 1, 1), (0, 4), accepted=False, eroded=1),
                _turn('raise', (2, 1), (4, 2), (2, 0, 1), (0, 4)),
                _turn('ship', (2, 0), (5, 0), (2, 0, 1), (0, 6)),
            ],
        },
        'counterfactual': {'basis': 'nursery', 'turns': [
            _turn('wait', (1, 1), (0, 0), (1, 2, 0), (0, 0)),
            _turn('grow', (1, 3), (0, 1), (1, 2, 0), (0, 0), accepted=False),
            _turn('grow', (1, 3), (0, 2), (1, 2, 0), (0, 0), accepted=False),
            _turn('wait', (1, 6), (0, 6), (0, 2, 1), (0, 0), eroded=1),
            _turn('recover', (0, 3), (0, 7), (0, 3, 0), (0, 0)),
            _turn('ship', (0, 2), (0, 7), (0, 3, 0), (0, 0), accepted=False),
        ]},
    },
}]


def _validate(data):
    _object(data, ('start', 'rain', 'goals', 'plans', 'counterfactual'), 'Strategy submission')
    _object(data['start'], ('barrier', 'spares'), 'Starting blocks')
    _integer(data['start']['barrier'], 0, _MAX_BARRIER, 'Starting barrier')
    _integer(data['start']['spares'], 0, 6, 'Starting spares')
    _array(data['rain'], 8, 'Rain', minimum=4)
    for rain in data['rain']:
        _integer(rain, 0, 12, 'Rain units')
    _object(data['goals'], _GOALS, 'Goals')
    for target in data['goals'].values():
        _integer(target, 2, 16, 'Goal target')
    _object(data['plans'], _GOALS, 'Plans')
    comparison = data['counterfactual']
    _object(comparison, ('basis', 'turns'), 'Counterfactual')
    _choice(comparison['basis'], _GOALS, 'Counterfactual basis')
    plans = dict(data['plans'], counterfactual=comparison['turns'])
    clocks = len(data['rain'])
    limits = {'diverted': 12, 'overflow': 12, 'bed_water': 96, 'yard_water': 96, 'eroded': 1,
              'barrier': _MAX_BARRIER, 'spares': 11, 'sediment': 11, 'seedlings': 16, 'deliveries': 16}
    for name, turns in plans.items():
        _array(turns, clocks, name, minimum=clocks)
        for turn in turns:
            _object(turn, ('action', 'expected'), 'Turn')
            _choice(turn['action'], _ACTIONS, 'Crew action')
            expected = turn['expected']
            _object(expected, ('accepted', *limits), 'Expected turn state')
            if type(expected['accepted']) is not bool:
                raise ValueError('Turn acceptance must be boolean.')
            for field, maximum in limits.items():
                _integer(expected[field], 0, maximum, field)
    return plans


def _simulate(start, rain, turns):
    barrier, spares = start['barrier'], start['spares']
    sediment = bed_water = yard_water = seedlings = deliveries = 0
    trace = []
    for amount, turn in zip(rain, turns, strict=True):
        action = turn['action']
        accepted = True
        if action == 'raise':
            accepted = spares > 0 and barrier < _MAX_BARRIER
            barrier += int(accepted)
            spares -= int(accepted)
        elif action == 'lower':
            accepted = barrier > 0
            barrier -= int(accepted)
            spares += int(accepted)
        elif action == 'recover':
            accepted = sediment > 0
            sediment -= int(accepted)
            spares += int(accepted)

        diverted = min(amount, barrier)
        overflow = amount - diverted
        bed_water = max(0, bed_water + diverted - 1)
        yard_water = max(0, yard_water + overflow - 2)
        eroded = int(overflow >= 4 and barrier > 0)
        barrier -= eroded
        sediment += eroded

        if action == 'grow':
            accepted = 1 <= bed_water <= 3
            seedlings += 2 * int(accepted)
        elif action == 'ship':
            accepted = yard_water <= 2
            deliveries += 2 * int(accepted)
        trace.append({'accepted': accepted, 'diverted': diverted, 'overflow': overflow,
                      'bed_water': bed_water, 'yard_water': yard_water, 'eroded': eroded,
                      'barrier': barrier, 'spares': spares, 'sediment': sediment,
                      'seedlings': seedlings, 'deliveries': deliveries})
    return trace


def _trace_check(key, fields, plans, traces):
    mismatches = [f'{name} turn {number}' for name in (*_GOALS, 'counterfactual')
                  for number, (turn, actual) in enumerate(zip(plans[name], traces[name], strict=True), 1)
                  if any(turn['expected'][field] != actual[field] for field in fields)]
    detail = 'Check ' + ', '.join(mismatches) + '.' if mismatches else 'All three predicted traces match the model.'
    return _result(key, not mismatches, detail)


def _target_status(state, targets):
    return tuple(state[field] >= targets[goal] for goal, field in zip(_GOALS, _TOTALS, strict=True))


def _counterfactual_check(basis, plans, traces, targets):
    before, after = plans[basis], plans['counterfactual']
    changed = [index for index, (a, b) in enumerate(zip(before, after, strict=True)) if a['action'] != b['action']]
    if len(changed) != 1:
        return _result('counterfactual', False, f'Expected one modified action. Found {len(changed)}.')
    index = changed[0]
    original, alternate = traces[basis], traces['counterfactual']
    goal = _GOALS.index(basis)
    isolated = before[index]['action'] in ('raise', 'lower') and after[index]['action'] == 'wait'
    hydrology = any(original[index][field] != alternate[index][field] for field in _TERRAIN[:4])
    met_before = _target_status(original[-1], targets)[goal]
    met_after = _target_status(alternate[-1], targets)[goal]
    total = _TOTALS[goal]
    return _result('counterfactual', isolated and hydrology and met_before and not met_after,
                   f'Turn {index + 1} changes {before[index]["action"]} to {after[index]["action"]}. '
                   f'Immediate water change {"yes" if hydrology else "no"}. '
                   f'Final {total} change from {original[-1][total]} to {alternate[-1][total]}, '
                   f'with a target of {targets[basis]}.')


def assess(exercise_id, submission):
    if exercise_id != 'reference-strategy':
        raise ValueError('Unknown reference strategy exercise.')
    plans = _validate(submission)
    traces = {name: _simulate(submission['start'], submission['rain'], turns) for name, turns in plans.items()}
    targets = submission['goals']
    nursery, freight = (traces[goal][-1] for goal in _GOALS)
    distinct = _target_status(nursery, targets) == (True, False) and _target_status(freight, targets) == (False, True)
    totals = ' '.join(f'{goal} plan yields {state["seedlings"]} seedlings and {state["deliveries"]} deliveries.'
                      for goal, state in zip(_GOALS, (nursery, freight), strict=True))
    return [
        _trace_check('terrain-trace', _TERRAIN, plans, traces),
        _trace_check('material-budget', _MATERIAL, plans, traces),
        _trace_check('resource-trace', ('accepted', *_TOTALS), plans, traces),
        _result('strategic-choice', distinct, totals + f' Targets are {targets["nursery"]} seedlings and {targets["freight"]} deliveries.'),
        _counterfactual_check(submission['counterfactual']['basis'], plans, traces, targets),
    ]
