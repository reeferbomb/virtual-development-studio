"""Compare declared build footprints and logical asset changes without opening assets."""

from collections import Counter, defaultdict
from hashlib import sha256
import re

from .lab_gameplay import _array, _integer, _object
from .provenance import spec_digest


_MAX_ASSETS = 256
_MAX_BUDGETS = 32
_MAX_BYTES = 1_000_000_000_000
_ID = re.compile(r'[a-z][a-z0-9_-]{0,31}')
_SHA = re.compile(r'[0-9a-f]{64}')
_EMPTY_SHA = sha256(b'').hexdigest()
_ASSET_FIELDS = ('sha256', 'bytes', 'group', 'type')
_ADVISORY = ('Advisory comparison of declared manifest metadata. Actual package contents, disk footprint, '
             'runtime performance and release approval require separate evidence.')


def _identifier(value, name):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError(f'{name} must be a logical lowercase ID of at most 32 characters.')


def _manifest(value, name):
    _object(value, ('build_id', 'assets'), name)
    _identifier(value['build_id'], 'Build ID')
    _array(value['assets'], _MAX_ASSETS, 'Manifest assets')
    assets = {}
    for row in value['assets']:
        _object(row, ('id', *_ASSET_FIELDS), 'Manifest asset')
        for field in ('id', 'group', 'type'):
            _identifier(row[field], field)
        if type(row['sha256']) is not str or not _SHA.fullmatch(row['sha256']):
            raise ValueError('Asset SHA-256 must contain 64 lowercase hexadecimal characters.')
        _integer(row['bytes'], 0, _MAX_BYTES, 'Asset bytes')
        if row['id'] in assets:
            raise ValueError('Each manifest must have distinct asset IDs.')
        assets[row['id']] = row
    return assets


def _policy(data):
    _array(data['budgets'], _MAX_BUDGETS, 'Group budgets')
    budgets = {}
    for row in data['budgets']:
        _object(row, ('group', 'max_bytes', 'max_growth_bytes'), 'Group budget')
        _identifier(row['group'], 'Budget group')
        for field in ('max_bytes', 'max_growth_bytes'):
            _integer(row[field], 0, _MAX_BYTES, field)
        if row['group'] in budgets:
            raise ValueError('Each group can have one budget.')
        budgets[row['group']] = row
    required = data['required_assets']
    _array(required, _MAX_ASSETS, 'Required assets')
    for name in required:
        _identifier(name, 'Required asset ID')
    if len(required) != len(set(required)):
        raise ValueError('Required assets must be distinct.')
    return budgets, set(required)


def _manifest_metrics(build_id, assets):
    ordered = [assets[name] for name in sorted(assets)]
    return {'build_id': build_id, 'manifest_sha256': spec_digest({'build_id': build_id, 'assets': ordered}),
            'asset_count': len(assets), 'bytes': sum(row['bytes'] for row in ordered)}


def _asset_changes(baseline, candidate):
    changed, identical = [], []
    for name in sorted(baseline.keys() & candidate.keys()):
        fields = [field for field in _ASSET_FIELDS if baseline[name][field] != candidate[name][field]]
        if fields:
            changed.append({'id': name, 'fields': fields})
        else:
            identical.append(name)
    return {'added': sorted(candidate.keys() - baseline.keys()), 'removed': sorted(baseline.keys() - candidate.keys()),
            'changed': changed, 'identical': identical}


def _digest_conflicts(baseline, candidate):
    rows = defaultdict(lambda: {'baseline': [], 'candidate': []})
    for role, manifest in [('baseline', baseline), ('candidate', candidate)]:
        for name in sorted(manifest):
            asset = manifest[name]
            rows[asset['sha256']][role].append((name, asset['bytes']))
    conflicts = []
    for digest, uses in sorted(rows.items()):
        sizes = {size for records in uses.values() for _, size in records}
        empty_mismatch = (digest == _EMPTY_SHA) != (0 in sizes)
        if len(sizes) > 1 or empty_mismatch:
            conflicts.append({'sha256': digest, 'declared_sizes': sorted(sizes),
                              'baseline_ids': [name for name, _ in uses['baseline']],
                              'candidate_ids': [name for name, _ in uses['candidate']]})
    return conflicts


def _group_totals(assets):
    totals = Counter()
    for row in assets.values():
        totals[row['group']] += row['bytes']
    return totals


def _group_metrics(baseline, candidate, budgets):
    return [{'group': name, 'baseline_bytes': baseline[name], 'candidate_bytes': candidate[name],
             'delta_bytes': candidate[name] - baseline[name], 'max_bytes': budgets.get(name, {}).get('max_bytes'),
             'max_growth_bytes': budgets.get(name, {}).get('max_growth_bytes')}
            for name in sorted(baseline.keys() | candidate.keys() | budgets.keys())]


def _check(key, label, status, detail):
    return {'id': key, 'label': label, 'status': status, 'detail': detail}


def _budget_check(key, label, groups, measured, limit):
    monitored = [row for row in groups if row[limit] is not None]
    exceeded = [row['group'] for row in monitored if row[measured] > row[limit]]
    detail = f'{len(exceeded)} of {len(monitored)} budgeted groups exceed the limit.'
    if exceeded:
        detail += ' Over budget: ' + ', '.join(exceeded) + '.'
    return _check(key, label, 'fail' if exceeded else 'pass', detail)


def analyze(data):
    """Return an advisory report for the closed v1 input schema or raise ValueError."""
    _object(data, ('baseline', 'candidate', 'budgets', 'required_assets'), 'Build comparison')
    baseline = _manifest(data['baseline'], 'Baseline manifest')
    candidate = _manifest(data['candidate'], 'Candidate manifest')
    budgets, required = _policy(data)
    before = _manifest_metrics(data['baseline']['build_id'], baseline)
    after = _manifest_metrics(data['candidate']['build_id'], candidate)
    candidate_groups = _group_totals(candidate)
    groups = _group_metrics(_group_totals(baseline), candidate_groups, budgets)
    conflicts = _digest_conflicts(baseline, candidate)
    unbudgeted = sorted(candidate_groups.keys() - budgets.keys())
    missing = sorted(required - candidate.keys())

    checks = [
        _check('manifest-consistency', 'Digest and size consistency', 'fail' if conflicts else 'pass',
               f'{len(conflicts)} declared digests have incompatible sizes or an invalid empty-content declaration.'),
        _check('required-assets', 'Required candidate assets', 'fail' if missing else 'pass',
               f'{len(required) - len(missing)} of {len(required)} required logical assets are declared in the candidate.'),
        _check('budget-coverage', 'Budget coverage', 'warn' if unbudgeted or not candidate else 'pass',
               f'{len(candidate)} candidate assets across {len(candidate_groups)} groups. {len(unbudgeted)} groups lack a budget.'),
        _budget_check('group-size', 'Candidate group size', groups, 'candidate_bytes', 'max_bytes'),
        _budget_check('group-growth', 'Group growth from baseline', groups, 'delta_bytes', 'max_growth_bytes'),
    ]
    severity = {'pass': 0, 'warn': 1, 'fail': 2}
    status = max((row['status'] for row in checks), key=severity.__getitem__)
    return {'schema_version': 1, 'kind': 'build', 'status': status, 'checks': checks,
            'metrics': {'baseline': before, 'candidate': after, 'delta_bytes': after['bytes'] - before['bytes'],
                        'assets': _asset_changes(baseline, candidate), 'groups': groups, 'missing_required': missing,
                        'unbudgeted_groups': unbudgeted, 'digest_conflicts': conflicts},
            'advisory': _ADVISORY}


def example():
    """Return a fresh synthetic package comparison."""
    def asset(name, fingerprint, size, group, kind):
        return {'id': name, 'sha256': fingerprint * 64, 'bytes': size, 'group': group, 'type': kind}

    return {
        'baseline': {'build_id': 'relay-a12', 'assets': [
            asset('boot-menu', '1', 4096, 'ui', 'scene'), asset('relay-mesh', '2', 10_000, 'meshes', 'glb'),
            asset('old-sign', '3', 2048, 'textures', 'png'),
        ]},
        'candidate': {'build_id': 'relay-a15', 'assets': [
            asset('boot-menu', '1', 4096, 'ui', 'scene'), asset('relay-mesh', '4', 12_000, 'meshes', 'glb'),
            asset('switch-click', '5', 832, 'audio', 'wav'),
        ]},
        'budgets': [
            {'group': 'audio', 'max_bytes': 2000, 'max_growth_bytes': 1000},
            {'group': 'meshes', 'max_bytes': 20_000, 'max_growth_bytes': 3000},
            {'group': 'textures', 'max_bytes': 2048, 'max_growth_bytes': 0},
            {'group': 'ui', 'max_bytes': 4096, 'max_growth_bytes': 0},
        ],
        'required_assets': ['boot-menu', 'relay-mesh'],
    }
