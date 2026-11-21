"""Pure task validation, state transitions and dispatch recommendations."""

from copy import deepcopy
from graphlib import CycleError, TopologicalSorter
import re

from .dispatch import default_profile
from .projects import PROJECT_ID


MAX_TASKS = 100
MAX_EVIDENCE = 8
MAX_TEXT = 512
_DEFINITION = {'id', 'title', 'role', 'priority', 'depends_on', 'gate'}
_RECORD = _DEFINITION | {'status', 'evidence', 'reason', 'job_id', 'attempts'}
_ROLES = {role['id']: role for role in default_profile()['roles']}
_JOB_ID = re.compile(r'[0-9a-f]{32}')
_ACTION_FIELDS = {
    'add': {'op', 'task'},
    'start': {'op', 'task_id'},
    'complete': {'op', 'task_id', 'evidence'},
    'block': {'op', 'task_id', 'reason'},
    'requeue': {'op', 'task_id'},
    'reassign': {'op', 'task_id', 'role'},
}
_ALLOWED_STATES = {
    'start': ('pending',), 'complete': ('running',), 'block': ('running',),
    'requeue': ('running', 'blocked'), 'reassign': ('pending', 'blocked'),
}


def _exact_fields(data, fields, label):
    if not isinstance(data, dict) or data.keys() != fields:
        raise ValueError(f'Invalid {label} fields')


def _task_id(value):
    if not isinstance(value, str) or len(value) > 64 or not PROJECT_ID.fullmatch(value):
        raise ValueError('Task IDs must be lowercase slugs of at most 64 characters')


def _text(value, limit, label):
    if not isinstance(value, str) or len(value) > limit or not value.strip():
        raise ValueError(f'{label} must contain nonblank text of at most {limit} characters')
    value.encode('utf-8')


def _validate_record(task):
    _exact_fields(task, _RECORD, 'task record')
    _task_id(task['id'])
    _text(task['title'], 120, 'title')
    if not isinstance(task['role'], str) or task['role'] not in _ROLES:
        raise ValueError('Unknown task role')
    if type(task['priority']) is not int or not 1 <= task['priority'] <= 5:
        raise ValueError('priority must be an integer from 1 to 5')
    if task['gate'] not in ('manual', 'build'):
        raise ValueError('Unknown completion gate')
    dependencies = task['depends_on']
    if not isinstance(dependencies, list) or len(dependencies) >= MAX_TASKS:
        raise ValueError('depends_on must be a list of at most 99 task IDs')
    for identifier in dependencies:
        _task_id(identifier)
    if len(set(dependencies)) != len(dependencies):
        raise ValueError('Duplicate task dependency')

    status = task['status']
    if status not in ('pending', 'running', 'blocked', 'completed'):
        raise ValueError('Unknown task status')
    if type(task['attempts']) is not int or task['attempts'] < (0 if status == 'pending' else 1):
        raise ValueError('attempts must count all task starts')
    if status == 'blocked':
        _text(task['reason'], MAX_TEXT, 'Blocking reason')
    elif task['reason'] is not None:
        raise ValueError('Only blocked tasks carry a reason')

    evidence = task['evidence']
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
        raise ValueError(f'evidence must be a list with at most {MAX_EVIDENCE} entries')
    if bool(evidence) != (status == 'completed'):
        raise ValueError('Completed tasks require evidence, and only completed tasks carry it')
    for entry in evidence:
        _text(entry, MAX_TEXT, 'Evidence')
    if status == 'completed' and task['gate'] == 'build':
        if not isinstance(task['job_id'], str) or not _JOB_ID.fullmatch(task['job_id']):
            raise ValueError('Build completion requires a valid lowercase 32-hex job_id')
    elif task['job_id'] is not None:
        raise ValueError('Only completed build-gated tasks carry a job_id')


def validate_tasks(tasks):
    """Reject malformed records, inconsistent lifecycle states and invalid dependency graphs."""
    if not isinstance(tasks, list) or len(tasks) > MAX_TASKS:
        raise ValueError(f'Tasks must be a list of at most {MAX_TASKS} records')
    graph = {}
    busy_roles = set()
    completed = set()
    for task in tasks:
        _validate_record(task)
        identifier = task['id']
        if identifier in graph:
            raise ValueError('Duplicate task ID')
        graph[identifier] = task['depends_on']
        if task['status'] == 'completed':
            completed.add(identifier)
        if task['status'] == 'running':
            if task['role'] in busy_roles:
                raise ValueError('Role already has a running task')
            busy_roles.add(task['role'])
    for task in tasks:
        dependencies = task['depends_on']
        if any(dependency not in graph for dependency in dependencies):
            raise ValueError('Unknown task dependency')
        if task['attempts'] and not completed.issuperset(dependencies):
            raise ValueError('A started task requires completed dependencies')
    try:
        TopologicalSorter(graph).prepare()
    except CycleError as exc:
        raise ValueError('Task dependencies contain a cycle') from exc


def apply_action(tasks, action, *, build_verified=False):
    """Apply one action to a fresh task list. The caller supplies trusted build verification."""
    validate_tasks(tasks)
    if not isinstance(action, dict) or not isinstance(action.get('op'), str):
        raise ValueError('Action must specify an operation')
    op = action['op']
    if op not in _ACTION_FIELDS:
        raise ValueError('Unknown task operation')
    fields = _ACTION_FIELDS[op]
    if op == 'complete' and 'job_id' in action:
        fields = fields | {'job_id'}
    _exact_fields(action, fields, 'action')

    if op == 'add':
        _exact_fields(action['task'], _DEFINITION, 'new task')
        task = dict(action['task'], status='pending', attempts=0, reason=None, job_id=None, evidence=[])
        updated = [*tasks, task]
    else:
        _task_id(action['task_id'])
        by_id = {task['id']: task for task in tasks}
        task = by_id.get(action['task_id'])
        if task is None:
            raise ValueError('Unknown task ID')
        if task['status'] not in _ALLOWED_STATES[op]:
            raise ValueError(f"Cannot {op} a {task['status']} task")

        if op == 'start':
            # Whole-board validation below also guards dependencies and role capacity.
            changes = {'status': 'running', 'attempts': task['attempts'] + 1}
        elif op == 'complete':
            if task['gate'] == 'build' and build_verified is not True:
                raise ValueError('Build completion requires a verified job')
            if task['gate'] == 'manual' and 'job_id' in action:
                raise ValueError('Manual completion does not accept a job_id')
            changes = {'status': 'completed', 'evidence': action['evidence'], 'job_id': action.get('job_id')}
        elif op == 'block':
            changes = {'status': 'blocked', 'reason': action['reason']}
        elif op == 'requeue':
            changes = {'status': 'pending', 'reason': None, 'evidence': [], 'job_id': None}
        else:
            changes = {'role': action['role']}
        by_id[task['id']] = task | changes
        updated = list(by_id.values())
    validate_tasks(updated)
    return deepcopy(updated)


def schedule(tasks):
    """Recommend the highest-priority ready task for each available specialist role."""
    validate_tasks(tasks)
    completed = {task['id'] for task in tasks if task['status'] == 'completed'}
    busy_roles = {task['role'] for task in tasks if task['status'] == 'running'}
    ready = sorted(
        (task for task in tasks if task['status'] == 'pending' and completed.issuperset(task['depends_on'])),
        key=lambda task: (-task['priority'], task['id']),
    )
    running = len(busy_roles)
    blocked = sum(task['status'] == 'blocked' for task in tasks)
    assignments = []
    for task in ready:
        role = _ROLES[task['role']]
        if role['id'] not in busy_roles:
            assignments.append({'task_id': task['id'], 'role': role['id'],
                                'model_id': role['model_id'], 'reasoning_effort': role['reasoning_effort']})
            busy_roles.add(role['id'])
    return {
        'summary': {
            'total': len(tasks), 'completed': len(completed), 'ready': len(ready),
            'running': running, 'blocked': blocked,
            'waiting': len(tasks) - len(completed) - len(ready) - running - blocked,
        },
        'ready_task_ids': [task['id'] for task in ready],
        'assignments': assignments,
    }
