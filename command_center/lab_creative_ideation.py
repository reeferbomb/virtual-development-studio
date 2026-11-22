"""Original divergent design practice; structural variation is not artistic merit."""

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _integer

TRACK = dict(id='creative-ideation', title='Creative ideation and concept development',
             roles=['architecture','gameplay','verification','ui','content','build_operations'],
             workflow=['Start from the player fantasy, audience, locked canon, budget and accessibility constraints. Ask what experience is missing.',
                       'Generate independent alternatives by changing verbs, rules, stakes, perspective, resources or consequences; avoid cosmetic variations and copying references.',
                       'Combine complementary ideas, test the weakest assumption first, and compare each option against tradeoffs. Preserve rejected ideas for later exploration.',
                       'Distinguish evidence from speculation, recommend a feasible original option, and explain why another option might be preferable.'],
             deliverables=['At least two meaningfully different concepts with player verbs and a clear tradeoff.',
                           'Feasible recommendation with separate measurable hypotheses and a cheap prototype plan.'],
             verification=['Check constraints, distinct mechanics and measurable assumptions; request independent critique.',
                           'Prototype and observe actual player choices later; neither novelty nor fun is certified by structural checks.'],
             exercise='Design multiple original courier experiences with distinct actions, tradeoffs and bounded prototype costs.')

EXERCISES = [dict(id=TRACK['id'],title='Generate contrasting concepts within a budget',
    brief='Provide 2–4 alternatives with unique lowercase IDs, a pitch, tradeoff, 2–4 unique verbs, prototype cost (1–12), a measurable hypothesis metric and threshold (1–100). Recommend an option. Every alternative must cost at most six units. The verb sets must differ and each option needs a distinct metric. This checks design structure, not creativity quality.',
    criteria=[dict(id='distinct',label='Alternatives use distinct sets of player verbs.'),dict(id='budget',label='Each prototype fits the six-unit budget.'),dict(id='hypotheses',label='Every concept has a distinct measurable test metric.'),dict(id='recommendation',label='Recommendation identifies a feasible alternative.')],
    example=dict(alternatives=[dict(id='route',pitch='Cross a shifting town with choices',tradeoff='More stateful navigation',verbs=['navigate','negotiate'],cost=5,metric='route-switches',threshold=2),
                               dict(id='salvage',pitch='Repair a courier machine as resources change',tradeoff='More inventory tuning',verbs=['salvage','repair'],cost=4,metric='successful-repairs',threshold=3)],recommendation='route'))]


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown creative practice')
    _object(submission, ('alternatives','recommendation'), 'submission')
    rows = submission['alternatives']
    _array(rows, 2, 4, 'alternatives')
    ids, verbs, metrics = set(), [], []
    costs = {}
    for row in rows:
        _object(row, ('id','pitch','tradeoff','verbs','cost','metric','threshold'), 'alternative')
        _identifier(row['id'],'alternative'); _identifier(row['metric'],'metric')
        if row['id'] in ids: raise ValueError('Duplicate alternative')
        ids.add(row['id'])
        _text(row['pitch'],240,'pitch'); _text(row['tradeoff'],240,'tradeoff')
        _array(row['verbs'],2,4,'verbs')
        for verb in row['verbs']: _identifier(verb,'verb')
        verbs.append(frozenset(row['verbs']))
        _integer(row['cost'],1,12,'prototype cost'); costs[row['id']] = row['cost']
        _integer(row['threshold'],1,100,'threshold'); metrics.append(row['metric'])
    _identifier(submission['recommendation'],'recommendation')
    return [_check('distinct', len(set(verbs)) == len(rows) and all(len(v)==len(r['verbs']) for v,r in zip(verbs,rows)), 'Compare distinct sets of actual player actions.'),
            _check('budget', all(c<=6 for c in costs.values()), 'Six prototype units per option.'),
            _check('hypotheses', len(set(metrics))==len(rows), 'Separate measurable predictions permit comparison.'),
            _check('recommendation', costs.get(submission['recommendation'],13)<=6, 'Recommendation must identify an affordable option.')]
