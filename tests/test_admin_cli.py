import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from command_center import admin_cli, admin_store


class AdminIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = self.root / 'journal.json'
        self.revision = 0

    def call(self, *args):
        return admin_cli.run(admin_cli.parser().parse_args(['--journal', str(self.journal), *args]))

    def data(self, value, filename='input.json'):
        path = self.root / filename
        path.write_text(json.dumps(value), encoding='utf-8')
        return str(path)

    def append(self, stream, event):
        state = self.call('append', stream, self.data(event), '--revision', str(self.revision))
        self.revision = state['revision']
        return state

    def test_registry_review_and_manual_response_share_one_private_journal(self):
        source = {'commit': 'a' * 40, 'release_ref': 'project/lab/v1', 'library_ref': None,
                  'sha256': 'b' * 64, 'dirty': False}
        self.append('registry', {'type': 'project', 'project_id': 'lab', 'name': 'Lab',
                                 'source': source, 'environment': {'engine': 'fixture'}})
        self.append('registry', {'type': 'checkpoint', 'project_id': 'lab', 'checkpoint_id': 'cp1',
                                 'summary': 'Synthetic continuity fixture', 'log_ids': [],
                                 'criteria': [{'id': 'c1', 'description': 'Verify output', 'high_risk': True}],
                                 'tests': [], 'pending': ['Run tests'], 'gaps': ['No transcript']})
        h = self.call('handoff', 'lab', 'cp1')
        self.assertEqual(h['project_id'], 'lab')
        self.append('registry', {'type': 'request', 'project_id': 'lab', 'checkpoint_id': 'cp1',
                                 'reason': 'user-request', 'detail': 'Synthetic requested continuation'})
        self.append('registry', {'type': 'receipt', 'project_id': 'lab', 'checkpoint_id': 'cp1',
                                 'packet_sha256': h['packet_sha256'], 'actual_project_id': 'lab', 'mode': 'regular',
                                 'chat_id': 'test-chat', 'ref': 'fixture:test-chat'})
        self.append('tribunal', {'op': 'open', 'event_id': 'open-one', 'review_id': 'review-one',
                                 'at': '2026-01-01T00:00:00Z', 'source_sha256': source['sha256'],
                                 'summary': 'Review a fictional narrow change', 'shareable': True})
        packet = self.call('packet', 'review-one', 'claude', 'proposal')
        p = self.data(packet, 'packet.json')
        prepared = self.call('relay', p, '--share-confirmed')
        template = prepared['response_template']
        template.update(at='2026-01-01T00:01:00Z', provenance='Synthetic test fixture; no provider invoked',
                        response_text='Private synthetic reply body', summary='A bounded public summary')
        response = self.data(template, 'response.json')
        after = self.call('receive', p, response, '--event-id', 'claude-one', '--revision',
                          str(self.revision), '--share-confirmed')
        self.revision = after['revision']
        self.assertEqual(len(after['registry']['projects']), 1)
        persisted = admin_store.load(self.journal)
        self.assertEqual(persisted['events'][-1]['event']['receipt']['response_text'], 'Private synthetic reply body')
        other = self.call('packet', 'review-one', 'gemini', 'proposal')
        self.assertNotIn('Private synthetic reply body', json.dumps(other))
        self.assertNotIn('A bounded public summary', json.dumps(other))
        with self.assertRaises((ValueError, OSError)):
            self.call('receive', p, response, '--event-id', 'claude-one', '--revision',
                      str(self.revision - 1), '--share-confirmed')
        self.assertEqual(admin_store.load(self.journal)['revision'], self.revision)

    def test_invalid_event_does_not_create_history_and_chat_status_is_honest(self):
        with self.assertRaises(ValueError):
            self.append('registry', {'type': 'not-a-real-event', 'project_id': 'lab'})
        self.assertEqual(admin_store.load(self.journal)['revision'], 0)
        result = subprocess.run([sys.executable, '-m', 'command_center.admin_cli', 'chat-capability'],
                                capture_output=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual((data['creation'], data['fullness'], data['default_mode']), ('manual', 'unknown', 'regular'))


if __name__ == '__main__':
    unittest.main()
