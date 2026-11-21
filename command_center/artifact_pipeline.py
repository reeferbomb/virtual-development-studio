"""Coordinate independent local asset checks without granting release approval."""

import argparse
import importlib
import json
import re


PROFILES = {'static': ('static',), 'character': ('rig', 'animation'), 'texture': ('texture',)}
_COMPONENTS = {'static': ('lab_artifact', 'inspect_glb'), 'rig': ('lab_rig', 'inspect_rig'),
               'animation': ('lab_animation', 'inspect_animation'), 'texture': ('lab_texture', 'inspect_texture'),
               'engine': ('lab_engine_import', 'inspect_engine_import')}
_STATUSES = ('pass', 'fail', 'unavailable')


def _inspect(component, path):
    module, function = _COMPONENTS[component]
    return getattr(importlib.import_module('.' + module, __package__), function)(path)


def inspect_pipeline(path, profile, *, engine=False):
    """Combine checks for the same file identity; engine work is explicitly opt-in."""
    if profile not in PROFILES or (engine and profile == 'texture'):
        raise ValueError('Choose static, character, or texture; engine import is GLB-only')
    components = list(PROFILES[profile])
    reports = [_inspect(component, path) for component in components]
    checks = []

    def coherent():
        digests = {report['sha256'] for report in reports}
        return (len(digests) == 1 and isinstance(next(iter(digests)), str)
                and re.fullmatch(r'[0-9a-f]{64}', next(iter(digests))) is not None)

    skipped_engine = engine and (not coherent() or any(r['status'] != 'pass' for r in reports))
    if engine and not skipped_engine:
        components.append('engine')
        reports.append(_inspect('engine', path))
    for component, report in zip(components, reports, strict=True):
        status = report['status']
        if status not in _STATUSES:
            raise RuntimeError('Unknown artifact report status')
        checks.append({'id': component, 'measured': status, 'limit': 'pass', 'status': status})
    if skipped_engine:
        checks.append({'id': 'engine', 'measured': 'skipped after preflight', 'limit': 'pass', 'status': 'unavailable'})
    identity = coherent()
    if not identity:
        checks.append({'id': 'asset_identity', 'measured': 'unconfirmed', 'limit': 'same SHA-256',
                       'status': 'unavailable'})
    measured = {f'profiles_{label}': sum(c['status'] == state for c in checks
                                        if c['id'] != 'asset_identity')
                for label, state in (('passed', 'pass'), ('failed', 'fail'), ('unavailable', 'unavailable'))}
    if not identity:
        result = 'unavailable'
    elif measured['profiles_failed']:
        result = 'fail'
    elif measured['profiles_unavailable']:
        result = 'unavailable'
    else:
        result = 'pass'
    return {'profile': f'artifact-pipeline-{profile}-v1', 'status': result,
            'sha256': reports[0]['sha256'] if identity else None,
            'measurements': measured, 'checks': checks, 'reports': reports,
            'note': 'Combined local evidence only. Checks must observe the same SHA-256; an unavailable '
                    'component never passes. Engine import runs only after structural preflight when requested. '
                    'This does not establish visual quality, frame rate, or release approval.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=tuple(PROFILES), required=True)
    parser.add_argument('--engine', action='store_true', help='explicitly run Godot GLB import probe')
    parser.add_argument('path')
    args = parser.parse_args(argv)
    if args.engine and args.profile == 'texture':
        parser.error('--engine is available only for GLB profiles')
    report = inspect_pipeline(args.path, args.profile, engine=args.engine)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
