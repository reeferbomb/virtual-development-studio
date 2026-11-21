"""Read and review private Academy practice records in an existing Studio workspace."""

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .projects import _safe_path
from .training_lab import MAX_BYTES, reject_duplicate_keys
from .training_progress import summarize_progress
from .training_records import TrainingRecordStore


ROOT = Path(__file__).resolve().parents[1]


class RecordsParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse may echo unrecognized private notes or filenames in its message.
        self.exit(2, json.dumps({'error': 'Invalid command arguments. ' + self.format_usage().strip()}) + '\n')


def read_submission(path):
    def open_nonblocking(name, flags):
        return os.open(name, flags | os.O_NONBLOCK)

    def reject_constant(value):
        raise ValueError('Submission numbers must be finite.')

    try:
        with open(path, 'rb', opener=open_nonblocking) as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError('Choose a regular submission file.')
            raw = source.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError('Could not read the submission file.') from exc
    if len(raw) > MAX_BYTES:
        raise ValueError('Submission file exceeds the byte limit.')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicate_keys,
                          parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Expected bounded UTF-8 JSON in the submission file.') from exc


def main(argv=None):
    parser = RecordsParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True, help='existing private workspace outside the checkout')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='list saved assessments and their reviews')
    commands.add_parser('progress', help='summarize practice records by role and exercise')
    record = commands.add_parser('record', help='assess a JSON submission and save the result')
    record.add_argument('exercise_id')
    record.add_argument('role')
    record.add_argument('file', metavar='FILE', help='local UTF-8 JSON submission file')
    review = commands.add_parser('review', help='save a decision for a recorded submission')
    review.add_argument('record_id')
    review.add_argument('reviewer_role')
    review.add_argument('decision', choices=('accepted', 'rejected'))
    review.add_argument('note')
    for command in (record, review):
        command.add_argument('--expected-revision', required=True, type=int, help='revision from the latest list')
    args = parser.parse_args(argv)

    try:
        # Preserve the store's no-follow boundary while accepting ../workspace.
        workspace = Path(os.path.abspath(_safe_path(args.workspace.absolute())))
        if workspace.is_relative_to(ROOT) or not workspace.is_dir():
            raise ValueError('Choose an existing private workspace outside the Studio checkout.')
        store = TrainingRecordStore(workspace)
        if args.command == 'list':
            result = store.read()
        elif args.command == 'progress':
            result = summarize_progress(store.read())
        else:
            if args.command == 'record':
                action = {'op': 'record', 'exercise_id': args.exercise_id, 'role': args.role,
                          'submission': read_submission(args.file)}
            else:
                action = {'op': 'review', 'record_id': args.record_id, 'reviewer_role': args.reviewer_role,
                          'decision': args.decision, 'note': args.note}
            result = store.apply({'expected_revision': args.expected_revision, 'action': action})
        print(json.dumps(result, indent=2, allow_nan=False))
    except (FileExistsError, ValueError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2
    except (OSError, RecursionError):
        print(json.dumps({'error': 'Could not access the private training records.'}), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
