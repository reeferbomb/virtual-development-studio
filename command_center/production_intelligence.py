"""Local advisory analysis of explicitly supplied production observations."""

import importlib
import json

from .provenance import spec_digest


KINDS = ('balance', 'playtest', 'frame', 'ui', 'audio', 'build')
STATUSES = ('pass', 'warn', 'fail')
MAX_BYTES = 4 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
ADVISORY = ('Analysis of supplied observations only. Missing domains are not evaluated. '
            'No authentication, source-file verification, human enjoyment, hardware certification '
            'or release approval. Independently verify the actual build and evidence.')


def _module(kind):
    if kind not in KINDS:
        raise ValueError('Unknown diagnostic domain.')
    return importlib.import_module(f'.intelligence_{kind}', __package__)


def example(kind=None):
    """Return fresh original synthetic inputs; never substitute these for real observations."""
    kinds = KINDS if kind is None else (kind,)
    return {'schema_version': 1, 'captures': {key: _module(key).example() for key in kinds}}


def _worst(statuses):
    return max(statuses, key=STATUSES.index)


def analyze_bundle(data):
    """Evaluate a closed bundle without writes, network calls or changes to release gates."""
    if (not isinstance(data, dict) or set(data) != {'schema_version', 'captures'}
            or type(data['schema_version']) is not int or data['schema_version'] != 1
            or not isinstance(data['captures'], dict) or not data['captures']
            or not set(data['captures']).issubset(KINDS)):
        raise ValueError('Expected schema_version 1 and one or more supported captures.')
    try:
        encoded = json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()
        if len(encoded) > MAX_BYTES:
            raise ValueError('Capture bundle exceeds byte limit.')
        digest = spec_digest(data)
    except (TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('Capture bundle is not bounded JSON.') from exc
    reports = []
    missing = []
    for kind in KINDS:
        if kind not in data['captures']:
            missing.append(kind)
            continue
        report = _module(kind).analyze(data['captures'][kind])
        # Every producer is first-party. Check the contract anyway so a future
        # producer cannot accidentally publish a contradictory summary.
        if (not isinstance(report, dict) or report.get('kind') != kind
                or type(report.get('schema_version')) is not int or report['schema_version'] != 1
                or report.get('status') not in STATUSES or not isinstance(report.get('metrics'), dict)
                or not isinstance(report.get('advisory'), str) or not report['advisory'].strip()
                or not isinstance(report.get('checks'), list) or not report['checks']):
            raise ValueError('Diagnostic producer returned an invalid report.')
        checks = report['checks']
        ids = set()
        for check in checks:
            if (not isinstance(check, dict) or set(check) != {'id', 'label', 'status', 'detail'}
                    or any(not isinstance(check[key], str) or not check[key].strip()
                           for key in ('id', 'label', 'detail'))
                    or check['id'] in ids or check['status'] not in STATUSES):
                raise ValueError('Diagnostic producer returned an invalid check.')
            ids.add(check['id'])
        if report['status'] != _worst(row['status'] for row in checks):
            raise ValueError('Diagnostic producer returned a contradictory status.')
        reports.append(dict(report, capture_sha256=spec_digest(data['captures'][kind])))
    statuses = [row['status'] for row in reports] + (['warn'] if missing else [])
    result = {'schema_version': 1, 'kind': 'production-intelligence', 'input_sha256': digest,
              'status': _worst(statuses), 'missing': missing, 'reports': reports, 'advisory': ADVISORY}
    result['report_sha256'] = spec_digest(result)
    if len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()) > MAX_REPORT_BYTES:
        raise ValueError('Diagnostic report exceeds byte limit.')
    return result
