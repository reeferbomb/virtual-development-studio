"""Build a deterministic release evidence report from read-only store projections."""

from . import acceptance as readiness
from . import performance, supervisor
from .defect_store import _fields, _text
from .evidence_history import CHECK_FIELDS, MAX_EVIDENCE, validate_audit
from .handoff_store import validate_history as validate_handoffs
from .pipeline import STATUSES
from .projects import PROJECT_ID, PROJECT_NAME, TEMPLATES
from .provenance import spec_digest
from .release_store import RELEASE_FIELDS, _output
from .task_store import JOB_ID, _valid_digest
from .work_orders import _check_board, order_id


def _check_scope(source, project_id, digest):
    if not readiness._same_scope(source, project_id, digest):
        raise ValueError('Source belongs to a different project or specification.')


def _project(project):
    if not isinstance(project, dict):
        raise ValueError('Expected project metadata.')
    identifier, name, kind = (project.get(key) for key in ('id', 'name', 'kind'))
    if (not isinstance(identifier, str) or len(identifier) > 80 or not PROJECT_ID.fullmatch(identifier)
            or not isinstance(name, str) or not PROJECT_NAME.fullmatch(name) or name != name.strip()
            or not isinstance(kind, str) or kind not in TEMPLATES or not isinstance(project.get('spec'), dict)):
        raise ValueError('Invalid project metadata.')
    return identifier, spec_digest(project['spec']), name, kind


def _audit(source, project_id, digest):
    _check_scope(source, project_id, digest)
    validate_audit(source)
    return source['status']


def _gates(source, project_id, digest):
    _check_scope(source, project_id, digest)
    _fields(source, {'project_id', 'spec_sha256', 'status', 'summary', 'gates'}, 'acceptance')
    _text(source['summary'], MAX_EVIDENCE, 'Acceptance summary')
    gates = source.get('gates')
    if not isinstance(gates, list) or len(gates) != len(readiness._LABELS):
        raise ValueError('Expected all seven local acceptance gates.')
    by_id = {}
    for gate in gates:
        _fields(gate, CHECK_FIELDS, 'acceptance gate')
        key = gate['id']
        if (not isinstance(key, str) or key not in readiness._LABELS or key in by_id
                or gate['label'] != readiness._LABELS[key] or gate['status'] not in ('pass', 'pending', 'fail')):
            raise ValueError('Invalid acceptance gate.')
        _text(gate['evidence'], MAX_EVIDENCE, 'Gate evidence')
        by_id[key] = dict(gate)
    statuses = {gate['status'] for gate in gates}
    expected = 'blocked' if 'fail' in statuses else 'pending' if 'pending' in statuses else 'ready'
    if source.get('status') != expected:
        raise ValueError('Acceptance status disagrees with the individual gates.')
    return [by_id[key] for key in readiness._LABELS]


def _job_id(value):
    return isinstance(value, str) and JOB_ID.fullmatch(value) is not None


def _commands(job):
    commands = job.get('commands', [])
    if not isinstance(commands, list):
        raise ValueError('Invalid command history.')
    seen = set()
    for command in commands:
        if not isinstance(command, dict) or command.get('stage') not in ('build', 'verify'):
            raise ValueError('Invalid command stage.')
        stage = command['stage']
        duration, code, timeout = (command.get(key) for key in ('duration_seconds', 'exit_code', 'timed_out'))
        if (stage in seen or (duration is not None and performance._seconds(duration) is None)
                or (code is not None and type(code) is not int) or ('timed_out' in command and type(timeout) is not bool)
                or (job['verified'] and (timeout is True or ('exit_code' in command and code != 0)))):
            raise ValueError('Inconsistent command verification or timing.')
        seen.add(stage)


def _jobs(project, jobs, project_id, digest):
    if not isinstance(jobs, list):
        raise ValueError('Expected the build history.')
    current = {}
    for job in jobs:
        owner = job.get('project_id') if isinstance(job, dict) else None
        if not isinstance(owner, str) or len(owner) > 80 or not PROJECT_ID.fullmatch(owner):
            raise ValueError('A job cannot be attributed to a project.')
        if owner != project_id:
            continue
        # Pre-digest jobs belong to the project but cannot establish current-spec evidence.
        saved = job.get('spec_sha256')
        if saved is not None and not _valid_digest(saved):
            raise ValueError('Invalid job specification identity.')
        if saved != digest:
            continue
        identifier = job.get('id')
        if (not _job_id(identifier) or identifier in current or job.get('status') not in STATUSES
                or type(job.get('verified')) is not bool or (job['verified'] and job['status'] != 'passed')
                or job.get('kind', project['kind']) != project['kind']
                or ('manifest_sha256' in job and not _valid_digest(job['manifest_sha256']))):
            raise ValueError('Invalid current-spec job identity, kind, verification or seal.')
        for field in ('created_at', 'started_at', 'finished_at'):
            if job.get(field) is not None and performance._timestamp(job[field]) is None:
                raise ValueError('Invalid job timestamp.')
        if ('queue_sequence' in job and (type(job['queue_sequence']) is not int or job['queue_sequence'] < 0)):
            raise ValueError('Invalid job queue sequence.')
        _commands(job)
        current[identifier] = job
    profile = performance.profile_jobs(project, list(current.values()))
    # The performance tab caps its display. A dossier includes every matching job.
    summaries = list(profile['samples'])
    if len(summaries) < len(current):
        remainder = sorted(set(current) - {s['job_id'] for s in summaries})
        for index in range(0, len(remainder), performance.SAMPLE_LIMIT):
            batch = remainder[index:index + performance.SAMPLE_LIMIT]
            summaries.extend(performance.profile_jobs(project, [current[i] for i in batch])['samples'])
    for row in summaries:
        job = current[row['job_id']]
        row.update(verified=job['verified'], manifest_sha256=job.get('manifest_sha256'))
    return sorted(summaries, key=lambda row: row['job_id']), profile


def _board(source, project_id, digest):
    checked = _check_board(project_id, digest, source)
    tasks = [dict(id=t['id'], title=t['title'], role=t['role'], gate=t['gate'], status=t['status'],
                  attempt=t['attempts'], evidence=list(t['evidence']), reason=t['reason'], job_id=t['job_id'])
             for t in sorted(checked['tasks'], key=lambda t: t['id'])]
    return dict(state=checked['state'], revision=checked['revision'], board_spec_sha256=checked['board_spec_sha256'],
                summary=dict(checked['summary']), tasks=tasks)


def _release(source, project_id, digest):
    _check_scope(source, project_id, digest)
    _fields(source, {'project_id', 'spec_sha256', 'revision', 'active_release_id', 'active_state', 'releases'},
            'release registry')
    rows, revision = source.get('releases'), source.get('revision')
    if (not isinstance(rows, list) or type(revision) is not int or revision < len(rows)
            or (not rows and revision != 0)):
        raise ValueError('Invalid registry length or revision.')
    ids, jobs = set(), set()
    active = None
    for row in rows:
        _fields(row, RELEASE_FIELDS, 'release')
        if (not _job_id(row['id']) or not _job_id(row['job_id']) or row['id'] in ids or row['job_id'] in jobs
                or not _valid_digest(row['spec_sha256']) or not _valid_digest(row['manifest_sha256'])
                or performance._timestamp(row['created_at']) is None or row['output'] != _output(row['job_id'])):
            raise ValueError('Invalid release record.')
        ids.add(row['id'])
        jobs.add(row['job_id'])
        if row['id'] == source.get('active_release_id'):
            active = row
    state = source.get('active_state')
    if rows:
        if (active is None or state not in ('current', 'invalid', 'stale')
                or (state == 'stale') != (active['spec_sha256'] != digest)):
            raise ValueError('Active release identity and state disagree.')
    elif source.get('active_release_id') is not None or state != 'empty':
        raise ValueError('Invalid empty registry.')
    return dict(revision=revision, active_state=state, active_release_id=active['id'] if active else None,
                job_id=active['job_id'] if active else None, manifest_sha256=active['manifest_sha256'] if active else None,
                spec_sha256=active['spec_sha256'] if active else None)


def _handoffs(source, project_id, digest, board):
    _check_scope(source, project_id, digest)
    validate_handoffs(source)
    current = [item for item in source['items'] if item['spec_sha256'] == digest]
    report = dict(revision=source['revision'], current_count=len(current),
                  historical_count=len(source['items']) - len(current),
                  current_reviews={state: sum(item['review'] == state for item in current)
                                   for state in ('pending', 'accepted', 'rejected')},
                  coverage_advisory=True,
                  completed_attempts=None, covered_attempts=None, coverage=None)
    if board is None or board['state'] == 'stale':
        return report
    accepted = {}
    for item in current:
        if item['review'] == 'accepted' and item['outcome'] == 'completed':
            accepted.setdefault((item['task_id'], item['role'], item['attempt']), []).append(item)
    coverage = []
    for task in sorted(board['tasks'], key=lambda task: task['id']):
        if task['status'] != 'completed':
            continue
        candidates = accepted.get((task['id'], task['role'], task['attempts']), [])
        ids = sorted(item['id'] for item in candidates
                     if item['board_revision'] < board['revision'] and
                     item['order_id'] == order_id(project_id, digest, item['board_revision'], task))
        coverage.append(dict(task_id=task['id'], role=task['role'], attempt=task['attempts'], handoff_ids=ids))
    report.update(coverage=coverage, completed_attempts=len(coverage),
                  covered_attempts=sum(bool(row['handoff_ids']) for row in coverage))
    return report


def build_dossier(project, audit, acceptance, board, releases, jobs, handoffs):
    """Return independent, descriptive evidence. Only live acceptance can establish readiness."""
    errors = {}

    def read(name, function, *args):
        try:
            return function(*args)
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            errors[name] = f'Cannot verify the {name} source.'
            return None

    identity = read('project', _project, project)
    identifier, digest, name, kind = identity or (None, None, None, None)
    audit_status = read('audit', _audit, audit, identifier, digest)
    gates = read('acceptance', _gates, acceptance, identifier, digest)
    accepted_status = acceptance['status'] if gates is not None else None
    if gates is None:
        gates = [readiness._gate(key, 'fail', 'Cannot verify the live acceptance report.') for key in readiness._LABELS]
    build_data = read('jobs', _jobs, project, jobs, identifier, digest) if identity else None
    rows, profile = build_data or (None, None)
    board_summary = read('board', _board, board, identifier, digest)
    release = read('release', _release, releases, identifier, digest)
    reports = read('handoffs', _handoffs, handoffs, identifier, digest, board if board_summary else None)

    if audit_status is not None and identity:
        # Recompute observable checks from the exact supplied evidence. This catches
        # mixed reads even when both the earlier and later build happen to pass.
        live = supervisor.audit_project(project, jobs if build_data else None, board if board_summary else None,
                                        releases if release else None, None, profile)
        observed = {check['id']: check for check in audit['checks']}
        for check in live['checks']:
            key = check['id']
            if key != 'defects' and check != observed[key]:
                errors['audit'] = 'The audit disagrees with the underlying evidence.'
        if accepted_status is not None:
            for gate in gates:
                if gate['id'] != 'audit_history':
                    check = observed[gate['id']]
                    if gate != readiness._gate(check['id'], check['status'], check['evidence']):
                        errors['acceptance'] = 'The live acceptance gates disagree with the audit.'

    if rows is not None:
        passed = {row['job_id']: row for row in rows if row['status'] == 'passed' and row['verified']}
        if board_summary and board_summary['state'] == 'current':
            for task in board_summary['tasks']:
                if task['gate'] == 'build' and task['status'] == 'completed' and task['job_id'] not in passed:
                    errors['board'] = 'A completed build task lacks its verified current-spec job.'
        if release and release['active_state'] == 'current':
            built = passed.get(release['job_id'])
            if built is None or built['manifest_sha256'] not in (None, release['manifest_sha256']):
                errors['release'] = 'The active release cannot be linked to its verified current-spec job and seal.'

    status = 'blocked' if errors else accepted_status
    body = dict(schema_version=1, project_id=identifier, spec_sha256=digest, name=name, kind=kind, status=status,
                audit_status=audit_status, acceptance_status=accepted_status, gates=gates, jobs=rows,
                release=release, board=board_summary, handoffs=reports, source_errors=errors)
    return dict(project_id=identifier, spec_sha256=digest, status=status, report_sha256=spec_digest(body), report=body)
