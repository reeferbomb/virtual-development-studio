"""Preview the first production milestone for an existing Studio project."""

from .dispatch import default_profile
from .dossier import _project
from .provenance import spec_digest
from .team import _TASKS
from .work_orders import _check_board


_TITLES = {
    'assets': 'First verified asset pack',
    'world': 'First traversable level',
    'gameplay': 'First playable encounter',
    'multiplayer': 'First synchronized multiplayer session',
    'cinematic': 'First rendered sequence',
    'simulation': 'First drivable objective route',
    'openworld': 'First streamed expedition and checkpoint',
    'unified': 'First expedition with transport, quests and trade',
    'living': 'First frontier contract and encounter',
    'city': 'First populated city district',
    'vertical': 'First interior and metro journey',
    'advanced': 'First shared tower and vehicle session',
    'frontline': 'First cooperative city mission',
}

# Architecture unblocks three parallel work orders. Independent verification
# reviews the package produced by the actual build-gated task.
_STEPS = (
    ('architecture', 5, ()),
    ('gameplay', 4, ('architecture',)),
    ('ui', 4, ('architecture',)),
    ('content', 4, ('architecture',)),
    ('build_operations', 4, ('gameplay', 'ui', 'content')),
    ('verification', 4, ('build_operations',)),
)


def _definitions(kind):
    roles = (role['id'] for role in default_profile()['roles'])
    briefs = dict(zip(roles, _TASKS[kind], strict=True))
    ids = {role: f"milestone-{kind}-{role.replace('_', '-')}" for role in briefs}
    return [dict(id=ids[role], title=briefs[role], role=role, priority=priority,
                 depends_on=[ids[dependency] for dependency in prerequisites],
                 gate='build' if role == 'build_operations' else 'manual')
            for role, priority, prerequisites in _STEPS]


def blueprint(project, board):
    """Return a reviewable plan for an empty board, or explain its existing state."""
    result = dict(project_id=None, spec_sha256=None, board_revision=None, status='blocked',
                  reason='', plan_id=None, tasks=[], template_id='', title='First production milestone')
    try:
        project_id, digest, _, kind = _project(project)
        result.update(project_id=project_id, spec_sha256=digest)
        if kind not in _TITLES or kind not in _TASKS:
            raise ValueError('No first production milestone is available for this project kind.')
        result.update(template_id=f'{kind}-first-milestone-v1', title=_TITLES[kind])
        checked = _check_board(project_id, digest, board)
        result['board_revision'] = checked['revision']
        if checked['state'] == 'stale':
            raise ValueError('Review the board and explicitly reset it for the saved specification.')
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        result['reason'] = str(exc)
        return result

    tasks = _definitions(kind)
    existing = {task['id']: task for task in checked['tasks']}
    if existing:
        for draft in tasks:
            record = existing.get(draft['id'])
            if record is None or any(record[key] != value for key, value in draft.items()):
                result['reason'] = ('This board already contains work and does not match the full milestone. '
                                    'Review its existing tasks before planning more work.')
                return result
        return dict(result, status='applied', tasks=tasks, reason='All milestone tasks are already on the board.')

    content = dict(project_id=project_id, spec_sha256=digest, board_revision=checked['revision'],
                   template_id=result['template_id'], title=result['title'], tasks=tasks)
    return dict(result, status='ready', tasks=tasks, plan_id=spec_digest(content),
                reason='Review these six tasks before adding the milestone to the empty board.')
