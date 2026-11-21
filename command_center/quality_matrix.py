"""Prioritize quality checks from the current project's live acceptance projection."""

from .dossier import _gates
from .projects import PROJECT_ID
from .provenance import spec_digest


# assess_acceptance emits one fixed summary per status. Reject contradictory
# summaries before displaying any checks from the supplied projection.
_SUMMARIES = {
    'ready': 'All local readiness gates pass. The release is ready for operator review.',
    'pending': 'Local release readiness is pending. Collect the outstanding evidence.',
    'blocked': 'Local release readiness is blocked. Review the failed gates.',
}
_PRIORITY = {'fail': 0, 'pending': 1, 'pass': 2}

# The role and guidance come from the gate's meaning. Evidence is display text.
_GUIDANCE = {
    'build': ('build_operations', 'Inspect the current build and verification logs.',
              'Collect the verification result for a build of the saved specification.'),
    'release': ('build_operations', 'Inspect the active release and its package integrity evidence.',
                'Review the release registry and the verified build for the saved specification.'),
    'task_board': ('architecture', 'Review the task board scope and each blocked task with its owner.',
                   'Review outstanding work on the current task board.'),
    'manual_review': ('verification', 'Inspect the current manual tasks and their recorded observations.',
                      'Gather observations for the outstanding manual checks.'),
    'defects': ('verification', 'Review open defects and verify the evidence for each correction.',
                'Gather the defect ledger for the saved specification.'),
    'performance': ('build_operations', 'Compare recorded build and verification timings with the baseline.',
                    'Collect comparable timings from verified builds of the saved specification.'),
    'audit_history': ('verification', 'Review the latest current-spec capture alongside the live audit.',
                      'Review the live audit and capture its results for the saved specification.'),
}


def quality_matrix(project, acceptance):
    """Return an advisory matrix of live gates, ordered by status then canonical gate order."""
    result = dict(project_id=None, spec_sha256=None, status='unavailable',
                  summary={'pass': 0, 'pending': 0, 'fail': 0}, checks=[],
                  note='A valid acceptance report for this project and saved specification is required.')
    project_id = project.get('id') if isinstance(project, dict) else None
    if not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id):
        return result
    result['project_id'] = project_id
    if not isinstance(project.get('spec'), dict):
        return result
    try:
        digest = result['spec_sha256'] = spec_digest(project['spec'])
        gates = _gates(acceptance, project_id, digest)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return result
    status = acceptance['status']
    if acceptance['summary'] != _SUMMARIES[status]:
        return result

    result.update(status=status, note='These local checks are advisory. Release decisions require operator review.')
    for gate in sorted(gates, key=lambda row: _PRIORITY[row['status']]):
        role, failed_action, pending_action = _GUIDANCE[gate['id']]
        state = gate['status']
        actions = {'fail': failed_action, 'pending': pending_action, 'pass': 'Retain the evidence for operator review.'}
        result['summary'][state] += 1
        result['checks'].append(dict(gate, role=role, next_action=actions[state]))
    return result
