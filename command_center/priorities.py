"""Read-only priority recommendations for a project task board."""

from graphlib import TopologicalSorter

from .projects import PROJECT_ID
from .provenance import spec_digest
from .work_orders import _check_board


def _rank_ready(board):
    tasks = board['tasks']
    busy_roles = {task['role'] for task in tasks if task['status'] == 'running'}
    children = {task['id']: [] for task in tasks if task['status'] != 'completed'}
    for task in tasks:
        for parent in task['depends_on']:
            if parent in children:
                children[parent].append(task['id'])

    # Visiting leaves first lets converging paths share completed calculations.
    descendants = {}
    chain_length = {}
    for task_id in TopologicalSorter(children).static_order():
        direct = children[task_id]
        downstream = set(direct)
        for child in direct:
            downstream.update(descendants[child])
        descendants[task_id] = downstream
        chain_length[task_id] = 1 + max((chain_length[child] for child in direct), default=0)

    ready = set(board['ready_task_ids'])
    candidates = [dict(task_id=task['id'], title=task['title'], role=task['role'], priority=task['priority'],
                       downstream_count=len(descendants[task['id']]), chain_length=chain_length[task['id']])
                  for task in tasks if task['id'] in ready and task['role'] not in busy_roles]
    candidates.sort(key=lambda row: (-row['priority'], -row['downstream_count'], -row['chain_length'], row['task_id']))
    recommendations = []
    for row in candidates:
        if row['role'] not in busy_roles:
            recommendations.append(row.copy())
            busy_roles.add(row['role'])
    return candidates, recommendations


def rank_tasks(project, board):
    """Rank eligible work in a single validated project snapshot."""
    result = dict(project_id=None, spec_sha256=None, board_revision=None, status='unavailable',
                  candidates=[], recommendations=[], note='A valid project and task board are required.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        checked = _check_board(project_id, digest, board)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return result

    state = checked['state']
    result.update(board_revision=checked['revision'], status=state)
    if state == 'empty':
        result['note'] = 'This project has no recorded task board.'
    elif state == 'stale':
        result['note'] = 'The task board belongs to an earlier specification.'
    else:
        result['candidates'], result['recommendations'] = _rank_ready(checked)
        if result['candidates']:
            result['note'] = ('Ready tasks for idle roles are ranked by priority, distinct unfinished descendants, '
                              'longest remaining chain including the task, then task ID. The lead claims work separately.')
        else:
            result['note'] = 'No ready tasks are available for idle roles.'
    return result
