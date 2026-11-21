"""Deterministic, data-only academy exercises for gameplay, QA and performance."""


def _criterion(identifier, label):
    return {'id': identifier, 'label': label}


def _capture(frames, memory):
    return {'scene': 'beacon-yard', 'device': 'fixture-a', 'width': 1280, 'height': 720,
            'samples': [{'frame_ms': ms, 'memory_mib': mib}
                        for ms, mib in zip(frames, memory, strict=True)]}


EXERCISES = [
    {
        'id': 'game-development', 'title': 'Inventory checkpoint',
        'brief': 'Start with zero cells, a five-cell capacity and an empty save slot. Supply up to 32 '
                 'ordered steps. Take or drop 1–100 units atomically, rejecting overflow and underflow. '
                 'Save replaces the slot with the current count. Load restores it, or is rejected if '
                 'no save exists. Predict accepted (boolean) and expected_count after every step. '
                 'Demonstrate successful take and drop, both limit rejections and a load that changes the count.',
        'criteria': [_criterion('transitions', 'Predict successful takes and drops'),
                     _criterion('rejections', 'Reject overflow and underflow without changing inventory'),
                     _criterion('persistence', 'Restore a saved count after changing the inventory')],
        'example': {'steps': [
            {'op': 'take', 'units': 3, 'accepted': True, 'expected_count': 3},
            {'op': 'save', 'accepted': True, 'expected_count': 3},
            {'op': 'drop', 'units': 1, 'accepted': True, 'expected_count': 2},
            {'op': 'take', 'units': 4, 'accepted': False, 'expected_count': 2},
            {'op': 'drop', 'units': 3, 'accepted': False, 'expected_count': 2},
            {'op': 'load', 'accepted': True, 'expected_count': 3}]},
    },
    {
        'id': 'quality-assurance', 'title': 'Beacon reward regression',
        'brief': 'Each case starts with an unlit beacon, zero rewards and an empty save slot. Light grants '
                 'one reward only when unlit. Save copies the lit flag and reward count. Load restores both '
                 'on the fixed build, while the broken build restores the count and always clears the flag. '
                 'Loading an empty slot does nothing. Trace first-light with one light, repeat-light with '
                 'consecutive lights, and checkpoint-light with a save/reload/relight that exposes the bug. '
                 'For each case predict the required reward total and the observed total on its build. '
                 'Supply a single regression sequence and predict its expected, broken and fixed reward totals. '
                 'Submit up to 16 cases and up to 32 actions per sequence.',
        'criteria': [_criterion('traceability', 'Link all three requirements to scenarios that exercise them'),
                     _criterion('observations', 'Record required and observed reward totals for each case'),
                     _criterion('regression', 'Use the same steps to detect the defect and verify the repair')],
        'example': {'cases': [
            {'requirement': 'first-light', 'build': 'fixed', 'steps': ['light'],
             'expected_rewards': 1, 'actual_rewards': 1},
            {'requirement': 'repeat-light', 'build': 'broken', 'steps': ['light', 'light'],
             'expected_rewards': 1, 'actual_rewards': 1},
            {'requirement': 'checkpoint-light', 'build': 'broken', 'steps': ['light', 'save', 'load', 'light'],
             'expected_rewards': 1, 'actual_rewards': 2}],
            'regression': {'steps': ['light', 'save', 'load', 'light'], 'expected_rewards': 1,
                           'broken_rewards': 2, 'fixed_rewards': 1}},
    },
    {
        'id': 'build-performance', 'title': 'Frame and memory budget comparison',
        'brief': 'Use paired synthetic captures of the same scene, device and resolution with the same number '
                 'of samples (5–32 per run). For each run report nearest-rank p95 frame time in milliseconds '
                 '(sort times, select rank ceil(0.95 × count), counting from one), and peak memory in MiB. '
                 'Start with a run that exceeds at least one budget. Meet both limits after optimization: '
                 'p95 at most 17 ms and peak at most 256 MiB. These measurements describe a fixture.',
        'criteria': [_criterion('comparability', 'Match scene, device, resolution and sample count'),
                     _criterion('summary', 'Calculate p95 frame time and peak memory for both captures'),
                     _criterion('budgets', 'Bring an over-budget baseline within both limits')],
        'example': {'baseline': _capture([19, 21, 20, 22, 18], [240, 250, 254, 263, 246]),
                    'optimized': _capture([15, 16, 14, 17, 15], [239, 240, 244, 245, 241]),
                    'summary': {'baseline_p95_ms': 22, 'baseline_peak_mib': 263,
                                'optimized_p95_ms': 17, 'optimized_peak_mib': 245}},
    },
]


def _object(value, keys, location):
    if type(value) is not dict or len(value) != len(keys) or not all(key in value for key in keys):
        raise ValueError(f'{location} requires exactly these fields: {", ".join(keys)}')


def _array(value, limit, location, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= limit:
        raise ValueError(f'{location} requires a list of {minimum}–{limit} entries')


def _integer(value, minimum, maximum, location):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{location} requires an integer from {minimum} to {maximum}')


def _number(value, maximum, location):
    if type(value) not in (int, float) or not 0 < value <= maximum:
        raise ValueError(f'{location} requires a positive finite measurement up to {maximum}')


def _choice(value, choices, location):
    if type(value) is not str or value not in choices:
        raise ValueError(f'{location} must be one of {", ".join(choices)}')


def _result(identifier, passed, detail):
    return {'id': identifier, 'status': 'pass' if passed else 'fail', 'detail': detail}


def _inventory(submission):
    _object(submission, ('steps',), 'Inventory')
    _array(submission['steps'], 32, 'steps')
    count, saved = 0, None
    moved, rejected = set(), set()
    restored = False
    errors = {}
    for index, step in enumerate(submission['steps'], 1):
        name = f'steps[{index - 1}]'
        if type(step) is not dict:
            raise ValueError(f'{name} requires an object')
        op = step.get('op')
        _choice(op, ('take', 'drop', 'save', 'load'), name + '.op')
        keys = ('op', 'accepted', 'expected_count')
        is_move = op in ('take', 'drop')
        _object(step, keys + (('units',) if is_move else ()), name)
        _integer(step['expected_count'], 0, 1000, name + '.expected_count')
        if type(step['accepted']) is not bool:
            raise ValueError(f'{name}.accepted requires a boolean')

        accepted = True
        if is_move:
            units = step['units']
            _integer(units, 1, 100, name + '.units')
            proposed = count + (units if op == 'take' else -units)
            accepted = 0 <= proposed <= 5
            if accepted:
                count = proposed
                moved.add(op)
                criterion = 'transitions'
            else:
                rejected.add(op)
                criterion = 'rejections'
        else:
            criterion = 'persistence'
            if op == 'save':
                saved = count
            elif saved is None:
                accepted = False
            else:
                restored |= count != saved
                count = saved
        if accepted != step['accepted'] or count != step['expected_count']:
            errors.setdefault(criterion, f'Step {index} ({op}) was {"accepted" if accepted else "rejected"} '
                                          f'and left {count} cells.')
    outcomes = [('transitions', len(moved) == 2, 'Successful action types covered', len(moved), 2),
                ('rejections', len(rejected) == 2, 'Limit rejection types covered', len(rejected), 2),
                ('persistence', restored, 'Loads restoring a different count demonstrated', int(restored), 1)]
    return [_result(key, covered and key not in errors, errors.get(key, f'{label}: {amount}/{target}.'))
            for key, covered, label, amount, target in outcomes]


_REQUIREMENTS = ('first-light', 'repeat-light', 'checkpoint-light')


def _reward_totals(steps, location):
    """Replay the same sequence on each build, with a fresh save slot per build."""
    _array(steps, 32, location)
    for step in steps:
        _choice(step, ('light', 'save', 'load'), location)
    totals = {}
    for build in ('broken', 'fixed'):
        lit, rewards, saved = False, 0, None
        for step in steps:
            if step == 'light' and not lit:
                lit = True
                rewards += 1
            elif step == 'save':
                saved = (lit, rewards)
            elif step == 'load' and saved is not None:
                lit, rewards = saved
                if build == 'broken':
                    lit = False
        totals[build] = rewards
    return totals


def _qa(submission):
    _object(submission, ('cases', 'regression'), 'QA')
    _array(submission['cases'], 16, 'cases')
    covered = set()
    trace_error = observation_error = None
    for index, case in enumerate(submission['cases'], 1):
        name = f'cases[{index - 1}]'
        _object(case, ('requirement', 'build', 'steps', 'expected_rewards', 'actual_rewards'), name)
        requirement, build, steps = case['requirement'], case['build'], case['steps']
        _choice(requirement, _REQUIREMENTS, name + '.requirement')
        _choice(build, ('broken', 'fixed'), name + '.build')
        totals = _reward_totals(steps, name + '.steps')
        for field in ('expected_rewards', 'actual_rewards'):
            _integer(case[field], 0, 1000, name + '.' + field)
        trace = {'first-light': steps == ['light'],
                 'repeat-light': len(steps) >= 2 and all(step == 'light' for step in steps),
                 'checkpoint-light': totals['broken'] != totals['fixed']}
        if trace[requirement]:
            covered.add(requirement)
        elif trace_error is None:
            trace_error = f'Case {index} does not exercise {requirement}.'
        if (case['expected_rewards'], case['actual_rewards']) != (totals['fixed'], totals[build]):
            if observation_error is None:
                observation_error = (f'Case {index} requires {totals["fixed"]} rewards; '
                                     f'the {build} fixture produced {totals[build]}.')
    regression = submission['regression']
    _object(regression, ('steps', 'expected_rewards', 'broken_rewards', 'fixed_rewards'), 'regression')
    totals = _reward_totals(regression['steps'], 'regression.steps')
    for field in ('expected_rewards', 'broken_rewards', 'fixed_rewards'):
        _integer(regression[field], 0, 1000, 'regression.' + field)
    detects = totals['broken'] != totals['fixed']
    matches = (regression['expected_rewards'] == regression['fixed_rewards'] == totals['fixed']
               and regression['broken_rewards'] == totals['broken'])
    missing = [key for key in _REQUIREMENTS if key not in covered]
    return [
        _result('traceability', not trace_error and not missing,
                trace_error or ('Missing scenarios: ' + ', '.join(missing) if missing else 'All requirements traced.')),
        _result('observations', bool(submission['cases']) and not observation_error,
                observation_error or f'{len(submission["cases"])} case observations matched the fixture.'),
        _result('regression', detects and matches,
                f'The replay requires {totals["fixed"]} rewards. Broken produced {totals["broken"]} '
                f'and fixed produced {totals["fixed"]}.'),
    ]


def _metrics(capture, stage):
    _object(capture, ('scene', 'device', 'width', 'height', 'samples'), stage)
    for field in ('scene', 'device'):
        value = capture[field]
        if type(value) is not str or not 1 <= len(value) <= 64 or not value.strip():
            raise ValueError(f'{stage}.{field} requires a name of 1–64 characters')
    for field in ('width', 'height'):
        _integer(capture[field], 1, 16384, stage + '.' + field)
    samples = capture['samples']
    _array(samples, 32, stage + '.samples', minimum=1)
    for index, sample in enumerate(samples):
        name = f'{stage}.samples[{index}]'
        _object(sample, ('frame_ms', 'memory_mib'), name)
        _number(sample['frame_ms'], 10000, name + '.frame_ms')
        _number(sample['memory_mib'], 1048576, name + '.memory_mib')
    times = sorted(s['frame_ms'] for s in samples)
    rank = (95 * len(times) + 99) // 100
    return times[rank - 1], max(s['memory_mib'] for s in samples)


def _performance(submission):
    _object(submission, ('baseline', 'optimized', 'summary'), 'Performance')
    baseline, optimized, summary = (submission[k] for k in ('baseline', 'optimized', 'summary'))
    before, after = _metrics(baseline, 'baseline'), _metrics(optimized, 'optimized')
    keys = ('baseline_p95_ms', 'baseline_peak_mib', 'optimized_p95_ms', 'optimized_peak_mib')
    _object(summary, keys, 'summary')
    mismatches = []
    for key, result in zip(keys, (*before, *after), strict=True):
        _number(summary[key], 10000 if key.endswith('_ms') else 1048576, 'summary.' + key)
        if summary[key] != result:
            mismatches.append(f'{key} should be {result}')
    dimensions = [k for k in ('scene', 'device', 'width', 'height') if baseline[k] != optimized[k]]
    if len(baseline['samples']) != len(optimized['samples']):
        dimensions.append('sample count differs')
    if min(len(baseline['samples']), len(optimized['samples'])) < 5:
        dimensions.append('fewer than five samples')
    over_before = before[0] > 17 or before[1] > 256
    within_after = after[0] <= 17 and after[1] <= 256
    return [
        _result('comparability', not dimensions,
                'Check capture conditions: ' + ', '.join(dimensions) if dimensions else 'Capture conditions match.'),
        _result('summary', not mismatches, ', '.join(mismatches) or 'Both runs match the computed p95 and peak.'),
        _result('budgets', not dimensions and over_before and within_after,
                f'Baseline: {before[0]} ms / {before[1]} MiB. Optimized: {after[0]} ms / {after[1]} MiB. '
                'Require comparable runs and a change from outside to within the 17 ms and 256 MiB limits.'),
    ]


def assess(exercise_id, submission):
    """Return ordered criterion results, raising ValueError on malformed lab data."""
    assessors = {'game-development': _inventory, 'quality-assurance': _qa, 'build-performance': _performance}
    if type(exercise_id) is not str or exercise_id not in assessors:
        raise ValueError('Unknown gameplay lab exercise')
    return assessors[exercise_id](submission)
