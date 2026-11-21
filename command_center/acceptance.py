"""Assess local release readiness from current evidence and explicitly captured audits."""

from . import supervisor
from .defect_store import DEFECT_ID, SEVERITIES
from .evidence_history import validate_audit, validate_history
from .projects import PROJECT_ID
from .provenance import spec_digest
from .task_store import _valid_digest


_LABELS = {**supervisor._LABELS, 'audit_history': 'Captured audit'}
_PRIORITY = {'pass': 0, 'pending': 1, 'warn': 2, 'fail': 3}


def _gate(identifier, status, evidence):
    return {'id': identifier, 'label': _LABELS[identifier],
            'status': 'fail' if status == 'warn' else status, 'evidence': evidence}


def _same_scope(source, project_id, digest):
    return (isinstance(source, dict) and source.get('project_id') == project_id
            and source.get('spec_sha256') == digest)


def _check_board(audit, board):
    revision = board.get('revision')
    if (type(revision) is not int or revision < 0
            or (revision == 0) != (board.get('state') == 'empty')):
        raise ValueError('The task board revision is invalid.')
    supervisor._board(audit, board)


def _check_ledger(audit, ledger):
    # Validate the scope of every row before excluding historical defects.
    items = ledger.get('items')
    if not isinstance(items, list):
        raise ValueError('The defect ledger has no readable records.')
    ids = set()
    counts = dict(current_open=0, current_resolved=0, historical_open=0, historical_resolved=0)
    for item in items:
        if (not isinstance(item, dict) or not _valid_digest(item.get('spec_sha256'))
                or not isinstance(item.get('id'), str) or not DEFECT_ID.fullmatch(item['id'])
                or item['id'] in ids or item.get('status') not in ('open', 'resolved')
                or item.get('severity') not in SEVERITIES):
            raise ValueError('The defect ledger contains an invalid or duplicate record.')
        ids.add(item['id'])
        scope = 'current' if item['spec_sha256'] == audit.digest else 'historical'
        counts[f"{scope}_{item['status']}"] += 1
    if 'summary' in ledger and ledger['summary'] != counts:
        raise ValueError('The defect counts disagree with the underlying records.')
    supervisor._defects(audit, ledger)


def _live_gates(project, project_id, digest, audit, board, defects):
    try:
        validate_audit(audit)
        if not _same_scope(audit, project_id, digest):
            raise ValueError('The live audit belongs to another project or specification.')
    except ValueError as error:
        return [_gate(key, 'fail', f'Cannot verify the live audit. {error}') for key in supervisor._LABELS]

    checks = {check['id']: check for check in audit['checks']}
    # Recheck the underlying work records. A separate, later read may reveal a
    # newly opened defect, a stale board, or manual evidence still outstanding.
    work = supervisor._Audit(project)
    work.inspect(board, ('task_board', 'manual_review'), _check_board)
    work.inspect(defects, ('defects',), _check_ledger)
    for check in work.checks:
        key = check['id']
        if _PRIORITY[check['status']] >= _PRIORITY[checks[key]['status']]:
            checks[key] = check
    return [_gate(key, checks[key]['status'], checks[key]['evidence']) for key in supervisor._LABELS]


def _captured_gate(history, project_id, digest):
    try:
        validate_history(history)
        if not _same_scope(history, project_id, digest):
            raise ValueError('The history belongs to another project or specification.')
    except ValueError as error:
        return _gate('audit_history', 'fail', f'Cannot verify the audit history. {error}')
    # The store returns append order, newest first. Wall-clock ordering can tie.
    latest = next((item for item in history['items'] if item['spec_sha256'] == digest), None)
    if latest is None:
        return _gate('audit_history', 'pending', 'Capture a passing audit for the current specification.')
    status = {'blocked': 'fail', 'attention': 'fail', 'pending': 'pending', 'pass': 'pass'}[latest['status']]
    evidence = f"Latest current-spec capture {latest['id']} at {latest['created_at']} recorded {latest['status']}."
    return _gate('audit_history', status, evidence)


def assess_acceptance(project, audit, board, defects, history):
    """Return a read-only advisory. Passing local gates does not constitute shipment."""
    project_id = project.get('id') if isinstance(project, dict) else None
    digest = None
    try:
        if (not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id)
                or not isinstance(project.get('spec'), dict)):
            raise ValueError('Invalid project identity or specification.')
        digest = spec_digest(project['spec'])
    except (TypeError, ValueError, RecursionError):
        gates = [_gate(key, 'fail', 'Cannot identify the project and its saved specification.') for key in _LABELS]
    else:
        gates = _live_gates(project, project_id, digest, audit, board, defects)
        gates.append(_captured_gate(history, project_id, digest))

    statuses = {gate['status'] for gate in gates}
    if 'fail' in statuses:
        status, summary = 'blocked', 'Local release readiness is blocked. Review the failed gates.'
    elif 'pending' in statuses:
        status, summary = 'pending', 'Local release readiness is pending. Collect the outstanding evidence.'
    else:
        status, summary = 'ready', 'All local readiness gates pass. The release is ready for operator review.'
    return dict(project_id=project_id if isinstance(project_id, str) else None, spec_sha256=digest,
                status=status, gates=gates, summary=summary)
