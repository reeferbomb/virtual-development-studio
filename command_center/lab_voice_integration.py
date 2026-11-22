"""Exercise a single spoken-voice lane and localized playback with synthetic data."""

import math
import re
from unicodedata import category

from .lab_design import _identifier, _text
from .lab_gameplay import _array, _choice, _integer, _object, _result


TRACK = {
    'id': 'voice-integration', 'title': 'Dialogue scheduling, barks, and localized playback',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification', 'build_operations'],
    'workflow': [
        'Give story dialogue and reactive barks stable line and speaker IDs. Give players room to hear critical '
        'information. Specify trigger conditions, priorities, per-line cooldowns, repeat suppression and what can resume.',
        'Build a locale manifest with exact voice files, durations, speaker captions and lip-sync assets. '
        'Check localized timing and caption readability independently for each pack.',
        'Budget resident and streamed clips. Prepare critical streams before their triggers and define behavior '
        'when a localized clip is still loading. Test alternate playback formats and seek points in the engine.',
        'Send dialogue, barks and ambience through separate buses. Reserve headroom, duck ambience during speech '
        'and restore it when speech releases. Compare captions and mouth motion against the active voice playhead.',
        'Replay matching trigger sequences with the exact build and locale packs. Exercise repeated barks, '
        'priority collisions, an interrupted line, its resume position, and final caption and mix cleanup.',
    ],
    'deliverables': [
        'Stable line and trigger table with priority, cooldown, interruption, resume and stream readiness rules.',
        'Localized build manifest with voice and lip-sync identities, captions, clip lengths and bus settings.',
        'Trace of scheduler decisions, voice offsets, caption and viseme state, plus engine and listening review notes.',
    ],
    'verification': [
        'Match the exact build, voice file, locale and timing assets. Verify subtitle and viseme playback after '
        'a late stream, a preemption and a seek back into a resumed line.',
        'Listen on representative outputs to check masking, continuity, intelligibility and transitions. '
        'Inspect speaking motion and captions in the localized build at actual gameplay speed.',
    ],
    'exercise': 'Run the same dialogue and bark encounter in two locale packs and predict exact voice-lane transitions.',
}


_KINDS = ('dialogue', 'bark')
_EVENTS = ('start', 'preempt', 'priority', 'cooldown', 'duplicate', 'not-ready', 'finish', 'resume', 'sample')
_REQUIRED = {'priority', 'cooldown', 'preempt', 'resume', 'finish', 'sample'}
_MIX_KEYS = ('dialogue_gain_db', 'bark_gain_db', 'ambience_gain_db', 'ambience_peak_dbfs', 'duck_db')
_PLAYING = ('line', 'speaker', 'voice_sha256', 'lip_sync_sha256', 'offset_ms', 'caption', 'viseme')
_CLOCK = 120_000
_CLIP_MS = 30_000


def _variant(voice, lip, duration, caption, peak, marks, ready=0):
    return {'voice_sha256': voice * 64, 'lip_sync_sha256': lip * 64, 'caption': caption,
            'duration_ms': duration, 'peak_dbfs': peak, 'load': 'streamed' if ready else 'resident', 'ready_ms': ready,
            'visemes': [{'at_ms': time, 'shape': shape} for time, shape in marks]}


_EXAMPLE_LINES = [
    {'id': 'briefing', 'speaker': 'foreman', 'kind': 'dialogue', 'priority': 40, 'cooldown_ms': 0, 'interrupt': 'resume',
     'variants': {
         'en-us': _variant('1', 'a', 1400, 'The west crane is clear. Walk under the blue beam.', -7,
                           [(0, 'closed'), (300, 'wide'), (820, 'round'), (1080, 'closed')]),
         'fr-fr': _variant('2', 'b', 1600, 'La grue ouest est libre. Passez sous la poutre bleue.', -8,
                           [(0, 'closed'), (440, 'wide'), (710, 'round'), (1100, 'closed')]),
     }},
    {'id': 'alarm', 'speaker': 'lookout', 'kind': 'bark', 'priority': 80, 'cooldown_ms': 700, 'interrupt': 'drop',
     'variants': {
         'en-us': _variant('3', 'c', 300, 'Heads up!', -5, [(0, 'closed'), (100, 'open')], ready=400),
         'fr-fr': _variant('4', 'd', 400, 'Attention !', -6, [(0, 'closed'), (100, 'open')], ready=460),
     }},
    {'id': 'step', 'speaker': 'worker', 'kind': 'bark', 'priority': 15, 'cooldown_ms': 400, 'interrupt': 'drop',
     'variants': {
         'en-us': _variant('5', 'e', 150, 'Mind the step.', -9, [(0, 'closed'), (50, 'open')]),
         'fr-fr': _variant('6', 'f', 190, 'Attention à la marche.', -8, [(0, 'closed'), (50, 'open')]),
     }},
]


def _teaching_trace(locale, alarm_end, briefing_end, step_duration):
    def row(time, event, line, playing=None, offset=0, viseme='closed'):
        state = None
        if playing:
            selected = next(item for item in _EXAMPLE_LINES if item['id'] == playing)
            variant = selected['variants'][locale]
            state = {'line': playing, 'speaker': selected['speaker'], 'offset_ms': offset, 'viseme': viseme,
                     **{key: variant[key] for key in ('voice_sha256', 'lip_sync_sha256', 'caption')}}
        return {'at_ms': time, 'event': event, 'line': line, 'playing': state, 'ambience_duck_db': -8 if state else 0}

    return [
        row(0, 'start', 'briefing', 'briefing'), row(100, 'priority', 'step', 'briefing', 100),
        row(220, 'not-ready', 'alarm', 'briefing', 220), row(500, 'preempt', 'alarm', 'alarm'),
        row(650, 'duplicate', 'alarm', 'alarm', 150, 'open'),
        row(alarm_end, 'resume', 'alarm', 'briefing', 500, 'wide'),
        row(1000, 'cooldown', 'alarm', 'briefing', 1500 - alarm_end, 'wide'),
        row(1150, 'sample', None, 'briefing', 1650 - alarm_end, 'round'),
        row(briefing_end, 'finish', 'briefing'), row(2100, 'start', 'step', 'step'),
        row(2100 + step_duration, 'finish', 'step'), row(2300, 'cooldown', 'step'),
        row(2500, 'start', 'step', 'step'), row(2500 + step_duration, 'finish', 'step'),
    ]


EXERCISES = [{
    'id': 'voice-integration', 'title': 'Keep a crane-yard briefing clear through a warning bark',
    'brief': 'Declare 2–4 lowercase locale tags and 2–12 lines. Each line needs its speaker, kind (dialogue or bark), '
             'priority 1–100, and a cooldown in whole milliseconds (zero for dialogue, 1–120000 for barks). '
             'A line may resume or drop on interruption. Barks drop. Give each line a distinct voice and lip-sync '
             'SHA-256 in every locale, a visible caption, clip duration (1–30000 ms) and digital peak (-60 to 0 dBFS). '
             'Use resident clips ready at zero and streamed clips with declared readiness time. Include 1–32 '
             'ordered visemes, starting at offset zero and ending before clip duration. Give each run the same exact '
             'build SHA-256 and predict the same 1–32 events at strictly increasing times (0–120000 ms). '
             'Natural completions precede events at the same time. A null request samples the current playhead. '
             'Other events request one line. Reject a line that is still loading, then check for an active or parked '
             'duplicate, then check its cooldown from the last accepted start. A strictly higher priority preempts. '
             'After a completion, resume the most recently parked line at its saved offset, or finish to silence. '
             'Trace request decisions and natural endpoints including the last completion. An endpoint names the '
             'completed line and shows the resulting playing state. Include the active locale clip and lip-sync '
             'digests, speaker, caption, offset and most recent viseme. Duck ambience at least 6 dB during speech '
             'and keep the conservative peak sum at or below -3 dBFS. Demonstrate priority, cooldown, preemption, '
             'resume, a natural finish, a sample, and a stream rejection followed by a successful retry in each locale. '
             'The practice simulates declared playback; engine playback and listening require a separate review.',
    'criteria': [
        {'id': 'localization', 'label': 'Bind distinct voice and lip-sync assets for all lines and locales to the exact build.'},
        {'id': 'schedule', 'label': 'Predict request decisions and priority, cooldown, interrupt, resume and completion transitions.'},
        {'id': 'streaming', 'label': 'Observe a stream readiness rejection followed by a successful retry in each locale.'},
        {'id': 'mix', 'label': 'Duck and release ambience at the correct times while keeping voice and bed within headroom.'},
        {'id': 'playback-sync', 'label': 'Match localized voice, captions and viseme state to the active playhead.'},
    ],
    'example': {
        'build_sha256': '9' * 64, 'locales': ['en-us', 'fr-fr'], 'lines': _EXAMPLE_LINES,
        'mix': {'dialogue_gain_db': -6, 'bark_gain_db': -8, 'ambience_gain_db': -6, 'ambience_peak_dbfs': -6, 'duck_db': -8},
        'events': [{'at_ms': clock, 'request': line} for clock, line in
                   [(0, 'briefing'), (100, 'step'), (220, 'alarm'), (500, 'alarm'), (650, 'alarm'),
                    (1000, 'alarm'), (1150, None), (2100, 'step'), (2300, 'step'), (2500, 'step')]],
        'runs': {
            'en-us': {'build_sha256': '9' * 64, 'observations': _teaching_trace('en-us', 800, 1700, 150)},
            'fr-fr': {'build_sha256': '9' * 64, 'observations': _teaching_trace('fr-fr', 900, 2000, 190)},
        },
    },
}]


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Build, voice and lip-sync identities must be lowercase SHA-256 digests.')


def _caption(value):
    _text(value, 240, 'Caption')
    if not any(category(ch)[0] in 'LNPS' for ch in value):
        raise ValueError('Caption requires visible text.')


def _validate_variant(variant):
    _object(variant, ('voice_sha256', 'lip_sync_sha256', 'caption', 'duration_ms', 'peak_dbfs', 'load', 'ready_ms',
                      'visemes'), 'Localized voice variant')
    _sha(variant['voice_sha256'])
    _sha(variant['lip_sync_sha256'])
    _caption(variant['caption'])
    _integer(variant['duration_ms'], 1, _CLIP_MS, 'Clip duration')
    _integer(variant['peak_dbfs'], -60, 0, 'Clip peak')
    _choice(variant['load'], ('resident', 'streamed'), 'Load mode')
    _integer(variant['ready_ms'], 0, 0 if variant['load'] == 'resident' else _CLOCK, 'Stream ready time')
    _array(variant['visemes'], 32, 'Visemes', minimum=1)
    previous = -1
    for mark in variant['visemes']:
        _object(mark, ('at_ms', 'shape'), 'Viseme')
        _integer(mark['at_ms'], previous + 1, variant['duration_ms'] - 1, 'Viseme offset')
        _identifier(mark['shape'], 'Viseme shape')
        previous = mark['at_ms']
    if variant['visemes'][0]['at_ms'] != 0:
        raise ValueError('First viseme must start at offset zero.')


def _validate_lines(rows, locales):
    _array(rows, 12, 'Voice lines', minimum=2)
    lines = {}
    for row in rows:
        _object(row, ('id', 'speaker', 'kind', 'priority', 'cooldown_ms', 'interrupt', 'variants'), 'Voice line')
        _identifier(row['id'], 'Line ID')
        _identifier(row['speaker'], 'Speaker ID')
        _choice(row['kind'], _KINDS, 'Voice kind')
        _integer(row['priority'], 1, 100, 'Priority')
        bark = row['kind'] == 'bark'
        _integer(row['cooldown_ms'], 1 if bark else 0, _CLOCK if bark else 0, 'Cooldown')
        _choice(row['interrupt'], ('drop',) if bark else ('drop', 'resume'), 'Interrupt policy')
        _object(row['variants'], locales, 'Line variants')
        for variant in row['variants'].values():
            _validate_variant(variant)
        if row['id'] in lines:
            raise ValueError('Duplicate line ID.')
        lines[row['id']] = row
    return lines


def _validate_run(run):
    _object(run, ('build_sha256', 'observations'), 'Locale run')
    _sha(run['build_sha256'])
    _array(run['observations'], 64, 'Trace observations')
    for row in run['observations']:
        _object(row, ('at_ms', 'event', 'line', 'playing', 'ambience_duck_db'), 'Trace row')
        _integer(row['at_ms'], 0, _CLOCK + 12 * _CLIP_MS, 'Trace time')
        _choice(row['event'], _EVENTS, 'Trace event')
        if row['line'] is not None:
            _identifier(row['line'], 'Trace line ID')
        _integer(row['ambience_duck_db'], -60, 0, 'Observed ambience duck')
        playing = row['playing']
        if playing is None:
            continue
        _object(playing, _PLAYING, 'Playing voice')
        for field in ('line', 'speaker', 'viseme'):
            _identifier(playing[field], field)
        for field in ('voice_sha256', 'lip_sync_sha256'):
            _sha(playing[field])
        _integer(playing['offset_ms'], 0, _CLIP_MS - 1, 'Playback offset')
        _caption(playing['caption'])


def _validate(data):
    _object(data, ('build_sha256', 'locales', 'lines', 'mix', 'events', 'runs'), 'Voice integration submission')
    _sha(data['build_sha256'])
    locales = data['locales']
    _array(locales, 4, 'Locale tags', minimum=2)
    if any(type(tag) is not str or not re.fullmatch('[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}', tag) for tag in locales):
        raise ValueError('Locale tags must use lowercase language and optional region subtags.')
    if len(set(locales)) != len(locales):
        raise ValueError('Duplicate locale tag.')
    lines = _validate_lines(data['lines'], locales)
    _object(data['mix'], _MIX_KEYS, 'Mix')
    for key, value in data['mix'].items():
        _integer(value, -60, 0, key)
    _array(data['events'], 32, 'Scenario events', minimum=1)
    previous = -1
    for event in data['events']:
        _object(event, ('at_ms', 'request'), 'Scenario event')
        _integer(event['at_ms'], previous + 1, _CLOCK, 'Scenario time')
        request = event['request']
        if request is not None:
            _identifier(request, 'Requested line')
            if request not in lines:
                raise ValueError('Scenario requests an unlisted line.')
        previous = event['at_ms']
    _object(data['runs'], locales, 'Locale runs')
    for run in data['runs'].values():
        _validate_run(run)
    return lines


def _simulate(events, lines, locale, mix):
    variants = {name: line['variants'][locale] for name, line in lines.items()}
    trace, parked, last_start = [], [], {}
    active = None  # Line ID, current start time, clip offset at that start.

    def observe(clock, event, line):
        playing = None
        if active:
            name, start, offset = active
            offset += clock - start
            variant = variants[name]
            viseme = next(mark['shape'] for mark in reversed(variant['visemes']) if mark['at_ms'] <= offset)
            playing = {'line': name, 'speaker': lines[name]['speaker'], 'offset_ms': offset, 'viseme': viseme,
                       **{key: variant[key] for key in ('voice_sha256', 'lip_sync_sha256', 'caption')}}
        trace.append({'at_ms': clock, 'event': event, 'line': line, 'playing': playing,
                      'ambience_duck_db': mix['duck_db'] if active else 0})

    def advance(limit):
        nonlocal active
        while active:
            name, start, offset = active
            end = start + variants[name]['duration_ms'] - offset
            if end > limit:
                break
            if parked:
                resume, resume_offset = parked.pop()
                active = (resume, end, resume_offset)
                observe(end, 'resume', name)
            else:
                active = None
                observe(end, 'finish', name)

    for step in events:
        clock, name = step['at_ms'], step['request']
        advance(clock)
        current = active[0] if active else None
        if name is None:
            event = 'sample'
        elif clock < variants[name]['ready_ms']:
            event = 'not-ready'
        elif name == current or any(paused == name for paused, offset in parked):
            event = 'duplicate'
        elif name in last_start and clock - last_start[name] < lines[name]['cooldown_ms']:
            event = 'cooldown'
        elif current is not None and lines[name]['priority'] <= lines[current]['priority']:
            event = 'priority'
        else:
            event = 'preempt' if active else 'start'
            if active and lines[current]['interrupt'] == 'resume':
                parked.append((current, active[2] + clock - active[1]))
            active = (name, clock, 0)
            last_start[name] = clock
        observe(clock, event, name)
    advance(_CLOCK + 12 * _CLIP_MS)
    return trace


def _events(rows):
    return [(row['at_ms'], row['event'], row['line']) for row in rows]


def _streaming_events(rows, streams):
    return [event for event in _events(rows) if event[1] in ('not-ready', 'start', 'preempt') and event[2] in streams]


def _peak(trace, lines, locale, mix):
    bed_db = mix['ambience_peak_dbfs'] + mix['ambience_gain_db']
    peaks = []
    for row in trace:
        playing = row['playing']
        voice = 0
        if playing:
            line = lines[playing['line']]
            voice_db = line['variants'][locale]['peak_dbfs'] + mix[f"{line['kind']}_gain_db"]
            voice = 10 ** (voice_db / 20)
        peaks.append(voice + 10 ** ((bed_db + row['ambience_duck_db']) / 20))
    return max(peaks)


def assess(exercise_id, submission):
    if exercise_id != 'voice-integration':
        raise ValueError('Unknown voice integration exercise.')
    lines = _validate(submission)
    locales, mix = submission['locales'], submission['mix']
    fingerprints = [variant[key] for line in lines.values() for variant in line['variants'].values()
                    for key in ('voice_sha256', 'lip_sync_sha256')]
    build = submission['build_sha256']
    bound = sum(submission['runs'][locale]['build_sha256'] == build for locale in locales)
    unique = len(set(fingerprints))
    schedule, streaming, sync, gains = [], [], [], []
    max_peak = 0
    for locale in locales:
        expected = _simulate(submission['events'], lines, locale, mix)
        observed = submission['runs'][locale]['observations']
        outcomes = {row['event'] for row in expected}
        started = {row['line'] for row in expected if row['event'] in ('start', 'preempt')}
        blocked = {row['line'] for row in expected if row['event'] == 'not-ready'}
        if (_events(expected) == _events(observed) and _REQUIRED <= outcomes
                and {lines[name]['kind'] for name in started} == set(_KINDS)):
            schedule.append(locale)
        if blocked & started and _streaming_events(expected, blocked) == _streaming_events(observed, blocked):
            streaming.append(locale)
        if [row['playing'] for row in expected] == [row['playing'] for row in observed]:
            sync.append(locale)
        if [row['ambience_duck_db'] for row in expected] == [row['ambience_duck_db'] for row in observed]:
            gains.append(locale)
        max_peak = max(max_peak, _peak(expected, lines, locale, mix))
    count = len(locales)
    return [
        _result('localization', bound == count and unique == len(fingerprints) and build not in fingerprints,
                f'{bound}/{count} locale runs name the exact build. {unique}/{len(fingerprints)} distinct voice and lip-sync digests.'),
        _result('schedule', len(schedule) == count,
                f'{len(schedule)}/{count} locale traces cover the expected request decisions and natural transitions.'),
        _result('streaming', len(streaming) == count,
                f'{len(streaming)}/{count} locale traces show a readiness rejection and successful use of that stream.'),
        _result('mix', len(gains) == count and mix['duck_db'] <= -6 and max_peak <= 10 ** (-3 / 20),
                f'{len(gains)}/{count} duck and release traces match, with {mix["duck_db"]} dB active duck and '
                f'{20 * math.log10(max_peak):+.2f} dBFS conservative summed peak.'),
        _result('playback-sync', len(sync) == count,
                f'{len(sync)}/{count} locale traces match the active voice, offset, caption and viseme state.'),
    ]
