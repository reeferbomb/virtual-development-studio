"""Compare anonymous, user-supplied aggregate session counts, without pooling cohorts.

Input v1 contains schema_version, minimum_per_arm (2..100000), review_delta_pp
(1..100), and 0..36 rows. Each row represents one variant, scenario and cohort.
Use the same scenario label only for the same concrete task and observation
protocol within a submission. The two window_minutes values must match.
Variants are baseline and candidate. Scenario and cohort labels are enumerated
below. Each count is in 0..100000. Completed and abandoned are disjoint final
outcomes at the observation cutoff. Retried and confusion count distinct
sessions with at least one retry or predefined observable confusion signal.

The three replay fields may all be null when unobserved. Otherwise replay_offered
counts started sessions given a genuinely optional replay. Chosen and declined
are disjoint recorded decisions. Unanswered offers are retained separately.
Completion, abandonment, retries and confusion use started as denominator.
Replay choice uses answered offers, with offer coverage reported alongside.

Output differences are candidate minus baseline in percentage points. They are
withheld for unmatched or under-minimum comparisons. Displayed rates and deltas
round to four decimal places. User-specified review thresholds use unrounded
rates. Only lower completion or higher abandonment/confusion can cross the
adverse review threshold. Retry and replay differences have no assumed direction.
"""

from fractions import Fraction


_SCENARIOS = ('onboarding', 'navigation', 'encounter', 'puzzle', 'objective', 'return')
_COHORTS = ('all', 'first-time', 'returning')
_VARIANTS = ('baseline', 'candidate')
_SESSION_COUNTS = ('started', 'completed', 'abandoned', 'retried', 'confusion')
_REPLAY_COUNTS = ('replay_offered', 'replay_chosen', 'replay_declined')
_ROW_KEYS = {'variant', 'scenario', 'cohort', 'window_minutes', *_SESSION_COUNTS, *_REPLAY_COUNTS}
_METRICS = {'completion': 'completed', 'abandonment': 'abandoned', 'retry': 'retried',
            'confusion': 'confusion', 'replay_choice': 'replay_chosen'}
_ADVERSE = {'completion': -1, 'abandonment': 1, 'confusion': 1}


def example():
    """Return a fresh synthetic fixture. No participant or project data is used."""
    def row(variant, cohort, started, completed, abandoned, retried, confusion, offered, chosen, declined):
        return {'variant': variant, 'scenario': 'navigation', 'cohort': cohort, 'window_minutes': 15,
                'started': started, 'completed': completed, 'abandoned': abandoned, 'retried': retried,
                'confusion': confusion, 'replay_offered': offered, 'replay_chosen': chosen, 'replay_declined': declined}
    return {'schema_version': 1, 'minimum_per_arm': 10, 'review_delta_pp': 15, 'rows': [
        row('baseline', 'first-time', 24, 16, 6, 13, 9, 16, 6, 10),
        row('candidate', 'first-time', 25, 21, 3, 9, 5, 20, 7, 13),
        row('baseline', 'returning', 18, 16, 1, 4, 2, 15, 7, 8),
        row('candidate', 'returning', 20, 18, 1, 6, 2, 16, 7, 9),
    ]}


def _object(value, keys, field):
    if type(value) is not dict or value.keys() != keys:
        raise ValueError(f'{field} requires exactly these fields: {", ".join(sorted(keys))}.')


def _integer(value, low, high, field):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{field} must be an integer from {low} to {high}.')


def _read_row(row):
    _object(row, _ROW_KEYS, 'Observation row')
    for name, choices in (('variant', _VARIANTS), ('scenario', _SCENARIOS), ('cohort', _COHORTS)):
        if type(row[name]) is not str or row[name] not in choices:
            raise ValueError(f'{name} must be one of {", ".join(choices)}.')
    _integer(row['window_minutes'], 1, 1440, 'window_minutes')
    for name in _SESSION_COUNTS:
        _integer(row[name], 0, 100000 if name == 'started' else row['started'], name)
    if row['completed'] + row['abandoned'] > row['started']:
        raise ValueError('Completed and abandoned sessions together exceed starts.')
    if any(row[k] is not None for k in _REPLAY_COUNTS):
        for name in _REPLAY_COUNTS:
            _integer(row[name], 0, row['started'], name)
        if row['replay_chosen'] + row['replay_declined'] > row['replay_offered']:
            raise ValueError('Recorded replay choices exceed the available offers.')
    counts = {k: row[k] for k in ('window_minutes', *_SESSION_COUNTS, *_REPLAY_COUNTS)}
    counts['other_outcome'] = row['started'] - row['completed'] - row['abandoned']
    counts['replay_answered'] = None
    counts['replay_unanswered'] = None
    if row['replay_offered'] is not None:
        counts['replay_answered'] = row['replay_chosen'] + row['replay_declined']
        counts['replay_unanswered'] = row['replay_offered'] - counts['replay_answered']
    return counts


def _rate(row, field, denominator):
    if row is None or row[field] is None:
        return None, None
    count, base = row[field], row[denominator]
    exact = Fraction(100 * count, base) if base else None
    return {'count': count, 'denominator': base, 'percent': _display(exact)}, exact


def _display(value):
    return float(round(value, 4)) if value is not None else None


def _compare(scenario, cohort, arms, minimum, threshold):
    baseline, candidate = (arms.get(name) for name in _VARIANTS)
    mismatch = None
    if baseline is None or candidate is None:
        mismatch = 'missing_variant'
    elif baseline['window_minutes'] != candidate['window_minutes']:
        mismatch = 'different_windows'
    measures = {}
    for name, field in _METRICS.items():
        denominator = 'replay_answered' if name == 'replay_choice' else 'started'
        left, base_rate = _rate(baseline, field, denominator)
        right, candidate_rate = _rate(candidate, field, denominator)
        reason = mismatch
        if reason is None:
            if left is None or right is None:
                reason = 'replay_unobserved'
            elif min(left['denominator'], right['denominator']) < minimum:
                reason = 'insufficient_denominator'
        delta = None if reason else candidate_rate - base_rate
        alert = None if delta is None or name not in _ADVERSE else _ADVERSE[name] * delta >= threshold
        measures[name] = {'baseline': left, 'candidate': right, 'delta_pp': _display(delta),
                          'evidence': 'insufficient' if reason else 'descriptive', 'reason': reason,
                          'adverse_threshold_crossed': alert}
    return {'scenario': scenario, 'cohort': cohort, 'matched': mismatch is None, 'match_issue': mismatch,
            'baseline': baseline, 'candidate': candidate, 'measures': measures}


def _check(key, label, status, detail):
    return {'id': key, 'label': label, 'status': status, 'detail': detail}


def analyze(data: dict) -> dict:
    """Return a read-only descriptive diagnostic under the caller's screening settings."""
    _object(data, {'schema_version', 'minimum_per_arm', 'review_delta_pp', 'rows'}, 'Playtest input')
    _integer(data['schema_version'], 1, 1, 'schema_version')
    minimum, threshold = data['minimum_per_arm'], data['review_delta_pp']
    _integer(minimum, 2, 100000, 'minimum_per_arm')
    _integer(threshold, 1, 100, 'review_delta_pp')
    rows = data['rows']
    if type(rows) is not list or len(rows) > 36:
        raise ValueError('rows must be a list with at most 36 aggregate rows.')
    groups = {}
    for row in rows:
        counts = _read_row(row)
        arms = groups.setdefault((row['scenario'], row['cohort']), {})
        if row['variant'] in arms:
            raise ValueError('Duplicate scenario, cohort and variant combination.')
        arms[row['variant']] = counts
    pairs = [_compare(*key, groups[key], minimum, threshold) for key in sorted(groups)]
    total = len(pairs)
    matched = sum(pair['matched'] for pair in pairs)
    sufficient = sum(pair['measures']['completion']['evidence'] == 'descriptive' for pair in pairs)
    replay = sum(pair['measures']['replay_choice']['evidence'] == 'descriptive' for pair in pairs)
    partial = sum(any(arm is not None and (arm['replay_unanswered'] or 0) > 0
                      for arm in (pair['baseline'], pair['candidate'])) for pair in pairs)
    alerts = [{'scenario': pair['scenario'], 'cohort': pair['cohort'], 'measure': name,
               'delta_pp': pair['measures'][name]['delta_pp']}
              for pair in pairs for name in _ADVERSE if pair['measures'][name]['adverse_threshold_crossed']]
    adequate = 'pass' if sufficient and sufficient == total else 'warn'
    coverage = f'{sufficient} of {total} groups have matched arms with at least {minimum} starts each.'
    if not pairs:
        coverage = 'Insufficient evidence. No aggregate observation rows were supplied.'
    elif sufficient < total:
        coverage += f' Evidence is insufficient for {total - sufficient} groups.'
    checks = [
        _check('matched-scenarios', 'Matched scenarios, cohorts and windows',
               'pass' if matched and matched == total else 'warn',
               f'{matched} of {total} groups have both variants and equal observation windows.'),
        _check('sample-coverage', 'Started-session denominators', adequate, coverage),
        _check('outcome-review', 'Observed outcomes against the chosen review threshold',
               'fail' if alerts else adequate,
               f'{len(alerts)} observed adverse differences reached {threshold} percentage points '
               f'among {sufficient} comparable groups.'),
        _check('optional-replay', 'Recorded voluntary replay decisions',
               'pass' if replay and replay == total and not partial else 'warn',
               f'{replay} of {total} groups have at least {minimum} answered offers in both matched arms. '
               f'{partial} groups have unanswered offers.'),
    ]
    status = max((c['status'] for c in checks), key=('pass', 'warn', 'fail').index)
    return {'schema_version': 1, 'kind': 'playtest', 'status': status, 'checks': checks,
            'metrics': {'minimum_per_arm': minimum, 'review_delta_pp': threshold, 'row_count': len(rows),
                        'comparisons': pairs, 'review_flags': alerts},
            'advisory': 'Differences describe the supplied aggregate observations within each scenario and cohort. '
                        'Matching labels and windows cannot verify recruitment or protocol equivalence. '
                        'The configured minimum and review threshold are screening choices. A retry can reflect '
                        'practice or unclear feedback. Causal attribution and player enjoyment require separate evidence. '
                        'This diagnostic has no release authority.'}
