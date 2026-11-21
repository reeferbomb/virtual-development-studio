"""Read-only, project-scoped supervision of saved Studio evidence."""

from collections import Counter
from datetime import datetime
from sys import float_info

from .provenance import spec_digest
from .scheduler import validate_tasks


_LABELS = {
    'build': 'Current-spec build', 'release': 'Active release',
    'task_board': 'Task board', 'manual_review': 'Manual task evidence',
    'defects': 'Defect tracking', 'performance': 'Build and verification timing',
}
_SEVERITIES = ('critical', 'high', 'medium', 'low')


class _Audit:
    def __init__(self, project):
        self.project_id = project['id']
        self.digest = spec_digest(project['spec'])
        self.checks = []
        self.recommendations = []

    def record(self, key, status, evidence, action=None):
        self.checks.append(dict(id=key, label=_LABELS[key], status=status, evidence=evidence))
        if action is not None:
            severity, role, title, detail = action
            self.recommendations.append(dict(id=key, severity=severity, role=role, title=title,
                                             detail=detail, evidence=[evidence]))

    def inspect(self, data, keys, inspect, *, project_scoped=True):
        # Store projections can be sampled separately while another writer changes the spec.
        try:
            if data is None:
                raise ValueError('Evidence source is unavailable.')
            if project_scoped and (not isinstance(data, dict) or data.get('project_id') != self.project_id
                                   or data.get('spec_sha256') != self.digest):
                raise ValueError('Evidence source does not identify this project and current specification.')
            inspect(self, data)
        except ValueError as error:
            for index, key in enumerate(keys):
                action = ('high', 'verification', f'Recover {_LABELS[key].lower()} evidence',
                          'Inspect the source record and refresh the audit for the saved specification.')
                self.record(key, 'fail', str(error), action if index == 0 else None)


def _rows(value, label):
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f'Invalid {label} records.')
    return value


def _latest_job(jobs):
    if len(jobs) == 1:
        return jobs[0]
    # Queue sequence is issued under the queue lock. Legacy jobs can lack it.
    sequences = [job.get('queue_sequence') for job in jobs]
    if all(type(seq) is int and seq > 0 for seq in sequences) and len(set(sequences)) == len(jobs):
        return max(jobs, key=lambda job: job['queue_sequence'])
    dates = []
    for job in jobs:
        value = job.get('created_at')
        try:
            date = datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            date = None
        if date is None or date.utcoffset() is None:
            raise ValueError('The submission order of the current-spec jobs cannot be verified.')
        dates.append(date)
    latest = max(dates)
    if dates.count(latest) != 1:
        raise ValueError('The latest current-spec job cannot be identified from tied submission times.')
    return jobs[dates.index(latest)]


def _build(audit, jobs):
    rows = _rows(jobs, 'build job')
    if any(not job.get('project_id') for job in rows):
        raise ValueError('The job history contains a record with unidentified project ownership.')
    project_jobs = [job for job in rows if job['project_id'] == audit.project_id]
    current = [job for job in project_jobs if job.get('spec_sha256') == audit.digest]
    if not current:
        evidence = f'No build job matches the current specification. {len(project_jobs)} project jobs carry other or missing specification digests.'
        audit.record('build', 'pending', evidence, ('medium', 'build_operations', 'Build the saved specification',
                     'Queue a build for this project and inspect its verification result.'))
        return
    job = _latest_job(current)
    job_id, status = job.get('id'), job.get('status')
    if not isinstance(job_id, str) or not job_id or status not in ('passed', 'failed', 'queued', 'running', 'canceled'):
        raise ValueError('The latest current-spec job has an invalid identity or status.')
    evidence = f'Latest current-spec job {job_id} is {status}.'
    if status == 'passed' and job.get('verified') is True:
        audit.record('build', 'pass', f'{evidence} Its recorded verification passed.')
    elif status in ('failed', 'passed'):
        if status == 'passed':
            evidence += ' A verified result is missing.'
        audit.record('build', 'fail', evidence, ('high', 'build_operations', 'Inspect the build evidence',
                     f'Review the log for job {job_id}, correct the cause and run a new verification.'))
    elif status == 'canceled':
        audit.record('build', 'pending', evidence, ('medium', 'build_operations', 'Resume build verification',
                     'Review the cancellation and queue a current-spec build when ready.'))
    else:
        audit.record('build', 'pending', evidence, ('low', 'build_operations', 'Follow the active build',
                     f'Check job {job_id} for its terminal status and verification result.'))


def _release(audit, registry):
    state, active_id = registry.get('active_state'), registry.get('active_release_id')
    releases = _rows(registry.get('releases'), 'release')
    if state == 'empty' and not releases and active_id is None:
        audit.record('release', 'pending', 'There is no active release.', ('low', 'build_operations',
                     'Review a release candidate', 'After verification, review a current-spec build for promotion.'))
        return
    active = [row for row in releases if row.get('id') == active_id]
    if not active_id or len(active) != 1 or not active[0].get('spec_sha256'):
        raise ValueError('The active release cannot be identified in the registry.')
    matches = active[0]['spec_sha256'] == audit.digest
    if state == 'current' and matches:
        audit.record('release', 'pass', f'Active release {active_id} passed the registry integrity check for the current specification.')
    elif state == 'stale' and not matches:
        audit.record('release', 'warn', f'Active release {active_id} belongs to a different specification.',
                     ('medium', 'build_operations', 'Review the stale release', 'Verify a build of the saved specification before promoting it.'))
    elif state == 'invalid':
        audit.record('release', 'fail', f'Active release {active_id} failed its registry integrity check.',
                     ('critical', 'build_operations', 'Investigate the invalid release',
                      'Inspect its job and package integrity, then select an intact current-spec release.'))
    else:
        raise ValueError('The release registry state disagrees with its active record.')


def _board(audit, board):
    tasks = board.get('tasks')
    validate_tasks(tasks)
    state, digest = board.get('state'), board.get('board_spec_sha256')
    if state == 'stale' and digest and digest != audit.digest:
        audit.record('task_board', 'warn', f'Board revision {board.get("revision")} belongs to an older specification.',
                     ('high', 'architecture', 'Reconcile the stale task board',
                      'Review the previous plan and running work before explicitly resetting it for the saved specification.'))
        audit.record('manual_review', 'pending', 'Manual task evidence from the stale board cannot establish current-spec completion.')
        return
    empty = state == 'empty' and digest is None and not tasks
    current = state == 'current' and digest == audit.digest
    if not (empty or current):
        raise ValueError('The task board state disagrees with its specification or tasks.')
    counts = Counter(task['status'] for task in tasks)
    if not tasks:
        audit.record('task_board', 'pending', 'The board has no tasks.', ('low', 'architecture',
                     'Plan the work', 'Add current-spec tasks with an owner and completion gate.'))
    elif counts['blocked']:
        blocked = sorted(task['id'] for task in tasks if task['status'] == 'blocked')
        audit.record('task_board', 'fail', f'Blocked tasks ({len(blocked)}) include {", ".join(blocked)}. {counts["running"]} tasks are running.',
                     ('high', 'architecture', 'Resolve blocked tasks', 'Inspect each blocking reason with its assigned specialist before requeuing.'))
    elif counts['completed'] == len(tasks):
        audit.record('task_board', 'pass', f'All {len(tasks)} current-spec board tasks have recorded completion.')
    else:
        audit.record('task_board', 'pending', f'{counts["running"]} running, {counts["pending"]} pending, {counts["completed"]} completed.',
                     ('low', 'architecture', 'Review remaining board work',
                      'Follow running tasks and use the scheduler to identify ready work for idle roles.'))
    manual = [task for task in tasks if task['gate'] == 'manual']
    completed = sum(task['status'] == 'completed' for task in manual)
    evidence = f'{completed} of {len(manual)} current-spec manual tasks have recorded completion evidence.'
    if manual and completed == len(manual):
        audit.record('manual_review', 'pass', evidence)
    else:
        audit.record('manual_review', 'pending', evidence, ('low', 'verification', 'Record manual review evidence',
                     'Review the planned manual checks and attach observed evidence to completed manual tasks.'))


def _defects(audit, ledger):
    items = _rows(ledger.get('items'), 'defect')
    if any(not isinstance(item.get('spec_sha256'), str) or not item['spec_sha256'] for item in items):
        raise ValueError('A defect has no specification identity.')
    current = [row for row in items if row['spec_sha256'] == audit.digest]
    if any(not isinstance(row.get('id'), str) or not row['id'] or row.get('status') not in ('open', 'resolved')
           or row.get('severity') not in _SEVERITIES for row in current):
        raise ValueError('A current-spec defect has an invalid identity, status or severity.')
    opened = sorted((row for row in current if row['status'] == 'open'),
                    key=lambda row: (_SEVERITIES.index(row['severity']), row['id']))
    if not opened:
        audit.record('defects', 'pass', f'No open defects among {len(current)} recorded for the current specification.')
        return
    top = opened[0]
    references = ', '.join(f'{item["id"]} ({item["severity"]})' for item in opened[:3])
    evidence = f'{len(opened)} open current-spec defect(s). Highest-priority records include {references}.'
    audit.record('defects', 'fail' if top['severity'] in ('critical', 'high') else 'warn', evidence,
                 (top['severity'], 'verification', 'Triage open defects',
                  f'Review defect {top["id"]} first, reproduce its observed symptoms and verify the correction before resolving it.'))


def _performance(audit, performance):
    regression = performance.get('regression')
    summary = performance.get('summary')
    if 'regression' not in performance or not isinstance(summary, dict):
        raise ValueError('The timing profile is incomplete.')
    if regression is None:
        audit.record('performance', 'pending', 'The timing profile has insufficient comparable verified samples or a usable baseline.',
                     ('low', 'build_operations', 'Collect comparable build timings',
                      'Review command timings from verified builds of the same specification until a comparison is available.'))
        return
    latest, baseline = summary.get('latest_total_seconds'), summary.get('baseline_total_seconds')
    if (type(regression) is not bool or not all(type(n) in (int, float) and 0 <= n <= float_info.max for n in (latest, baseline))
            or baseline <= 0):
        raise ValueError('The timing comparison has invalid or missing measurements.')
    evidence = f'The latest build and verification took {latest:g} seconds against a baseline of {baseline:g} seconds.'
    if regression:
        audit.record('performance', 'warn', evidence + ' The profile flagged a regression.', ('medium', 'build_operations',
                     'Investigate slower build timings', 'Compare build and verification command durations with the previous timed runs.'))
    else:
        audit.record('performance', 'pass', evidence + ' The profile reports no regression.')


def audit_project(project, jobs, board, registry, defects, performance):
    """Project an audit from caller-supplied snapshots without reading or changing any store."""
    audit = _Audit(project)
    audit.inspect(jobs, ('build',), _build, project_scoped=False)
    audit.inspect(registry, ('release',), _release)
    audit.inspect(board, ('task_board', 'manual_review'), _board)
    audit.inspect(defects, ('defects',), _defects)
    audit.inspect(performance, ('performance',), _performance)
    statuses = {check['status'] for check in audit.checks}
    status = next((result for check, result in (('fail', 'blocked'), ('warn', 'attention'), ('pending', 'pending'))
                   if check in statuses), 'pass')
    return dict(project_id=audit.project_id, spec_sha256=audit.digest, status=status, checks=audit.checks,
                recommendations=sorted(audit.recommendations, key=lambda item: (_SEVERITIES.index(item['severity']), item['id'])))
