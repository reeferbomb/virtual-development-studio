"""Assess a declared game-audio cue sheet and simulated playback observations."""

import math
import re
import unicodedata

from .lab_design import _identifier
from .lab_gameplay import _array, _choice, _integer, _object, _result


TRACK = {
    'id': 'game-audio', 'title': 'Game audio, mixing and dialogue playback',
    'roles': ['content', 'gameplay', 'ui', 'verification'],
    'workflow': [
        'List the cues a player needs to hear, the gameplay events that trigger them and who owns each source recording.',
        'Route voices, ambience and effects to named buses. Estimate peak headroom where cues overlap and automate ambience ducking under speech.',
        'Write speaker captions against audible line timing, including skipped dialogue. Specify loop, stop and interruption behavior.',
        'Capture playback against the exact build and audio settings. Listen for clicks, masking and intelligibility on the target output.',
    ],
    'deliverables': [
        'Event-to-asset cue sheet with bus gains, playback rules, recording credits, permission and source digests.',
        'Subtitle and ducking timelines with a playback trace covering overlap, loop wrap, interruption and release.',
    ],
    'verification': [
        'Compare expected active voices, playheads and gain changes at transitions. Check the conservative peak estimate against the mix budget.',
        'Record actual engine playback and listening observations separately from the simulated trace. Review subtitle synchronization and loop seams.',
    ],
    'exercise': 'Score a short scene with a looping ambience bed, a one-shot effect and an interrupted voice line.',
}

BUSES = ('ambience', 'dialogue', 'effects')
TIMELINE_MS = 120_000


def _asset(identifier, bus, duration, peak, loop, description, digest_digit):
    return {'id': identifier, 'bus': bus, 'duration_ms': duration, 'peak_dbfs': peak, 'loop': loop,
            'source': description, 'credit': 'Academy fixture', 'license': 'Synthetic teaching declaration',
            'sha256': digest_digit * 64}


def _observation(at_ms, gain_db, **playheads):
    return {'at_ms': at_ms, 'ambience_duck_db': gain_db, 'playheads_ms': playheads}


EXERCISES = [{
    'id': 'game-audio', 'title': 'Score the harbor signal',
    'brief': 'Plan a scene up to 120000 ms with 1–16 assets and 1–32 events. Give each asset a source, credit, '
             'license and lowercase SHA-256. IDs use 1–32 lowercase letters, digits, hyphens or underscores '
             'and start with a letter. Use whole milliseconds and whole dB. Bus gains and clip peaks range '
             'from -60 to 0. Each event includes its start and excludes its end. A complete one-shot lasts '
             'the clip duration, an interrupt cuts a one-shot short, and a stop ends a loop. '
             'Subtitle every dialogue event with speaker and text. Use up to 32 subtitles and 32 nonoverlapping '
             'ambience duck windows. For each simultaneous voice, add source peak, bus gain and applicable '
             'duck gain in dB, convert to linear amplitude (10 to the power of dB/20) and sum. '
             'Provide up to 160 playback observations. At each event or duck boundary and each loop’s first wrap, '
             'predict all active event playheads and ambience duck gain. Example sources and fingerprints are fictional. '
             'The simulation does not read or play audio.',
    'criteria': [
        {'id': 'routing', 'label': 'Use each asset and route events through all three buses.'},
        {'id': 'provenance', 'label': 'Declare the source, credit, permission or license and SHA-256 for each asset.'},
        {'id': 'transport', 'label': 'Complete a one-shot, interrupt another early, and stop a loop after it wraps.'},
        {'id': 'subtitles', 'label': 'Match each spoken event with one caption within 100 ms of both playback boundaries.'},
        {'id': 'ducking', 'label': 'Play ambience at least 6 dB below its bus gain under every line and restore gain outside speech.'},
        {'id': 'headroom', 'label': 'Keep the peak amplitude sum at or below -3 dBFS across the cue sheet.'},
        {'id': 'playback', 'label': 'Predict active playheads and ambience gain at every required transition.'},
    ],
    'example': {
        'assets': [_asset('surf', 'ambience', 1000, -6, True, 'Invented shore loop', '1'),
                   _asset('hail', 'dialogue', 1500, -3, False, 'Invented harbor hail', '2'),
                   _asset('brass', 'effects', 200, -3, False, 'Invented bell strike', '3'),
                   _asset('alert', 'dialogue', 1100, -3, False, 'Invented lookout warning', '4')],
        'bus_gain_db': {'ambience': -6, 'dialogue': -6, 'effects': -12},
        'events': [
            {'id': 'bed', 'asset': 'surf', 'start_ms': 0, 'end_ms': 4000, 'ending': 'stop'},
            {'id': 'call', 'asset': 'hail', 'start_ms': 1000, 'end_ms': 2500, 'ending': 'complete'},
            {'id': 'chime', 'asset': 'brass', 'start_ms': 1500, 'end_ms': 1700, 'ending': 'complete'},
            {'id': 'warning', 'asset': 'alert', 'start_ms': 3000, 'end_ms': 3500, 'ending': 'interrupt'},
        ],
        'subtitles': [
            {'event': 'call', 'speaker': 'Keeper', 'text': 'The boat is here.', 'start_ms': 1000, 'end_ms': 2500},
            {'event': 'warning', 'speaker': 'Lookout', 'text': 'Wait!', 'start_ms': 3000, 'end_ms': 3500},
        ],
        'ducking': [{'start_ms': 1000, 'end_ms': 2500, 'gain_db': -9},
                    {'start_ms': 3000, 'end_ms': 3500, 'gain_db': -9}],
        'observations': [
            _observation(0, 0, bed=0), _observation(1000, -9, bed=0, call=0),
            _observation(1500, -9, bed=500, call=500, chime=0), _observation(1700, -9, bed=700, call=700),
            _observation(2500, 0, bed=500), _observation(3000, -9, bed=0, warning=0),
            _observation(3500, 0, bed=500), _observation(4000, 0),
        ],
    },
}]


def _bounded_text(value, limit, label):
    if type(value) is not str or len(value) > limit:
        raise ValueError(f'{label} must be a string of at most {limit} characters.')


def _visible(value):
    return any(ch.isprintable() and not ch.isspace() and unicodedata.category(ch)[0] != 'M' for ch in value)


def _interval(row):
    for field in ('start_ms', 'end_ms'):
        _integer(row[field], 0, TIMELINE_MS, field)
    if row['start_ms'] >= row['end_ms']:
        raise ValueError('Every audio interval must have positive duration.')


def _index(rows, field):
    indexed = {row[field]: row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError(f'Duplicate audio {field}.')
    return indexed


def _parse(plan):
    _object(plan, ('assets', 'events', 'bus_gain_db', 'subtitles', 'ducking', 'observations'), 'Cue sheet')
    _object(plan['bus_gain_db'], BUSES, 'Bus gains')
    for bus, gain in plan['bus_gain_db'].items():
        _integer(gain, -60, 0, bus)
    _array(plan['assets'], 16, 'Assets', minimum=1)
    for asset in plan['assets']:
        _object(asset, ('id', 'bus', 'duration_ms', 'peak_dbfs', 'loop', 'source', 'credit', 'license', 'sha256'), 'Asset')
        _identifier(asset['id'], 'Asset ID')
        _choice(asset['bus'], BUSES, 'Asset bus')
        _integer(asset['duration_ms'], 1, TIMELINE_MS, 'Asset duration')
        _integer(asset['peak_dbfs'], -60, 0, 'Source peak')
        if type(asset['loop']) is not bool:
            raise ValueError('An asset loop flag must be boolean.')
        for field in ('source', 'credit', 'license', 'sha256'):
            _bounded_text(asset[field], 240, field)
    _array(plan['events'], 32, 'Events', minimum=1)
    for cue in plan['events']:
        _object(cue, ('id', 'asset', 'start_ms', 'end_ms', 'ending'), 'Event')
        _identifier(cue['id'], 'Event ID')
        _identifier(cue['asset'], 'Source asset ID')
        _choice(cue['ending'], ('stop', 'interrupt', 'complete'), 'Event ending')
        _interval(cue)
    _array(plan['subtitles'], 32, 'Subtitles')
    for caption in plan['subtitles']:
        _object(caption, ('event', 'speaker', 'text', 'start_ms', 'end_ms'), 'Subtitle')
        _identifier(caption['event'], 'Caption event')
        _bounded_text(caption['speaker'], 80, 'Speaker')
        _bounded_text(caption['text'], 240, 'Subtitle')
        _interval(caption)
    _array(plan['ducking'], 32, 'Ducking windows')
    for window in plan['ducking']:
        _object(window, ('start_ms', 'end_ms', 'gain_db'), 'Duck window')
        _interval(window)
        _integer(window['gain_db'], -60, 0, 'Duck gain')
    windows = sorted(plan['ducking'], key=lambda row: row['start_ms'])
    if any(a['end_ms'] > b['start_ms'] for a, b in zip(windows, windows[1:])):
        raise ValueError('Ducking windows must not overlap.')
    _array(plan['observations'], 160, 'Playback observations')
    for row in plan['observations']:
        _object(row, ('at_ms', 'playheads_ms', 'ambience_duck_db'), 'Observation')
        _integer(row['at_ms'], 0, TIMELINE_MS, 'Observation time')
        _integer(row['ambience_duck_db'], -60, 0, 'Observed ambience duck gain')
        offsets = row['playheads_ms']
        if type(offsets) is not dict or len(offsets) > 32:
            raise ValueError('Provide a map of up to 32 playheads.')
        for name, offset in offsets.items():
            _identifier(name, 'Active event ID')
            _integer(offset, 0, TIMELINE_MS, 'Observed playhead')
    return (_index(plan['assets'], 'id'), _index(plan['events'], 'id'),
            _index(plan['subtitles'], 'event'), windows, _index(plan['observations'], 'at_ms'))


def _transport(events, assets):
    valid = 0
    demonstrated = set()
    for cue in events.values():
        asset = assets.get(cue['asset'])
        if not asset:
            continue
        elapsed = cue['end_ms'] - cue['start_ms']
        duration = asset['duration_ms']
        if asset['loop']:
            if cue['ending'] == 'stop':
                valid += 1
                if elapsed > duration:
                    demonstrated.add('wrap')
        elif ((cue['ending'] == 'complete' and elapsed == duration)
              or (cue['ending'] == 'interrupt' and elapsed < duration)):
            valid += 1
            demonstrated.add(cue['ending'])
    return _result('transport', valid == len(events) and len(demonstrated) == 3,
                   f'{valid}/{len(events)} valid endings. Demonstrated {", ".join(sorted(demonstrated)) or "none"}.')


def _subtitles(events, assets, captions):
    spoken = {name for name, cue in events.items()
              if cue['asset'] in assets and assets[cue['asset']]['bus'] == 'dialogue'}
    matched = 0
    for name in spoken & captions.keys():
        caption, cue = captions[name], events[name]
        if (_visible(caption['speaker']) and _visible(caption['text'])
                and all(abs(caption[f] - cue[f]) <= 100 for f in ('start_ms', 'end_ms'))
                and caption['start_ms'] < cue['end_ms'] and caption['end_ms'] > cue['start_ms']):
            matched += 1
    return _result('subtitles', bool(spoken) and matched == len(spoken) == len(captions),
                   f'{matched}/{len(spoken)} spoken events have a visible, synchronized speaker caption. '
                   f'{len(captions)} captions submitted.')


def _active(row, timestamp):
    return row['start_ms'] <= timestamp < row['end_ms']


def _mix_checks(events, assets, gains, windows, observations):
    # Gains are constant between adjacent boundaries. Inspect every boundary even if no observation was submitted.
    required = {row[f] for row in [*events.values(), *windows] for f in ('start_ms', 'end_ms')}
    resolved = all(cue['asset'] in assets for cue in events.values())
    for cue in events.values():
        asset = assets.get(cue['asset'])
        if asset and asset['loop']:
            wrap = cue['start_ms'] + asset['duration_ms']
            if wrap < cue['end_ms']:
                required.add(wrap)

    max_amplitude, peak_at, duck_errors, spoken_ms, matching = 0, 0, 0, 0, 0
    times = sorted(required | observations.keys())
    for i, timestamp in enumerate(times):
        duck = next((row['gain_db'] for row in windows if _active(row, timestamp)), 0)
        playheads, amplitudes, buses = {}, [], set()
        for name, cue in events.items():
            asset = assets.get(cue['asset'])
            if asset and _active(cue, timestamp):
                bus = asset['bus']
                buses.add(bus)
                offset = timestamp - cue['start_ms']
                playheads[name] = offset % asset['duration_ms'] if asset['loop'] else offset
                db = asset['peak_dbfs'] + gains[bus] + (duck if bus == 'ambience' else 0)
                amplitudes.append(10 ** (db / 20))
        amplitude = math.fsum(amplitudes)
        if amplitude > max_amplitude:
            max_amplitude, peak_at = amplitude, timestamp
        interval = times[i + 1] - timestamp if i + 1 < len(times) else 0
        if 'dialogue' in buses:
            spoken_ms += interval
            if duck > -6 or 'ambience' not in buses:
                duck_errors += interval
        elif duck != 0:
            duck_errors += interval
        if timestamp in observations:
            observed = observations[timestamp]
            matching += observed['playheads_ms'] == playheads and observed['ambience_duck_db'] == duck

    covered = len(required & observations.keys())
    peak_detail = (f'Conservative summed peak {20 * math.log10(max_amplitude):+.2f} dBFS at {peak_at} ms.'
                   if resolved else 'Peak unavailable because an event references a missing asset.')
    return [
        _result('ducking', resolved and spoken_ms > 0 and duck_errors == 0,
                f'{spoken_ms} ms with speech. {duck_errors} ms with missing bed, insufficient duck or unreleased gain.'),
        _result('headroom', resolved and max_amplitude <= 10 ** (-3 / 20), peak_detail),
        _result('playback', resolved and covered == len(required) and matching == len(observations),
                f'{covered}/{len(required)} required times covered. {matching}/{len(observations)} playback observations match.'),
    ]


def assess(exercise_id, submission):
    if exercise_id != 'game-audio':
        raise ValueError('Unknown audio exercise.')
    assets, events, captions, windows, observations = _parse(submission)
    used = {cue['asset'] for cue in events.values()}
    routed = {assets[asset]['bus'] for asset in used & assets.keys()}
    credited = sum(all(_visible(asset[f]) for f in ('source', 'credit', 'license'))
                   and bool(re.fullmatch('[0-9a-f]{64}', asset['sha256'])) for asset in assets.values())
    return [
        _result('routing', used == assets.keys() and len(routed) == len(BUSES),
                f'{len(used & assets.keys())}/{len(assets)} assets used on {len(routed)}/3 buses. '
                f'{len(used - assets.keys())} missing asset references.'),
        _result('provenance', credited == len(assets),
                f'{credited}/{len(assets)} assets declare credits, source, license and a SHA-256 fingerprint.'),
        _transport(events, assets), _subtitles(events, assets, captions),
        *_mix_checks(events, assets, submission['bus_gain_db'], windows, observations),
    ]
