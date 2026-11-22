"""Evaluate local production captures; exit 0 pass, 1 warn/fail, 2 invalid."""

import argparse
import json

from .production_intelligence import KINDS, MAX_BYTES, analyze_bundle, example
from .training_lab import reject_duplicate_keys


def _reject_constant(_):
    raise ValueError('Non-finite JSON number.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    sample = commands.add_parser('example', help='Print original synthetic input, not production evidence')
    sample.add_argument('kind', nargs='?', choices=KINDS)
    analyze = commands.add_parser('analyze', help='Read one local capture bundle and print findings')
    analyze.add_argument('file')
    args = parser.parse_args(argv)
    try:
        if args.command == 'example':
            report, code = example(args.kind), 0
        else:
            with open(args.file, 'rb') as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError('Capture bundle exceeds byte limit.')
            report = analyze_bundle(json.loads(raw, object_pairs_hook=reject_duplicate_keys,
                                               parse_constant=_reject_constant))
            code = int(report['status'] != 'pass')
    except (OSError, UnicodeError, ValueError, RecursionError, OverflowError):
        # Do not echo private filenames or portions of malformed submissions.
        report = {'schema_version': 1, 'kind': 'production-intelligence', 'status': 'unavailable',
                  'advisory': 'Capture bundle could not be read or validated. Check the local schema and limits.'}
        code = 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, separators=(',', ':')))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
