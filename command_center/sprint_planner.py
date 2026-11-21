"""Turn a supervisor audit and a task board snapshot into a reviewable sprint."""

from . import scheduler
from .dispatch import default_profile
from .provenance import spec_digest


_PRIORITY = {'critical': 5, 'high': 4, 'medium': 3, 'low': 2}
_ROLES = {role['id'] for role in default_profile()['roles']}
_CHECKS = {'build', 'release', 'task_board', 'manual_review', 'defects', 'performance'}


def _nonblank(value):
    if not isinstance(value, str) or not value.strip():
        return False
    # Use the same text encoding as the task store before offering an add.
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def _board_tasks(identity, board):
    if not isinstance(board, dict):
        raise ValueError('The task board is unavailable. Restore it and refresh the preview.')
    if any(board.get(key) != identity[key] for key in ('project_id', 'spec_sha256')):
        raise ValueError('The task board belongs to a different project or specification.')
    revision = identity['board_revision']
    if revision is None:
        raise ValueError('The task board revision is invalid.')
    if board.get('state') == 'stale':
        raise ValueError('Review and explicitly reset the stale task board before planning.')
    tasks = board.get('tasks')
    scheduler.validate_tasks(tasks)
    empty = (board.get('state') == 'empty' and revision == 0 and not tasks
             and 'board_spec_sha256' in board and board['board_spec_sha256'] is None)
    current = (board.get('state') == 'current' and revision > 0
               and board.get('board_spec_sha256') == identity['spec_sha256'])
    if not (empty or current):
        raise ValueError('The task board state, revision and specification are inconsistent.')
    return {task['id']: task for task in tasks}


def _recommendations(identity, audit):
    if not isinstance(audit, dict) or any(audit.get(key) != identity[key] for key in ('project_id', 'spec_sha256')):
        raise ValueError('A supervisor audit for this project and saved specification is required.')
    if not isinstance(audit.get('checks'), list) or not isinstance(audit.get('recommendations'), list):
        raise ValueError('The supervisor audit is incomplete.')
    checks = {}
    for check in audit['checks']:
        if (not isinstance(check, dict) or not _nonblank(check.get('id')) or check['id'] in checks
                or check.get('status') not in ('fail', 'warn', 'pending', 'pass')
                or not _nonblank(check.get('evidence'))):
            raise ValueError('The supervisor audit contains an invalid check.')
        checks[check['id']] = check
    statuses = {check['status'] for check in checks.values()}
    overall = next((status for check, status in (('fail', 'blocked'), ('warn', 'attention'), ('pending', 'pending'))
                    if check in statuses), 'pass')
    if checks.keys() != _CHECKS or audit.get('status') != overall:
        raise ValueError('The supervisor audit has missing checks or an inconsistent status.')

    recommendations = {}
    for rec in audit['recommendations']:
        if (not isinstance(rec, dict) or not _nonblank(rec.get('id')) or rec['id'] not in checks
                or not _nonblank(rec.get('severity')) or rec['severity'] not in _PRIORITY
                or not _nonblank(rec.get('role')) or rec['role'] not in _ROLES
                or not _nonblank(rec.get('title')) or len(rec['title']) > 120
                or not _nonblank(rec.get('detail')) or not isinstance(rec.get('evidence'), list)
                or not all(_nonblank(entry) for entry in rec['evidence'])):
            raise ValueError('The supervisor audit contains an invalid recommendation.')
        check = checks[rec['id']]
        if check['status'] == 'pass' or check['evidence'] not in rec['evidence']:
            raise ValueError('A recommendation does not match the recorded check evidence.')
        task_id = 'supervisor-' + rec['id'].replace('_', '-')
        if task_id in recommendations and recommendations[task_id] != rec:
            raise ValueError('The audit contains conflicting recommendations for one task.')
        recommendations[task_id] = rec
    # When the board source fails the supervisor emits one recovery action for
    # both board checks. It is unsafe to plan from that evidence.
    if checks['manual_review']['status'] == 'fail' or checks['task_board']['status'] == 'warn':
        raise ValueError('The supervisor could not audit a valid current task board. Refresh the preview.')
    if any(check['status'] != 'pass' and 'supervisor-' + key.replace('_', '-') not in recommendations
           for key, check in checks.items()):
        raise ValueError('A supervisor check is missing its recommended action.')
    return recommendations


def _drafts(recommendations, existing):
    tasks = {}
    for identifier, rec in recommendations.items():
        if identifier in existing:
            continue
        build = rec['id'] == 'build' and rec['role'] == 'build_operations'
        tasks[identifier] = dict(id=identifier, title=rec['title'], role=rec['role'],
                                 priority=_PRIORITY[rec['severity']], gate='build' if build else 'manual',
                                 depends_on=[])
    available = existing | tasks
    triage = recommendations.get('supervisor-defects')
    # A failed ledger read also produces a high-severity recommendation. Only
    # a recommendation to triage observed defects orders work on a correction.
    serious_defect = (triage and triage['title'] == 'Triage open defects'
                      and triage['severity'] in ('critical', 'high'))
    build = available.get('supervisor-build')
    build_gate = build and build['gate'] == 'build'
    if 'supervisor-build' in tasks and build_gate and serious_defect:
        tasks['supervisor-build']['depends_on'].append('supervisor-defects')
    release = tasks.get('supervisor-release')
    if release and release['title'] in ('Review a release candidate', 'Review the stale release'):
        if build_gate:
            release['depends_on'].append('supervisor-build')
        # An existing build task cannot be amended. Preserve the triage
        # prerequisite when the build does not already enforce it.
        if serious_defect and (not build_gate or 'supervisor-defects' not in build['depends_on']):
            release['depends_on'].append('supervisor-defects')
    return tasks


def plan_sprint(project, audit, board):
    """Return an advisory plan of new tasks in dependency-safe insertion order."""
    revision = board.get('revision') if isinstance(board, dict) else None
    identity = dict(project_id=project['id'], spec_sha256=spec_digest(project['spec']),
                    board_revision=revision if type(revision) is int and revision >= 0 else None)
    tasks, rationale = [], []
    try:
        if not isinstance(project.get('spec'), dict):
            raise ValueError('The saved specification is not a JSON object. Restore it before planning.')
        existing = _board_tasks(identity, board)
        recommendations = _recommendations(identity, audit)
        pending = _drafts(recommendations, existing)
        known = set(existing)
        while pending and len(known) < scheduler.MAX_TASKS:
            ready = (task for task in pending.values() if known.issuperset(task['depends_on']))
            task = min(ready, key=lambda item: (-item['priority'], item['id']))
            identifier = task['id']
            tasks.append(task)
            rec = recommendations[identifier]
            rationale.append(dict(task_id=identifier, detail=rec['detail'], evidence=list(rec['evidence'])))
            known.add(identifier)
            del pending[identifier]
        status = 'ready' if tasks else 'empty'
        reason = ('Review the proposed tasks and their source evidence.' if tasks else
                  'The supervisor has no new tasks to propose.')
        if pending:
            status = 'ready' if tasks else 'blocked'
            capacity_note = f'The board limit of {scheduler.MAX_TASKS} leaves {len(pending)} recommendation(s) for later.'
            reason = f'{reason} {capacity_note}' if tasks else capacity_note
        covered = recommendations.keys() & existing.keys()
        if covered:
            completed = sum(existing[key]['status'] == 'completed' for key in covered)
            reason += f' {len(covered)} recommendation(s) already have board tasks, including {completed} completed.'
            if completed and audit['status'] == 'blocked':
                reason += ' If a failed check persists, manually plan a follow-up against its current evidence.'
    except ValueError as error:
        status, reason = 'blocked', str(error)
        tasks, rationale = [], []
    content = dict(**identity, tasks=tasks, rationale=rationale)
    return dict(**content, plan_id=spec_digest(content), status=status, reason=reason)
