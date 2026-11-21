"""Replay and compare player-selected survey routes under one deterministic ruleset."""

from itertools import product

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'replayability', 'title': 'Replayability and meaningful repeat play',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification'],
    'workflow': [
        'Name a reason someone might choose a second run. In a platformer that might be a cleaner line through '
        'the same room. In a detective story it might be a different witness, in a tactics game a new counter '
        'to a familiar opponent, and in a sandbox a self-chosen construction goal. Some stories earn a single '
        'satisfying playthrough. Preserve that ending.',
        'Prototype two strategies from the same starting state. Before each decision, show what the player '
        'can know and what they must give up. Try a slower resource-rich route and a fast route with fewer '
        'resources. Search for a third route that beats either on both goals.',
        'Vary one constraint at a time. For a generated layout, replay the same seed with different choices, '
        'then repeat the same choices across seeds. Record which decisions, costs or reachable outcomes '
        'changed. Swapped scenery can support atmosphere while leaving the underlying strategy identical.',
        'Complete the first run with a fresh profile. Bank the outcome, offer an easy exit and leave replay '
        'to an explicit choice. Check whether a repeat-count gate forces players to grind before they can '
        'try the alternatives. Show what they might try on a return without penalizing a break.',
    ],
    'deliverables': [
        'A first-run goal and an optional return goal suited to the genre, with two worked player decisions.',
        'Two fresh-start run traces, a comparison of their tradeoffs, and a counterexample search for a dominant strategy.',
        'An end-of-run save and exit flow, plus a playtest prompt that makes choosing to stop equally acceptable.',
    ],
    'verification': [
        'Reproduce both runs from identical initial conditions. Check that both can finish, identify the '
        'specific decisions that changed play, and test whether a feasible alternative outperforms either.',
        'Observe a fresh player reaching the end and freely choosing to leave or try again. Ask what they '
        'wanted to try or why they were satisfied. Report observed choices and stated reasons separately '
        'from playtime and return counts. Only player evidence can speak to enjoyment.',
    ],
    'exercise': 'Design a short survey with a fast route, a richer route and a clean place to stop.',
}


EXERCISES = [{
    'id': 'replayability', 'title': 'Give a field survey two worthwhile itineraries',
    'brief': 'Design 2–5 ordered legs with 2–4 options each. A fresh player has zero previous finishes. Choose '
             'one local option ID per leg. Each adds its minutes (1–45) and observations (0–20), and is available '
             'when prior_finishes (0–20) is at most the number already completed. Each run starts fresh. Reach '
             'the last leg within the common deadline (1–225 minutes). Submit two runs with their predicted '
             'minutes and observations. Vary the actual costs or yields on two or more legs. One run must be '
             'strictly faster and the other strictly richer in observations. Across every feasible first-run '
             'itinerary, no route may equal or improve both metrics and strictly improve at least one over either '
             'submission. Finish rules choose bank_on (arrival or replay), restart (opt_in or automatic) and '
             'quit_cost (0–100 observations). A clean stop banks the result on arrival, charges nothing to leave '
             'and waits for an explicit replay. These checks model route choices and exit rules.',
    'criteria': [
        {'id': 'predictions', 'label': 'Reproduce both claimed results by adding the chosen options.'},
        {'id': 'fresh-runs', 'label': 'Complete both itineraries before or at the deadline with zero prior finishes.'},
        {'id': 'decision-variety', 'label': 'Change a cost or yield through player choice on at least two legs.'},
        {'id': 'viable-tradeoff', 'label': 'Trade speed for discoveries on two routes that withstand comparison with every feasible itinerary.'},
        {'id': 'clean-stop', 'label': 'Bank the full result on arrival and make another run optional.'},
    ],
    'example': {
        'deadline': 16,
        'legs': [
            [{'id': 'boardwalk', 'minutes': 2, 'observations': 1, 'prior_finishes': 0},
             {'id': 'reed_hide', 'minutes': 5, 'observations': 4, 'prior_finishes': 0}],
            [{'id': 'crossing', 'minutes': 3, 'observations': 1, 'prior_finishes': 0},
             {'id': 'shoreline', 'minutes': 6, 'observations': 4, 'prior_finishes': 0}],
            [{'id': 'stairs', 'minutes': 2, 'observations': 1, 'prior_finishes': 0},
             {'id': 'lookout', 'minutes': 5, 'observations': 3, 'prior_finishes': 0}],
        ],
        'runs': [
            {'route': ['boardwalk', 'crossing', 'stairs'], 'minutes': 7, 'observations': 3},
            {'route': ['reed_hide', 'shoreline', 'lookout'], 'minutes': 16, 'observations': 11},
        ],
        'finish': {'bank_on': 'arrival', 'restart': 'opt_in', 'quit_cost': 0},
    },
}]


def _routes(legs):
    _array(legs, 2, 5, 'legs')
    indexed = []
    for index, leg in enumerate(legs, 1):
        _array(leg, 2, 4, f'Leg {index} options')
        options = {}
        for option in leg:
            _object(option, ('id', 'minutes', 'observations', 'prior_finishes'), f'Leg {index} option')
            _identifier(option['id'], 'Option ID')
            if option['id'] in options:
                raise ValueError(f'Leg {index} has a duplicate option ID.')
            _integer(option['minutes'], 1, 45, 'Option minutes')
            _integer(option['observations'], 0, 20, 'Option observations')
            _integer(option['prior_finishes'], 0, 20, 'Option prior_finishes')
            options[option['id']] = option
        indexed.append(options)
    return indexed


def _totals(options):
    return sum(option['minutes'] for option in options), sum(option['observations'] for option in options)


def _trace(run, legs):
    _object(run, ('route', 'minutes', 'observations'), 'Run')
    _integer(run['minutes'], 0, 225, 'Predicted minutes')
    _integer(run['observations'], 0, 100, 'Predicted observations')
    _array(run['route'], len(legs), len(legs), 'Run route')
    chosen = []
    for index, (name, options) in enumerate(zip(run['route'], legs), 1):
        _identifier(name, 'Chosen option ID')
        if name not in options:
            raise ValueError(f'Unknown option {name} on leg {index}.')
        chosen.append(options[name])
    return chosen


def _compare_itineraries(legs, deadline, totals):
    unlocked = [[option for option in options.values() if option['prior_finishes'] == 0] for options in legs]
    possible = ((route, _totals(route)) for route in product(*unlocked))
    feasible = [(route, score) for route, score in possible if score[0] <= deadline]
    witnesses = []
    for index, (minutes, observations) in enumerate(totals, 1):
        for route, (t, n) in feasible:
            if t <= minutes and n >= observations and (t, n) != (minutes, observations):
                path = ' / '.join(option['id'] for option in route)
                witnesses.append(f'Run {index} is beaten by {path} ({t} minutes, {n} observations).')
                break
    return len(feasible), witnesses


def assess(exercise_id, submission):
    if exercise_id != 'replayability':
        raise ValueError('Unknown replayability exercise.')
    _object(submission, ('deadline', 'legs', 'runs', 'finish'), 'Replayability submission')
    deadline = submission['deadline']
    _integer(deadline, 1, 225, 'deadline')
    legs = _routes(submission['legs'])
    runs = submission['runs']
    _array(runs, 2, 2, 'runs')
    chosen = [_trace(run, legs) for run in runs]
    totals = [_totals(route) for route in chosen]
    predictions = [(run['minutes'], run['observations']) for run in runs]
    finish = submission['finish']
    _object(finish, ('bank_on', 'restart', 'quit_cost'), 'finish')
    _choice(finish['bank_on'], ('arrival', 'replay'), 'bank_on')
    _choice(finish['restart'], ('opt_in', 'automatic'), 'restart')
    _integer(finish['quit_cost'], 0, 100, 'quit_cost')

    fresh = [all(option['prior_finishes'] == 0 for option in route) and minutes <= deadline
             for route, (minutes, _) in zip(chosen, totals)]
    different = sum((a['minutes'], a['observations']) != (b['minutes'], b['observations'])
                    for a, b in zip(*chosen))
    feasible_count, witnesses = _compare_itineraries(legs, deadline, totals)
    fast, slow = sorted(totals)
    tradeoff = fast[0] < slow[0] and fast[1] < slow[1]
    summary = 'The faster route finds fewer observations.' if tradeoff else 'The routes lack a strict speed/discovery tradeoff.'
    return [
        _check('predictions', predictions == totals,
               f'Computed (minutes, observations) pairs were {totals[0]} and {totals[1]}.'),
        _check('fresh-runs', all(fresh), f'{sum(fresh)} of 2 routes can finish fresh within {deadline} minutes.'),
        _check('decision-variety', different >= 2,
               f'Player choices changed minutes or observations on {different} of {len(legs)} legs.'),
        _check('viable-tradeoff', all(fresh) and tradeoff and not witnesses,
               ' '.join([f'Compared {feasible_count} feasible itineraries.', summary, *witnesses])),
        _check('clean-stop', finish == {'bank_on': 'arrival', 'restart': 'opt_in', 'quit_cost': 0},
               f"Bank on {finish['bank_on']}, restart {finish['restart']}, cost to leave {finish['quit_cost']}."),
    ]
