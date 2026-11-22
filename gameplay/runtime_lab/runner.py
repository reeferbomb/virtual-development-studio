"""Export and optionally execute the fixed, original Godot runtime lab offline."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

from cinematic.production.runner import (_decode_json, _has_engine_error, _json_bytes, _output_path,
                                         _read_regular, _verify_original_files)
from command_center.lab_engine_import import MAX_OUTPUT, _installed_godot, _offline_prefix, _run_bounded, _sandbox_env
from command_center.production_intelligence import analyze_bundle
from command_center.provenance import spec_digest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / 'gameplay/runtime_lab/template'
DOMAINS = ('npc', 'difficulty', 'capture', 'interface', 'presentation', 'replay')
FILES = ('project.godot', 'qa.gd', *(f'{domain}.gd' for domain in DOMAINS))
CHECKS = {
    'npc': ('patrol-motion', 'sight-gates', 'chase-acquisition', 'search-memory', 'reacquisition',
            'memory-expiry', 'patrol-recovery'),
    'difficulty': ('consent-lock', 'hysteresis', 'cooldown-recovery', 'change-receipts', 'tier-limits',
                   'midround-freeze', 'accessibility-parity'),
    'capture': ('lifecycle-start', 'frame-coverage', 'frame-clock', 'gameplay-timeline', 'lifecycle-stop', 'lifecycle-reset'),
    'interface': ('startup-focus', 'menu-navigation', 'desktop-layout', 'handheld-layout', 'settings-restore',
                  'pause-resume', 'retry-state'),
    'presentation': ('environment-clues', 'cue-onset', 'effect-lifetime', 'normal-completion', 'interruption',
                     'accessible-alternatives', 'scene-cleanup'),
    'replay': ('recorded-route', 'deterministic-replay', 'checkpoint-roundtrip', 'retry-reset', 'invalid-rejected',
               'divergence-detected', 'probe-cleanup'),
}
MARKER = b'GRAVEFORGE_RUNTIME_QA '
SCOPE = ('Fixed original Godot headless runtime probes; no human participants, visual quality, '
         'GPU/target-device performance, accessibility or release certification.')


def _parse_marker(raw, code, digest, *, domains=DOMAINS, checks=CHECKS, marker=MARKER):
    if len(raw) > MAX_OUTPUT or _has_engine_error(raw):
        raise ValueError('Godot emitted an error or exceeded the output limit.')
    lines = [line for line in raw.splitlines() if line.lstrip().startswith(marker.rstrip())]
    if len(lines) != 1 or not lines[0].startswith(marker):
        raise ValueError('Expected exactly one Runtime Lab marker.')
    doc = _decode_json(lines[0][len(marker):], 'Runtime Lab marker')
    if (type(doc) is not dict or set(doc) != {'schema_version', 'source_sha256', 'passed', 'reports'}
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or doc['source_sha256'] != digest or type(doc['passed']) is not bool
            or type(doc['reports']) is not list or len(doc['reports']) != len(domains)):
        raise ValueError('Runtime marker does not match the exported source or expected domains.')
    all_passed = True
    for domain, report in zip(domains, doc['reports'], strict=True):
        if (type(report) is not dict or set(report) != {'id', 'checks', 'metrics'} or report['id'] != domain
                or type(report['metrics']) is not dict or type(report['checks']) is not list
                or not 4 <= len(report['checks']) <= 8):
            raise ValueError('Unexpected runtime domain or check coverage.')
        seen = set()
        for row in report['checks']:
            if (type(row) is not dict or set(row) != {'id', 'passed', 'detail'}
                    or type(row['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', row['id'])
                    or row['id'] in seen or type(row['passed']) is not bool
                    or type(row['detail']) is not str or not row['detail'].strip() or len(row['detail']) > 2048):
                raise ValueError('Invalid or duplicate runtime check.')
            seen.add(row['id'])
            all_passed &= row['passed']
        if seen != set(checks[domain]):
            raise ValueError('Runtime domain has different check IDs from the fixed probe contract.')
    if doc['passed'] != all_passed or code != (0 if all_passed else 1):
        raise ValueError('Runtime marker checks, summary and exit code disagree.')
    return doc


def _export(output, *, template=TEMPLATE, files=FILES):
    if template.resolve() != template or not template.is_relative_to(ROOT):
        raise ValueError('Runtime template must be inside the Studio checkout.')
    sources = {name: _read_regular(template / name, 256 * 1024, 'Runtime template') for name in files}
    inventory = [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                 for name, data in sorted(sources.items())]
    output.mkdir(mode=0o700)
    (output / 'reports').mkdir(mode=0o700)
    (output / 'reports/.gdignore').touch()
    for name, data in sources.items():
        (output / name).write_bytes(data)
    return inventory


def _runtime(output, digest, *, parser=_parse_marker, scope=SCOPE, log_name='qa.log'):
    result = {'status': 'unavailable', 'scope': scope}
    godot, offline = _installed_godot(), _offline_prefix()
    if godot is None or offline is None:
        return dict(result, reason='Local Godot 4 and Linux network isolation are required.')
    try:
        with tempfile.TemporaryDirectory(prefix='.engine-', dir=output / 'reports') as directory:
            env = _sandbox_env(Path(directory))
            version = _run_bounded([*offline, godot, '--version'], output, env, timeout=5)
            if version.returncode or not re.fullmatch(rb'4\.\d+(?:\.\d+)?\.[A-Za-z0-9_.-]{1,100}', version.stdout.strip()):
                return dict(result, reason='Could not identify the isolated Godot 4 executable.')
            result.update(status='failed', godot_version=version.stdout.strip().decode('ascii'))
            qa = _run_bounded([*offline, godot, '--headless', '--path', str(output), '--script', 'res://qa.gd', '--', digest],
                              output, env, timeout=45, max_output=MAX_OUTPUT)
            (output / 'reports' / log_name).write_bytes(qa.stdout)
            result['log_sha256'] = hashlib.sha256(qa.stdout).hexdigest()
            result['qa'] = parser(qa.stdout, qa.returncode, digest)
            result['status'] = 'passed' if result['qa']['passed'] else 'failed'
            return result
    except (ValueError, OSError, RuntimeError) as exc:
        return dict(result, reason=str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Local runtime I/O failed.')


def run(output, *, engine=False):
    """Only generate into a fresh private path; never execute an input project."""
    output = _output_path(output)
    inventory = _export(output)
    digest = spec_digest(inventory)
    report = {'schema_version': 1, 'status': 'exported', 'files': inventory, 'source_sha256': digest,
              'runtime': {'status': 'not_requested', 'scope': SCOPE}}
    if engine:
        runtime = _runtime(output, digest)
        try:
            _verify_original_files(output, inventory)
            if runtime['status'] == 'passed':
                captures = {row['id']: row['metrics']['capture'] for row in runtime['qa']['reports']
                            if row['id'] in ('capture', 'interface') and 'capture' in row['metrics']}
                if set(captures) != {'capture', 'interface'}:
                    raise ValueError('Runtime frame or interface capture is missing.')
                bundle = {'schema_version': 1, 'captures': {'frame': captures['capture'], 'ui': captures['interface']}}
                intelligence = analyze_bundle(bundle)
                (output / 'reports/captures.json').write_bytes(_json_bytes(bundle))
                (output / 'reports/intelligence.json').write_bytes(_json_bytes(intelligence))
                runtime['intelligence_status'] = intelligence['status']
                runtime['capture_sha256'] = intelligence['input_sha256']
        except (ValueError, OSError) as exc:
            runtime.update(status='failed', reason=str(exc) if isinstance(exc, ValueError) else 'Local evidence I/O failed.')
        report.update(status=runtime['status'], runtime=runtime)
    (output / 'reports/report.json').write_bytes(_json_bytes(report))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='new private directory outside the checkout')
    parser.add_argument('--engine', action='store_true', help='explicitly run fixed isolated Godot QA')
    args = parser.parse_args(argv)
    try:
        report = run(args.output, engine=args.engine)
    except (ValueError, OSError):
        print(json.dumps({'status': 'unavailable', 'reason': 'Export requires a new private directory and trusted template files.'}))
        return 2
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return {'exported': 0, 'passed': 0, 'failed': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    sys.exit(main())
