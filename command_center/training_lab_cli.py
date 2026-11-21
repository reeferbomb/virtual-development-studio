"""Run bounded, deterministic practice checks offline without starting a service."""

import argparse
import json

from .training_lab import MAX_BYTES, assess_submission, lab_catalog, reject_duplicate_keys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('catalog', help='List exercises and teaching examples')
    commands.add_parser('examples', help='Run all bundled reference examples')
    assess = commands.add_parser('assess', help='Assess a named exercise using a local JSON submission')
    assess.add_argument('exercise_id')
    assess.add_argument('file')
    args = parser.parse_args(argv)
    if args.command == 'catalog':
        report = lab_catalog()
        code = 0
    elif args.command == 'examples':
        catalog = lab_catalog()
        reports = [assess_submission(e['id'], e['example']) for e in catalog['exercises']]
        failed = sum(r['status'] != 'pass' for r in reports)
        report = {
            'lab_sha256': catalog['lab_sha256'],
            'summary': {'pass': len(reports) - failed, 'fail': failed}, 'reports': reports,
            'note': 'Bundled reference exercise checks; not evidence of a specialist completing independent work.',
        }
        code = int(bool(failed))
    else:
        try:
            with open(args.file, 'rb') as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('Submission file exceeds the byte limit')
            report = assess_submission(args.exercise_id, json.loads(raw, object_pairs_hook=reject_duplicate_keys))
            code = int(report['status'] != 'pass')
        except (OSError, ValueError, RecursionError) as exc:
            report = {'status': 'unavailable', 'note': str(exc)}
            code = 2
    print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
