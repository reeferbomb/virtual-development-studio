"""Export ranked start actions from one coherent workspace snapshot."""

from .allocation import allocation
from .portfolio import _dispatch_plan
from .provenance import spec_digest


def dispatch_cycle(portfolio):
    """Preview exact claims for the lead to review, without touching a task board."""
    capacity = allocation(portfolio)
    result = dict(status='unavailable', cycle_id=None, steps=[], conflicts=[], note=capacity['note'])
    if capacity['status'] == 'unavailable':
        return result

    # Fingerprint every board, even if it has no recommended work. A competing
    # claim or spec change elsewhere can invalidate the next dispatch decision.
    projects = {row['project_id']: {key: row[key] for key in ('state', 'revision', 'spec_sha256', 'summary')}
                for row in portfolio['projects']}
    owners = {row['role']: row['project_ids'] for row in capacity['roles']
              if row['state'] in ('occupied', 'conflict')}
    assignments = portfolio['assignments']  # Already validated, in portfolio rank order.
    try:
        # A serialized portfolio repeats task identity in the exported assignments
        # and work orders. Require all of those observations to agree.
        if spec_digest(portfolio.get('dispatch_plan')) != spec_digest(_dispatch_plan(assignments)):
            result['note'] = 'Refresh the portfolio. Its dispatch export disagrees with its ranked assignments.'
            return result
        result['cycle_id'] = spec_digest(dict(projects=projects, role_occupancy=owners, assignments=assignments))
    except (TypeError, ValueError, OverflowError, RecursionError):
        result['note'] = 'Refresh the portfolio to obtain a valid dispatch snapshot.'
        return result

    conflicts = [dict(role=role, project_ids=ids) for role, ids in owners.items() if len(ids) > 1]
    if conflicts:
        return dict(result, status='blocked', conflicts=conflicts,
                    note='Resolve the competing claims and refresh the portfolio before dispatch.')
    if not assignments:
        return dict(result, status='idle', note='No ready task is recommended for an available role.')

    steps = [dict(project_id=item['project_id'], task_id=item['task_id'], role=item['role'], title=item['title'],
                  priority=item['priority'], expected_revision=item['board_revision'], spec_sha256=item['spec_sha256'],
                  action=dict(op='start', task_id=item['task_id'])) for item in assignments]
    return dict(result, status='ready', steps=steps,
                note='Preview only. Recheck the cycle and board before claiming the next task. '
                     'Refresh after each claim to review the new board revision and role availability.')
