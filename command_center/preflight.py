"""Read-only local release preflight from the live dossier and board forecast."""

from . import acceptance
from .dossier import _job_id, _project
from .pipeline import STATUSES
from .provenance import spec_digest
from .scheduler import MAX_EVIDENCE, MAX_TEXT, _ROLES, _task_id, _text
from .task_store import _valid_digest


def _sealed_report(dossier, identity):
    if identity is None or not isinstance(dossier, dict):
        return None
    project_id, digest, name, kind = identity
    body = dossier.get('report')
    if not isinstance(body, dict):
        return None
    if (type(body.get('schema_version')) is not int or body['schema_version'] != 1
            or body.get('name') != name or body.get('kind') != kind
            or any(source.get('project_id') != project_id or source.get('spec_sha256') != digest
                   for source in (dossier, body))
            or body.get('status') not in ('ready', 'pending', 'blocked')
            or body['status'] != dossier.get('status') or dossier.get('report_sha256') != spec_digest(body)):
        return None
    return body


def _verified_jobs(rows):
    if not isinstance(rows, list):
        raise ValueError
    seen, verified = set(), {}
    for job in rows:
        identifier, manifest = job['job_id'], job['manifest_sha256']
        if (not _job_id(identifier) or identifier in seen or job['status'] not in STATUSES
                or type(job['verified']) is not bool or (job['verified'] and job['status'] != 'passed')
                or (manifest is not None and not _valid_digest(manifest))):
            raise ValueError
        seen.add(identifier)
        if job['verified']:
            verified[identifier] = manifest
    return verified


def _current_evidence(body):
    if body is None or body.get('source_errors') != {}:
        return 'fail', 'A complete, verified dossier is required.'
    status = body['status']
    if status == 'blocked':
        return 'fail', 'The live release dossier reports a blocker.'
    gates = body['gates']
    if not isinstance(gates, list) or len(gates) != len(acceptance._LABELS):
        raise ValueError
    by_id = {gate['id']: gate for gate in gates}
    if by_id.keys() != acceptance._LABELS.keys():
        raise ValueError
    for key, gate in by_id.items():
        if (gate['label'] != acceptance._LABELS[key] or gate['status'] not in ('pass', 'pending')
                or not isinstance(gate['evidence'], str) or not gate['evidence'].strip()):
            raise ValueError
    live_pending = any(g['status'] == 'pending' for key, g in by_id.items() if key != 'audit_history')
    pending = live_pending or by_id['audit_history']['status'] == 'pending'
    if (body['audit_status'] != ('pending' if live_pending else 'pass')
            or body['acceptance_status'] != status or status != ('pending' if pending else 'ready')):
        raise ValueError
    # Artifact integrity is verified by the dossier producer. Cross-check its
    # recorded release-to-job link even while an unrelated gate is pending.
    release = body['release']
    verified = _verified_jobs(body['jobs'])
    if (type(release['revision']) is not int or release['revision'] < 0
            or body['handoffs']['coverage_advisory'] is not True):
        raise ValueError
    if by_id['release']['status'] == 'pass':
        if (release['active_state'] != 'current' or release['revision'] < 1 or release['spec_sha256'] != body['spec_sha256']
                or not _job_id(release['active_release_id']) or not _job_id(release['job_id'])
                or not _valid_digest(release['manifest_sha256'])):
            raise ValueError
        if release['job_id'] not in verified or verified[release['job_id']] not in (None, release['manifest_sha256']):
            raise ValueError
    elif (release['active_state'] != 'empty' or release['revision'] != 0 or any(release[k] is not None for k in
                                          ('active_release_id', 'job_id', 'manifest_sha256', 'spec_sha256'))):
        raise ValueError
    if pending:
        return 'pending', 'The live dossier lists outstanding acceptance evidence.'
    return 'pass', 'All current acceptance gates pass and the active release links to its verified build.'


def _board_work(body, forecast):
    """Match every forecast task to the sealed board, including blocked descendants."""
    if body is None or not isinstance(forecast, dict):
        raise ValueError
    board = body['board']
    state, revision = board['state'], board['revision']
    if (state not in ('empty', 'current') or forecast['status'] != state
            or forecast['project_id'] != body['project_id'] or forecast['spec_sha256'] != body['spec_sha256']
            or type(revision) is not int or revision < 0 or (revision == 0) != (state == 'empty')
            or type(forecast['board_revision']) is not int or forecast['board_revision'] != revision
            or board['board_spec_sha256'] != (None if state == 'empty' else body['spec_sha256'])):
        raise ValueError

    tasks = board['tasks']
    if not isinstance(tasks, list) or (state == 'empty' and tasks):
        raise ValueError
    statuses = {}
    verified = _verified_jobs(body['jobs'])
    for task in tasks:
        task_id, status = task['id'], task['status']
        _task_id(task_id)
        if task_id in statuses or status not in ('pending', 'running', 'blocked', 'completed'):
            raise ValueError
        _text(task['title'], 120, 'Task title')
        if (task['role'] not in _ROLES or task['gate'] not in ('build', 'manual')
                or type(task['attempt']) is not int or task['attempt'] < (0 if status == 'pending' else 1)):
            raise ValueError
        evidence = task['evidence']
        if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE or bool(evidence) != (status == 'completed'):
            raise ValueError
        for entry in evidence:
            _text(entry, MAX_TEXT, 'Task evidence')
        if status == 'completed' and task['gate'] == 'build':
            if task['job_id'] not in verified:
                raise ValueError
        elif task['job_id'] is not None:
            raise ValueError
        if status == 'blocked':
            _text(task['reason'], MAX_TEXT, 'Blocking reason')
        elif task['reason'] is not None:
            raise ValueError
        statuses[task_id] = status
    unfinished = {key for key, status in statuses.items() if status != 'completed'}
    blocked = {key for key, status in statuses.items() if status == 'blocked'}
    summary = board['summary']
    if (not isinstance(summary, dict) or any(type(n) is not int or n < 0 for n in summary.values())
            or summary['total'] != len(tasks) or summary['completed'] != len(tasks) - len(unfinished)
            or summary['blocked'] != len(blocked) or summary['running'] != sum(s == 'running' for s in statuses.values())
            or sum(summary[k] for k in ('ready', 'waiting', 'blocked', 'running')) != len(unfinished)):
        raise ValueError

    waves, unscheduled = forecast['waves'], forecast['unscheduled']
    if (not isinstance(waves, list) or not isinstance(unscheduled, list)
            or type(forecast['remaining_tasks']) is not int or forecast['remaining_tasks'] != len(unfinished)):
        raise ValueError
    forecast_ids = list(unscheduled)
    for index, wave in enumerate(waves, 1):
        if (type(wave['wave']) is not int or wave['wave'] != index
                or not isinstance(wave['task_ids'], list) or not wave['task_ids']):
            raise ValueError
        forecast_ids.extend(wave['task_ids'])
    minimum = forecast['minimum_dependency_waves']
    if (len(forecast_ids) != len(unfinished) or set(forecast_ids) != unfinished
            or not blocked.issubset(unscheduled) or bool(blocked) != bool(unscheduled)
            or (unscheduled and minimum is not None)
            or (not unscheduled and (type(minimum) is not int or not int(bool(waves)) <= minimum <= len(waves)))):
        raise ValueError
    if body['status'] == 'ready' and (not tasks or unfinished):
        raise ValueError
    return revision, len(tasks), len(unfinished), len(blocked), len(unscheduled)


def preflight(project, dossier, forecast):
    """Summarize current evidence for local operator review without changing any input."""
    invalid = (KeyError, ValueError, TypeError, OverflowError, RecursionError)
    try:
        identity = _project(project)
    except invalid:
        identity = None
    try:
        body = _sealed_report(dossier, identity)
    except invalid:
        body = None
    try:
        evidence = _current_evidence(body)
    except invalid:
        evidence = 'fail', 'The recorded release, build or acceptance evidence is incomplete or inconsistent.'
    try:
        revision, total, remaining, blocked, unscheduled = _board_work(body, forecast)
    except invalid:
        revision = None
        source = 'fail', 'The forecast and sealed board must identify the same current revision and tasks.'
        work = 'fail', 'Cannot establish which current tasks are complete.'
        schedule = 'fail', 'Cannot establish whether work is unscheduled.'
    else:
        source = 'pass', f'The forecast matches sealed board revision {revision}.'
        if blocked:
            work = 'fail', f'{blocked} of {remaining} unfinished tasks are blocked.'
        elif remaining:
            work = 'pending', f'Completion evidence is outstanding for {remaining} of {total} tasks.'
        elif not total:
            work = 'pending', 'The board has no tasks with completion evidence.'
        else:
            work = 'pass', f'Completion evidence covers the entire board ({total}/{total}).'
        schedule = (('fail', f'The forecast cannot schedule {unscheduled} unfinished task(s).') if unscheduled else
                    ('pass', 'The forecast has no unscheduled tasks.'))

    seal = (('pass', 'The dossier checksum and project identity match its report.') if body is not None else
            ('fail', 'Cannot verify the dossier checksum and current project identity.'))
    checks = [dict(id=key, label=label, status=result[0], detail=result[1]) for key, label, result in (
        ('dossier_seal', 'Dossier integrity', seal), ('current_evidence', 'Current release evidence', evidence),
        ('forecast_source', 'Forecast source', source), ('remaining_work', 'Task completion', work),
        ('unscheduled_work', 'Unscheduled work', schedule))]
    statuses = {check['status'] for check in checks}
    status = 'blocked' if 'fail' in statuses else 'pending' if 'pending' in statuses else 'ready'
    project_id, digest = identity[:2] if identity else (None, None)
    report = dict(schema_version=1, project_id=project_id, spec_sha256=digest, status=status, checks=checks,
                  dossier_sha256=dossier['report_sha256'] if body is not None else None, board_revision=revision,
                  advisory='Local operator review only. External publication requires separate authorization.')
    return dict(project_id=project_id, spec_sha256=digest, status=status, checks=checks,
                report_sha256=spec_digest(report), report=report)
