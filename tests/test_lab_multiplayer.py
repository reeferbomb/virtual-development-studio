"""Protocol observations are computed from inputs and packet delivery order."""

from copy import deepcopy
import unittest

from command_center.lab_multiplayer import EXERCISES, TRACK, assess


def trace():
    return deepcopy(EXERCISES[0]['example'])


def results(submission):
    return {row['id']: row['status'] for row in assess('multiplayer', submission)}


def expected(result, server, client, ack, epoch=1, online=True):
    return dict(result=result, server=server, client=client, ack=ack, epoch=epoch, online=online)


class MultiplayerLabTests(unittest.TestCase):
    def test_reference_is_deterministic_and_public_rubric_matches(self):
        self.assertEqual(TRACK['roles'], ['architecture', 'gameplay', 'verification', 'build_operations'])
        self.assertEqual(TRACK['id'], 'multiplayer')
        self.assertEqual([item['id'] for item in EXERCISES], [TRACK['id']])
        submission = trace()
        original = deepcopy(submission)
        rows = assess('multiplayer', submission)
        self.assertEqual([row['id'] for row in rows], [row['id'] for row in EXERCISES[0]['criteria']])
        self.assertTrue(all(row['status'] == 'pass' and row['detail'] for row in rows))
        self.assertEqual(rows, assess('multiplayer', submission))
        self.assertEqual(original, submission)

    def test_wrong_observation_at_any_step_fails_even_if_final_state_is_correct(self):
        for index, event in enumerate(trace()['events']):
            with self.subTest(index=index, op=event['op']):
                submission = trace()
                submission['events'][index]['expect']['client'] += 1
                self.assertEqual(results(submission)['observations'], 'fail')

    def test_input_variation_grades_an_independent_passing_trace(self):
        submission = trace()
        for event in submission['events']:
            if event['op'] == 'send':
                event['delta'] *= -1
            for field in ('server', 'client'):
                event['expect'][field] *= -1
        self.assertEqual(set(results(submission).values()), {'pass'})

    def test_retry_after_gap_replays_only_unacknowledged_inputs(self):
        events = [
            dict(op='send', actor='owner', seq=1, delta=-2, expect=expected('sent', 0, -2, 0)),
            dict(op='send', actor='owner', seq=2, delta=1, expect=expected('sent', 0, -1, 0)),
            dict(op='deliver', packet=2, expect=expected('out-of-order', 0, -1, 0)),
            dict(op='deliver', packet=1, expect=expected('applied', -2, -1, 1)),
            dict(op='snapshot', expect=expected('snapshot', -2, -1, 1)),
            dict(op='deliver', packet=2, expect=expected('applied', -1, -1, 2)),
            dict(op='snapshot', expect=expected('snapshot', -1, -1, 2)),
        ]
        self.assertEqual(results({'events': events})['observations'], 'pass')
        events[4]['expect']['client'] = -2
        self.assertEqual(results({'events': events})['observations'], 'fail')

    def test_invalid_and_unowned_packets_cannot_advance_the_sequence(self):
        events = [
            dict(op='send', actor='guest', seq=1, delta=1, expect=expected('sent', 0, 0, 0)),
            dict(op='deliver', packet=1, expect=expected('unowned', 0, 0, 0)),
            dict(op='send', actor='owner', seq=1, delta=0, expect=expected('sent', 0, 0, 0)),
            dict(op='deliver', packet=3, expect=expected('invalid', 0, 0, 0)),
            dict(op='send', actor='owner', seq=1, delta=2, expect=expected('sent', 0, 2, 0)),
            dict(op='deliver', packet=5, expect=expected('applied', 2, 2, 1)),
            dict(op='deliver', packet=5, expect=expected('duplicate', 2, 2, 1)),
        ]
        self.assertEqual(results({'events': events})['observations'], 'pass')
        events[-1]['expect']['result'] = 'applied'
        self.assertEqual(results({'events': events})['observations'], 'fail')

    def test_coverage_requires_actual_rejections_reconciliation_and_session_recovery(self):
        events = trace()['events']
        self.assertEqual(set(results({'events': []}).values()), {'fail'})
        simple = [dict(op='snapshot', expect=expected('snapshot', 0, 0, 0))]
        check = results({'events': simple})
        self.assertEqual(check['observations'], 'pass')
        for criterion in ('authority', 'prediction', 'session'):
            self.assertEqual(check[criterion], 'fail')
        for reason in ('duplicate', 'out-of-order', 'unowned', 'invalid', 'offline', 'stale-session'):
            with self.subTest(reason=reason):
                submission = trace()
                event = next(e for e in submission['events'] if e['expect']['result'] == reason)
                event.clear()
                event.update(op='snapshot', expect=expected('snapshot', 0, 0, 0))
                criterion = 'session' if reason in ('offline', 'stale-session') else 'authority'
                self.assertEqual(results(submission)[criterion], 'fail')
        before_reconnect = events[:next(i for i, e in enumerate(events) if e['op'] == 'reconnect')]
        self.assertEqual(results({'events': before_reconnect})['session'], 'fail')

    def test_a_fresh_move_before_stale_rejection_does_not_complete_the_recovery(self):
        submission = trace()
        events = submission['events']
        stale = next(e for e in events if e['expect']['result'] == 'stale-session')
        # Keep event numbers stable. Deliver the stale packet after the fresh move.
        index = events.index(stale)
        current = dict(events[index - 1]['expect'], result='snapshot')
        events[index] = dict(op='snapshot', expect=current)
        stale['expect'] = dict(events[-1]['expect'], result='stale-session')
        events.insert(-1, stale)
        check = results(submission)
        self.assertEqual(check['observations'], 'pass')
        self.assertEqual(check['session'], 'fail')

    def test_reconnect_and_disconnect_are_idempotent_and_offline_inputs_have_no_packet(self):
        events = [
            dict(op='reconnect', expect=expected('already-online', 0, 0, 0)),
            dict(op='disconnect', expect=expected('disconnected', 0, 0, 0, online=False)),
            dict(op='disconnect', expect=expected('already-offline', 0, 0, 0, online=False)),
            dict(op='send', actor='owner', seq=1, delta=2, expect=expected('offline', 0, 0, 0, online=False)),
            dict(op='snapshot', expect=expected('offline', 0, 0, 0, online=False)),
            dict(op='reconnect', expect=expected('reconnected', 0, 0, 0, epoch=2)),
            dict(op='reconnect', expect=expected('already-online', 0, 0, 0, epoch=2)),
        ]
        self.assertEqual(results({'events': events})['observations'], 'pass')
        events.append(dict(op='deliver', packet=4, expect=expected('stale-session', 0, 0, 0, epoch=2)))
        with self.assertRaises(ValueError):
            assess('multiplayer', {'events': events})

    def test_equal_coordinates_do_not_prove_convergence_with_unresolved_inputs(self):
        submission = trace()
        last = submission['events'][-1]['expect']

        def step(op, verdict, client, **fields):
            return dict(op=op, **fields, expect=dict(last, result=verdict, client=client))

        submission['events'].extend([
            step('send', 'sent', last['server'] + 1, actor='owner', seq=last['ack'] + 1, delta=1),
            step('send', 'sent', last['server'], actor='owner', seq=last['ack'] + 2, delta=-1),
            step('snapshot', 'snapshot', last['server']),
        ])
        check = results(submission)
        self.assertEqual(check['observations'], 'pass')
        self.assertEqual(check['convergence'], 'fail')

    def test_malformed_schema_and_packet_references_raise_value_error(self):
        mutations = [
            lambda d: d.update(extra=0), lambda d: d.update(events='bad'),
            lambda d: d.update(events=d['events'] * 4), lambda d: d['events'].__setitem__(0, []),
            lambda d: d['events'][0].update(op=[]), lambda d: d['events'][0].update(actor='server'),
            lambda d: d['events'][0].update(seq=True), lambda d: d['events'][0].update(seq=0),
            lambda d: d['events'][0].update(seq=33), lambda d: d['events'][0].update(delta=1.0),
            lambda d: d['events'][0].update(delta=-10), lambda d: d['events'][0].update(extra=0),
            lambda d: d['events'][0]['expect'].update(server=False),
            lambda d: d['events'][0]['expect'].update(online=1),
            lambda d: d['events'][0]['expect'].update(result=[]),
            lambda d: d['events'][0]['expect'].pop('ack'),
            lambda d: d['events'][2].update(packet=3), lambda d: d['events'][2].update(packet=0),
            lambda d: d['events'][3].update(packet=3),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                submission = trace()
                mutate(submission)
                with self.assertRaises(ValueError):
                    assess('multiplayer', submission)
        for exercise_id in ('unknown', None, []):
            with self.assertRaises(ValueError):
                assess(exercise_id, trace())
