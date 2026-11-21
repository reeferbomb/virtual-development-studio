"""Read-only timings from the command center's saved pipeline jobs."""

import math
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from statistics import median

from .pipeline import STATUSES
from .provenance import spec_digest


SAMPLE_LIMIT = 50


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo is not None:
            return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        pass
    return None


def _seconds(value):
    if type(value) not in (int, float) or value < 0:
        return None
    try:
        if math.isfinite(value):
            return float(value)
    except OverflowError:
        pass
    return None


def _stage(commands, name):
    """Read a single measured command; duplicate stage records are ambiguous."""
    matches = [cmd for cmd in commands if isinstance(cmd, dict) and cmd.get('stage') == name]
    if len(matches) != 1:
        return None, False
    cmd = matches[0]
    # Older records may only have durations. Explicit failure contradicts a passed job.
    code = cmd.get('exit_code', 0)
    success = type(code) is int and code == 0 and cmd.get('timed_out', False) is False
    return _seconds(cmd.get('duration_seconds')), success


def _decimal(value):
    # Jobs record base-ten JSON seconds. Preserve that precision at inclusive thresholds.
    return Decimal(str(value))


def _median(values):
    numbers = [_decimal(value) for value in values]
    return float(median(numbers)) if numbers else None


def profile_jobs(project, jobs):
    """Profile this saved spec. The 50-row display limit does not limit the baseline.

    A sample's total is build plus verify, in seconds, excluding queue time.
    Medians use verified passed jobs with a complete pair of measured commands.
    Compare the newest dated such job to the median of at least two dated prior
    jobs, and flag regressions of at least 25 percent AND at least one second.
    A zero baseline has no defined percentage.
    """
    if (not isinstance(project, dict) or not isinstance(project.get('id'), str)
            or not project['id'] or not isinstance(project.get('spec'), dict)):
        raise ValueError('Expected a saved project with an ID and specification')
    if not isinstance(jobs, Iterable) or isinstance(jobs, (str, bytes, dict)):
        raise ValueError('Expected a collection of pipeline jobs')
    project_id, digest = project['id'], spec_digest(project['spec'])
    counts = dict.fromkeys(('total', *STATUSES), 0)
    rows = []
    seen = set()
    for job in jobs:
        if (not isinstance(job, dict) or job.get('project_id') != project_id
                or job.get('spec_sha256') != digest or job.get('status') not in STATUSES):
            continue
        job_id = job.get('id')
        if not isinstance(job_id, str) or not job_id or job_id in seen:
            continue
        seen.add(job_id)
        status = job['status']
        counts[status] += 1
        counts['total'] += 1
        created = _timestamp(job.get('created_at'))
        started = _timestamp(job.get('started_at'))
        queue = (started - created).total_seconds() if created and started and started >= created else None
        commands = job.get('commands')
        if not isinstance(commands, list):
            commands = []
        build, build_ok = _stage(commands, 'build')
        verify, verify_ok = _stage(commands, 'verify')
        total = None
        if build is not None and verify is not None:
            total = _seconds(float(_decimal(build) + _decimal(verify)))
        eligible = (status == 'passed' and job.get('verified') is True
                    and build_ok and verify_ok and total is not None)
        sample = {'job_id': job_id, 'status': status, 'created_at': job['created_at'] if created else None,
                  'queue_seconds': queue, 'build_seconds': build, 'verify_seconds': verify,
                  'total_seconds': total}
        rows.append((created, sample, eligible))

    rows.sort(key=lambda row: (row[0] is not None, row[0], row[1]['job_id']), reverse=True)
    passed = [sample for _, sample, eligible in rows if eligible]
    dated_totals = [sample['total_seconds'] for sample in passed if sample['created_at'] is not None]
    latest = dated_totals[0] if dated_totals else None
    baseline = _median(dated_totals[1:]) if len(dated_totals) >= 3 else None
    percent = regression = None
    if baseline is not None and baseline > 0:
        delta = _decimal(latest) - _decimal(baseline)
        change = float(delta / _decimal(baseline) * 100)
        if math.isfinite(change):
            percent = change
            regression = delta >= 1 and change >= 25
    summary = {f'median_{key}': _median(sample[key] for sample in passed)
               for key in ('build_seconds', 'verify_seconds', 'total_seconds')}
    summary.update(latest_total_seconds=latest, baseline_total_seconds=baseline,
                   regression_percent=percent)
    return {'project_id': project_id, 'spec_sha256': digest, 'scope': 'current_spec',
            'counts': counts, 'samples': [sample for _, sample, _ in rows[:SAMPLE_LIMIT]],
            'summary': summary, 'regression': regression}
