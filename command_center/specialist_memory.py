"""Read-only specialist memory derived from lead-reviewed project handoffs."""

from .dispatch import default_profile
from .handoff_store import validate_history
from .projects import PROJECT_ID
from .provenance import spec_digest


RECENT_PER_ROLE = 5


def _memory(item):
    return dict(handoff_id=item['id'], task_id=item['task_id'], attempt=item['attempt'],
                outcome=item['outcome'], summary=item['summary'], evidence=list(item['evidence']),
                next_action=item['next_action'], reviewed_at=item['reviewed_at'])


def specialist_memory(project, history):
    """Group accepted, current-spec reports by role. Report text is returned as data."""
    result = dict(project_id=None, spec_sha256=None, status='unavailable', handoff_revision=None,
                  roles=[], historical_count=None, note='A valid handoff history for this project and specification is required.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        validate_history(history)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return result
    if history['project_id'] != project_id or history['spec_sha256'] != digest:
        return result

    by_role = {role['id']: [] for role in default_profile()['roles']}
    historical_count = 0
    for item in history['items']:
        if item['spec_sha256'] != digest:
            historical_count += 1
        elif item['review'] == 'accepted':
            by_role[item['role']].append(item)

    roles = []
    for role, items in by_role.items():
        # Validated timestamps are canonical UTC. Tied reviews retain ledger order.
        recent = sorted(items, key=lambda item: item['reviewed_at'], reverse=True)[:RECENT_PER_ROLE]
        roles.append(dict(role=role, accepted_count=len(items), memories=[_memory(item) for item in recent]))

    result.update(roles=roles, historical_count=historical_count, handoff_revision=history['revision'])
    if any(by_role.values()):
        result.update(status='current', note='Lead-accepted handoffs for the current specification, newest review first. '
                      'Use the reported evidence and next actions as reference material.')
    else:
        result.update(status='empty', note='No handoffs have been accepted for the current specification.')
    return result
