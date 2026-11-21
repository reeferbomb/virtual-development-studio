"""Assess a bounded production schedule and simulated release evidence."""

from collections import Counter
from graphlib import CycleError, TopologicalSorter
from itertools import combinations
import re


_ID = 'production-pipeline'
_ROLES = ('architecture', 'content', 'build_operations', 'verification')
# Required role, artifact ID and prerequisite stages. Other tasks may bridge the edges.
_STAGES = {
    'prototype': ('architecture', 'loop-notes', ()),
    'vertical-slice': ('architecture', 'slice-build', ('prototype',)),
    'prepare-content': ('content', 'asset-export', ('prototype',)),
    'integrate-content': ('content', 'integrated-scene', ('vertical-slice', 'prepare-content')),
    'package': ('build_operations', 'build-manifest', ('integrate-content',)),
    'review': ('verification', 'smoke-report', ('package',)),
    'rollback-drill': ('build_operations', 'rollback-log', ('package',)),
    'handoff': ('build_operations', 'acceptance-packet', ('review', 'rollback-drill')),
}
_DEADLINES = {'prototype': 3, 'vertical-slice': 6, 'integrate-content': 8, 'handoff': 14}
_SCENARIOS = ('launch', 'core-loop', 'content-import')
_LAST_GOOD = '4985c701552838eb9fae3e3cbe15e3e268dc770f4b52c80c451953a79a0a47fc'
_EXAMPLE_PACKAGE = 'b38d3c61627810ae8b86ff15da90755520101312acf34e744857360a5cfc8cee'


TRACK = {
    'id': _ID,
    'title': 'Production pipeline and integration',
    'roles': list(_ROLES),
    'workflow': [
        'Prototype the smallest core loop with placeholders. Record what you learned and pick one player goal for the vertical slice.',
        'Build that goal end to end at representative quality. Agree on asset formats, import settings and ownership before authoring content in parallel.',
        'Sequence tasks by dependencies and role capacity. Track milestone deadlines, expected artifacts and acceptance criteria.',
        'Review changes on scoped branches, track editable sources and import settings, and integrate against a named source revision.',
        'Pin toolchain and dependency versions. Build the same commit from two clean checkouts with the same target and settings, and compare package checksums.',
        'Have an independent reviewer test that exact candidate. Hold handoff on failed gates and retain a verified last-known-good package for rollback.',
    ],
    'deliverables': [
        'Prototype findings, a playable vertical slice, and an integrated content scene with editable sources and import settings.',
        'Dependency plan and milestone dates, pinned build inputs and package checksums, review evidence, and a rollback record.',
    ],
    'verification': [
        'Check dependency ordering, role capacity and milestone finish times against the plan.',
        'Compare clean build manifests and run launch, core-loop and content-import checks against the exact candidate.',
        'Match the restored package against the last-known-good digest and run a smoke test after restoration.',
    ],
    'exercise': 'Plan and check an integrated vertical slice from prototype through release handoff using simulated production records.',
}


def _task(identifier, start, duration):
    role, artifact, parents = _STAGES[identifier]
    return dict(id=identifier, role=role, start=start, duration=duration, artifact=artifact,
                depends_on=list(parents))


def _build(workspace):
    return dict(workspace=workspace, revision='32bf1d2a341fe818a8902ed3708b0684af767120',
                toolchain='godot-4.4.1',
                lock_sha256='a679b17b2dce45dac15447a272ce5db15cd9669498e1df65b497c56ed182a399',
                package_sha256=_EXAMPLE_PACKAGE)


EXERCISES = [{
    'id': _ID,
    'title': 'Schedule and verify a vertical-slice handoff',
    'brief': (
        'Plan a beacon-yard slice with 1–12 tasks. Use the eight required stage IDs, role owners and artifact IDs '
        'shown in the example. Task and artifact IDs use up to 32 lowercase letters, digits, hyphens or underscores '
        'and start with a letter. Carry each listed dependency directly or through other tasks, and make every '
        'task part of the handoff. Choose integer starts from 0–32 and durations from 1–8. Each role handles one '
        'task at a time. A task finishes at start plus duration, and another may start at that finish. '
        'Predict the handoff finish and the longest chain of task durations ending at handoff, ignoring role '
        'capacity and waiting for the latter. Finish prototype by step 3, vertical slice by 6, content integration '
        'by 8 and handoff by 14. '
        'Submit two simulated clean builds in distinct workspaces with the same full 40-character Git revision, '
        'versioned toolchain ID, dependency-lock SHA-256 and package SHA-256. Have verification review the exact '
        'package with 1–5 numeric exit codes each for launch, core-loop and content-import. A zero exit code passes. '
        'Simulate a rollback of that candidate to the supplied last-known-good SHA-256 '
        f'{_LAST_GOOD} and check the restored package with a smoke test. '
        'The exercise compares fixture records. Real release acceptance requires the actual artifacts and tests.'
    ),
    'criteria': [
        {'id': 'dependencies', 'label': 'Link all stages and planned tasks to the handoff in an acyclic dependency graph.'},
        {'id': 'artifacts', 'label': 'Assign each stage to its owner and produce its expected, unique artifact.'},
        {'id': 'schedule', 'label': 'Finish prerequisites before dependent starts and keep every role within capacity.'},
        {'id': 'forecast', 'label': 'Predict the weighted dependency critical path length and scheduled handoff finish.'},
        {'id': 'milestones', 'label': 'Meet the four fixed milestone deadlines.'},
        {'id': 'reproducibility', 'label': 'Match the pinned inputs and package checksum across distinct clean-build records.'},
        {'id': 'verification', 'label': 'Have the independent role record successful smoke runs on the exact candidate.'},
        {'id': 'rollback', 'label': 'Restore the supplied last-known-good package and record a successful smoke run.'},
    ],
    'example': {
        'tasks': [_task('prototype', 0, 2), _task('vertical-slice', 2, 3), _task('prepare-content', 2, 2),
                  _task('integrate-content', 5, 2), _task('package', 7, 2), _task('review', 9, 2),
                  _task('rollback-drill', 9, 1), _task('handoff', 12, 1)],
        'forecast': {'critical_path_steps': 12, 'handoff_step': 13},
        'builds': [_build('clean-a'), _build('clean-b')],
        'review': {'role': 'verification', 'package_sha256': _EXAMPLE_PACKAGE,
                   'scenarios': [{'id': name, 'exit_codes': [0]} for name in _SCENARIOS]},
        'rollback': {'candidate_sha256': _EXAMPLE_PACKAGE, 'previous_sha256': _LAST_GOOD,
                     'restored_sha256': _LAST_GOOD, 'smoke_exit_code': 0},
    },
}]


def _object(value, fields, label):
    if type(value) is not dict or value.keys() != set(fields):
        raise ValueError(f'{label} requires exactly these fields ({", ".join(fields)}).')


def _array(value, low, high, label):
    if type(value) is not list or not low <= len(value) <= high:
        raise ValueError(f'{label} requires a list of {low}–{high} entries.')


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} requires an integer from {low} to {high}.')


def _identifier(value, label):
    if type(value) is not str or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', value):
        raise ValueError(f'{label} requires a lowercase identifier of at most 32 characters.')


def _role(value):
    if type(value) is not str or value not in _ROLES:
        raise ValueError(f'Role must be one of {", ".join(_ROLES)}.')


def _digest(value, length, label):
    if type(value) is not str or len(value) != length or not re.fullmatch('[a-f0-9]+', value):
        raise ValueError(f'{label} requires exactly {length} lowercase hexadecimal characters.')


def _tasks(rows):
    _array(rows, 1, 12, 'tasks')
    tasks = {}
    for task in rows:
        _object(task, ('id', 'role', 'start', 'duration', 'artifact', 'depends_on'), 'Task')
        identifier = task['id']
        _identifier(identifier, 'Task ID')
        _identifier(task['artifact'], 'Artifact ID')
        _role(task['role'])
        _integer(task['start'], 0, 32, 'Task start')
        _integer(task['duration'], 1, 8, 'Task duration')
        _array(task['depends_on'], 0, 11, 'Task prerequisites')
        for parent in task['depends_on']:
            _identifier(parent, 'Prerequisite ID')
        if identifier in tasks or len(set(task['depends_on'])) != len(task['depends_on']):
            raise ValueError('Task IDs and each task’s prerequisite IDs must be unique.')
        tasks[identifier] = task
    return tasks


def _validate_evidence(builds, review, rollback):
    _array(builds, 2, 2, 'builds')
    for build in builds:
        _object(build, ('workspace', 'revision', 'toolchain', 'lock_sha256', 'package_sha256'), 'Build')
        _identifier(build['workspace'], 'Clean workspace ID')
        _digest(build['revision'], 40, 'Git revision')
        if type(build['toolchain']) is not str or not re.fullmatch(
                '[a-z][a-z0-9_.-]{0,47}', build['toolchain']):
            raise ValueError('Toolchain requires a versioned identifier of at most 48 characters.')
        for field in ('lock_sha256', 'package_sha256'):
            _digest(build[field], 64, field)

    _object(review, ('role', 'package_sha256', 'scenarios'), 'Review')
    _role(review['role'])
    _digest(review['package_sha256'], 64, 'Reviewed package')
    _array(review['scenarios'], 0, len(_SCENARIOS), 'Review scenarios')
    scenarios = set()
    for scenario in review['scenarios']:
        _object(scenario, ('id', 'exit_codes'), 'Smoke scenario')
        identifier = scenario['id']
        if type(identifier) is not str or identifier not in _SCENARIOS or identifier in scenarios:
            raise ValueError('Review requires unique scenario IDs from the exercise.')
        scenarios.add(identifier)
        _array(scenario['exit_codes'], 1, 5, 'Smoke exit codes')
        for code in scenario['exit_codes']:
            _integer(code, 0, 255, 'Smoke exit code')

    _object(rollback, ('candidate_sha256', 'previous_sha256', 'restored_sha256', 'smoke_exit_code'), 'Rollback')
    for field in ('candidate_sha256', 'previous_sha256', 'restored_sha256'):
        _digest(rollback[field], 64, field)
    _integer(rollback['smoke_exit_code'], 0, 255, 'Rollback smoke exit code')


def _result(identifier, passed, detail):
    return {'id': identifier, 'status': 'pass' if passed else 'fail', 'detail': detail}


def _graph(tasks):
    graph = {identifier: sorted(tasks[identifier]['depends_on']) for identifier in sorted(tasks)}
    unknown = sorted({parent for parents in graph.values() for parent in parents} - tasks.keys())
    if unknown:
        return {}, None, 'Unknown prerequisite IDs include ' + ', '.join(unknown[:3]) + '.'
    try:
        order = tuple(TopologicalSorter(graph).static_order())
    except CycleError as error:
        return {}, None, 'Dependency cycle through ' + ' → '.join(error.args[1]) + '.'

    ancestors, paths = {}, {}
    for identifier in order:
        parents = graph[identifier]
        ancestors[identifier] = set(parents).union(*(ancestors[parent] for parent in parents))
        weight, path = min((paths[parent] for parent in parents), default=(0, ()),
                           key=lambda item: (-item[0], item[1]))
        paths[identifier] = weight + tasks[identifier]['duration'], (*path, identifier)
    return ancestors, paths.get('handoff'), None


def _dependencies(tasks, ancestors, error):
    if error:
        return _result('dependencies', False, error)
    missing = sorted(_STAGES.keys() - tasks.keys())
    if missing:
        return _result('dependencies', False, 'Missing required stages ' + ', '.join(missing) + '.')
    for identifier, (_, _, parents) in _STAGES.items():
        absent = sorted(set(parents) - ancestors[identifier])
        if absent:
            return _result('dependencies', False, f'{identifier} must follow {", ".join(absent)}.')
    detached = sorted(tasks.keys() - ancestors['handoff'] - {'handoff'})
    if detached:
        return _result('dependencies', False, 'Handoff does not depend on ' + ', '.join(detached) + '.')
    return _result('dependencies', True, f'All {len(tasks)} tasks reach the handoff through an acyclic graph.')


def _artifacts(tasks):
    for identifier, (role, artifact, _) in _STAGES.items():
        task = tasks.get(identifier)
        if not task or (task['role'], task['artifact']) != (role, artifact):
            return _result('artifacts', False, f'{identifier} requires role {role} and artifact {artifact}.')
    duplicates = sorted(artifact for artifact, count in Counter(
        task['artifact'] for task in tasks.values()).items() if count > 1)
    if duplicates:
        return _result('artifacts', False, 'Multiple tasks produce ' + ', '.join(duplicates) + '.')
    return _result('artifacts', True, f'All {len(tasks)} artifacts are unique and required stages have their designated owners.')


def _schedule(tasks, finishes, error):
    if error:
        return _result('schedule', False, 'A resolvable dependency graph is required to check the schedule.')
    for identifier, task in sorted(tasks.items()):
        for parent in sorted(task['depends_on']):
            if finishes[parent] > task['start']:
                return _result('schedule', False, f'{identifier} starts at step {task["start"]}, '
                               f'before {parent} finishes at step {finishes[parent]}.')
    for left, right in combinations(sorted(tasks), 2):
        a, b = tasks[left], tasks[right]
        if a['role'] == b['role'] and max(a['start'], b['start']) < min(finishes[left], finishes[right]):
            return _result('schedule', False, f'{left} and {right} overlap on role {a["role"]}.')
    return _result('schedule', True, f'All {len(tasks)} tasks respect prerequisite finish times and role capacity.')


def _forecast(forecast, path, handoff):
    if path is None:
        return _result('forecast', False, 'A resolvable graph and a handoff task are required to compute the forecast.')
    duration, chain = path
    matches = (forecast['critical_path_steps'], forecast['handoff_step']) == (duration, handoff)
    return _result('forecast', matches, f'Dependency critical path takes {duration} steps '
                   f'({" → ".join(chain)}). Scheduled handoff finishes at step {handoff}.')


def _milestones(finishes):
    descriptions = []
    for stage, deadline in _DEADLINES.items():
        finish = finishes.get(stage, 'missing')
        descriptions.append(f'{stage} {finish} (due {deadline})')
    reached = sum(finishes.get(stage, deadline + 1) <= deadline for stage, deadline in _DEADLINES.items())
    return _result('milestones', reached == len(_DEADLINES),
                   f'{reached} of {len(_DEADLINES)} scheduled milestones meet their deadlines. '
                   + ', '.join(descriptions) + '.')


def _reproducibility(builds):
    first, second = builds
    fields = ('revision', 'toolchain', 'lock_sha256', 'package_sha256')
    differences = [field for field in fields if first[field] != second[field]]
    if first['workspace'] == second['workspace']:
        return _result('reproducibility', False, 'The two build records use the same workspace ID.')
    if differences:
        return _result('reproducibility', False, 'The two build records differ in ' + ', '.join(differences) + '.')
    return _result('reproducibility', True, 'Two workspace records agree on revision, toolchain, lock and package digest.')


def _verification(tasks, package_digests, review):
    issues = []
    if package_digests != {review['package_sha256']}:
        issues.append('Review digest must match both build outputs.')
    role = review['role']
    if (role != tasks.get('review', {}).get('role') or role != 'verification'
            or role == tasks.get('package', {}).get('role')):
        issues.append('The designated verification role must review independently of packaging.')
    checked = {scenario['id']: scenario['exit_codes'] for scenario in review['scenarios']}
    missing = sorted(set(_SCENARIOS) - checked.keys())
    failed = sorted(identifier for identifier, codes in checked.items() if any(codes))
    if missing:
        issues.append('Missing smoke scenarios ' + ', '.join(missing) + '.')
    if failed:
        issues.append('Nonzero smoke exits for ' + ', '.join(failed) + '.')
    runs = sum(map(len, checked.values()))
    passed = sum(code == 0 for codes in checked.values() for code in codes)
    return _result('verification', not issues,
                   f'{passed} of {runs} recorded smoke runs exited zero. ' + ' '.join(issues)
                   if issues else f'Independent review matched the candidate. All {runs} smoke runs exited zero.')


def _rollback(package_digests, rollback):
    if package_digests != {rollback['candidate_sha256']}:
        return _result('rollback', False, 'Rollback drill must identify the package produced by both builds.')
    if rollback['candidate_sha256'] == _LAST_GOOD or rollback['previous_sha256'] != _LAST_GOOD:
        return _result('rollback', False, 'The drill requires the supplied last-known-good package distinct from the candidate.')
    if rollback['restored_sha256'] != _LAST_GOOD:
        return _result('rollback', False, 'Restored digest differs from the supplied last-known-good package.')
    code = rollback['smoke_exit_code']
    return _result('rollback', code == 0, f'Restored digest matches last-known-good. Smoke exit code {code}.')


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown production exercise.')
    _object(submission, ('tasks', 'forecast', 'builds', 'review', 'rollback'), 'Submission')
    tasks = _tasks(submission['tasks'])
    forecast = submission['forecast']
    _object(forecast, ('critical_path_steps', 'handoff_step'), 'Forecast')
    _integer(forecast['critical_path_steps'], 1, 96, 'Critical path')
    _integer(forecast['handoff_step'], 1, 40, 'Handoff step')
    builds, review, rollback = (submission[field] for field in ('builds', 'review', 'rollback'))
    _validate_evidence(builds, review, rollback)
    package_digests = {build['package_sha256'] for build in builds}
    ancestors, path, graph_error = _graph(tasks)
    finishes = {identifier: task['start'] + task['duration'] for identifier, task in tasks.items()}
    return [
        _dependencies(tasks, ancestors, graph_error),
        _artifacts(tasks),
        _schedule(tasks, finishes, graph_error),
        _forecast(forecast, path, finishes.get('handoff')),
        _milestones(finishes),
        _reproducibility(builds),
        _verification(tasks, package_digests, review),
        _rollback(package_digests, rollback),
    ]
