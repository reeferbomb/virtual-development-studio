"""Compare encounter results from matched, user-supplied test conditions.

Version 1 accepts only schema_version, source ('synthetic' or 'production'),
builds (2–12 unique IDs), scenarios (1–12) and rows. Each scenario declares
an id and trials (1–32). Two optional fields express the designer's viability
constraints: max_win_ms (inclusive) and min_win_percent (1–100). A win meeting
the time budget qualifies. Without a percentage target one qualifying win
suffices. Times are integer milliseconds in the range 1–3,600,000.

Each row has scenario, build, trial (1-based), outcome (win/loss/timeout), and
win_ms (a completion time for a win, null otherwise). The same scenario/trial
must represent the same setup, seed and test conditions across builds. The
ordinal labels a scripted condition. The format has no participant field.

Missing rows and plans below three trials produce coverage warnings. Viability
is evaluated only on complete scenario/build cells with three or more trials.
Dominance is assessed for a pair only when both builds meet that requirement in
every declared scenario. Within a trial, a win beats a nonwin and a faster win
beats a slower win. Loss and timeout tie. A build dominates if it ties or beats
its counterpart in every trial and strictly beats it in at least one. Viability
uses the authored constraints, while dominance compares the raw results. These
are descriptive screens over the supplied matrix without statistical inference.
"""

from itertools import combinations
from statistics import median

from .lab_design import _identifier
from .lab_gameplay import _array, _choice, _integer, _object


_MAX_WIN_MS = 3_600_000
_MIN_TRIALS = 3
_OUTCOMES = ('win', 'loss', 'timeout')


def example():
    """Return a fresh synthetic matrix with different strengths at each encounter."""
    builds = ['anchor', 'glider', 'coil']
    scenarios = [
        {'id': 'relay-ring', 'trials': 3, 'max_win_ms': 75000, 'min_win_percent': 50},
        {'id': 'lantern-yard', 'trials': 3},
    ]
    times = {
        'relay-ring': [(41000, 41000, 'loss'), (47000, 'timeout', 35000), ('loss', 39000, 46000)],
        'lantern-yard': [(60000, 54000, 'timeout'), ('loss', 30000, 37000), (42500, 'loss', 49500)],
    }
    rows = []
    for scenario, courses in times.items():
        for build, results in zip(builds, courses, strict=True):
            for trial, result in enumerate(results, 1):
                won = isinstance(result, int)
                rows.append({'scenario': scenario, 'build': build, 'trial': trial,
                             'outcome': 'win' if won else result, 'win_ms': result if won else None})
    return {'schema_version': 1, 'source': 'synthetic', 'builds': builds, 'scenarios': scenarios, 'rows': rows}


def _read(data):
    _object(data, ('schema_version', 'source', 'builds', 'scenarios', 'rows'), 'Balance input')
    _integer(data['schema_version'], 1, 1, 'Schema version')
    _choice(data['source'], ('synthetic', 'production'), 'Source')
    _array(data['builds'], 12, 'Builds', minimum=2)
    for build in data['builds']:
        _identifier(build, 'Build ID')
    builds = sorted(data['builds'])
    if len(set(builds)) != len(builds):
        raise ValueError('Build IDs must be unique.')
    _array(data['scenarios'], 12, 'Scenarios', minimum=1)
    scenarios = {}
    for spec in data['scenarios']:
        if type(spec) is not dict:
            raise ValueError('Scenario must be an object.')
        optional = [key for key in ('max_win_ms', 'min_win_percent') if key in spec]
        _object(spec, ('id', 'trials', *optional), 'Scenario')
        _identifier(spec['id'], 'Scenario ID')
        _integer(spec['trials'], 1, 32, 'Planned trials')
        if 'max_win_ms' in spec:
            _integer(spec['max_win_ms'], 1, _MAX_WIN_MS, 'Maximum win time')
        if 'min_win_percent' in spec:
            _integer(spec['min_win_percent'], 1, 100, 'Minimum qualifying win percentage')
        if spec['id'] in scenarios:
            raise ValueError('Scenario IDs must be unique.')
        scenarios[spec['id']] = spec

    _array(data['rows'], len(builds) * sum(s['trials'] for s in scenarios.values()), 'Rows')
    cells = {(scenario, build): {} for scenario in sorted(scenarios) for build in builds}
    for row in data['rows']:
        _object(row, ('scenario', 'build', 'trial', 'outcome', 'win_ms'), 'Test row')
        _choice(row['scenario'], scenarios, 'Row scenario')
        _choice(row['build'], builds, 'Row build')
        cell = cells[row['scenario'], row['build']]
        trial = row['trial']
        _integer(trial, 1, scenarios[row['scenario']]['trials'], 'Row trial')
        if trial in cell:
            raise ValueError('Duplicate trial for the same scenario and build.')
        _choice(row['outcome'], _OUTCOMES, 'Outcome')
        if row['outcome'] == 'win':
            _integer(row['win_ms'], 1, _MAX_WIN_MS, 'Win time')
        elif row['win_ms'] is not None:
            raise ValueError('A loss or timeout must have a null win time.')
        cell[trial] = row
    return builds, scenarios, cells


def _summarize(spec, build, cell):
    win_times = [row['win_ms'] for row in cell.values() if row['outcome'] == 'win']
    qualified = sum(ms <= spec.get('max_win_ms', _MAX_WIN_MS) for ms in win_times)
    trials = spec['trials']
    required = max(1, (trials * spec.get('min_win_percent', 0) + 99) // 100)
    assessed = len(cell) == trials and trials >= _MIN_TRIALS
    viability = 'unassessed'
    if assessed:
        viability = 'meets-target' if qualified >= required else 'below-target'
    return {
        'scenario': spec['id'], 'build': build, 'planned_trials': trials, 'observed_trials': len(cell),
        'missing_trials': [i for i in range(1, trials + 1) if i not in cell],
        'wins': len(win_times), 'losses': sum(r['outcome'] == 'loss' for r in cell.values()),
        'timeouts': sum(r['outcome'] == 'timeout' for r in cell.values()),
        'median_win_ms': median(win_times) if win_times else None, 'max_win_ms': spec.get('max_win_ms'),
        'min_win_percent': spec.get('min_win_percent'), 'qualifying_wins': qualified,
        'required_wins': required, 'viability': viability,
    }


def _pairwise(builds, scenarios, cells, eligible):
    pairs = []
    for left, right in combinations(builds, 2):
        if left not in eligible or right not in eligible:
            continue
        left_better = right_better = tied = 0
        for scenario in sorted(scenarios):
            for trial, lrow in cells[scenario, left].items():
                rrow = cells[scenario, right][trial]
                # Both nonwins sort after the slowest accepted win and tie each other.
                ltime = lrow['win_ms'] if lrow['outcome'] == 'win' else _MAX_WIN_MS + 1
                rtime = rrow['win_ms'] if rrow['outcome'] == 'win' else _MAX_WIN_MS + 1
                if ltime < rtime:
                    left_better += 1
                elif rtime < ltime:
                    right_better += 1
                else:
                    tied += 1
        dominant = None
        if left_better and not right_better:
            dominant = left
        elif right_better and not left_better:
            dominant = right
        pairs.append({'left': left, 'right': right, 'left_better': left_better, 'right_better': right_better,
                      'tied': tied, 'dominant': dominant})
    return pairs


def analyze(data: dict) -> dict:
    """Return a deterministic JSON-ready advisory without modifying the supplied data."""
    builds, scenarios, cells = _read(data)
    summaries = [_summarize(scenarios[scenario], build, cell) for (scenario, build), cell in cells.items()]
    unassessed = [s for s in summaries if s['viability'] == 'unassessed']
    below = sum(s['viability'] == 'below-target' for s in summaries)
    eligible = set(builds) - {s['build'] for s in unassessed}
    pairs = _pairwise(builds, scenarios, cells, eligible)
    possible_pairs = len(builds) * (len(builds) - 1) // 2
    dominant = sum(pair['dominant'] is not None for pair in pairs)
    planned = sum(s['planned_trials'] for s in summaries)
    observed = len(data['rows'])

    checks = [
        {'id': 'coverage', 'label': 'Matched trial coverage', 'status': 'warn' if unassessed else 'pass',
         'detail': f'{observed}/{planned} planned rows supplied. {len(unassessed)}/{len(summaries)} '
                   f'build/scenario cells lack a complete plan of at least {_MIN_TRIALS} trials.'},
        {'id': 'viability', 'label': 'Observed encounter viability',
         'status': 'fail' if below else ('warn' if unassessed else 'pass'),
         'detail': f'{below} complete cells fell below their win target. {len(unassessed)} cells unassessed.'},
        {'id': 'dominance', 'label': 'Matched build dominance',
         'status': 'warn' if dominant or len(pairs) < possible_pairs else 'pass',
         'detail': f'Compared {len(pairs)}/{possible_pairs} build pairs across every scenario. '
                   f'{dominant} pairs had one build match or beat the other on every trial with at least one strict advantage.'},
    ]
    status = max((c['status'] for c in checks), key=('pass', 'warn', 'fail').index)
    return {
        'schema_version': 1, 'kind': 'balance', 'status': status, 'checks': checks,
        'metrics': {'source': data['source'], 'planned_rows': planned, 'observed_rows': observed, 'cells': summaries,
                    'possible_pairs': possible_pairs, 'compared_pairs': len(pairs), 'pair_results': pairs},
        'advisory': 'These observations cover only the supplied encounter conditions. Confirm matched setups, '
                    'investigate flagged builds and test player experience separately. Release decisions require independent review.',
    }
