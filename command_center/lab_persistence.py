"""Replay a bounded save-slot migration, interrupted commit and checkpoint recovery in memory."""

import json

from .lab_gameplay import _array, _choice, _criterion, _integer, _object, _result


TRACK = {
    'id': 'persistence',
    'title': 'Save, load and checkpoint recovery',
    'roles': ['architecture', 'gameplay', 'verification', 'build_operations'],
    'workflow': [
        'Version the save schema. Give checkpoints and one-time rewards stable IDs. Identify persistent '
        'fields, derived totals and transient state such as an in-progress death animation.',
        'Decode and migrate an older save into a candidate state. Validate IDs, field ranges, reward '
        'uniqueness and derived inventory totals before replacing the running world.',
        'Write a complete candidate into a temporary file in the destination directory. Flush it as '
        'required on the target platform, retain the last good generation, then atomically replace the slot.',
        'At death, restore the last committed checkpoint before replaying rewards. If the primary save is '
        'invalid, try the backup. If both fail, report the error and preserve the running state.',
    ],
    'deliverables': [
        'Versioned save-field and migration table with one valid old save and its expected current state.',
        'Checkpoint trace with slot generations, interruption points, retry outcomes and recovery messages.',
    ],
    'verification': [
        'Round-trip current saves, migrate supported older versions and reject unknown versions before mutation.',
        'Interrupt a save before replacement, retry after death and attempt to collect the same reward twice.',
        'Test truncated and internally inconsistent saves, backup fallback and recovery when both slots fail. '
        'Verify atomic replacement and durability on the actual target filesystem separately.',
    ],
    'exercise': 'Predict the restored checkpoint, reward ledger and coin balance across a schema migration, '
                'interrupted replacement, death, retry and corrupt primary and backup slots.',
}

# Stable order is part of the v1 bitmap and the v2 canonical reward ledger.
REWARDS = {'dock': 2, 'kiln': 3, 'vault': 5, 'spire': 7}
ROOMS = tuple(REWARDS)
OBSERVATIONS = ('migration', 'interruption', 'retry', 'fallback', 'unreadable')


def _state(checkpoint, claimed, coins):
    return {'version': 2, 'checkpoint': checkpoint, 'claimed': claimed, 'coins': coins}


def _observation(source, state):
    return {'source': source, 'state': state}


EXERCISES = [{
    'id': 'persistence', 'title': 'Recover the beacon checkpoint',
    'brief': 'Supply a v1 primary save and a route of two distinct, previously unclaimed beacons. '
             'In order, dock, kiln, vault and spire have IDs 0–3 and one-time rewards of 2, 3, 5 and 7 coins. '
             'In v1, checkpoint_id is a beacon ID and bit i of claimed_mask records reward i. In v2, use the '
             'checkpoint name, claimed names in ID order and their total coins. Visiting a beacon selects it '
             'as checkpoint and collects its reward once. Predict the source and v2 state at five observations. '
             '(1) migration: load the v1 primary. (2) interruption: visit and save the first beacon, visit the '
             'second, interrupt its save before replacement, then restart and load. (3) retry: revisit the '
             'second beacon, finish its save, die, reload and collect there again. Each complete save rotates '
             'the former primary to backup. (4) fallback: change the primary coin total by one and load. '
             '(5) unreadable: visit the second beacon again without saving, truncate the backup, then try to '
             'load. Use source primary, backup or unchanged to report which state survives.',
    'criteria': [
        _criterion('migration', 'Decode the legacy checkpoint ID and reward bitmap into a valid v2 ledger'),
        _criterion('atomic-write', 'Recover the first committed checkpoint after interrupting a different save'),
        _criterion('death-retry', 'Restore the second checkpoint at death and award its pickup exactly once'),
        _criterion('recovery', 'Fall back after a balance mismatch and preserve live progress when both slots fail'),
    ],
    'example': {
        'legacy': {'version': 1, 'checkpoint_id': 0, 'claimed_mask': 1},
        'route': ['kiln', 'spire'],
        'expected': {
            'migration': _observation('primary', _state('dock', ['dock'], 2)),
            'interruption': _observation('primary', _state('kiln', ['dock', 'kiln'], 5)),
            'retry': _observation('primary', _state('spire', ['dock', 'kiln', 'spire'], 12)),
            'fallback': _observation('backup', _state('kiln', ['dock', 'kiln'], 5)),
            'unreadable': _observation('unchanged', _state('spire', ['dock', 'kiln', 'spire'], 12)),
        },
    },
}]


def _migrate(record):
    _object(record, ('version', 'checkpoint_id', 'claimed_mask'), 'legacy')
    _integer(record['version'], 1, 1, 'legacy.version')
    _integer(record['checkpoint_id'], 0, 3, 'legacy.checkpoint_id')
    _integer(record['claimed_mask'], 0, 15, 'legacy.claimed_mask')
    claimed = [room for index, room in enumerate(ROOMS) if record['claimed_mask'] & (1 << index)]
    return _state(ROOMS[record['checkpoint_id']], claimed, sum(REWARDS[room] for room in claimed))


def _validate_shape(state, where):
    _object(state, ('version', 'checkpoint', 'claimed', 'coins'), where)
    _integer(state['version'], 2, 2, where + '.version')
    _choice(state['checkpoint'], ROOMS, where + '.checkpoint')
    _array(state['claimed'], 4, where + '.claimed')
    for room in state['claimed']:
        _choice(room, ROOMS, where + '.claimed')
    _integer(state['coins'], 0, 100, where + '.coins')


def _load(slots, live):
    for source, raw in zip(('primary', 'backup'), slots, strict=True):
        if raw is None:
            continue
        try:
            record = json.loads(raw)
            if type(record) is not dict:
                continue
            if record.get('version') == 1:
                record = _migrate(record)
            _validate_shape(record, source)
        except ValueError:
            continue
        claimed = [room for room in ROOMS if room in record['claimed']]
        if claimed == record['claimed'] and sum(REWARDS[room] for room in claimed) == record['coins']:
            return _observation(source, record)
    return _observation('unchanged', live)


def _visit(live, beacon):
    claimed = [room for room in ROOMS if room == beacon or room in live['claimed']]
    coins = live['coins'] + (0 if beacon in live['claimed'] else REWARDS[beacon])
    return _state(beacon, claimed, coins)


def _save(slots, live, interrupted=False):
    staged = json.dumps(live)
    if interrupted:
        return slots
    return staged, slots[0]


def _replay(legacy, first, second):
    slots = (json.dumps(legacy), None)
    migration = _load(slots, None)
    live = _visit(migration['state'], first)
    slots = _save(slots, live)
    live = _visit(live, second)
    slots = _save(slots, live, interrupted=True)
    interruption = _load(slots, None)  # Restart discards the live world and the staged write.

    live = _visit(interruption['state'], second)
    slots = _save(slots, live)
    respawn = _load(slots, None)  # Death clears volatile state.
    retry = _observation(respawn['source'], _visit(respawn['state'], second))

    damaged = json.loads(slots[0])
    damaged['coins'] += 1
    slots = (json.dumps(damaged), slots[1])
    fallback = _load(slots, retry['state'])
    live = _visit(fallback['state'], second)
    unreadable = _load((slots[0], slots[1][:-1]), live)
    return dict(migration=migration, interruption=interruption, retry=retry,
                fallback=fallback, unreadable=unreadable)


def assess(exercise_id, submission):
    if exercise_id != 'persistence':
        raise ValueError('Unknown persistence lab exercise')
    _object(submission, ('legacy', 'route', 'expected'), 'Persistence')
    # A malformed source submission is an input error. Damage introduced during the replay is recoverable.
    _migrate(submission['legacy'])
    _array(submission['route'], 2, 'route', minimum=2)
    for room in submission['route']:
        _choice(room, ROOMS, 'route beacon')
    expected = submission['expected']
    _object(expected, OBSERVATIONS, 'expected')
    for name in OBSERVATIONS:
        _object(expected[name], ('source', 'state'), name)
        _choice(expected[name]['source'], ('primary', 'backup', 'unchanged'), name + '.source')
        _validate_shape(expected[name]['state'], name + '.state')

    first, second = submission['route']
    actual = _replay(submission['legacy'], first, second)
    fresh = len({first, second} - set(actual['migration']['state']['claimed'])) == 2
    checks = []
    for criterion, names in [('migration', ('migration',)), ('atomic-write', ('interruption',)),
                             ('death-retry', ('retry',)), ('recovery', ('fallback', 'unreadable'))]:
        covered = criterion == 'migration' or fresh
        matches = all(expected[name] == actual[name] for name in names)
        details = [f'{name}: {json.dumps(actual[name], sort_keys=True)}.' for name in names]
        if not covered:
            details.append('Visit two distinct, previously unclaimed beacons to exercise checkpoint recovery.')
        checks.append(_result(criterion, covered and matches, ' '.join(details)))
    return checks
