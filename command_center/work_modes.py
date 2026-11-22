"""Private pre-production work sessions; no agent launch, build or release side effects."""

from copy import deepcopy
import re

from .dispatch import default_profile
from .provenance import spec_digest


_TASKS = {
    'creative': (
        'Explore original system concepts, technical tradeoffs and alternatives; avoid premature architecture commitments.',
        'Propose distinct player fantasies, core loops, playstyles, fun and replayability hypotheses.',
        'Independently critique assumptions by identifying unknowns, failure modes and falsifiable playtest questions; do not author the final concept.',
        'Explore distinct HUD, menus, onboarding, audio feedback, accessibility and controller concepts.',
        'Explore original art direction, environmental storytelling, characters, animation, voices, music and VFX ideas.',
        'Identify feasibility, asset licensing, free-tool, hardware and production constraints; estimate uncertainty, not guaranteed costs.'),
    'planning': (
        'Map system boundaries, milestones, prerequisites and technical risks into an implementable plan.',
        'Define player-facing gameplay slices, dependencies and measurable feature acceptance criteria.',
        'Independently critique the plan; specify positive and negative verification, raw evidence and invalidation triggers.',
        'Plan interface and accessibility milestones, controller focus, input and visual acceptance.',
        'Plan original assets, animation, narrative, sound and VFX production with provenance and deliverables.',
        'Plan build, packaging, tooling, capacity, rollback and recovery checkpoints; identify blockers.'),
}
_LIMIT = 64


def _fields(value, keys):
    if type(value) is not dict or set(value) != set(keys.split()):
        raise ValueError('Invalid work-mode fields.')


def _text(value):
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise ValueError('Invalid work-mode text.')


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,95}', value):
        raise ValueError('Invalid work-mode ID.')


def _strings(items, *, nonempty=False):
    if type(items) is not list or len(items) > _LIMIT or (nonempty and not items):
        raise ValueError('Invalid work-mode list.')
    for item in items:
        _text(item)


def _identity(project):
    return spec_digest({k: project[k] for k in ('source', 'environment', 'decision_order')})


def _session(project, sid):
    _id(sid)
    if sid not in project.get('work_modes', {}):
        raise ValueError('Unknown work-mode session.')
    return project['work_modes'][sid]


def _roles():
    return [r['id'] for r in default_profile()['roles']]


def _synthesis(mode, output):
    if mode == 'creative':
        _fields(output, 'alternatives recommendation risks')
        options = output['alternatives']
        if type(options) is not list or not 2 <= len(options) <= _LIMIT:
            raise ValueError('Creative synthesis needs at least two original alternatives.')
        ids = set()
        for option in options:
            _fields(option, 'id title pitch tradeoff')
            _id(option['id'])
            for key in ('title', 'pitch', 'tradeoff'):
                _text(option[key])
            if option['id'] in ids:
                raise ValueError('Duplicate creative alternative.')
            ids.add(option['id'])
        _id(output['recommendation'])
        if output['recommendation'] not in ids:
            raise ValueError('Recommendation must identify an alternative.')
    else:
        _fields(output, 'tasks risks')
        tasks = output['tasks']
        if type(tasks) is not list or not 1 <= len(tasks) <= _LIMIT:
            raise ValueError('Planning requires bounded tasks.')
        graph = {}
        for task in tasks:
            _fields(task, 'id title owner depends_on acceptance high_risk')
            _id(task['id'])
            _text(task['title'])
            _strings(task['acceptance'], nonempty=True)
            _strings(task['depends_on'])
            if task['owner'] not in _roles() or type(task['high_risk']) is not bool or task['id'] in graph:
                raise ValueError('Invalid planning task.')
            for dep in task['depends_on']:
                _id(dep)
            if len(set(task['depends_on'])) != len(task['depends_on']):
                raise ValueError('Duplicate dependency.')
            graph[task['id']] = set(task['depends_on'])
        if any(deps - graph.keys() for deps in graph.values()):
            raise ValueError('Unknown task dependency.')
        remaining = set(graph)
        while remaining:
            ready = {key for key in remaining if not graph[key] & remaining}
            if not ready:
                raise ValueError('Cyclic plan dependencies.')
            remaining -= ready
    _strings(output['risks'])


def apply(project, event):
    """Apply one validated session event to the registry's detached project copy."""
    shapes = {'start': 'mode brief constraints from_session', 'report': 'role status summary',
              'synthesize': 'actor output', 'decide': 'actor decision choice digest rationale'}
    if type(event) is not dict or type(event.get('op')) is not str or event['op'] not in shapes:
        raise ValueError('Invalid work-mode event.')
    op = event['op']
    _fields(event, 'op session_id ' + shapes[op])
    sid = event['session_id']
    _id(sid)
    if op == 'start':
        sessions = project.setdefault('work_modes', {})
        mode = event['mode']
        if mode not in ('creative', 'planning') or sid in sessions or len(sessions) >= _LIMIT:
            raise ValueError('Invalid or duplicate work-mode session.')
        if any(s['decision'] is None for s in sessions.values()):
            raise ValueError('Close the existing work-mode session first.')
        _text(event['brief'])
        _strings(event['constraints'])
        parent = None
        if event['from_session'] is not None:
            p = _session(project, event['from_session'])
            if mode != 'planning' or p['mode'] != 'creative' or not p['decision'] or p['decision']['decision'] != 'approve' or p['identity'] != _identity(project):
                raise ValueError('Planning parent must be a current, user-approved creative session.')
            parent = next(option for option in p['synthesis']['alternatives'] if option['id'] == p['decision']['choice'])
        sessions[sid] = deepcopy(dict(mode=mode, brief=event['brief'], constraints=event['constraints'],
                                      from_session=event['from_session'], parent_concept=parent, identity=_identity(project),
                                      source=project['source'], environment=project['environment'], reports={}, synthesis=None,
                                      synthesis_sha256=None, decision=None))
        return
    s = _session(project, sid)
    if s['decision'] is not None:
        raise ValueError('Closed work-mode session is immutable.')
    fresh = s['identity'] == _identity(project)
    if op == 'report':
        role = event['role']
        if not fresh or s['synthesis'] is not None or role not in _roles() or role in s['reports'] or event['status'] not in ('reported', 'unavailable'):
            raise ValueError('Stale, duplicate or invalid specialist report.')
        _text(event['summary'])
        s['reports'][role] = dict(status=event['status'], summary=event['summary'])
    elif op == 'synthesize':
        if not fresh or s['synthesis'] is not None or event['actor'] != 'lead' or set(s['reports']) != set(_roles()):
            raise ValueError('Synthesis requires current session and all six report dispositions.')
        _synthesis(s['mode'], event['output'])
        s['synthesis'] = deepcopy(event['output'])
        s['synthesis_sha256'] = spec_digest(s)
    else:
        decision = event['decision']
        if event['actor'] != 'user' or decision not in ('approve', 'defer', 'reject'):
            raise ValueError('Only the user may decide.')
        _text(event['rationale'])
        if decision == 'approve':
            if not fresh or s['synthesis'] is None or event['digest'] != s['synthesis_sha256'] or s['reports']['verification']['status'] != 'reported':
                raise ValueError('Approval needs current synthesis and independent verification-role critique.')
            choices = [o['id'] for o in s['synthesis']['alternatives']] if s['mode'] == 'creative' else [None]
            if event['choice'] not in choices:
                raise ValueError('Select an actual creative alternative or approve the plan.')
        elif event['choice'] is not None or event['digest'] not in (None, s['synthesis_sha256']):
            raise ValueError('A non-approval cannot select an alternative.')
        s['decision'] = deepcopy({k: event[k] for k in ('actor', 'decision', 'choice', 'digest', 'rationale')})


def dispatch(project, sid):
    """Same independent assignments even after another role reports; private by default."""
    s = _session(project, sid)
    if s['decision'] is not None or s['identity'] != _identity(project):
        raise ValueError('Work-mode dispatch is closed or stale.')
    profile = default_profile()
    instructions = [dict(role=role['id'], instruction=task + ' Return independent ideas or planning findings, not implementation or evidence of execution.')
                    for role, task in zip(profile['roles'], _TASKS[s['mode']], strict=True)]
    return deepcopy(dict(status='dispatch-plan-only', mode=s['mode'], session_id=sid, profile=profile,
                         brief=s['brief'], constraints=s['constraints'], parent_concept=s['parent_concept'], source=s['source'],
                         assignments=instructions, private=True, launches_agents=False, authorizes_execution=False,
                         phase_policy='Stop at user decision. Sustained-work settings do not authorize implementation or publication.'))


def handoff(project, sid):
    s = _session(project, sid)
    return deepcopy(dict(s, session_id=sid, fresh=s['identity'] == _identity(project), private=True,
                         authorizes_execution=False, authorizes_release=False))
