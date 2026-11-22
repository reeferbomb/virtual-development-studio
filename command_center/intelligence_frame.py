"""Offline frame-time analysis for named scenarios, using only the submitted intervals.

Input: {"scenarios": [{"name": str, "target_fps": int, "frame_times_us": [int, ...],
"budget": {...}}]}. Budget is optional. Its optional integer fields are min_samples
(default 100), max_p95_us (default ceil(1,000,000 / target_fps)), max_p99_us,
max_frame_us, max_late_bps, and max_late_run. Other limits apply only if provided.
Limits are inclusive. A short or empty capture warns; an observed budget breach fails.
Without an explicit run limit, a cluster of two or more late frames warns. Without
an explicit maximum-frame limit, a frame reaching double the rounded target period
warns. Separate scenarios have independent targets, budgets, and runs.
"""

_MAX_SCENARIOS = 16
_MAX_SAMPLES = 4096
_MAX_TOTAL = 8192
_MAX_FRAME_US = 10_000_000
_REPORTED_RUNS = 5
_BUDGET_BOUNDS = {
    'min_samples': (1, _MAX_SAMPLES),
    'max_p95_us': (1, _MAX_FRAME_US),
    'max_p99_us': (1, _MAX_FRAME_US),
    'max_frame_us': (1, _MAX_FRAME_US),
    'max_late_bps': (0, 10_000),
    'max_late_run': (0, _MAX_SAMPLES),
}
_SEVERITY = {'pass': 0, 'warn': 1, 'fail': 2}


def example():
    """An invented steady courtyard and tram-arrival capture; the latter has a short hitch cluster."""
    return {'scenarios': [
        {'name': 'Courtyard traversal', 'target_fps': 60,
         'frame_times_us': [14_950, 15_300, 15_870, 16_420] * 25},
        {'name': 'Tram arrival', 'target_fps': 40,
         'frame_times_us': [23_700] * 41 + [29_200, 33_100, 28_400] + [24_200] * 56,
         'budget': {'max_p99_us': 32_000, 'max_frame_us': 40_000, 'max_late_bps': 400}},
    ]}


def _fields(value, required, optional, label):
    if (type(value) is not dict or len(value) > len(required) + len(optional)
            or not required <= value.keys() or not value.keys() <= required | optional):
        raise ValueError(f'{label} has missing or unsupported fields.')


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer from {low} through {high}.')


def _validated(data):
    _fields(data, {'scenarios'}, set(), 'Frame analysis')
    scenarios = data['scenarios']
    if type(scenarios) is not list or not 1 <= len(scenarios) <= _MAX_SCENARIOS:
        raise ValueError(f'Provide 1–{_MAX_SCENARIOS} named scenarios.')
    names, total = set(), 0
    for row in scenarios:
        _fields(row, {'name', 'target_fps', 'frame_times_us'}, {'budget'}, 'Scenario')
        name = row['name']
        if (type(name) is not str or not 1 <= len(name) <= 64 or name != name.strip()
                or not name.isprintable() or name.casefold() in names):
            raise ValueError('Use distinct printable scenario names of 1–64 characters without outer spaces.')
        names.add(name.casefold())
        _integer(row['target_fps'], 1, 1000, 'target_fps')
        frames = row['frame_times_us']
        if type(frames) is not list or len(frames) > _MAX_SAMPLES:
            raise ValueError(f'Use at most {_MAX_SAMPLES} frame intervals per scenario.')
        total += len(frames)
        if total > _MAX_TOTAL:
            raise ValueError(f'Frame analysis accepts at most {_MAX_TOTAL} intervals across scenarios.')
        for interval in frames:
            _integer(interval, 1, _MAX_FRAME_US, 'Frame interval in microseconds')
        budget = row.get('budget', {})
        _fields(budget, set(), set(_BUDGET_BOUNDS), 'Scenario budget')
        for key, value in budget.items():
            _integer(value, *_BUDGET_BOUNDS[key], key)
    return scenarios


def _late_runs(frames, period):
    late_count = longest = 0
    clusters = []
    start, peak = None, 0
    # The sentinel closes a trailing cluster without modifying the supplied list.
    for index in range(len(frames) + 1):
        if index < len(frames) and frames[index] > period:
            if start is None:
                start = index
            peak = max(peak, frames[index])
            late_count += 1
        elif start is not None:
            length = index - start
            longest = max(longest, length)
            if length >= 2:
                clusters.append({'start_index': start, 'end_exclusive': index, 'frames': length, 'max_us': peak})
            start, peak = None, 0
    clusters.sort(key=lambda run: (-run['frames'], run['start_index']))
    return late_count, longest, clusters


def _scenario(row, index):
    frames = row['frame_times_us']
    count = len(frames)
    fps = row['target_fps']
    period = (1_000_000 + fps - 1) // fps
    budget = {'min_samples': 100, 'max_p95_us': period, **row.get('budget', {})}
    checks = []

    def check(key, label, status, detail):
        checks.append({'id': f'frame-{index}-{key}', 'label': f'{row["name"]} — {label}',
                       'status': status, 'detail': detail})

    check('coverage', 'Sample coverage', 'pass' if count >= budget['min_samples'] else 'warn',
          f'{count} observed intervals against the requested minimum of {budget["min_samples"]}.')
    values = sorted(frames)
    late_count, longest, clusters = _late_runs(frames, period)
    metrics = {
        'name': row['name'], 'target_fps': fps, 'target_period_us': period, 'budget': budget,
        'sample_count': count, 'observed_time_us': sum(frames),
        'p95_us': values[(95 * count + 99) // 100 - 1] if count else None,
        'p99_us': values[(99 * count + 99) // 100 - 1] if count else None,
        'max_us': values[-1] if count else None,
        'worst_frame_index': frames.index(values[-1]) if count else None,
        'late_frames': late_count, 'late_bps': (late_count * 10_000 + count - 1) // count if count else None,
        'longest_late_run': longest if count else None, 'stutter_run_count': len(clusters),
        'stutter_runs': clusters[:_REPORTED_RUNS], 'omitted_runs': max(0, len(clusters) - _REPORTED_RUNS),
    }
    if not count:
        check('pacing', 'Frame-time budgets', 'warn', 'No frame intervals were supplied for this scenario.')
        check('stutter', 'Hitches and late runs', 'warn', 'Hitch severity and late-frame share are unmeasured.')
        return metrics, checks

    thresholds = [('p95_us', 'max_p95_us'), ('p99_us', 'max_p99_us'), ('max_us', 'max_frame_us')]
    breaches = [f'{measure} {metrics[measure]} exceeds {budget[limit]}'
                for measure, limit in thresholds if limit in budget and metrics[measure] > budget[limit]]
    check('pacing', 'Frame-time budgets', 'fail' if breaches else 'pass',
          '. '.join(breaches) + '.' if breaches else 'Recorded intervals meet the configured frame-time limits.')

    breaches, signals = [], []
    if 'max_late_bps' in budget and metrics['late_bps'] > budget['max_late_bps']:
        breaches.append(f'Late share {metrics["late_bps"]} bps exceeds {budget["max_late_bps"]}.')
    if 'max_late_run' in budget and longest > budget['max_late_run']:
        breaches.append(f'A run of {longest} late frames exceeds {budget["max_late_run"]}.')
    if 'max_late_run' not in budget and clusters:
        signals.append(f'{len(clusters)} stutter runs observed. The longest lasted {longest} frames.')
    if 'max_frame_us' not in budget and metrics['max_us'] >= 2 * period:
        signals.append(f'The {metrics["max_us"]} us worst frame reached at least two target periods.')
    check('stutter', 'Hitches and late runs', 'fail' if breaches else 'warn' if signals else 'pass',
          ' '.join(breaches + signals) or f'{late_count}/{count} frames exceeded {period} us.')
    return metrics, checks


def analyze(data: dict) -> dict:
    """Return a JSON-compatible report with advisory severity. Invalid inputs raise ValueError."""
    scenarios = _validated(data)
    checks, summaries = [], []
    for index, scenario in enumerate(scenarios, 1):
        metrics, findings = _scenario(scenario, index)
        summaries.append(metrics)
        checks.extend(findings)
    return {
        'schema_version': 1, 'kind': 'frame',
        'status': max((item['status'] for item in checks), key=_SEVERITY.get),
        'checks': checks,
        'metrics': {'scenario_count': len(summaries), 'sample_count': sum(s['sample_count'] for s in summaries),
                    'scenarios': summaries},
        'advisory': 'Only the supplied intervals and named scenarios were evaluated. P95 and P99 use nearest '
                    'rank. The target period and late share in basis points round up. A stutter run contains '
                    'at least two consecutive frames strictly over that period. Frame indices are zero-based. '
                    'Up to five longest runs are shown, earliest first on ties. Short samples give coarse tail '
                    'estimates. Confirm findings using repeat captures on identified hardware and a CPU/GPU '
                    'profiler. These numbers cannot determine the cause of a hitch or certify hardware or release readiness.',
    }
