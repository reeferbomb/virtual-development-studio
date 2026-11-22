"""Test distinct character builds against the same original clockwork fair assignment."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'fallout-playstyles', 'title': 'Fallout playstyles and viable character builds',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Read presentation_studies/FALLOUT_PLAYSTYLES.md. Compare the targeting pause and percentage Speech '
        'challenges of Fallout 3, the faction-specific reputation and skill thresholds of New Vegas, and the '
        'ranked perks, time-slowing targeting and workshops of Fallout 4. Name the game and optional mode.',
        'Give a direct competitor, a quiet mover, a negotiator, an explorer, a maker and a provisioner the '
        'same destination. For each, name the information they notice, the action they take, the resource '
        'they spend and the opportunity they give up. Build an original setting and vocabulary.',
        'Spend the same advancement budget on two specialists and one hybrid. Place at least one later '
        'opportunity that depends on an earlier consequence. Compare the clock and inventory at the finish.',
        'Remove each signature investment and search again, including detours and routes the designer did '
        'not select. Then check the playable build for readable costs, uncertainty, refusals and recovery.',
    ],
    'deliverables': [
        'A title-specific comparison with primary sources, an original quest, and a route-and-consequence table.',
        'Three equal-budget builds, predicted outcomes and counterfactual evidence that the hybrid needs both skills.',
    ],
    'verification': [
        'Replay all builds under identical starting conditions. Check skill requirements, standing carried '
        'between gates, available supplies and the inclusive deadline on every leg.',
        'Look for alternate options that make a signature investment redundant or dominate a claimed '
        'tradeoff. Ask an authorized tester to explain a route and the cost of choosing it.',
    ],
    'exercise': 'Bring three differently trained couriers to the same fair before closing and explain their tradeoffs.',
}

_SKILLS = ('contest', 'quiet', 'rapport', 'survey', 'craft', 'provision')
_BUILDS = ('fast', 'stock', 'hybrid')


def _option(name, skill, rank, minutes, supplies, standing=0, need=0):
    return {'id': name, 'skill': skill, 'rank': rank, 'minutes': minutes,
            'supplies': supplies, 'standing': standing, 'need': need}


def _build(ranks, route, minutes, supplies, standing):
    return {'ranks': ranks, 'route': route, 'expected': {'minutes': minutes, 'supplies': supplies, 'standing': standing}}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Reach the clockwork fair before closing',
    'brief': 'Design 3–6 ordered stops with 2–6 options per stop. Give each option a local ID, skill '
             '(contest, quiet, rapport, survey, craft or provision), minimum rank (0–3), minutes (1–12), '
             'signed supply change (−3 to 3), signed standing change (−2 to 2) and minimum prior standing '
             'need (−12 to 12). All builds start at zero minutes and standing, with the same supplies (0–12) '
             'and deadline (1–72 minutes). An option requires the named rank and standing before it applies '
             'both changes. Supplies must stay nonnegative and arrival at the deadline counts. Give each '
             'build four training points using only its nonzero ranks. Fast and stock invest 3+1 and must '
             'specialize in different skills. Hybrid invests 2+2. Pick one option ID per stop and predict '
             'final minutes, supplies and standing. Each route must finish. Demonstrate a later option '
             'requiring positive standing earned earlier. Fast must beat stock on time and arrive with fewer '
             'supplies. Among all routes available to the three builds, none may finish at least as quickly '
             'with at least as many supplies and improve one measure over a submitted result. Removing a '
             'specialist’s top skill or either hybrid skill without reallocating its points must prevent that '
             'build from finishing by any route. These limits apply only to this synthetic fair.',
    'criteria': [
        {'id': 'builds', 'label': 'Allocate equal budgets to two distinct specialists and a two-skill hybrid.'},
        {'id': 'routes', 'label': 'Finish all three selected routes within the shared supply and time limits.'},
        {'id': 'consequences', 'label': 'Use earned standing to qualify for a later choice and predict all final states.'},
        {'id': 'tradeoffs', 'label': 'Exhibit efficient outcomes and exchange speed for supplies.'},
        {'id': 'investments', 'label': 'Make every signature skill necessary across all available routes.'},
    ],
    'example': {
        'supplies': 5, 'deadline': 8,
        'stops': [
            [_option('exhibition', 'contest', 3, 1, -2), _option('volunteer', 'rapport', 3, 3, 0, 1),
             _option('survey_cache', 'survey', 2, 2, 1)],
            [_option('qualifier', 'contest', 3, 1, -1), _option('liaison', 'rapport', 3, 2, -1, 1),
             _option('fit_coupling', 'craft', 2, 2, -2, 1)],
            [_option('arena_lift', 'contest', 3, 2, -1), _option('guest_lift', 'rapport', 3, 2, 0, need=2),
             _option('survey_span', 'survey', 2, 2, -1, need=1)],
        ],
        'builds': {
            'fast': _build({'contest': 3, 'craft': 1}, ['exhibition', 'qualifier', 'arena_lift'], 4, 1, 0),
            'stock': _build({'rapport': 3, 'quiet': 1}, ['volunteer', 'liaison', 'guest_lift'], 7, 4, 2),
            'hybrid': _build({'survey': 2, 'craft': 2}, ['survey_cache', 'fit_coupling', 'survey_span'], 6, 3, 1),
        },
    },
}]


def _read(data):
    _object(data, ('supplies', 'deadline', 'stops', 'builds'), 'fair')
    _integer(data['supplies'], 0, 12, 'starting supplies')
    _integer(data['deadline'], 1, 72, 'deadline')
    _array(data['stops'], 3, 6, 'stops')
    stops = []
    for choices in data['stops']:
        _array(choices, 2, 6, 'options')
        indexed = {}
        for opt in choices:
            _object(opt, ('id', 'skill', 'rank', 'minutes', 'supplies', 'standing', 'need'), 'option')
            _identifier(opt['id'], 'option ID')
            if opt['id'] in indexed:
                raise ValueError('Option IDs must be unique within each stop.')
            _choice(opt['skill'], _SKILLS, 'skill')
            for field, low, high in [('rank', 0, 3), ('minutes', 1, 12), ('supplies', -3, 3),
                                     ('standing', -2, 2), ('need', -12, 12)]:
                _integer(opt[field], low, high, field)
            indexed[opt['id']] = opt
        stops.append(indexed)
    _object(data['builds'], _BUILDS, 'builds')
    for build in data['builds'].values():
        _object(build, ('ranks', 'route', 'expected'), 'build')
        ranks = build['ranks']
        if type(ranks) is not dict or not 1 <= len(ranks) <= len(_SKILLS):
            raise ValueError('List the nonzero ranks for this build.')
        for skill, value in ranks.items():
            _choice(skill, _SKILLS, 'skill')
            _integer(value, 1, 3, 'training rank')
        _array(build['route'], len(stops), len(stops), 'route')
        for option_id in build['route']:
            _identifier(option_id, 'chosen option')
        _object(build['expected'], ('minutes', 'supplies', 'standing'), 'expected result')
        for field, low, high in [('minutes', 0, 72), ('supplies', 0, 30), ('standing', -12, 12)]:
            _integer(build['expected'][field], low, high, field)
    return stops


def _advance(state, option, ranks, deadline):
    minutes, supplies, standing = state
    if ranks.get(option['skill'], 0) < option['rank'] or standing < option['need']:
        return None
    minutes += option['minutes']
    supplies += option['supplies']
    if minutes > deadline or supplies < 0:
        return None
    return minutes, supplies, standing + option['standing']


def _outcomes(stops, initial, deadline, ranks):
    # With equal stock and standing at the same stop, the earlier arrival
    # can take every remaining option the later arrival could take.
    earliest = {(initial, 0): 0}
    for options in stops:
        after = {}
        for (stock, standing), minutes in earliest.items():
            for option in options.values():
                result = _advance((minutes, stock, standing), option, ranks, deadline)
                if result is not None:
                    time, supplies, reputation = result
                    key = supplies, reputation
                    if key not in after or time < after[key]:
                        after[key] = time
        earliest = after
    return {(time, stock) for (stock, _), time in earliest.items()}


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown Fallout playstyles exercise.')
    stops = _read(submission)
    initial, deadline = submission['supplies'], submission['deadline']
    builds = submission['builds']
    peaks = {name: {k for k, v in builds[name]['ranks'].items() if v == 3} for name in ('fast', 'stock')}
    valid_builds = (all(sorted(builds[n]['ranks'].values()) == [1, 3] for n in peaks)
                    and peaks['fast'] != peaks['stock'] and sorted(builds['hybrid']['ranks'].values()) == [2, 2])
    all_outcomes, selected = set(), {}
    matched = essential = 0
    earned_access = False
    details = []
    for name in _BUILDS:
        build = builds[name]
        ranks = build['ranks']
        outcomes = _outcomes(stops, initial, deadline, ranks)
        all_outcomes.update(outcomes)
        signatures = ranks if name == 'hybrid' else peaks[name]
        for skill in signatures:
            reduced = dict(ranks)
            del reduced[skill]
            if outcomes and not _outcomes(stops, initial, deadline, reduced):
                essential += 1
        state = (0, initial, 0)
        used_standing = False
        for i, (options, choice) in enumerate(zip(stops, build['route']), 1):
            opt = options.get(choice)
            state = _advance(state, opt, ranks, deadline) if opt is not None else None
            if state is None:
                details.append(f'{name} cannot take {choice} at stop {i}')
                break
            used_standing |= opt['need'] > 0
        if state is not None:
            earned_access |= used_standing
            selected[name] = state[:2]
            predicted = build['expected']
            matched += state == (predicted['minutes'], predicted['supplies'], predicted['standing'])
            details.append(f'{name} finishes in {state[0]} minutes with {state[1]} supplies and standing {state[2]}')

    efficient = sum(not any(t <= time and s >= stock and (t, s) != (time, stock) for t, s in all_outcomes)
                    for time, stock in selected.values())
    trades = ('fast' in selected and 'stock' in selected and selected['fast'][0] < selected['stock'][0]
              and selected['fast'][1] < selected['stock'][1])
    return [
        _check('builds', valid_builds, 'Expected distinct 3+1 specialists and a 2+2 hybrid. '
               + ', '.join(f'{n} spent {sum(builds[n]["ranks"].values())}' for n in _BUILDS) + '.'),
        _check('routes', len(selected) == 3, '. '.join(details) + '.'),
        _check('consequences', earned_access and matched == 3, f'{matched}/3 forecasts match. '
               + ('Earned standing opens a later gate.' if earned_access else 'No successful route used a positive standing gate.')),
        _check('tradeoffs', trades and efficient == 3, f'{efficient}/3 results withstand comparison with all three builds. '
               + ('Fast trades stock for speed.' if trades else 'The fast and stock outcomes need a time/supply tradeoff.')),
        _check('investments', valid_builds and essential == 4,
               f'{essential} individual skill removals rule out every finish for their build. Four are required.'),
    ]
