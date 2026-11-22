"""Private, local cross-chat registry and Tribunal command-line coordinator."""

import argparse
import json
import math
from pathlib import Path
import sys

from . import admin_registry, admin_store, tribunal, tribunal_relay, admin_lineage


def _json(path):
    """Bounded strict JSON input; never execute or expand packet contents."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key.')
            result[key] = value
        return result

    def invalid(_):
        raise ValueError('Nonfinite JSON value.')

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('Nonfinite JSON value.')
        return result

    with Path(path).open('rb') as handle:
        data = handle.read(1_048_577)
    if len(data) > 1_048_576:
        raise ValueError('JSON input exceeds 1 MiB.')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)


def replay(journal):
    """Replay both event streams; every mutation is validated before persistence."""
    registry = admin_registry.empty()
    reviews = tribunal.empty()
    for row in journal['events']:
        if row['stream'] == 'registry':
            registry = admin_registry.apply(registry, row['event'])
        elif row['stream'] == 'tribunal':
            reviews = tribunal.apply(reviews, row['event'])
        else:
            raise ValueError('Unknown journal stream.')
    return {'revision': journal['revision'], 'registry': registry, 'tribunal': reviews}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--journal', type=Path, help='private JSON journal outside the repository')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('state', help='Read validated project and review history')
    add = sub.add_parser('append', help='Validate and append one JSON event')
    add.add_argument('stream', choices=('registry', 'tribunal'))
    add.add_argument('event', type=Path)
    add.add_argument('--revision', required=True, type=int)
    h = sub.add_parser('handoff', help='Export a same-project regular Chat continuation packet')
    h.add_argument('project')
    h.add_argument('checkpoint')
    t = sub.add_parser('review-handoff', help='Export the private review history and decision')
    t.add_argument('review')
    packet = sub.add_parser('packet', help='Generate a deliberately shareable review packet')
    packet.add_argument('review')
    packet.add_argument('provider')
    packet.add_argument('round', choices=('proposal', 'critique'))
    relay = sub.add_parser('relay', help='Prepare a copy/paste browser relay; does not send data')
    relay.add_argument('packet', type=Path)
    relay.add_argument('--share-confirmed', action='store_true')
    receive = sub.add_parser('receive', help='Import a real manually returned provider response')
    receive.add_argument('packet', type=Path)
    receive.add_argument('response', type=Path)
    receive.add_argument('--event-id', required=True)
    receive.add_argument('--revision', required=True, type=int)
    receive.add_argument('--share-confirmed', action='store_true')
    provider = sub.add_parser('provider', help='Show explicitly declared manual provider availability')
    provider.add_argument('provider')
    provider.add_argument('--status', default='unknown')
    git = sub.add_parser('fingerprint-git', help='Read local Git source identity without touching it')
    git.add_argument('repo', type=Path)
    git.add_argument('project')
    git.add_argument('version')
    archive = sub.add_parser('fingerprint-file', help='Hash an archive or evidence file without extracting it')
    archive.add_argument('path', type=Path)
    archive.add_argument('project')
    archive.add_argument('version')
    compare = sub.add_parser('compare', help='Compare private fingerprint JSON files; version labels are not ancestry')
    compare.add_argument('base', type=Path)
    compare.add_argument('candidate', type=Path)
    compare.add_argument('--repo', type=Path, help='optional local repository containing both commits')
    sub.add_parser('chat-capability', help='Report chat creation and fullness availability honestly')
    return p


def run(args):
    action = args.action
    if action == 'provider':
        return tribunal_relay.availability(args.provider, args.status)
    if action == 'relay':
        return tribunal_relay.prepare_request(_json(args.packet), confirmed=args.share_confirmed)
    if action == 'fingerprint-git':
        return admin_lineage.capture_git(args.repo, args.project, args.version)
    if action == 'fingerprint-file':
        return admin_lineage.fingerprint_archive(args.path, args.project, args.version)
    if action == 'compare':
        base, candidate = _json(args.base), _json(args.candidate)
        ancestry = 'unknown'
        if args.repo and base.get('commit') and candidate.get('commit'):
            ancestry = admin_lineage.git_ancestry(args.repo, base['commit'], candidate['commit'])
        return admin_lineage.compare_sources(base, candidate, ancestry)
    if action == 'chat-capability':
        return {'creation': 'manual', 'fullness': 'unknown', 'default_mode': 'regular',
                'same_project': True, 'automatic_deletion': False,
                'reason': 'No authenticated chat creation or fullness adapter is configured. Record verified receipts manually.'}
    if args.journal is None:
        raise ValueError('--journal is required for this command.')
    if action == 'append':
        return replay(admin_store.append(args.journal, args.revision, args.stream, _json(args.event), validator=replay))
    if action == 'receive':
        imported = tribunal_relay.import_response(_json(args.packet), _json(args.response),
                                                  event_id=args.event_id, confirmed=args.share_confirmed)
        return replay(admin_store.append(args.journal, args.revision, 'tribunal', imported['event'], validator=replay))
    state = replay(admin_store.load(args.journal, validator=replay))
    if action == 'state':
        return state
    if action == 'handoff':
        return admin_registry.handoff(state['registry'], args.project, args.checkpoint)
    if action == 'review-handoff':
        return tribunal.handoff(state['tribunal'], args.review)
    if action == 'packet':
        return tribunal.packet(state['tribunal'], args.review, args.provider, args.round)
    raise ValueError('Unknown command.')


def main(argv=None):
    try:
        result = run(parser().parse_args(argv))
        print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as exc:
        # Keep rejected material private; exact validation details remain local.
        reason = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        print(json.dumps({'status': 'rejected', 'reason': reason}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
