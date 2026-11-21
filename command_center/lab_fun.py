"""Assess the consequences and feedback of an authored choice in a synthetic courier game."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _integer


# Design references: Ryan, Rigby & Przybylski (2006), https://doi.org/10.1007/s11031-006-9051-8
# Hunicke, LeBlanc & Zubek (2004), https://aaai.org/papers/ws04-04-001-mda-a-formal-approach-to-game-design-and-game-research/
TRACK = {
    'id': 'player-enjoyment', 'title': 'Designing for player enjoyment',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Name a player fantasy and a particular audience. A marsh courier might want to feel resourceful. '
        'Give that player two routes, then ask what they noticed that made one worth taking.',
        'Treat autonomy, mastery and social connection as separate design hypotheses. Give a puzzle player '
        'room to try an approach, show the consequence and let them apply what they learned. In co-op, give '
        'partners different information and watch whether each has a decision worth communicating.',
        'Map a short sequence of decisions, signals and recovery. A horror player may welcome a long quiet '
        'approach when each sound changes what they expect. The same delay after a missed rhythm cue can '
        'interrupt practice. Compare what players predicted, noticed and tried next in each case.',
        'Prototype the verbs before polishing the scene. Make a route’s affordances and costs readable at '
        'play distance, then compare a player’s prediction before choosing with their explanation afterward. '
        'A striking visual can establish a promise that the available actions fail to deliver.',
        'Give players a clear stopping point, a way to retry and the option to decline another round without '
        'losing earned progress. Invite a second attempt for a new strategy or shared goal. Ask what made '
        'continuing or stopping worthwhile to the person who chose it.',
    ],
    'deliverables': [
        'Audience and fantasy statement, a playable choice with two viable approaches, and a diagram of the '
        'information available before and after it.',
        'A short playtest guide with neutral questions, a prediction that could prove wrong, and a revision '
        'linked to observed actions and the player’s own explanation.',
    ],
    'verification': [
        'Compare complete strategies, including unadvertised combinations. Check for a dominant shortcut, '
        'consequences too late to inform the next decision, and a recovery phase that repeats solved work.',
        'Ask for permission, observe a first attempt, then ask what the player expected and which part they '
        'would change. Record their words separately from your interpretation. Someone who retries may be '
        'confused or experimenting. A session length alone cannot distinguish those explanations.',
    ],
    'exercise': 'Design courier crossings for two different goals and verify the time, charge and feedback '
                'on both routes before inviting people to play.',
}


def _option(name, ticks, charge):
    return {'id': name, 'ticks': ticks, 'charge': charge, 'feedback': {'after_ticks': 1, 'charge': charge}}


_BUDGETS = {'urgent': (7, 12), 'reserve': (14, 4)}
EXERCISES = [{
    'id': TRACK['id'], 'title': 'Give the marsh courier a reason to change routes',
    'brief': 'Author 2–8 successive crossings for a courier. Each crossing is an array of 2–4 options with '
             'distinct lowercase IDs, time (1–12 ticks) and battery charge spent (0–12). Costs add across '
             'crossings. Each option issues one battery receipt with after_ticks (0–12 from selection) and '
             'charge (0–12 spent). This prototype requires correct feedback within one tick of the choice. '
             'For each dispatch, choose one option ID per crossing in order and predict total ticks and '
             'charge (0–96 each). Urgent has 7 ticks and 12 charge. Reserve has 14 ticks and 4 charge. '
             'Make urgent faster and more costly than reserve. Neither chosen route may have an alternative '
             'that saves either resource without spending more of the other. No route may fit both dispatch '
             'budgets. All limits apply only to this synthetic game. A human playtest is needed to learn '
             'whether players understand or enjoy the choice.',
    'criteria': [
        {'id': 'route-budgets', 'label': 'Complete both dispatches within their respective time and charge limits.'},
        {'id': 'tradeoff', 'label': 'Deliver two efficient, distinct strategies with no route that fits both briefs.'},
        {'id': 'feedback', 'label': 'Report the actual charge spent within one tick on every option.'},
        {'id': 'prediction', 'label': 'Predict the time and charge spent by each complete route.'},
    ],
    'example': {
        'crossings': [
            [_option('power_winch', 2, 4), _option('hand_crank', 4, 1)],
            [_option('pulse_motor', 2, 3), _option('follow_current', 4, 1)],
            [_option('lift_gate', 2, 4), _option('pole_around', 5, 1)],
        ],
        'routes': {
            'urgent': {'choices': ['power_winch', 'pulse_motor', 'lift_gate'], 'ticks': 6, 'charge': 11},
            'reserve': {'choices': ['hand_crank', 'follow_current', 'pole_around'], 'ticks': 13, 'charge': 3},
        },
    },
}]


def _read_crossings(rows):
    _array(rows, 2, 8, 'crossings')
    crossings = []
    for options in rows:
        _array(options, 2, 4, 'crossing options')
        by_id = {}
        for option in options:
            _object(option, ('id', 'ticks', 'charge', 'feedback'), 'option')
            name = option['id']
            _identifier(name, 'option ID')
            if name in by_id:
                raise ValueError('Each option needs a unique ID within its crossing.')
            _integer(option['ticks'], 1, 12, 'ticks')
            _integer(option['charge'], 0, 12, 'charge')
            feedback = option['feedback']
            _object(feedback, ('after_ticks', 'charge'), 'feedback')
            _integer(feedback['after_ticks'], 0, 12, 'after_ticks')
            _integer(feedback['charge'], 0, 12, 'feedback charge')
            by_id[name] = option
        crossings.append(by_id)
    return crossings


def _route_total(route, crossings):
    _object(route, ('choices', 'ticks', 'charge'), 'route')
    _integer(route['ticks'], 0, 96, 'predicted ticks')
    _integer(route['charge'], 0, 96, 'predicted charge')
    _array(route['choices'], len(crossings), len(crossings), 'route choices')
    for name in route['choices']:
        _identifier(name, 'chosen option')
    ticks = charge = 0
    for choices, name in zip(crossings, route['choices']):
        if name not in choices:
            return None
        ticks += choices[name]['ticks']
        charge += choices[name]['charge']
    return ticks, charge


def _least_charge_by_finish(crossings):
    # Future options depend only on the crossing. At any given arrival tick a
    # more costly route can never improve on a cheaper route to that crossing.
    best = {0: 0}
    for choices in crossings:
        after = {}
        for elapsed, spent in best.items():
            for option in choices.values():
                finish = elapsed + option['ticks']
                charge = spent + option['charge']
                if finish not in after or charge < after[finish]:
                    after[finish] = charge
        best = after
    return best


def _efficient(total, best):
    return not any(t <= total[0] and c <= total[1] and (t, c) != total for t, c in best.items())


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown player enjoyment exercise.')
    _object(submission, ('crossings', 'routes'), 'courier submission')
    crossings = _read_crossings(submission['crossings'])
    routes = submission['routes']
    _object(routes, tuple(_BUDGETS), 'routes')
    totals = {name: _route_total(routes[name], crossings) for name in _BUDGETS}
    within_budget = predicted = 0
    details = []
    for name, total in totals.items():
        if total is None:
            details.append(f'{name} chose an unknown option')
            continue
        ticks, charge = total
        tick_limit, charge_limit = _BUDGETS[name]
        within_budget += ticks <= tick_limit and charge <= charge_limit
        predicted += total == (routes[name]['ticks'], routes[name]['charge'])
        details.append(f'{name} used {ticks}/{tick_limit} ticks and {charge}/{charge_limit} charge')

    best = _least_charge_by_finish(crossings)
    fits_both = any(t <= _BUDGETS['urgent'][0] and c <= _BUDGETS['reserve'][1] for t, c in best.items())
    urgent, reserve = totals['urgent'], totals['reserve']
    efficient_count = sum(total is not None and _efficient(total, best) for total in totals.values())
    trade = urgent is not None and reserve is not None and urgent[0] < reserve[0] and urgent[1] > reserve[1]
    direction = 'Urgent spends more charge to save time.' if trade else 'Urgent needs to spend more charge to save time.'
    shared = 'A route fits both budgets.' if fits_both else 'No route fits both budgets.'
    options = [option for crossing in crossings for option in crossing.values()]
    receipts = sum(option['feedback']['after_ticks'] <= 1 and option['feedback']['charge'] == option['charge']
                   for option in options)
    return [
        _check('route-budgets', within_budget == 2, '. '.join(details) + '.'),
        _check('tradeoff', trade and efficient_count == 2 and not fits_both,
               f'{efficient_count}/2 chosen routes are efficient. {direction} {shared}'),
        _check('feedback', receipts == len(options), f'{receipts}/{len(options)} receipts give the correct charge within one tick.'),
        _check('prediction', predicted == 2, f'{predicted}/2 predictions match both simulated totals.'),
    ]
