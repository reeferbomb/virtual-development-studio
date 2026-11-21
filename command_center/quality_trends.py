"""Compare supervisor gate observations against the latest current-spec capture."""

from .evidence_history import validate_audit, validate_history
from .projects import PROJECT_ID
from .provenance import spec_digest
from .supervisor import _LABELS


_RANK = {'fail': 0, 'warn': 1, 'pending': 2, 'pass': 3}


def _trend(baseline, live):
    if _RANK[live] > _RANK[baseline]:
        return 'improved'
    if _RANK[live] < _RANK[baseline]:
        return 'regressed'
    return 'unchanged'


def quality_trends(project, audit, history):
    """Return observed changes in gate status for one project and saved specification."""
    result = dict(project_id=None, spec_sha256=None, status='unavailable', history_revision=None,
                  baseline_id=None, baseline_status=None, live_status=None,
                  summary=dict(improved=0, regressed=0, unchanged=0), checks=[], historical_count=None,
                  note='A valid live audit and evidence history for the current project specification are required.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        validate_audit(audit)
        validate_history(history)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return result
    for source in (audit, history):
        if source['project_id'] != project_id or source['spec_sha256'] != digest:
            return result

    # Validated history uses newest-first insertion order, including tied timestamps.
    current = [item for item in history['items'] if item['spec_sha256'] == digest]
    result.update(history_revision=history['revision'], live_status=audit['status'],
                  historical_count=len(history['items']) - len(current))
    if not current:
        result.update(status='empty', note='No audit has been captured for the current specification.')
        return result

    baseline = current[0]
    saved = {row['id']: row['status'] for row in baseline['checks']}
    live = {row['id']: row['status'] for row in audit['checks']}
    for key, label in _LABELS.items():
        trend = _trend(saved[key], live[key])
        result['checks'].append(dict(id=key, label=label, baseline_status=saved[key], live_status=live[key], trend=trend))
        result['summary'][trend] += 1
    result.update(status='current', baseline_id=baseline['id'], baseline_status=baseline['status'],
                  note='Compared the latest current-spec capture with the live audit. '
                       'Changes reflect observed gate statuses, ordered from fail through warn and pending to pass.')
    return result
