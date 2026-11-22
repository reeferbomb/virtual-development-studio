from copy import deepcopy
import hashlib
import json
import unittest

from command_center import intelligence_build as build


def statuses(report):
    return {row['id']: row['status'] for row in report['checks']}


class BuildIntelligenceTests(unittest.TestCase):
    def test_synthetic_example_compares_declared_footprint_and_is_stateless(self):
        data = build.example()
        original = deepcopy(data)
        report = build.analyze(data)
        self.assertEqual(set(report), {'schema_version', 'kind', 'status', 'checks', 'metrics', 'advisory'})
        self.assertEqual((report['schema_version'], report['kind'], report['status']), (1, 'build', 'pass'))
        self.assertTrue(all(set(row) == {'id', 'label', 'status', 'detail'} for row in report['checks']))
        self.assertEqual(statuses(report), dict.fromkeys(statuses(report), 'pass'))
        self.assertEqual(build.analyze(data), report)
        self.assertEqual(data, original)
        self.assertEqual(build.example(), original)
        self.assertEqual(json.loads(json.dumps(report)), report)
        metrics = report['metrics']
        self.assertEqual(metrics['delta_bytes'], metrics['candidate']['bytes'] - metrics['baseline']['bytes'])
        self.assertEqual(metrics['assets'], {'added': ['switch-click'], 'removed': ['old-sign'],
                                             'changed': [{'id': 'relay-mesh', 'fields': ['sha256', 'bytes']}],
                                             'identical': ['boot-menu']})
        self.assertIn('declared', report['advisory'].lower())

    def test_order_independent_hashes_groups_and_diffs(self):
        data = build.example()
        expected = build.analyze(data)
        for key in ('candidate', 'baseline'):
            data[key]['assets'].reverse()
        data['budgets'].reverse()
        data['required_assets'].reverse()
        self.assertEqual(build.analyze(data), expected)
        data['candidate']['assets'][0]['type'] = 'sprite'
        self.assertNotEqual(build.analyze(data)['metrics']['candidate']['manifest_sha256'],
                            expected['metrics']['candidate']['manifest_sha256'])

    def test_size_and_growth_budgets_are_independent_and_inclusive(self):
        data = build.example()
        measured = {row['group']: row for row in build.analyze(data)['metrics']['groups']}
        for budget in data['budgets']:
            group = measured[budget['group']]
            budget.update(max_bytes=group['candidate_bytes'], max_growth_bytes=max(0, group['delta_bytes']))
        self.assertEqual(build.analyze(data)['status'], 'pass')
        audio = next(row for row in data['budgets'] if row['group'] == 'audio')
        audio['max_bytes'] -= 1
        report = build.analyze(data)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual((statuses(report)['group-size'], statuses(report)['group-growth']), ('fail', 'pass'))
        audio['max_bytes'] += 1
        audio['max_growth_bytes'] -= 1
        report = build.analyze(data)
        self.assertEqual((statuses(report)['group-size'], statuses(report)['group-growth']), ('pass', 'fail'))

    def test_missing_required_outranks_unbudgeted_groups(self):
        data = build.example()
        data['budgets'] = [row for row in data['budgets'] if row['group'] != 'audio']
        coverage = build.analyze(data)
        self.assertEqual(coverage['status'], 'warn')
        self.assertEqual(coverage['metrics']['unbudgeted_groups'], ['audio'])
        data['required_assets'].append('old-sign')
        report = build.analyze(data)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(statuses(report)['budget-coverage'], 'warn')
        self.assertEqual(statuses(report)['required-assets'], 'fail')
        self.assertEqual(report['metrics']['missing_required'], ['old-sign'])

    def test_digest_size_conflict_includes_cross_asset_aliases(self):
        data = build.example()
        baseline = next(row for row in data['baseline']['assets'] if row['id'] == 'relay-mesh')
        candidate = next(row for row in data['candidate']['assets'] if row['id'] == 'switch-click')
        candidate['sha256'] = baseline['sha256']
        report = build.analyze(data)
        self.assertEqual(report['status'], 'fail')
        self.assertEqual(statuses(report)['manifest-consistency'], 'fail')
        self.assertEqual(report['metrics']['digest_conflicts'], [
            {'sha256': baseline['sha256'], 'declared_sizes': sorted([baseline['bytes'], candidate['bytes']]),
             'baseline_ids': ['relay-mesh'], 'candidate_ids': ['switch-click']},
        ])

    def test_same_size_aliases_count_each_declared_asset_and_metadata_changes_are_visible(self):
        data = build.example()
        menu = next(row for row in data['candidate']['assets'] if row['id'] == 'boot-menu')
        menu['group'] = 'audio'
        menu['type'] = 'fallback'
        data['candidate']['assets'].append(dict(menu, id='menu-alias'))
        report = build.analyze(data)
        self.assertEqual(statuses(report)['manifest-consistency'], 'pass')
        self.assertIn({'id': 'boot-menu', 'fields': ['group', 'type']}, report['metrics']['assets']['changed'])
        audio = next(row for row in report['metrics']['groups'] if row['group'] == 'audio')
        self.assertEqual(audio['candidate_bytes'], sum(row['bytes'] for row in data['candidate']['assets'] if row['group'] == 'audio'))

    def test_empty_digest_and_empty_manifest_have_distinct_meanings(self):
        empty = hashlib.sha256(b'').hexdigest()
        data = build.example()
        asset = data['candidate']['assets'][0]
        asset.update(bytes=0, sha256=empty)
        self.assertEqual(statuses(build.analyze(data))['manifest-consistency'], 'pass')
        asset['bytes'] = 1
        self.assertEqual(statuses(build.analyze(data))['manifest-consistency'], 'fail')
        asset.update(bytes=0, sha256='0' * 64)
        self.assertEqual(statuses(build.analyze(data))['manifest-consistency'], 'fail')
        data['candidate']['assets'].clear()
        data['required_assets'].clear()
        self.assertEqual(build.analyze(data)['status'], 'warn')

    def test_closed_schema_rejects_nonlogical_ids_and_malformed_values(self):
        for mutate in (
            lambda d: d.update(url='https://example.invalid/manifest'),
            lambda d: d['candidate'].update(build_id='/tmp/published'),
            lambda d: d['candidate']['assets'][0].update(path='assets/test.bin'),
            lambda d: d['candidate']['assets'][0].update(id='../escape'),
            lambda d: d['candidate']['assets'][0].update(group='data/stream'),
            lambda d: d['candidate']['assets'][0].update(type='md\n'),
            lambda d: d['candidate']['assets'][0].update(sha256='A' * 64),
            lambda d: d['candidate']['assets'][0].update(bytes=True),
            lambda d: d['candidate']['assets'][0].update(bytes=float('nan')),
            lambda d: d['candidate']['assets'][0].update(bytes=1_000_000_000_001),
            lambda d: d['candidate']['assets'].append(deepcopy(d['candidate']['assets'][0])),
            lambda d: d['candidate'].update(assets=d['candidate']['assets'] * 90),
            lambda d: d['budgets'].append(deepcopy(d['budgets'][0])),
            lambda d: d['budgets'][0].pop('max_growth_bytes'),
            lambda d: d['budgets'][0].update(max_bytes=-1),
            lambda d: d['required_assets'].append(d['required_assets'][0]),
            lambda d: d.update(required_assets={}),
        ):
            with self.subTest(mutate=mutate):
                data = build.example()
                mutate(data)
                with self.assertRaises(ValueError):
                    build.analyze(data)
        for data in (None, [], {'baseline': {}}):
            with self.assertRaises(ValueError):
                build.analyze(data)


if __name__ == '__main__':
    unittest.main()
