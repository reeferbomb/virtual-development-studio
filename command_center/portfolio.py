"""Read the workspace's task boards and recommend work for shared specialist roles."""

import fcntl
import os
from collections import defaultdict
from contextlib import ExitStack, contextmanager

from .checkpoints import _locked_directory
from .dispatch import default_profile, production_instruction
from .projects import PROJECT_ID, ProjectStore
from .priorities import rank_tasks
from .studio_curriculum import training_instruction
from .task_store import TaskStore, _read_json


@contextmanager
def _locked_projects(projects):
    # Keep directory membership and every readable project stable through the scan.
    # Creators take the list lock; individual board and spec writers take only a project lock.
    with _locked_directory(projects.projects, fcntl.LOCK_SH) as root, ExitStack() as locks:
        with os.scandir(root) as entries:
            ids = sorted(entry.name for entry in entries
                         if PROJECT_ID.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False))
        directories = {}
        for project_id in ids:
            try:
                directories[project_id] = locks.enter_context(
                    _locked_directory(projects.directory(project_id), fcntl.LOCK_SH))
            except (OSError, ValueError):
                directories[project_id] = None
        yield directories


def _dispatch_plan(assignments):
    profile = default_profile()
    roles = {role['id']: role for role in profile['roles']}
    spawn_args = []
    for assignment in assignments:
        project_id = assignment['project_id']
        role = assignment['role']
        message = (
            f"Studio project {project_id}. The Midnight Shift: {roles[role]['name']} (role {role}). "
            f"Task {assignment['task_id']}: {assignment['title']}. "
            f"Specification SHA-256 {assignment['spec_sha256']}, board revision {assignment['board_revision']}. "
            f"Before launch, the lead must refresh /api/portfolio and /api/projects/{project_id}/tasks, "
            "confirm this assignment is still recommended and claim the exact task with a start action "
            "using the current board revision and matching specification digest. Refresh the export if "
            "the recommendation or specification has changed or the claim fails. "
            "Work only on the claimed task. Return completion evidence to the lead for board and checkpoint updates. "
            f"{production_instruction(project_id)}"
            f"{training_instruction(role)}"
            f"{profile['continuity']['host_instruction']}"
        )
        spawn_args.append({'task_name': roles[role]['agent_task_name'], 'fork_turns': 'none', 'model': assignment['model_id'],
                           'reasoning_effort': assignment['reasoning_effort'], 'message': message})
    return {'execution_mode': 'export_only', 'host_tool': 'collaboration.spawn_agent', 'profile': profile,
            'assignments': assignments, 'spawn_args': spawn_args}


def portfolio_plan(projects: ProjectStore, tasks: TaskStore) -> dict:
    """Read a coherent workspace snapshot without claiming or launching work."""
    rows = []
    summary = dict.fromkeys(('projects', 'current', 'stale', 'empty', 'unavailable', 'running', 'ready'), 0)
    running_projects = defaultdict(list)
    candidates = []
    roles = {role['id']: role for role in default_profile()['roles']}
    with _locked_projects(projects) as directories:
        for project_id, directory in directories.items():
            name = project_id
            try:
                if directory is None:
                    raise ValueError('Could not lock project directory')
                metadata = _read_json(directory, 'project.json')
                if not isinstance(metadata, dict):
                    raise ValueError('Invalid project metadata')
                if isinstance(metadata.get('name'), str) and metadata['name']:
                    name = metadata['name']
                project = {**metadata, 'spec': _read_json(directory, 'spec.json')}
                board = tasks.get(project_id)
                ranked = rank_tasks(project, board)
                if ranked['status'] == 'unavailable':
                    raise ValueError('Invalid scheduling snapshot')
            except (OSError, ValueError, RecursionError):
                rows.append({'project_id': project_id, 'name': name, 'state': 'unavailable',
                             'revision': None, 'spec_sha256': None, 'summary': None,
                             'error': 'Could not read the project metadata, specification or task board.'})
                summary['unavailable'] += 1
                continue

            state = board['state']
            rows.append({'project_id': project_id, 'name': name, 'state': state,
                         'revision': board['revision'], 'spec_sha256': board['spec_sha256'],
                         'summary': board['summary']})
            summary[state] += 1
            summary['running'] += board['summary']['running']
            summary['ready'] += board['summary']['ready']
            for task in board['tasks']:
                # A stale board cannot offer work, but its specialist may still be running.
                if task['status'] == 'running':
                    running_projects[task['role']].append(project_id)
            if state == 'current':
                for task in ranked['recommendations']:
                    role = roles[task['role']]
                    candidate = {'task_id': task['task_id'], 'role': task['role'],
                                 'model_id': role['model_id'], 'reasoning_effort': role['reasoning_effort'],
                                 'project_id': project_id, 'title': task['title'], 'priority': task['priority'],
                                 'board_revision': board['revision'], 'spec_sha256': board['spec_sha256']}
                    key = (-task['priority'], -task['downstream_count'], -task['chain_length'], project_id, task['task_id'])
                    candidates.append((key, candidate))

    summary['projects'] = len(rows)
    assignments = []
    if not summary['unavailable'] and not any(len(owners) > 1 for owners in running_projects.values()):
        taken = set(running_projects)
        for _, candidate in sorted(candidates, key=lambda entry: entry[0]):
            if candidate['role'] not in taken:
                assignments.append(candidate)
                taken.add(candidate['role'])

    occupied_roles = sorted(running_projects)
    conflicts = [{'role': role, 'project_ids': running_projects[role]} for role in occupied_roles
                 if len(running_projects[role]) > 1]
    return {'projects': rows, 'summary': summary, 'occupied_roles': occupied_roles,
            'role_occupancy': dict(running_projects), 'assignments': assignments,
            'conflicts': conflicts, 'dispatch_plan': _dispatch_plan(assignments)}
