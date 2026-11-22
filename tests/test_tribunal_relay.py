"""Synthetic offline fixtures only. These tests never submit a request to a provider."""

import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from command_center import tribunal, tribunal_relay as relay


def signed(fields):
    body = {key: value for key, value in fields.items() if key != 'packet_sha256'}
    wire = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return {**body, 'packet_sha256': hashlib.sha256(wire.encode()).hexdigest()}


def packet(provider='claude', phase='proposal'):
    proposals = [] if phase == 'proposal' else [
        {'provider': name, 'status': 'received', 'summary': 'Synthetic peer assessment.'}
        for name in ('claude', 'gemini', 'chatgpt')
    ]
    return signed({
        'schema_version': 1, 'provider': provider, 'round': phase,
        'review_id': 'synthetic-roundtable', 'source_sha256': 'a' * 64,
        'summary': 'Synthetic example: compare a guided tour with an optional map.',
        'proposals': proposals,
    })


def filled(request):
    return {
        **request['response_template'], 'at': '2026-03-31T15:00:00.250Z',
        'provenance': 'Synthetic local test fixture.',
        'response_text': 'Synthetic full reply.\nCompare first-turn navigation times.\tΔ',
        'summary': 'Synthetic proposal to measure first-turn navigation.',
    }


def receive(request, response, **kwargs):
    return relay.import_response(request, response, event_id='synthetic-import', confirmed=True, **kwargs)


class RelayTests(unittest.TestCase):
    def test_availability_is_operator_reported_and_never_assumed(self):
        for name in ('claude', 'gemini', 'chatgpt', 'other-reviewer'):
            self.assertEqual(relay.availability(name)['status'], 'unknown')
            for status in ('unavailable', 'ready-for-manual'):
                self.assertEqual(relay.availability(name, status)['status'], status)
        for bad in (None, {}, True, 'available', 'invoked', 'ready'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                relay.availability('claude', bad)
        with self.assertRaises(ValueError):
            relay.availability('../private')

    def test_named_and_generic_providers_copy_only_explicit_packet(self):
        for provider, name in (('claude', 'Claude'), ('gemini', 'Gemini'),
                               ('chatgpt', 'ChatGPT'), ('other-reviewer', 'other-reviewer')):
            data = packet(provider)
            original = copy.deepcopy(data)
            handoff = relay.prepare_request(data, confirmed=True)
            self.assertEqual(data, original)
            instruction, content = handoff['copy_text'].split('\n\n', 1)
            self.assertIn(name, instruction)
            self.assertIn('independent proposal', instruction)
            self.assertEqual(json.loads(content), data)
            self.assertEqual(handoff['response_template']['response_text'], '')
            self.assertIn('unavailable', handoff['instructions'])

    def test_full_paste_and_manual_json_make_identical_private_receipts(self):
        data = packet('gemini', 'critique')
        request = relay.prepare_request(data, confirmed=True)
        self.assertIn('Critique the supplied proposals', request['copy_text'])
        reply = filled(request)
        reply['at'] = '2026-01-02T14:59:00+00:00'
        imported = receive(data, reply)
        self.assertEqual(receive(data, json.dumps(reply)), imported)
        receipt = imported['receipt']
        self.assertEqual(receipt['attribution'], 'operator-reported')
        self.assertEqual(receipt['provenance'], reply['provenance'])
        self.assertEqual(receipt['response_text'], reply['response_text'])
        self.assertEqual(receipt['response_sha256'], hashlib.sha256(reply['response_text'].encode()).hexdigest())
        event = imported['event']
        self.assertEqual(event['receipt'], receipt)
        self.assertEqual(event['summary'], reply['summary'])
        self.assertNotIn('response_text', event)
        self.assertTrue(event['shareable'])
        self.assertEqual(event['event_id'], receipt['event_id'])
        relay.validate_receipt(receipt, event)

    def test_actual_core_keeps_full_reply_only_in_private_history(self):
        open_event = {
            'op': 'open', 'event_id': 'synthetic-open', 'review_id': 'test-review',
            'at': '2026-01-01T12:00:00Z', 'source_sha256': 'a' * 64,
            'providers': ['claude', 'gemini'], 'summary': 'Synthetic navigation choices.', 'shareable': True,
        }
        state = tribunal.apply(tribunal.empty(), open_event)
        for provider in open_event['providers']:
            data = tribunal.packet(state, 'test-review', provider, 'proposal')
            form = filled(relay.prepare_request(data, confirmed=True))
            imported = relay.import_response(data, form, event_id=f'import-{provider}', confirmed=True)
            state = tribunal.apply(state, imported['event'])
        full_reply = form['response_text']
        self.assertEqual(state['history'][-1]['receipt']['response_text'], full_reply)
        self.assertNotIn('response_text', json.dumps(state['reviews']))
        outbound = tribunal.packet(state, 'test-review', 'gemini', 'critique')
        exported = relay.prepare_request(outbound, confirmed=True)
        self.assertIn(form['summary'], exported['copy_text'])
        self.assertNotIn('response_text', exported['copy_text'])
        self.assertNotIn('Compare first-turn navigation times.', exported['copy_text'])
        self.assertNotIn(form['provenance'], exported['copy_text'])

    def test_replay_detects_metadata_digest_or_text_substitution(self):
        data = packet()
        imported = receive(data, filled(relay.prepare_request(data, confirmed=True)))
        for field in relay.RECEIPT_FIELDS - {'provenance'}:
            receipt = {**imported['receipt'], field: 'changed'}
            with self.subTest(field=field), self.assertRaises(ValueError):
                relay.validate_receipt(receipt, imported['event'])
        for changes in ({'op': 'decision'}, {'status': 'unavailable'}, {'shareable': False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                relay.validate_receipt(imported['receipt'], {**imported['event'], **changes})
        with self.assertRaises(ValueError):
            relay.validate_receipt({**imported['receipt'], 'attachment': {}}, imported['event'])

    def test_confirmation_precedes_output_and_adapter_parsing(self):
        class MustNotParse:
            def parse_response(self, supplied):
                raise AssertionError('Adapter received unapproved data.')

        data = packet()
        for unchecked in (False, None, 1, 'true'):
            with self.subTest(unchecked=unchecked), self.assertRaises(ValueError):
                relay.prepare_request(data, confirmed=unchecked)
            with self.assertRaises(ValueError):
                relay.import_response(data, {}, event_id='example', confirmed=unchecked, adapter=MustNotParse())

    def test_rejects_extra_fields_tampering_private_paths_and_obvious_secrets(self):
        data = packet()
        packets = [
            {**data, 'summary': 'Tampered after sealing.'}, signed({**data, 'attachments': []}),
            signed({**data, 'raw_transcript': 'Do not export.'}),
            signed({**data, 'summary': 'Refer to file:///private/log'}),
            signed({**data, 'summary': 'Review /home/example/private.'}),
            signed({**data, 'summary': 'Contact synthetic@example.test.'}),
            signed({**data, 'summary': 'Authorization: Bearer ' + 'x' * 18}),
            signed({**data, 'summary': 'Private API_KEY=' + 'example' * 3}),
            signed({**data, 'summary': 'Do not paste data:image/png;base64,AAAA.'}),
        ]
        critique = packet(phase='critique')
        critique['proposals'][0]['summary'] = 'password = test-placeholder'
        packets.append(signed(critique))
        for index, candidate in enumerate(packets):
            with self.subTest(index=index), self.assertRaises(ValueError):
                relay.prepare_request(candidate, confirmed=True)

    def test_empty_template_mismatched_source_and_bad_fields_fail(self):
        data = packet()
        handoff = relay.prepare_request(data, confirmed=True)
        with self.assertRaises(ValueError):
            receive(data, handoff['response_template'])
        good = filled(handoff)
        for field, bad in (('provider', 'gemini'), ('round', 'critique'), ('packet_sha256', 'b' * 64),
                           ('at', '2026-03-31T15:00:00'), ('at', '2026-02-31T15:00:00Z'),
                           ('at', '2026-03-31T15:00:00+02:00'), ('at', 123), ('provenance', ''),
                           ('response_text', '  '), ('response_text', 'ABC\x00DEF'),
                           ('response_text', 'x' * (relay.MAX_RESPONSE_CHARS + 1)),
                           ('response_text', 'Private key: -----BEGIN PRIVATE KEY-----'),
                           ('summary', 'too\nlong'), ('summary', 'x' * 1201), ('extra', 'unexpected')):
            with self.subTest(field=field, bad=str(bad)[:30]), self.assertRaises(ValueError):
                receive(data, {**good, field: bad})
        for event_id in ('../x', [], 'Uppercase'):
            with self.subTest(event_id=event_id), self.assertRaises(ValueError):
                relay.import_response(data, good, event_id=event_id, confirmed=True)

    def test_manual_json_fallback_rejects_path_duplicate_and_deeply_nested_input(self):
        data = packet()
        with patch('builtins.open', side_effect=AssertionError('Unexpected local file read')):
            for bad in ('/tmp/reply.json', '{"at":"first","at":"second"}', '[' * 2000,
                        ' ' * (relay.MAX_JSON_CHARS + 1), '[]', 'false'):
                with self.subTest(bad=bad[:25]), self.assertRaises(ValueError):
                    receive(data, bad)

    def test_generic_adapter_can_decode_an_existing_locally_supplied_reply(self):
        class SyntheticAdapter:
            """Local fixture for a different reply envelope."""
            def parse_response(self, supplied):
                return supplied['already_received']

        data = packet('other-reviewer')
        actual = filled(relay.prepare_request(data, confirmed=True))
        result = receive(data, {'already_received': actual}, adapter=SyntheticAdapter())
        self.assertEqual(result['receipt']['provider'], 'other-reviewer')
        with self.assertRaises(ValueError):
            receive(data, {'already_received': {'generated': True}}, adapter=SyntheticAdapter())

    def test_free_text_does_not_execute(self):
        data = packet()
        form = filled(relay.prepare_request(data, confirmed=True))
        text = 'Synthetic reply. <script>example()</script>\nUse "$(example)" as a label.'
        with patch('subprocess.Popen', side_effect=AssertionError('No execution permitted')):
            result = receive(data, {**form, 'response_text': text})
        self.assertEqual(result['receipt']['response_text'], text)


if __name__ == '__main__':
    unittest.main()
