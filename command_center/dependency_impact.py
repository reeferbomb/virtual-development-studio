"""Read-only dependency impact and remaining chain for a project task board."""

from graphlib import TopologicalSorter

from .projects import PROJECT_ID
from .provenance import spec_digest
from .work_orders import _check_board


def _longest(chains):
    return min(chains, key=lambda chain: (-len(chain), chain), default=[])


def _remaining_impact(tasks):
    remaining = {task['id']: task for task in tasks if task['status'] != 'completed'}
    children = {task_id: [] for task_id in remaining}
    for task_id, task in remaining.items():
        for dependency in task['depends_on']:
            if dependency in remaining:
                children[dependency].append(task_id)

    # Process leaves first so shared tails are computed once, even in a dense DAG.
    descendants = {}
    chains = {}
    for task_id in TopologicalSorter(children).static_order():
        direct = children[task_id]
        downstream = set(direct)
        for child in direct:
            downstream.update(descendants[child])
        descendants[task_id] = downstream
        chains[task_id] = [task_id, *_longest(chains[child] for child in direct)]

    blocked = []
    affected = set()
    for task_id in sorted(remaining):
        task = remaining[task_id]
        if task['status'] == 'blocked':
            downstream = descendants[task_id]
            blocked.append(dict(task_id=task_id, role=task['role'], reason=task['reason'],
                                affected_task_ids=sorted(downstream), affected_count=len(downstream)))
            affected.update(downstream)
    return dict(blocked=blocked, affected_task_ids=sorted(affected), critical_chain=_longest(chains.values()))


def dependency_impact(project, board):
    """Describe blockers and the longest chain of unfinished tasks in a validated snapshot."""
    result = dict(project_id=None, spec_sha256=None, board_revision=None, status='unavailable',
                  blocked=[], affected_task_ids=[], critical_chain=[],
                  note='A valid task board for this project and specification is required.')
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
    result.update(board_revision=checked['revision'], status=state, note='No remaining tasks.')
    if state == 'stale':
        result['note'] = 'The task board belongs to an earlier specification.'
    elif state == 'current':
        result.update(_remaining_impact(checked['tasks']))
        if result['critical_chain']:
            result['note'] = ('The critical chain counts unfinished tasks in dependency order. '
                              'Durations and specialist availability are outside this calculation.')
    return result
