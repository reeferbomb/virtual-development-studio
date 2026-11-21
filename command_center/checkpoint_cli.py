"""Read or save a project's local active-work checkpoint."""
import argparse
import json
import sys
from pathlib import Path

from .checkpoints import CheckpointStore
from .projects import ProjectStore


ROOT = Path(__file__).resolve().parents[1]
MAX_INPUT_BYTES = 1024 * 1024


class CheckpointParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, json.dumps({'error': message}) + '\n')


def read_input(source):
    if source == '-':
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        with Path(source).open('rb') as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('Checkpoint input exceeds 1 MiB')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object')
    return value


def main():
    parser = CheckpointParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True,
                        help='workspace used by the Studio command center')
    commands = parser.add_subparsers(dest='command', required=True)
    show = commands.add_parser('show', help='show the latest checkpoint and remaining active time')
    show.add_argument('project_id')
    save = commands.add_parser('save', help='save a checkpoint for the expected revision')
    save.add_argument('project_id')
    save.add_argument('--input', required=True, metavar='FILE', help='JSON file or - for standard input')
    args = parser.parse_args()

    try:
        store = CheckpointStore(ProjectStore(ROOT, args.workspace))
        if args.command == 'show':
            result = store.get(args.project_id)
        else:
            result = store.save(args.project_id, read_input(args.input))
        print(json.dumps(result, indent=2, allow_nan=False))
    except (OSError, ValueError, RecursionError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
