"""Pure reducer for one private registry. Start with empty() or replay its accepted events.

Every event has type and project_id. Additional exact fields:
 project: name, source, environment. identity: source, environment.
 log: log_id, chat_id, ref, sha256, complete.
 decision: decision_id, decision, rationale, status, supersedes (prior ID or null).
 proposal: proposal_id, owner, source_sha256, candidate_ref, description, status,
 supersedes (prior ID or null). Status is proposed/under_review/accepted/deferred/rejected.
 The candidate hash can differ from the project's current source. A revision
 belongs to the same project and responsible owner as its predecessor.
 checkpoint: checkpoint_id, summary, log_ids, criteria, tests, pending, gaps.
 request: checkpoint_id, reason (user-request/platform-warning), detail.
 receipt: checkpoint_id, packet_sha256, actual_project_id, mode, chat_id, ref.

Source is {commit, release_ref, library_ref, sha256, dirty}. Commit is full Git
hex or null; at least one of commit/release_ref/library_ref must identify the
source. Dirty is true, false or null (unknown). Environment is a nonempty map
of string labels to string values. References are opaque and never dereferenced.
Criteria have id, description, high_risk. Tests have id, criterion_id, kind
(positive/negative), evidence (observed/reported/not-run), result
(pass/fail/unknown), raw (null or {ref,sha256}). A checkpoint inherits its exact
source/environment and the decision history through its creation. Its log_ids
explicitly identify relevant transcripts from that project's log registry.

The packet digest covers the checkpoint and freshness against current identity.
Requests bind this digest; receipts bind it again and record the observed chat
location and mode. Requests and receipts are separate from export. An expired
request needs a fresh checkpoint. This module never creates a chat or verifies
remote facts. External callers verify receipt details before recording them.
"""

from copy import deepcopy
import re

from .provenance import spec_digest
from .admin_lineage import triage_proposal


_FIELDS = {
    'project': 'name source environment', 'identity': 'source environment',
    'log': 'log_id chat_id ref sha256 complete', 'decision': 'decision_id decision rationale status supersedes',
    'proposal': 'proposal_id owner source_sha256 candidate_ref description status supersedes',
    'checkpoint': 'checkpoint_id summary log_ids criteria tests pending gaps', 'request': 'checkpoint_id reason detail',
    'receipt': 'checkpoint_id packet_sha256 actual_project_id mode chat_id ref',
}
_DECISION_STATUSES = ('proposed', 'accepted', 'rejected', 'deferred')


def _fields(value, keys, label):
    if type(value) is not dict or len(value) != len(keys) or any(k not in value for k in keys):
        raise ValueError(f'{label} requires exactly {", ".join(keys)}.')


def _text(value, label, maximum=2048):
    if type(value) is not str or len(value) > maximum or not value.strip():
        raise ValueError(f'Invalid {label}.')


def _id(value, label):
    if type(value) is not str or len(value) > 96 or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', value):
        raise ValueError(f'Invalid {label}.')


def _chat(value):
    if type(value) is not str or len(value) > 128 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*', value):
        raise ValueError('Invalid chat ID.')


def _digest(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError('Expected a lowercase SHA-256 digest.')


def _choice(value, choices, label):
    if type(value) is not str or value not in choices:
        raise ValueError(f'Invalid {label}.')


def _array(value, label, limit=128):
    if type(value) is not list or len(value) > limit:
        raise ValueError(f'Invalid {label} list.')


def _identity(source, environment):
    _fields(source, ('commit', 'release_ref', 'library_ref', 'sha256', 'dirty'), 'Source')
    _digest(source['sha256'])
    commit = source['commit']
    if commit is not None and (type(commit) is not str or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', commit)):
        raise ValueError('Expected a full Git commit or null.')
    for key in ('release_ref', 'library_ref'):
        if source[key] is not None:
            _text(source[key], key)
    if not any(source[k] for k in ('commit', 'release_ref', 'library_ref')):
        raise ValueError('At least one source reference is required.')
    if source['dirty'] is not None and type(source['dirty']) is not bool:
        raise ValueError('Dirty state must be boolean or null.')
    if type(environment) is not dict or not 1 <= len(environment) <= 32:
        raise ValueError('Provide a bounded, nonempty environment description.')
    for key, value in environment.items():
        _text(key, 'environment key', 64)
        _text(value, 'environment value', 512)


def _new_key(table, key, label):
    _id(key, label)
    if key in table:
        raise ValueError(f'Duplicate {label}.')


def _get(table, key, label):
    _id(key, label)
    if key not in table:
        raise ValueError(f'Unknown {label}.')
    return table[key]


def _evidence(criteria, tests):
    _array(criteria, 'criteria', 64)
    if not criteria:
        raise ValueError('Define at least one acceptance criterion.')
    ids = set()
    for row in criteria:
        _fields(row, ('id', 'description', 'high_risk'), 'Criterion')
        _new_key(ids, row['id'], 'criterion ID')
        ids.add(row['id'])
        _text(row['description'], 'criterion')
        if type(row['high_risk']) is not bool:
            raise ValueError('high_risk must be boolean.')
    _array(tests, 'tests', 256)
    test_ids = set()
    for row in tests:
        _fields(row, ('id', 'criterion_id', 'kind', 'evidence', 'result', 'raw'), 'Test')
        _new_key(test_ids, row['id'], 'test ID')
        test_ids.add(row['id'])
        _choice(row['criterion_id'], ids, 'test criterion')
        _choice(row['kind'], ('positive', 'negative'), 'test kind')
        _choice(row['evidence'], ('observed', 'reported', 'not-run'), 'evidence class')
        _choice(row['result'], ('pass', 'fail', 'unknown'), 'test result')
        raw = row['raw']
        if raw is not None:
            _fields(raw, ('ref', 'sha256'), 'Raw output reference')
            _text(raw['ref'], 'raw output reference')
            _digest(raw['sha256'])
        if row['evidence'] == 'observed' and (raw is None or row['result'] == 'unknown'):
            raise ValueError('An observed result needs a known outcome and raw output reference.')
        if row['evidence'] == 'not-run' and (raw is not None or row['result'] != 'unknown'):
            raise ValueError('A test not run cannot carry output or a known result.')


def empty() -> dict:
    return {'schema_version': 1, 'projects': {}}


def _projects(state):
    _fields(state, ('schema_version', 'projects'), 'Registry state')
    if type(state['schema_version']) is not int or state['schema_version'] != 1 or type(state['projects']) is not dict:
        raise ValueError('Unsupported registry state.')
    return state['projects']


def _new_project(event):
    _text(event['name'], 'project name', 160)
    _identity(event['source'], event['environment'])
    return {'name': event['name'], 'source': deepcopy(event['source']), 'environment': dict(event['environment']),
            'logs': {}, 'decisions': {}, 'decision_order': [], 'proposals': {}, 'proposal_order': [],
            'checkpoints': {}, 'continuations': {}}


def _store_log(projects, project, event):
    _new_key(project['logs'], event['log_id'], 'log ID')
    _chat(event['chat_id'])
    _text(event['ref'], 'transcript reference')
    _digest(event['sha256'])
    if type(event['complete']) is not bool:
        raise ValueError('Log completeness must be boolean.')
    for other_id, other in projects.items():
        if other_id != event['project_id'] and (any(row['chat_id'] == event['chat_id'] for row in other['logs'].values())
                or any(c['receipt'] and c['receipt']['chat_id'] == event['chat_id'] for c in other['continuations'].values())):
            raise ValueError('Chat belongs to another project.')
    project['logs'][event['log_id']] = {k: v for k, v in event.items() if k != 'type'}


def _store_decision(project, event):
    decisions = project['decisions']
    _new_key(decisions, event['decision_id'], 'decision ID')
    _text(event['decision'], 'decision')
    _text(event['rationale'], 'decision rationale')
    _choice(event['status'], _DECISION_STATUSES, 'decision status')
    old = event['supersedes']
    if old is not None:
        _get(decisions, old, 'superseded decision ID')
        if any(row['supersedes'] == old for row in decisions.values()):
            raise ValueError('A later decision already supersedes this record.')
    project['decisions'][event['decision_id']] = {k: v for k, v in event.items() if k not in ('type', 'project_id')}
    project['decision_order'].append(event['decision_id'])


def _store_proposal(project, event):
    proposals = project.setdefault('proposals', {})
    _new_key(proposals, event['proposal_id'], 'proposal ID')
    _digest(event['source_sha256'])
    triage_proposal(event['owner'], event['candidate_ref'], event['status'])
    _text(event['description'], 'proposal description')
    prior_id = event['supersedes']
    if prior_id is not None:
        prior = _get(proposals, prior_id, 'superseded proposal ID')
        if prior['owner'] != event['owner']:
            raise ValueError('A revision must retain its proposal owner.')
        if any(p['supersedes'] == prior_id for p in proposals.values()):
            raise ValueError('A later proposal already supersedes this record.')
    proposals[event['proposal_id']] = {k: v for k, v in event.items() if k not in ('type', 'project_id')}
    project.setdefault('proposal_order', []).append(event['proposal_id'])


def _store_checkpoint(project, event):
    _new_key(project['checkpoints'], event['checkpoint_id'], 'checkpoint ID')
    _text(event['summary'], 'checkpoint summary', 8192)
    _array(event['log_ids'], 'log IDs')
    included = set()
    for log_id in event['log_ids']:
        _new_key(included, log_id, 'checkpoint log ID')
        _get(project['logs'], log_id, 'project log ID')
        included.add(log_id)
    _evidence(event['criteria'], event['tests'])
    for name in ('pending', 'gaps'):
        _array(event[name], name)
        for item in event[name]:
            _text(item, name)
    checkpoint = deepcopy({k: v for k, v in event.items() if k not in ('type', 'project_id')})
    checkpoint.update(source=dict(project['source']), environment=dict(project['environment']),
                      decision_ids=project['decision_order'].copy(), proposal_ids=project.get('proposal_order', []).copy())
    project['checkpoints'][event['checkpoint_id']] = checkpoint


def _acceptance(checkpoint, current):
    results = []
    for criterion in checkpoint['criteria']:
        rows = [t for t in checkpoint['tests'] if t['criterion_id'] == criterion['id']]
        observed = {r['kind'] for r in rows if r['evidence'] == 'observed' and r['result'] == 'pass'}
        required = {'positive', 'negative'} if criterion['high_risk'] else {'positive'}
        status = 'pending'
        if not current:
            status = 'stale'
        elif any(r['evidence'] == 'observed' and r['result'] == 'fail' for r in rows):
            status = 'failed'
        elif required <= observed and all(r['evidence'] == 'observed' and r['result'] == 'pass' for r in rows):
            status = 'verified'
        results.append(dict(criterion, status=status, missing_observed_passes=sorted(required - observed)))
    return results


def handoff(state: dict, project_id: str, checkpoint_id: str) -> dict:
    """Export one scoped continuation packet. Repeated calls have no side effects."""
    project = _get(_projects(state), project_id, 'project ID')
    cp = _get(project['checkpoints'], checkpoint_id, 'checkpoint ID')
    source_matches = cp['source'] == project['source']
    environment_matches = cp['environment'] == project['environment']
    subsequent = [project['decisions'][key] for key in project['decision_order'][len(cp['decision_ids']):]]
    current = source_matches and environment_matches and not subsequent
    logs = [project['logs'][key] for key in cp['log_ids']]
    decisions = [project['decisions'][key] for key in cp['decision_ids']]
    superseded = {d['supersedes']: d['decision_id'] for d in decisions if d['supersedes'] is not None}
    gaps = list(cp['gaps'])
    if not logs:
        gaps.append('No project transcript was referenced for this checkpoint.')
    for row in logs:
        if not row['complete']:
            gaps.append(f'Project transcript {row["log_id"]} was recorded as incomplete.')
    if not source_matches or not environment_matches:
        gaps.append('The project identity changed. Re-run verification for the current source and environment.')
    if subsequent:
        gaps.append('Project decisions changed after capture. Recheck acceptance against the current decision history.')
    packet = {
        'schema_version': 1, 'project_id': project_id, 'project_name': project['name'], 'checkpoint_id': checkpoint_id,
        'summary': cp['summary'], 'source': cp['source'], 'environment': cp['environment'],
        'current_source': project['source'], 'current_environment': project['environment'],
        'freshness': {'source_matches': source_matches, 'environment_matches': environment_matches, 'decisions_match': not subsequent},
        'logs': logs, 'decisions': [dict(d, superseded_by=superseded.get(d['decision_id'])) for d in decisions],
        'subsequent_decisions': subsequent,
        'tests': [dict(t, valid_for_current_identity=source_matches and environment_matches,
                       needs_reverification=not current) for t in cp['tests']],
        'acceptance': _acceptance(cp, current),
        'pending': cp['pending'], 'gaps': gaps,
        'target': {'project_id': project_id, 'mode': 'regular', 'fullness': 'unknown'},
    }
    if project.get('proposals'):
        prior_ids = cp.get('proposal_ids', [])
        captured = [project['proposals'][key] for key in prior_ids]
        later = project['proposal_order'][len(prior_ids):]
        successors = {p['supersedes']: p['proposal_id'] for p in captured if p['supersedes'] is not None}
        packet['proposals'] = [dict(p, superseded_by=successors.get(p['proposal_id'])) for p in captured]
        packet['subsequent_proposals'] = [project['proposals'][key] for key in later]
    return deepcopy(dict(packet, packet_sha256=spec_digest(packet)))


def _continuation(state, project, event):
    checkpoint_id = event['checkpoint_id']
    packet = handoff(state, event['project_id'], checkpoint_id)
    continuations = project['continuations']
    if event['type'] == 'request':
        _new_key(continuations, checkpoint_id, 'continuation request')
        _choice(event['reason'], ('platform-warning', 'user-request'), 'request reason')
        _text(event['detail'], 'request evidence')
        continuations[checkpoint_id] = {'reason': event['reason'], 'detail': event['detail'],
                                        'prior_chat_ids': sorted({row['chat_id'] for row in project['logs'].values()}),
                                        'packet_sha256': packet['packet_sha256'], 'receipt': None}
        return
    continuation = _get(continuations, checkpoint_id, 'continuation request')
    if continuation['receipt'] is not None:
        raise ValueError('A creation receipt already exists for this request.')
    _digest(event['packet_sha256'])
    if event['packet_sha256'] != continuation['packet_sha256'] or event['packet_sha256'] != packet['packet_sha256']:
        raise ValueError('Creation receipt does not match the current requested packet.')
    if event['actual_project_id'] != event['project_id'] or event['mode'] != 'regular':
        raise ValueError('Receipt must confirm a regular chat in the requested project.')
    _chat(event['chat_id'])
    _text(event['ref'], 'creation receipt reference')
    if event['chat_id'] in continuation['prior_chat_ids']:
        raise ValueError('Chat ID existed before the creation request.')
    for other_id, other in state['projects'].items():
        if other_id != event['project_id'] and any(log['chat_id'] == event['chat_id'] for log in other['logs'].values()):
            raise ValueError('Chat ID belongs to another project.')
        if any(c['receipt'] and c['receipt']['chat_id'] == event['chat_id'] for c in other['continuations'].values()):
            raise ValueError('A chat ID can fulfill only one creation request.')
    continuation['receipt'] = {k: event[k] for k in ('actual_project_id', 'mode', 'chat_id', 'ref', 'packet_sha256')}


def apply(state: dict, event: dict) -> dict:
    """Apply one closed-schema event and detach the result from both inputs."""
    _projects(state)
    if type(event) is not dict:
        raise ValueError('Expected one registry event.')
    kind = event.get('type')
    _choice(kind, _FIELDS, 'event type')
    _fields(event, ['type', 'project_id', *_FIELDS[kind].split()], 'Registry event')
    project_id = event['project_id']
    _id(project_id, 'project ID')
    updated = deepcopy(state)
    projects = updated['projects']
    if kind == 'project':
        _new_key(projects, project_id, 'project ID')
        projects[project_id] = _new_project(event)
    else:
        project = _get(projects, project_id, 'project ID')
        if kind == 'identity':
            _identity(event['source'], event['environment'])
            project.update(source=dict(event['source']), environment=dict(event['environment']))
        elif kind == 'log':
            _store_log(projects, project, event)
        elif kind == 'decision':
            _store_decision(project, event)
        elif kind == 'proposal':
            _store_proposal(project, event)
        elif kind == 'checkpoint':
            _store_checkpoint(project, event)
        else:
            _continuation(updated, project, event)
    return updated
