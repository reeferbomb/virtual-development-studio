"""Forecast execution waves for one project using its validated task board."""

from .projects import PROJECT_ID
from .provenance import spec_digest
from .scheduler import schedule
from .work_orders import _check_board


def _simulate(board):
    remaining = {task['id']: task for task in board['tasks'] if task['status'] != 'completed'}
    task_count = len(remaining)
    depth = {}
    waves = []
    plan = board
    running = sorted(identifier for identifier, task in remaining.items() if task['status'] == 'running')
    while remaining:
        selected = running + [assignment['task_id'] for assignment in plan['assignments']]
        if not selected:
            break
        waves.append(dict(wave=len(waves) + 1, task_ids=selected))
        for identifier in selected:
            dependencies = remaining.pop(identifier)['depends_on']
            depth[identifier] = 1 + max((depth.get(parent, 0) for parent in dependencies), default=0)

        # Project the residual graph into the existing scheduler. Removing tasks
        # and their satisfied edges leaves every real task and evidence field intact.
        plan = schedule([dict(task, depends_on=[p for p in task['depends_on'] if p in remaining])
                         for task in remaining.values()])
        running = []

    return dict(remaining_tasks=task_count, waves=waves, unscheduled=sorted(remaining),
                minimum_dependency_waves=None if remaining else max(depth.values(), default=0))


def forecast(project, board):
    """Return a read-only, project-local scenario in waves, with no duration estimates."""
    result = dict(project_id=None, spec_sha256=None, board_revision=None, status='unavailable',
                  waves=[], unscheduled=[], remaining_tasks=0, minimum_dependency_waves=None,
                  note='A forecast requires a valid board for this project and specification.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        checked = _check_board(project_id, digest, board)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return result

    state = checked['state']
    result.update(board_revision=checked['revision'], status=state)
    if state == 'stale':
        result['note'] = 'The board belongs to an earlier specification. Its tasks have no current forecast.'
    elif state == 'empty':
        result.update(minimum_dependency_waves=0, note='This project has no recorded task board.')
    else:
        result.update(_simulate(checked))
        result['note'] = ('Each wave assumes its tasks finish and satisfy their gates before the next wave. '
                          'Running tasks occupy their roles in wave 1. The dependency minimum ignores role '
                          'contention. Waves describe ordering only and do not claim or complete work.')
        if result['unscheduled']:
            result['note'] += ' Blocked tasks and their dependents prevent a whole-board dependency minimum.'
    return result
