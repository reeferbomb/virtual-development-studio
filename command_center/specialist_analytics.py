"""Project current-specification handoff counts and review timing by specialist role."""

from collections import Counter
from datetime import datetime
from statistics import median

from .dispatch import default_profile
from .handoff_store import validate_history
from .projects import PROJECT_ID
from .provenance import spec_digest


def _role_summary(role, items):
    reviews = Counter(item['review'] for item in items)
    outcomes = Counter(item['outcome'] for item in items if item['review'] == 'accepted')
    review_seconds = [
        (datetime.fromisoformat(item['reviewed_at']) - datetime.fromisoformat(item['created_at'])).total_seconds()
        for item in items if item['review'] != 'pending'
    ]
    return dict(role=role, submitted=len(items), accepted=reviews['accepted'], rejected=reviews['rejected'],
                pending=reviews['pending'], unique_orders=len({item['order_id'] for item in items}),
                completed=outcomes['completed'], blocked=outcomes['blocked'], progress=outcomes['progress'],
                median_review_seconds=median(review_seconds) if review_seconds else None)


def specialist_analytics(project, history):
    """Summarize submissions for this project and spec after validating the entire ledger."""
    result = dict(project_id=None, spec_sha256=None, status='unavailable', handoff_revision=None,
                  historical_count=None, roles=[], note='A valid handoff history for this project and specification is required.')
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
        if item['spec_sha256'] == digest:
            by_role[item['role']].append(item)
        else:
            historical_count += 1

    result.update(handoff_revision=history['revision'], historical_count=historical_count,
                  roles=[_role_summary(role, items) for role, items in by_role.items()])
    if any(by_role.values()):
        result.update(status='current', note='Outcomes count lead-accepted reports. Review time measures '
                      'the interval from submission to an accepted or rejected decision.')
    else:
        result.update(status='empty', note='No handoffs have been submitted for the current specification.')
    return result
