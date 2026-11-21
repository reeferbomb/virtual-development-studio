"""Forecast shared role capacity from a read-only portfolio recommendation."""

from collections import Counter

from . import scheduler
from .dispatch import default_profile
from .projects import PROJECT_ID
from .task_store import _valid_digest


_ROLES = {role['id']: role for role in default_profile()['roles']}
_BOARD_COUNTS = {'total', 'completed', 'running', 'ready', 'waiting', 'blocked'}
_ASSIGNMENT_FIELDS = {'role', 'task_id', 'title', 'project_id', 'spec_sha256', 'board_revision',
                      'priority', 'model_id', 'reasoning_effort'}


def _valid_counts(counts, fields):
    return (isinstance(counts, dict) and counts.keys() == fields
            and all(type(n) is int and n >= 0 for n in counts.values()))


def _projects(portfolio):
    rows = portfolio['projects']
    if not isinstance(rows, list):
        raise ValueError('Invalid portfolio project list')
    projects = {}
    totals = dict(projects=len(rows), current=0, empty=0, stale=0, unavailable=0, ready=0, running=0)
    for row in rows:
        project_id, state, revision = row['project_id'], row['state'], row['revision']
        if (not isinstance(project_id, str) or len(project_id) > 80 or not PROJECT_ID.fullmatch(project_id)
                or project_id in projects or state not in ('current', 'empty', 'stale')
                or type(revision) is not int or revision < 0 or (revision == 0) != (state == 'empty')
                or not _valid_digest(row['spec_sha256'])):
            raise ValueError('Unavailable project or invalid board identity')
        counts = row['summary']
        if (not _valid_counts(counts, _BOARD_COUNTS)
                or counts['total'] != sum(counts[key] for key in _BOARD_COUNTS - {'total'})
                or counts['running'] > len(_ROLES) or counts['total'] > scheduler.MAX_TASKS
                or (state == 'empty' and counts['total']) or (state == 'stale' and counts['ready'])):
            raise ValueError('Invalid project task counts')
        projects[project_id] = row
        totals[state] += 1
        totals['running'] += counts['running']
        totals['ready'] += counts['ready']
    if not _valid_counts(portfolio['summary'], totals.keys()) or portfolio['summary'] != totals:
        raise ValueError('Inconsistent portfolio summary')
    return projects


def _owners(portfolio, projects):
    reported = portfolio['role_occupancy']
    occupied = portfolio['occupied_roles']
    if (not isinstance(reported, dict) or not isinstance(occupied, list)
            or sorted(occupied) != sorted(reported) or not reported.keys() <= _ROLES.keys()):
        raise ValueError('Inconsistent occupied roles')
    owners = {}
    counts = Counter()
    for role, ids in reported.items():
        if (not isinstance(ids, list) or not ids or len(set(ids)) != len(ids)
                or not set(ids) <= projects.keys()):
            raise ValueError('Invalid role ownership')
        owners[role] = sorted(ids)
        counts.update(ids)
    if any(counts[pid] != row['summary']['running'] for pid, row in projects.items()):
        raise ValueError('Ownership differs from the recorded running tasks')
    conflicts = portfolio['conflicts']
    if not isinstance(conflicts, list):
        raise ValueError('Invalid conflicts')
    declared = {}
    for conflict in conflicts:
        role, ids = conflict['role'], conflict['project_ids']
        if role in declared or not isinstance(ids, list):
            raise ValueError('Invalid conflict ownership')
        declared[role] = sorted(ids)
    if declared != {role: ids for role, ids in owners.items() if len(ids) > 1}:
        raise ValueError('Conflicts differ from role ownership')
    return owners


def _assignments(portfolio, projects, owners):
    if not isinstance(portfolio['assignments'], list):
        raise ValueError('Invalid assignments')
    if portfolio['assignments'] and any(len(ids) > 1 for ids in owners.values()):
        raise ValueError('Resolve role conflicts before assigning new work')
    selected = {}
    task_ids = set()
    counts = Counter()
    for item in portfolio['assignments']:
        if not isinstance(item, dict) or item.keys() != _ASSIGNMENT_FIELDS:
            raise ValueError('Invalid assignment fields')
        project_id, role, task_id = item['project_id'], item['role'], item['task_id']
        project = projects[project_id]
        profile = _ROLES[role]
        scheduler._task_id(task_id)
        scheduler._text(item['title'], 120, 'title')
        counts[project_id] += 1
        if (project['state'] != 'current' or role in owners or role in selected
                or (project_id, task_id) in task_ids or counts[project_id] > project['summary']['ready']
                or type(item['board_revision']) is not int or item['board_revision'] != project['revision']
                or item['spec_sha256'] != project['spec_sha256']
                or type(item['priority']) is not int or not 1 <= item['priority'] <= 5
                or item['model_id'] != profile['model_id'] or item['reasoning_effort'] != profile['reasoning_effort']):
            raise ValueError('Invalid assignment identity or scope')
        selected[role] = item.copy()
        task_ids.add((project_id, task_id))
    if not selected and not owners and portfolio['summary']['ready']:
        raise ValueError('Ready tasks on an idle team require a recommendation')
    return selected


def allocation(portfolio):
    """Project the portfolio's chosen tasks onto the six shared roles without claiming them."""
    summary = dict(capacity=len(_ROLES), assigned=0, occupied=0, conflicts=0, idle=0)
    try:
        projects = _projects(portfolio)
        owners = _owners(portfolio, projects)
        selected = _assignments(portfolio, projects, owners)
    except (KeyError, TypeError, ValueError):
        return dict(status='unavailable', roles=[], summary=summary,
                    note='Refresh the portfolio and resolve unreadable boards or inconsistent scheduling evidence.')

    rows = []
    for role in _ROLES:
        ids = owners.get(role, [])
        assignment = selected.get(role)
        if ids:
            state = 'conflict' if len(ids) > 1 else 'occupied'
        elif assignment:
            state, ids = 'assigned', [assignment['project_id']]
        else:
            state = 'idle'
        summary['conflicts' if state == 'conflict' else state] += 1
        rows.append(dict(role=role, state=state, project_ids=ids, assignment=assignment))
    status = 'empty' if all(row['state'] == 'empty' for row in projects.values()) else 'current'
    note = 'Assigned roles show portfolio recommendations. Refresh the board and claim the exact task before dispatch.'
    if summary['conflicts']:
        note += ' Resolve competing claims on a role before issuing new work.'
    return dict(status=status, roles=rows, summary=summary, note=note)
