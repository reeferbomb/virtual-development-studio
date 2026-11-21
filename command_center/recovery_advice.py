"""Read-only guidance for the lead reviewing blocked task attempts."""

from .dependency_impact import _remaining_impact
from .handoff_store import validate_history
from .projects import PROJECT_ID
from .provenance import spec_digest
from .work_orders import _check_board, order_id


def _matching_handoffs(project_id, digest, revision, blocked, history):
    matches = {}
    # Resets can recreate an identical task under a restored spec. Only a work
    # order from the immediately preceding revision establishes continuity.
    for row in history['items']:
        task = blocked.get(row['task_id'])
        if (task is None or task['id'] in matches or row['review'] != 'accepted'
                or row['outcome'] not in ('blocked', 'progress') or row['spec_sha256'] != digest
                or row['role'] != task['role'] or row['attempt'] != task['attempts']
                or row['board_revision'] != revision - 1):
            continue
        if row['order_id'] == order_id(project_id, digest, row['board_revision'], task):
            matches[task['id']] = row['id']
    return matches


def recovery_advice(project, board, history):
    """Return manual recovery guidance from validated board and handoff projections."""
    result = dict(project_id=None, spec_sha256=None, board_revision=None, handoff_revision=None,
                  status='unavailable', items=[],
                  note='A valid task board and handoff history for this project are required.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        checked = _check_board(project_id, digest, board)
        validate_history(history)
        if history['project_id'] != project_id or history['spec_sha256'] != digest:
            return result
    except (ValueError, TypeError, OverflowError, RecursionError):
        return result

    state, revision = checked['state'], checked['revision']
    result.update(status=state, board_revision=revision, handoff_revision=history['revision'])
    if state == 'stale':
        result['note'] = 'The task board belongs to an earlier specification.'
        return result
    result['note'] = 'No blocked tasks to review.'
    blocked = {task['id']: task for task in checked['tasks'] if task['status'] == 'blocked'}
    if not blocked:
        return result

    matches = _matching_handoffs(project_id, digest, revision, blocked, history)
    for impact in _remaining_impact(checked['tasks'])['blocked']:
        task = blocked[impact['task_id']]
        handoff = matches.get(task['id'])
        review = ('Review the board reason and the accepted handoff for this attempt.' if handoff else
                  'Review the board reason with the assigned specialist and gather evidence for this attempt.')
        result['items'].append(dict(
            task_id=task['id'], title=task['title'], role=task['role'], attempt=task['attempts'],
            reason=task['reason'], affected_count=impact['affected_count'], handoff_id=handoff,
            next_action=review + ' Confirm the blocker is resolved before deciding whether to requeue.'
        ))
    result['note'] = 'The lead reviews each blocker and decides whether to retry it through the task board.'
    return result
