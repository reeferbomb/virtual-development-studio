"""Deterministic, local Tribunal review journal. All events are operator-supplied.

A digest binds an observation to a named source and artifact. It does not check
artifact contents or authenticate the person supplying the observation.
"""
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime

from .tribunal_relay import validate_receipt, validate_shareable_text


DEFAULT_PROVIDERS = ('chatgpt', 'claude', 'gemini')
DEFAULT_ROLES = {'chatgpt': 'Synthesis lead', 'claude': 'Independent critic',
                 'gemini': 'Alternative design reviewer'}
ROUNDS = ('proposal', 'critique')
MAX_EVENTS = 512
MAX_PROVIDERS = 8
MAX_SUMMARY = 1200
IDENTIFIER = re.compile(r'[a-z][a-z0-9_-]{0,63}')
DIGEST = re.compile(r'[0-9a-f]{64}')
UTC = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)')
# Obvious pasted credentials are rejected even when the shareable box was ticked.
CREDENTIAL = re.compile(r'-----BEGIN [^-]*PRIVATE KEY-----|\bBearer\s+\S+|'
                        r'\b(?:sk-(?:ant-|proj-)?|gh[pousr]_)[A-Za-z0-9_-]{12,}|'
                        r'\bAKIA[A-Z0-9]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b|'
                        r'\b(?:api[-_ ]?key|password|secret|access[-_ ]?token|authorization)\s*[:=]\s*\S+',
                        re.IGNORECASE)


def _fields(value, required, optional=()):
    if type(value) is not dict or not required <= value.keys() <= required.union(optional):
        raise ValueError('Unexpected or missing Tribunal fields')


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or CREDENTIAL.search(value):
        raise ValueError('Invalid Tribunal identifier')
    validate_shareable_text(value)


def _digest(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise ValueError('Expected lowercase SHA-256 digest')


def _text(value, limit=MAX_SUMMARY):
    if (not isinstance(value, str) or not 1 <= len(value) <= limit or value != value.strip()
            or not value.isprintable() or CREDENTIAL.search(value)):
        raise ValueError('Expected a bounded, printable, credential-free summary')


def _public_summary(value):
    _text(value)
    validate_shareable_text(value)


def _at(value):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise ValueError('Expected UTC timestamp with seconds')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _choice(value, options):
    if not isinstance(value, str) or value not in options:
        raise ValueError(f'Expected one of {", ".join(options)}')


def _ids(values, minimum, maximum):
    if not isinstance(values, list) or not minimum <= len(values) <= maximum:
        raise ValueError('Invalid number of identifiers')
    for value in values:
        _id(value)
    if len(values) != len(set(values)):
        raise ValueError('Duplicate identifiers')


def _hash(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def empty():
    return {'schema_version': 1, 'reviews': {}, 'history': []}


def _sealed(review, round_name):
    return len(review['rounds'][round_name]) == len(review['providers'])


def _make_packet(review, provider, round_name):
    _id(provider)
    _choice(round_name, ROUNDS)
    if provider not in review['providers']:
        raise ValueError('Unknown Tribunal reviewer')
    peers = []
    if round_name == 'critique':
        if not _sealed(review, 'proposal'):
            raise ValueError('All proposal slots must be accounted for before cross-critique')
        for name in review['providers']:
            submission = review['rounds']['proposal'][name]
            peers.append({key: submission[key] for key in ('provider', 'status', 'summary')})
    payload = {'schema_version': 1, 'review_id': review['id'], 'provider': provider,
               'round': round_name, 'source_sha256': review['source_sha256'],
               'summary': review['summary'], 'proposals': peers}
    return {**payload, 'packet_sha256': _hash(payload)}


def validate_packet(payload):
    """Validate the exact public wire format and its canonical, unkeyed digest."""
    _fields(payload, {'schema_version', 'review_id', 'provider', 'round', 'source_sha256',
                      'summary', 'proposals', 'packet_sha256'})
    if type(payload['schema_version']) is not int or payload['schema_version'] != 1:
        raise ValueError('Unsupported Tribunal packet version')
    for key in ('review_id', 'provider'):
        _id(payload[key])
    _choice(payload['round'], ROUNDS)
    _digest(payload['source_sha256'])
    _public_summary(payload['summary'])
    _digest(payload['packet_sha256'])
    peers = payload['proposals']
    if not isinstance(peers, list) or len(peers) > MAX_PROVIDERS:
        raise ValueError('Invalid proposal list')
    names = []
    for peer in peers:
        _fields(peer, {'provider', 'status', 'summary'})
        _id(peer['provider'])
        _choice(peer['status'], ('received', 'unavailable'))
        _public_summary(peer['summary'])
        names.append(peer['provider'])
    if payload['round'] == 'proposal' and peers:
        raise ValueError('Independent packet must omit all reviewer responses')
    if payload['round'] == 'critique':
        _ids(names, 2, MAX_PROVIDERS)
        if payload['provider'] not in names:
            raise ValueError('Incomplete proposal roster')
    if _hash({k: v for k, v in payload.items() if k != 'packet_sha256'}) != payload['packet_sha256']:
        raise ValueError('Tribunal packet digest mismatch')


def _open(event):
    if event['shareable'] is not True:
        raise ValueError('Explicit shareable summary review required')
    _public_summary(event['summary'])
    _digest(event['source_sha256'])
    providers = event.get('providers', list(DEFAULT_PROVIDERS))
    _ids(providers, 2, MAX_PROVIDERS)
    owner = event.get('owner', providers[0])
    _id(owner)
    if owner not in providers or 'user' in providers:
        raise ValueError('Synthesis needs a rostered reviewer distinct from the final user')
    risk = event.get('risk', 'normal')
    _choice(risk, ('normal', 'high'))
    roles = event.get('roles', {name: DEFAULT_ROLES.get(name, f'Reviewer {index + 1}')
                                for index, name in enumerate(providers)})
    _fields(roles, set(providers))
    for role in roles.values():
        _text(role, 80)
    if len({role.casefold() for role in roles.values()}) != len(providers):
        raise ValueError('Reviewers require distinct named roles')
    return {'id': event['review_id'], 'opened_at': event['at'], 'summary': event['summary'],
            'source_sha256': event['source_sha256'], 'providers': providers, 'roles': roles,
            'owner': owner, 'risk': risk, 'rounds': {r: {} for r in ROUNDS},
            'disputes': {}, 'evidence': {}, 'synthesis': None, 'decision': None}


def _response(review, event):
    if event['shareable'] is not True:
        raise ValueError('Explicit shareable response summary review required')
    _public_summary(event['summary'])
    _choice(event['status'], ('received', 'unavailable'))
    packet = _make_packet(review, event['provider'], event['round'])
    if event['packet_sha256'] != packet['packet_sha256']:
        raise ValueError('Response refers to a stale or different provider packet')
    slots = review['rounds'][event['round']]
    if event['provider'] in slots:
        raise ValueError('Reviewer slot already recorded')
    if 'receipt' in event:
        validate_receipt(event['receipt'], event)
    summary = {k: v for k, v in event.items() if k != 'receipt'}
    attribution = 'operator-reported' if 'receipt' in event else 'operator-reported-summary'
    slots[event['provider']] = {**summary, 'source_sha256': review['source_sha256'],
                               'attribution': attribution}


def _dispute(review, event):
    _ids(event['providers'], 2, MAX_PROVIDERS)
    if not _sealed(review, 'proposal'):
        raise ValueError('Independent proposal round still open')
    for provider in event['providers']:
        if not any(review['rounds'][r].get(provider, {}).get('status') == 'received' for r in ROUNDS):
            raise ValueError('Disagreement requires actual received contributions')
    review['disputes'][event['event_id']] = {**event, 'resolution': None}


def _evidence(review, event):
    _digest(event['source_sha256'])
    if review['source_sha256'] != event['source_sha256']:
        raise ValueError('Observation is for a different source revision')
    _id(event['verifier'])
    if event['verifier'] in review['providers']:
        raise ValueError('Evidence verifier must be independent of the review roster')
    _choice(event['risk'], ('normal', 'high'))
    _choice(event['test_kind'], ('positive', 'negative'))
    _choice(event['status'], ('observed', 'reported', 'not-run'))
    _choice(event['outcome'], ('pass', 'fail', 'unknown'))
    if event['status'] == 'observed':
        _digest(event['artifact_sha256'])
        _choice(event['outcome'], ('pass', 'fail'))
    elif event['artifact_sha256'] is not None or (event['status'] == 'not-run' and event['outcome'] != 'unknown'):
        raise ValueError('Unobserved evidence cannot bind an inspected artifact or unrun result')
    check_id = event.get('check_id', event.get('supersedes', event['event_id']))
    _id(check_id)
    if 'supersedes' in event:
        _id(event['supersedes'])
        prior = review['evidence'].get(event['supersedes'])
        if (prior is None or prior['superseded_by'] is not None or prior['check_id'] != check_id
                or event['status'] != 'observed'
                or any(prior[k] != event[k] for k in ('verifier', 'test_kind', 'risk'))):
            raise ValueError('Retest requires a corresponding current evidence record and observation')
        prior['superseded_by'] = event['event_id']
    review['evidence'][event['event_id']] = {**event, 'check_id': check_id, 'superseded_by': None}


def _active_observed(review, evidence_id):
    observation = review['evidence'].get(evidence_id)
    return observation and observation['status'] == 'observed' and observation['superseded_by'] is None


def _resolved(review, dispute):
    record = dispute['resolution']
    return record is not None and all(_active_observed(review, key) for key in record['evidence_ids'])


def _resolve(review, event):
    _id(event['dispute_id'])
    dispute = review['disputes'].get(event['dispute_id'])
    if dispute is None or _resolved(review, dispute):
        raise ValueError('Expected an open disagreement')
    _ids(event['evidence_ids'], 1, 16)
    if not all(_active_observed(review, key) for key in event['evidence_ids']):
        raise ValueError('Resolution requires current observed evidence from this review')
    dispute['resolution'] = event


def _blockers(review):
    reasons = []
    for round_name in ROUNDS:
        if not _sealed(review, round_name):
            reasons.append(f'pending-{round_name}')
    proposals = {p for p, row in review['rounds']['proposal'].items() if row['status'] == 'received'}
    critiques = {p for p, row in review['rounds']['critique'].items() if row['status'] == 'received'}
    if not proposals:
        reasons.append('no-received-proposals')
    if not any(p != c for p in proposals for c in critiques):
        reasons.append('no-received-peer-critique')
    observations = [row for row in review['evidence'].values() if row['superseded_by'] is None]
    passes = [row for row in observations if row['status'] == 'observed' and row['outcome'] == 'pass']
    if not any(row['test_kind'] == 'positive' for row in passes):
        reasons.append('missing-observed-positive')
    high = review['risk'] == 'high' or any(row['risk'] == 'high' for row in observations)
    if high and not any(row['test_kind'] == 'negative' and row['risk'] == 'high' for row in passes):
        reasons.append('missing-observed-high-risk-negative')
    for row in observations:
        if row['outcome'] == 'fail':
            reasons.append(f"unresolved-failure/{row['event_id']}")
    for identifier, dispute in review['disputes'].items():
        if not _resolved(review, dispute):
            reasons.append(f'unresolved-dispute/{identifier}')
    return reasons


BASE = {'op', 'event_id', 'review_id', 'at', 'summary'}
EVENTS = {
    'open': ({'source_sha256', 'shareable'}, {'providers', 'owner', 'risk', 'roles'}),
    'response': ({'provider', 'round', 'status', 'packet_sha256', 'shareable'}, {'receipt'}),
    'dispute': ({'providers'}, set()),
    'evidence': ({'source_sha256', 'verifier', 'artifact_sha256', 'status', 'outcome', 'risk', 'test_kind'},
                 {'supersedes', 'check_id'}),
    'resolve': ({'dispute_id', 'evidence_ids'}, set()),
    'synthesize': ({'owner', 'next_action'}, set()),
    'decide': ({'actor', 'decision'}, set()),
}


def _append(state, event):
    if type(event) is not dict:
        raise ValueError('Expected a Tribunal event')
    op = event.get('op')
    _choice(op, EVENTS)
    required, optional = EVENTS[op]
    _fields(event, BASE | required, optional)
    _id(event['event_id'])
    _id(event['review_id'])
    _text(event['summary'])
    now = _at(event['at'])
    review = state['reviews'].get(event['review_id'])
    if op == 'open':
        if review is not None:
            raise ValueError('Duplicate Tribunal review ID')
        state['reviews'][event['review_id']] = _open(event)
    else:
        if review is None or review['decision'] is not None:
            raise ValueError('Review does not exist or has a recorded user decision')
        # Independent replies can be received in one order and entered in another.
        earliest = _at(review['last_at'])
        if op == 'response':
            earliest = _at(review['opened_at'])
            if event['round'] == 'critique' and _sealed(review, 'proposal'):
                earliest = max(_at(row['at']) for row in review['rounds']['proposal'].values())
        if now < earliest:
            raise ValueError('Event predates its review prerequisites')
        if op == 'response':
            _response(review, event)
        elif op == 'dispute':
            _dispute(review, event)
        elif op == 'evidence':
            _evidence(review, event)
        elif op == 'resolve':
            _resolve(review, event)
        elif op == 'synthesize':
            if review['synthesis'] is not None or event['owner'] != review['owner']:
                raise ValueError('A fresh synthesis from the assigned owner is required')
            if not _sealed(review, 'critique'):
                raise ValueError('Both rounds must account for every reviewer before synthesis')
            _text(event['next_action'])
            review['synthesis'] = {**event, 'blockers': _blockers(review)}
        elif op == 'decide':
            _choice(event['decision'], ('accept', 'revise', 'defer', 'reject'))
            if event['actor'] != 'user' or review['synthesis'] is None:
                raise ValueError('Explicit user decision and a current synthesis are required')
            if event['decision'] == 'accept' and _blockers(review):
                raise ValueError('Cannot accept with unresolved evidence or disagreement')
            review['decision'] = event
        if op not in ('synthesize', 'decide'):
            review['synthesis'] = None  # Earlier draft remains in the journal.
    if review is None or now >= _at(review['last_at']):
        state['reviews'][event['review_id']]['last_at'] = event['at']
    state['history'].append(event)


def _replay(state):
    _fields(state, {'schema_version', 'reviews', 'history'})
    if (type(state['schema_version']) is not int or state['schema_version'] != 1
            or type(state['reviews']) is not dict or not isinstance(state['history'], list)
            or len(state['history']) > MAX_EVENTS):
        raise ValueError('Invalid Tribunal state')
    rebuilt = empty()
    known = {}
    for row in state['history']:
        event = deepcopy(row)
        _append(rebuilt, event)
        if event['event_id'] in known:
            raise ValueError('Duplicate event in Tribunal history')
        known[event['event_id']] = event
    if rebuilt['reviews'] != state['reviews']:
        raise ValueError('Stored review projection disagrees with its event history')
    return rebuilt, known


def apply(state, event):
    """Return detached state. Replaying the same event ID and content is a no-op."""
    result, known = _replay(state)
    if not isinstance(event, dict):
        raise ValueError('Expected a Tribunal event')
    _id(event.get('event_id'))
    prior = known.get(event['event_id'])
    if prior is not None:
        if prior != event or _hash(prior) != _hash(event):
            raise ValueError('Event ID reused with different content')
        return result
    if len(known) >= MAX_EVENTS:
        raise ValueError('Tribunal journal capacity reached')
    _append(result, deepcopy(event))
    return result


def _read_review(state, review_id):
    _id(review_id)
    rebuilt, _ = _replay(state)
    if review_id not in rebuilt['reviews']:
        raise ValueError('Unknown Tribunal review')
    return rebuilt['reviews'][review_id], rebuilt['history']


def packet(state, review_id, provider, round):
    """Return exactly the manually approved public summaries bound to this packet."""
    review, _ = _read_review(state, review_id)
    return _make_packet(review, provider, round)


def handoff(state, review_id):
    """Return local audit history, reviewer availability and outstanding evidence."""
    review, history = _read_review(state, review_id)
    return {'schema_version': 1, 'review': review, 'blockers': _blockers(review),
            'history': [event for event in history if event['review_id'] == review_id]}
