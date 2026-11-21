"""Run an evidence-based quality check against a local running Studio.

Exit 0: ready; 1: pending or blocked; 2: unavailable or inconsistent evidence.
This is a read-only point-in-time check, not publication permission.
"""

import argparse
import http.client
import json

from .acceptance import _LABELS
from .projects import PROJECT_ID
from .scheduler import _ROLES
from .task_store import _valid_digest


LIMIT = 1024 * 1024


def report_exit_code(project_id, report):
    try:
        if (not isinstance(report, dict) or report['project_id'] != project_id
                or not _valid_digest(report['spec_sha256']) or report['status'] not in ('ready', 'pending', 'blocked')
                or not isinstance(report['note'], str) or not report['note'].strip()):
            return 2
        checks = report['checks']
        if not isinstance(checks, list) or len(checks) != len(_LABELS):
            return 2
        seen = set()
        counts = dict.fromkeys(('pass', 'pending', 'fail'), 0)
        for row in checks:
            key, status = row['id'], row['status']
            if (key in seen or row['label'] != _LABELS[key] or status not in counts
                    or row['role'] not in _ROLES
                    or any(not isinstance(row[field], str) or not row[field].strip()
                           for field in ('evidence', 'next_action'))):
                return 2
            seen.add(key)
            counts[status] += 1
        if (not isinstance(report['summary'], dict) or report['summary'] != counts
                or any(type(n) is not int for n in report['summary'].values())):
            return 2
        expected = 'blocked' if counts['fail'] else 'pending' if counts['pending'] else 'ready'
        if report['status'] != expected:
            return 2
        return 0 if expected == 'ready' else 1
    except (KeyError, TypeError, ValueError):
        return 2


def fetch_report(project_id, port):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        connection.request('GET', f'/api/projects/{project_id}/quality-matrix')
        with connection.getresponse() as response:
            if response.status != 200:
                raise ValueError('Quality endpoint unavailable')
            raw = response.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError('Quality report exceeds size limit')
            return json.loads(raw)
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_id')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    if not PROJECT_ID.fullmatch(args.project_id) or len(args.project_id) > 80 or not 1 <= args.port <= 65535:
        parser.error('Expected a project ID and valid local port')
    try:
        report = fetch_report(args.project_id, args.port)
        code = report_exit_code(args.project_id, report)
    except (OSError, ValueError, http.client.HTTPException, RecursionError):
        code = 2
    if code == 2:
        report = {'project_id': args.project_id, 'status': 'unavailable',
                  'note': 'Quality evidence is unavailable or inconsistent. Refresh the local Studio.'}
    print(json.dumps(report, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
