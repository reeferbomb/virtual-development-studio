import hashlib
import json
import unittest
from copy import deepcopy

from command_center import tribunal, tribunal_relay


SOURCE = hashlib.sha256(b'original player interaction').hexdigest()
OUTPUT = hashlib.sha256(b'independently inspected result').hexdigest()
AT = '2026-11-22T09:00:00Z'


def event(op, event_id, **values):
    return {'op': op, 'event_id': event_id, 'review_id': 'crossing', 'at': AT,
            'summary': 'Reviewed dispatch yard observation.', **values}


def opened(**values):
    fields = {'providers': ['alpha', 'reviewer-b'], 'source_sha256': SOURCE, 'shareable': True, **values}
    return tribunal.apply(tribunal.empty(), event('open', 'opened', **fields))


def respond(state, provider, round_name, status='received', **values):
    packet = tribunal.packet(state, 'crossing', provider, round_name)
    fields = {'provider': provider, 'round': round_name, 'status': status, 'shareable': True,
              'packet_sha256': packet['packet_sha256'], **values}
    return tribunal.apply(state, event('response', f'{provider}-{round_name}', **fields))


def rounds(**values):
    state = opened(**values)
    for phase in ('proposal', 'critique'):
        for provider in state['reviews']['crossing']['providers']:
            state = respond(state, provider, phase)
    return state


def evidence(identifier, **values):
    fields = {'verifier': 'independent-qa', 'source_sha256': SOURCE, 'artifact_sha256': OUTPUT,
              'test_kind': 'positive', 'risk': 'normal', 'status': 'observed', 'outcome': 'pass', **values}
    return event('evidence', identifier, **fields)


def synth(identifier='synth', **values):
    return event('synthesize', identifier, owner='alpha', next_action='Inspect the route at the crossing.', **values)


def decide(decision='accept', actor='user'):
    return event('decide', 'decision', actor=actor, decision=decision)


class TribunalTests(unittest.TestCase):
    def test_round_sealing_blind_proposals_and_stable_packets(self):
        state = opened()
        initial = tribunal.packet(state, 'crossing', 'reviewer-b', 'proposal')
        state = respond(state, 'alpha', 'proposal', summary='Consider an alternate route.')
        self.assertEqual(initial, tribunal.packet(state, 'crossing', 'reviewer-b', 'proposal'))
        self.assertEqual(initial['proposals'], [])
        with self.assertRaises(ValueError):
            tribunal.packet(state, 'crossing', 'alpha', 'critique')
        state = respond(state, 'reviewer-b', 'proposal', 'unavailable', summary='No browser access.')
        cross = tribunal.packet(state, 'crossing', 'alpha', 'critique')
        tribunal.validate_packet(cross)
        self.assertEqual(cross['proposals'], [
            {'provider': 'alpha', 'status': 'received', 'summary': 'Consider an alternate route.'},
            {'provider': 'reviewer-b', 'status': 'unavailable', 'summary': 'No browser access.'}])
        state = respond(state, 'alpha', 'critique', summary='Critique stays out of peer packets.')
        self.assertEqual(cross, tribunal.packet(state, 'crossing', 'alpha', 'critique'))
        self.assertNotIn('Critique stays out', repr(tribunal.packet(state, 'crossing', 'reviewer-b', 'critique')))
        self.assertNotIn('receipt', cross)
        with self.assertRaises(ValueError):
            tribunal.apply(state, event('dispute', 'disagreement', providers=['alpha', 'reviewer-b']))

    def test_schema_privacy_and_source_packet_binding(self):
        state = opened()
        initial = tribunal.packet(state, 'crossing', 'alpha', 'proposal')
        unsigned = {key: value for key, value in initial.items() if key != 'packet_sha256'}
        canonical = json.dumps(unsigned, separators=(',', ':'), sort_keys=True, ensure_ascii=False).encode()
        self.assertEqual(initial['packet_sha256'], hashlib.sha256(canonical).hexdigest())
        for changes in ({'shareable': 1}, {'summary': 'token\nraw output'},
                        {'summary': 'Authorization: Bearer sample-value'}, {'raw_log': 'text'},
                        {'summary': 'Refer to /workspace/private/source.txt.'},
                        {'risk': []}, {'providers': ['alpha', 'alpha']}, {'providers': ['alpha', 'user']},
                        {'roles': {'alpha': 'Same', 'reviewer-b': 'same'}}, {'at': '2026-02-30T09:00:00Z'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                opened(**changes)
        for changes in ({'status': 'simulated'}, {'packet_sha256': 'b' * 64},
                        {'packet_sha256': initial['packet_sha256']}, {'shareable': False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                respond(state, 'reviewer-b', 'proposal', **changes)
        for changes in ({'schema_version': True}, {'summary': 'Changed'}, {'proposals': ['text']},
                        {'attachments': []}, {'round': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tribunal.validate_packet({**initial, **changes})

    def test_independent_receipts_can_be_entered_out_of_order(self):
        state = respond(opened(), 'alpha', 'proposal', at='2026-11-22T09:02:00Z')
        state = respond(state, 'reviewer-b', 'proposal', at='2026-11-22T09:01:00Z')
        self.assertEqual(state['reviews']['crossing']['last_at'], '2026-11-22T09:02:00Z')
        with self.assertRaises(ValueError):
            respond(state, 'alpha', 'critique', at='2026-11-22T09:01:59Z')
        state = respond(state, 'alpha', 'critique', at='2026-11-22T09:04:00Z')
        state = respond(state, 'reviewer-b', 'critique', at='2026-11-22T09:03:00Z')
        with self.assertRaises(ValueError):
            tribunal.apply(state, {**synth(), 'at': '2026-11-22T09:03:30Z'})

    def test_private_receipt_attached_once_and_withheld_from_peer_packet(self):
        state = opened()
        packet = tribunal.packet(state, 'crossing', 'alpha', 'proposal')
        request = tribunal_relay.prepare_request(packet, confirmed=True)
        form = {**request['response_template'], 'at': AT, 'provenance': 'Operator supplied manual reply.',
                'response_text': 'Private original reply.\nInternal explanation.', 'summary': 'Review only the crossing.'}
        imported = tribunal_relay.import_response(packet, form, event_id='reply', confirmed=True)
        state = tribunal.apply(state, imported['event'])
        response = state['reviews']['crossing']['rounds']['proposal']['alpha']
        self.assertEqual(response['attribution'], 'operator-reported')
        self.assertNotIn('receipt', response)
        self.assertEqual(state['history'][-1]['receipt'], imported['receipt'])
        state = respond(state, 'reviewer-b', 'proposal')
        self.assertEqual(state['reviews']['crossing']['rounds']['proposal']['reviewer-b']['attribution'],
                         'operator-reported-summary')
        cross = tribunal.packet(state, 'crossing', 'reviewer-b', 'critique')
        self.assertIn(form['summary'], repr(cross))
        for private in ('Private original reply', form['provenance'], imported['receipt']['response_sha256']):
            self.assertNotIn(private, repr(cross))
        for changes in ({'response_text': 'Falsified.'}, {'provider': 'reviewer-b'}, {'summary': 'Mismatch.'}):
            malformed = {**imported['event'], 'receipt': {**imported['receipt'], **changes}}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tribunal.apply(opened(), malformed)

    def test_default_roles_and_local_handoff(self):
        seed = event('open', 'one', source_sha256=SOURCE, shareable=True)
        state = tribunal.apply(tribunal.empty(), seed)
        state = tribunal.apply(state, {**seed, 'event_id': 'two', 'review_id': 'secondary'})
        handoff = tribunal.handoff(state, 'crossing')
        review = handoff['review']
        self.assertEqual(review['providers'], ['chatgpt', 'claude', 'gemini'])
        self.assertEqual(review['owner'], 'chatgpt')
        self.assertEqual(len(set(review['roles'].values())), 3)
        self.assertEqual(handoff['history'], [seed])
        self.assertIsNone(review['decision'])
        self.assertIn('pending-proposal', handoff['blockers'])
        handoff['review']['providers'].clear()
        self.assertEqual(len(state['reviews']['crossing']['providers']), 3)

    def test_retries_collisions_and_input_isolation(self):
        state = opened()
        original = deepcopy(state)
        row = evidence('check')
        result = tribunal.apply(state, row)
        retry = tribunal.apply(result, dict(row))
        self.assertEqual(retry, result)
        self.assertEqual(state, original)
        row['summary'] = 'Changed outside.'
        self.assertNotEqual(row['summary'], result['history'][-1]['summary'])
        retry['history'].clear()
        self.assertEqual(len(result['history']), 2)
        with self.assertRaises(ValueError):
            tribunal.apply(result, row)
        with self.assertRaises(ValueError):
            tribunal.apply(state, {**state['history'][0], 'shareable': 1})
        malformed = deepcopy(state)
        malformed['reviews']['crossing']['risk'] = 'high'
        with self.assertRaises(ValueError):
            tribunal.packet(malformed, 'crossing', 'alpha', 'proposal')

    def test_reported_unrun_and_unbound_claims_cannot_pass(self):
        state = rounds()
        for row in (evidence('stale', source_sha256='1' * 64), evidence('self', verifier='alpha'),
                    evidence('no-proof', artifact_sha256=None), evidence('claimed-proof', status='reported'),
                    evidence('did-not-run', status='not-run', artifact_sha256=None)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                tribunal.apply(state, row)
        for status, outcome in [('reported', 'pass'), ('not-run', 'unknown')]:
            state = tribunal.apply(state, evidence(status, status=status, outcome=outcome, artifact_sha256=None))
        state = tribunal.apply(state, synth())
        self.assertIn('missing-observed-positive', tribunal.handoff(state, 'crossing')['blockers'])
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide())
        decided = tribunal.apply(state, decide('defer'))
        self.assertEqual(decided['reviews']['crossing']['decision']['decision'], 'defer')
        with self.assertRaises(ValueError):
            tribunal.apply(decided, evidence('late'))

    def test_disagreement_retest_and_fresh_synthesis(self):
        state = rounds(risk='high')
        dispute = event('dispute', 'routing', providers=['alpha', 'reviewer-b'])
        state = tribunal.apply(state, dispute)
        state = tribunal.apply(state, evidence('initial', outcome='fail', check_id='routing-check'))
        state = tribunal.apply(state, evidence('heard', status='reported', artifact_sha256=None))
        state = tribunal.apply(state, evidence('negative', risk='high', test_kind='negative'))
        resolve = event('resolve', 'resolution', dispute_id='routing', evidence_ids=['initial'])
        for ids in ([], ['unknown'], ['heard']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                tribunal.apply(state, {**resolve, 'evidence_ids': ids})
        state = tribunal.apply(state, resolve)
        state = tribunal.apply(state, synth())
        before = tribunal.handoff(state, 'crossing')['blockers']
        self.assertIn('unresolved-failure/initial', before)
        self.assertNotIn('unresolved-dispute/routing', before)
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide())
        retest = evidence('recheck', supersedes='initial', check_id='routing-check')
        for changes in ({'check_id': 'another-check'}, {'verifier': 'other-qa'}, {'test_kind': 'negative'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                tribunal.apply(state, {**retest, **changes})
        state = tribunal.apply(state, retest)
        self.assertIsNone(state['reviews']['crossing']['synthesis'])
        self.assertIn('unresolved-dispute/routing', tribunal.handoff(state, 'crossing')['blockers'])
        state = tribunal.apply(state, {**resolve, 'event_id': 'resolved-again', 'evidence_ids': ['recheck']})
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide())
        state = tribunal.apply(state, synth('final-synthesis'))
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide(actor='alpha'))
        state = tribunal.apply(state, decide())
        handoff = tribunal.handoff(state, 'crossing')
        self.assertEqual(handoff['blockers'], [])
        self.assertEqual(handoff['review']['evidence']['initial']['superseded_by'], 'recheck')
        self.assertEqual(handoff['review']['decision']['actor'], 'user')
        self.assertEqual([row['event_id'] for row in handoff['history'] if row['op'] == 'synthesize'],
                         ['synth', 'final-synthesis'])

    def test_high_risk_change_needs_observed_high_risk_negative(self):
        state = tribunal.apply(rounds(risk='high'), evidence('positive'))
        state = tribunal.apply(state, evidence('wrong-scope', test_kind='negative'))
        state = tribunal.apply(state, evidence('unrun', test_kind='negative', risk='high', status='not-run',
                                               outcome='unknown', artifact_sha256=None))
        with self.assertRaises(ValueError):
            tribunal.apply(state, {**synth(), 'owner': 'reviewer-b'})
        state = tribunal.apply(state, synth())
        self.assertEqual(tribunal.handoff(state, 'crossing')['blockers'], ['missing-observed-high-risk-negative'])
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide())

    def test_unavailable_has_no_inferred_contribution(self):
        state = opened()
        for phase in ('proposal', 'critique'):
            for provider in ('alpha', 'reviewer-b'):
                state = respond(state, provider, phase, 'unavailable')
        state = tribunal.apply(state, evidence('positive'))
        state = tribunal.apply(state, synth())
        self.assertEqual(tribunal.handoff(state, 'crossing')['blockers'],
                         ['no-received-proposals', 'no-received-peer-critique'])
        with self.assertRaises(ValueError):
            tribunal.apply(state, decide())
        state = tribunal.apply(state, decide('revise'))
        self.assertEqual(state['reviews']['crossing']['decision']['decision'], 'revise')


if __name__ == '__main__':
    unittest.main()
