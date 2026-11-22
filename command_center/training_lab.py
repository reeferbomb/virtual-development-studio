"""Versioned, deterministic data-only practice assessments for Graveforge Academy.

This evaluates structured submissions, not arbitrary source code, files, game
builds, creative merit, model weights, or specialist competency. It is stateless.
"""

import json
import math
from copy import deepcopy

from .provenance import spec_digest
from .studio_curriculum import curriculum


MAX_BYTES = 128 * 1024
MAX_NODES = 20_000
MAX_DEPTH = 12
MAX_STRING = 4096
# Bump on any change to rubric or evaluator behavior, even if catalog text is
# unchanged: saved records are re-evaluated only under the exact current digest.
VERSION = 6


def reject_duplicate_keys(pairs):
    """Reject ambiguous declarations at JSON decoding boundaries."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('A JSON object contains a duplicate field')
        result[key] = value
    return result


def _validate_data(value):
    """Restrict the evaluator boundary to bounded finite JSON without coercion."""
    count, size = 0, 0

    def account(length):
        nonlocal size
        size += length
        if size > MAX_BYTES:
            raise ValueError('Practice submission exceeds the byte limit')

    def scalar(node):
        try:
            account(len(json.dumps(node, ensure_ascii=False, allow_nan=False).encode('utf-8')))
        except UnicodeError as exc:
            raise ValueError('Invalid Unicode in the practice submission') from exc

    def visit(node, depth):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('The practice submission exceeds the structural limit')
        if node is None or type(node) is bool:
            scalar(node)
            return
        if type(node) is int and abs(node) <= 10 ** 12:
            scalar(node)
            return
        if type(node) is float and math.isfinite(node) and abs(node) <= 10 ** 12:
            scalar(node)
            return
        if type(node) is str and len(node) <= MAX_STRING:
            scalar(node)
            return
        if type(node) is list:
            account(2 + max(0, len(node) - 1))
            for item in node:
                visit(item, depth + 1)
            return
        if type(node) is dict:
            account(2 + len(node) + max(0, len(node) - 1))
            for key, item in node.items():
                if type(key) is not str:
                    raise ValueError('Practice object keys must be strings')
                visit(key, depth + 1)
                visit(item, depth + 1)
            return
        raise ValueError('Expected finite, bounded JSON practice data')

    if type(value) is not dict:
        raise ValueError('Practice submission must be a JSON object')
    visit(value, 0)


def _definitions():
    # Imported lazily so training and project operations do not depend on lab initialization.
    from . import lab_content, lab_design, lab_gameplay, lab_interface, studio_curriculum
    modules = (lab_content, lab_design, lab_gameplay, lab_interface, *studio_curriculum.extension_modules())
    entries = {}
    for module in modules:
        for exercise in module.EXERCISES:
            key = exercise['id']
            if key in entries:
                raise RuntimeError('Duplicate academy exercise ID')
            entries[key] = (exercise, module.assess)
    tracks = curriculum()['tracks']
    if set(entries) != {track['id'] for track in tracks}:
        raise RuntimeError('Academy exercise IDs do not match the curriculum')
    return {track['id']: (dict(entries[track['id']][0], roles=track['roles']), entries[track['id']][1])
            for track in tracks}


def _catalog(definitions):
    body = {
        'version': VERSION,
        'exercises': [deepcopy(exercise) for exercise, evaluator in definitions.values()],
        'note': 'Practice structured game-production artifacts with deterministic rubric checks. Reference examples are teaching fixtures, not proof of agent competence, visual quality or release readiness. Assessments are not persisted.',
    }
    return dict(body, lab_sha256=spec_digest(body))


def lab_catalog():
    return _catalog(_definitions())


def assess_submission(exercise_id, submission):
    if not isinstance(exercise_id, str):
        raise ValueError('Expected a practice exercise ID')
    definitions = _definitions()
    if exercise_id not in definitions:
        raise ValueError('Unknown practice exercise')
    _validate_data(submission)
    exercise, evaluator = definitions[exercise_id]
    catalog = _catalog(definitions)
    submission_digest = spec_digest(submission)
    try:
        evaluated = evaluator(exercise_id, deepcopy(submission))
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError('Invalid practice submission schema') from exc
    criteria = exercise['criteria']
    if (not isinstance(evaluated, list) or len(evaluated) != len(criteria)
            or any(not isinstance(c, dict) or set(c) != {'id', 'status', 'detail'}
                   or c['status'] not in ('pass', 'fail') or not isinstance(c['detail'], str)
                   or not 1 <= len(c['detail']) <= 2000 for c in evaluated)
            or [c['id'] for c in evaluated] != [c['id'] for c in criteria]):
        raise RuntimeError('Evaluator violated its rubric contract')
    checks = [dict(result, label=criterion['label']) for result, criterion in zip(evaluated, criteria, strict=True)]
    passed = sum(c['status'] == 'pass' for c in checks)
    failed = len(checks) - passed
    body = {
        'version': VERSION, 'lab_sha256': catalog['lab_sha256'], 'exercise_id': exercise_id,
        'submission_sha256': submission_digest, 'status': 'fail' if failed else 'pass',
        'summary': {'pass': passed, 'fail': failed}, 'checks': checks,
        'note': 'Only these structural or simulated criteria were measured; no human playtest, artistic quality, model training or release certification is implied.',
    }
    return dict(body, assessment_sha256=spec_digest(body))
