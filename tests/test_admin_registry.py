from copy import deepcopy
import json
import unittest

from command_center.admin_registry import apply, empty, handoff
from command_center.provenance import spec_digest


def event(kind, project='yard', **values):
    return dict(type=kind, project_id=project, **values)


def project(name='yard'):
    return event('project', name, name='Synthetic ' + name,
                 source=dict(commit='1' * 40, release_ref='synthetic-release', library_ref=None,
                             sha256='2' * 64, dirty=False), environment={'engine': 'synthetic-v1'})


def log(identifier='l1', chat='source-chat', complete=True, owner='yard'):
    return event('log', owner, log_id=identifier, chat_id=chat, ref='fixture-' + identifier, sha256='3' * 64,
                 complete=complete)


def result_row(identifier='accept', kind='positive', evidence='observed', result='pass'):
    raw = {'ref': 'fixture-output-' + identifier, 'sha256': '4' * 64} if evidence == 'observed' else None
    return dict(id=identifier, criterion_id='delivery', kind=kind, evidence=evidence, result=result, raw=raw)


def checkpoint(identifier='first', **changes):
    values = dict(checkpoint_id=identifier, summary='Original synthetic dock session.',
                  log_ids=['l1'], criteria=[dict(id='delivery', description='Credit one delivery.', high_risk=True)],
                  tests=[result_row(), result_row('duplicate', 'negative')], pending=['Check a second dock.'], gaps=[])
    values.update(changes)
    return event('checkpoint', **values)


def reduce_events(*events):
    state = empty()
    for item in events:
        state = apply(state, item)
    return state


def request(checkpoint_id='first', reason='user-request'):
    return event('request', checkpoint_id=checkpoint_id, reason=reason, detail='Synthetic explicit request.')


def receipt(state, checkpoint_id='first', chat_id='new-chat'):
    return event('receipt', checkpoint_id=checkpoint_id, chat_id=chat_id, actual_project_id='yard', mode='regular',
                 ref='synthetic-creation-receipt', packet_sha256=handoff(state, 'yard', checkpoint_id)['packet_sha256'])


class RegistryTests(unittest.TestCase):
    def test_handoff_reproducible_detached_digest_and_default_regular_same_project(self):
        p, c = project(), checkpoint()
        state = reduce_events(p, log(), c)
        snapshot = deepcopy(state)
        result = handoff(state, 'yard', 'first')
        self.assertEqual(result, handoff(state, 'yard', 'first'))
        self.assertEqual(result['target'], {'project_id': 'yard', 'mode': 'regular', 'fullness': 'unknown'})
        self.assertEqual(result['packet_sha256'], spec_digest({k: v for k, v in result.items() if k != 'packet_sha256'}))
        self.assertEqual(result['acceptance'][0]['status'], 'verified')
        self.assertEqual(result['logs'][0]['sha256'], '3' * 64)
        result['tests'][0]['raw']['sha256'] = 'f' * 64
        p['source']['sha256'] = '9' * 64
        c['tests'].clear()
        self.assertEqual(state, snapshot)
        self.assertEqual(state['projects']['yard']['continuations'], {})

    def test_foreign_chat_logs_and_unselected_transcripts_excluded(self):
        state = reduce_events(project(), project('other'), log(), log('side', 'side-chat'),
                              log('private-log', 'other-chat', owner='other'), checkpoint())
        self.assertEqual([l['log_id'] for l in handoff(state, 'yard', 'first')['logs']], ['l1'])
        with self.assertRaises(ValueError):
            apply(state, checkpoint('bad', log_ids=['private-log']))
        with self.assertRaises(ValueError):
            apply(state, log('stolen', 'other-chat'))
        with self.assertRaises(ValueError):
            handoff(state, 'other', 'first')

    def test_no_or_incomplete_logs_explicit_as_gaps_and_checkpoint_snapshot_does_not_drift(self):
        state = reduce_events(project(), log(complete=False), checkpoint(log_ids=[]), checkpoint('second'))
        self.assertIn('No project transcript', handoff(state, 'yard', 'first')['gaps'][0])
        original = handoff(state, 'yard', 'second')
        self.assertIn('incomplete', original['gaps'][0])
        state = apply(state, log('complete', 'source-chat', True))
        self.assertEqual(handoff(state, 'yard', 'second'), original)

    def test_append_only_decisions_preserve_status_reason_order_and_checkpoint_cutoff(self):
        def decision(identifier, prior=None, status='proposed'):
            return event('decision', decision_id=identifier, decision='Use one dock', rationale='Shared receipt.',
                         status=status, supersedes=prior)
        state = reduce_events(project(), log(), decision('z-first'), checkpoint(), decision('a-next', 'z-first', 'accepted'))
        state = json.loads(json.dumps(state, sort_keys=True))
        later = apply(state, checkpoint('second'))
        historical = handoff(later, 'yard', 'first')
        previous, = historical['decisions']
        self.assertEqual((previous['decision_id'], previous['superseded_by'], previous['status']), ('z-first', None, 'proposed'))
        self.assertEqual(historical['subsequent_decisions'][0]['supersedes'], 'z-first')
        self.assertFalse(historical['freshness']['decisions_match'])
        self.assertEqual(historical['acceptance'][0]['status'], 'stale')
        self.assertTrue(historical['tests'][0]['needs_reverification'])
        chronology = handoff(later, 'yard', 'second')['decisions']
        self.assertEqual([r['decision_id'] for r in chronology], ['z-first', 'a-next'])
        self.assertEqual((chronology[0]['superseded_by'], chronology[1]['rationale']), ('a-next', 'Shared receipt.'))
        for invalid in (decision('z-first'), decision('third', 'z-first'), decision('third', 'absent')):
            with self.assertRaises(ValueError):
                apply(later, invalid)

    def test_reported_and_not_run_do_not_verify_high_risk_even_with_passing_positive(self):
        for extra in [[], [result_row('neg', 'negative', 'reported')], [result_row('neg', 'negative', 'not-run', 'unknown')]]:
            state = reduce_events(project(), log(), checkpoint(tests=[result_row(), *extra]))
            result = handoff(state, 'yard', 'first')['acceptance'][0]
            self.assertEqual((result['status'], result['missing_observed_passes']), ('pending', ['negative']))
        state = reduce_events(project(), log(), checkpoint(tests=[result_row(), result_row('neg', 'negative', result='fail')]))
        self.assertEqual(handoff(state, 'yard', 'first')['acceptance'][0]['status'], 'failed')
        # A bound manual test still outstanding blocks verification even if required positive/negative passes exist.
        c = checkpoint()
        c['tests'].append(result_row('manual', 'positive', 'not-run', 'unknown'))
        self.assertEqual(handoff(reduce_events(project(), log(), c), 'yard', 'first')['acceptance'][0]['status'], 'pending')

    def test_source_or_environment_change_marks_raw_results_stale_preserving_historical_outputs(self):
        state = reduce_events(project(), log(), checkpoint())
        before = handoff(state, 'yard', 'first')
        for source, environment in [
            (dict(before['source'], sha256='b' * 64), before['environment']),
            (dict(before['source'], dirty=True), before['environment']),
            (before['source'], {'engine': 'synthetic-v2'}),
        ]:
            changed = apply(state, event('identity', source=source, environment=environment))
            packet = handoff(changed, 'yard', 'first')
            self.assertEqual(packet['source'], before['source'])
            self.assertNotEqual(packet['packet_sha256'], before['packet_sha256'])
            self.assertEqual(packet['acceptance'][0]['status'], 'stale')
            self.assertTrue(all(not t['valid_for_current_identity'] for t in packet['tests']))
            self.assertEqual(packet['tests'][0]['raw'], before['tests'][0]['raw'])
            self.assertIn('Re-run verification', packet['gaps'][-1])
            self.assertEqual(handoff(state, 'yard', 'first'), before)

    def test_only_explicit_trigger_and_digest_bound_regular_receipt_can_complete_request(self):
        state = reduce_events(project(), log(), checkpoint())
        packet = handoff(state, 'yard', 'first')
        with self.assertRaises(ValueError):
            apply(state, receipt(state))
        with self.assertRaises(ValueError):
            apply(state, request(reason='guessed-fullness'))
        for reason in ('user-request', 'platform-warning'):
            requested = apply(state, request(reason=reason))
            self.assertEqual(handoff(requested, 'yard', 'first'), packet)
            base = receipt(requested)
            for updates in [dict(packet_sha256='0' * 64), dict(actual_project_id='other'), dict(mode='temporary'),
                            dict(chat_id='source-chat'), dict(chat_id='')]:
                with self.assertRaises(ValueError):
                    apply(requested, dict(base, **updates))
            complete = apply(requested, base)
            self.assertEqual(complete['projects']['yard']['continuations']['first']['receipt']['chat_id'], 'new-chat')
            self.assertEqual(handoff(complete, 'yard', 'first'), packet)
            with self.assertRaises(ValueError):
                apply(complete, base)
            with self.assertRaises(ValueError):
                apply(requested, request())

    def test_changed_packet_after_authorization_cannot_receive_an_old_receipt(self):
        state = reduce_events(project(), log(), checkpoint(), request())
        old = receipt(state)
        changed = apply(state, event('identity', source=project()['source'], environment={'engine': 'elsewhere'}))
        for record in (old, receipt(changed)):
            with self.assertRaises(ValueError):
                apply(changed, record)

    def test_proposals_preserve_owner_candidate_and_checkpoint_history_in_project_scope(self):
        first = event('proposal', proposal_id='tuning', owner='Dock Team', source_sha256='a' * 64,
                      candidate_ref='synthetic-candidate', description='Retain the arrival receipt.',
                      status='proposed', supersedes=None)
        revision = dict(first, proposal_id='review', supersedes='tuning', status='under_review')
        state = reduce_events(project(), project('other'), log(), checkpoint('before'))
        empty_packet = handoff(state, 'yard', 'before')
        state = apply(state, dict(first, project_id='other', description='Unrelated private candidate.'))
        self.assertEqual(handoff(state, 'yard', 'before'), empty_packet)
        state = apply(apply(state, first), checkpoint('during'))
        state = apply(apply(state, revision), checkpoint('after'))
        historical = handoff(state, 'yard', 'during')
        self.assertEqual(historical['proposals'][0]['status'], 'proposed')
        self.assertIsNone(historical['proposals'][0]['superseded_by'])
        self.assertEqual(historical['subsequent_proposals'][0]['status'], 'under_review')
        after = handoff(json.loads(json.dumps(state, sort_keys=True)), 'yard', 'after')
        self.assertEqual([p['proposal_id'] for p in after['proposals']], ['tuning', 'review'])
        self.assertEqual(after['proposals'][0]['superseded_by'], 'review')
        self.assertEqual(after['proposals'][1]['source_sha256'], 'a' * 64)
        self.assertEqual(after['proposals'][1]['owner'], 'Dock Team')
        self.assertEqual(after['subsequent_proposals'], [])
        self.assertNotIn('Unrelated private candidate.', json.dumps(after))
        self.assertEqual(after['acceptance'][0]['status'], 'verified')

    def test_proposals_reject_invalid_hash_owner_status_foreign_and_duplicate_supersession(self):
        p = event('proposal', proposal_id='one', owner='architecture', source_sha256='a' * 64,
                  candidate_ref='synthetic-candidate', description='Keep an evidence pointer.',
                  status='proposed', supersedes=None)
        state = reduce_events(project(), project('other'), p)
        for change in [{'source_sha256': 'f' * 63}, {'owner': ' '}, {'owner': 'team\nname'}, {'status': 'released'},
                       {'description': ''}, {'candidate_ref': ''}, {'supersedes': 'one', 'owner': 'other'},
                       {'supersedes': 'one', 'project_id': 'other'}, {'proposal_id': 'one'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                apply(state, dict(p, **{'proposal_id': 'two', **change}))
        for status in ['under_review', 'accepted', 'deferred', 'rejected']:
            updated = apply(state, dict(p, proposal_id='two', status=status, supersedes='one'))
            with self.assertRaises(ValueError):
                apply(updated, dict(p, proposal_id='three', supersedes='one'))

    def test_same_chat_cannot_fulfill_two_requests_or_cross_projects(self):
        state = reduce_events(project(), project('other'), log(), checkpoint(), request())
        state = apply(state, log('new-log', 'new-chat'))  # The actual new chat can be logged before recording its receipt.
        state = apply(state, receipt(state))
        with self.assertRaises(ValueError):
            apply(state, log('elsewhere', 'new-chat', owner='other'))
        state = apply(apply(state, checkpoint('second')), request('second'))
        with self.assertRaises(ValueError):
            apply(state, receipt(state, 'second'))

    def test_no_destructive_events_and_invalid_values_do_not_modify_inputs(self):
        state = reduce_events(project(), log())
        snapshot = deepcopy(state)
        invalid = [event('delete'), project(), log(), checkpoint(log_ids=['l1', 'l1']),
                   checkpoint(tests=[result_row(), result_row()]), checkpoint(criteria=[]),
                   checkpoint(tests=[dict(result_row(), criterion_id='other')]),
                   checkpoint(tests=[dict(result_row(), raw=None)]),
                   checkpoint(tests=[dict(result_row(), evidence='not-run')]),
                   checkpoint(tests=[dict(result_row(), raw={'sha256': False, 'ref': 'example'})]),
                   event('identity', source=dict(project()['source'], dirty=1), environment={'os': 'somewhere'}),
                   event('identity', source=project()['source'], environment={}),
                   event('identity', source=dict(project()['source'], commit='truncated'), environment={'os': 'x'}),
                   dict(project('another'), extra='invalid')]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                apply(state, item)
        self.assertEqual(state, snapshot)
