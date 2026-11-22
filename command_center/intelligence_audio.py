"""Offline diagnostics for anonymous, paired standard/quiet mix measurements.

A scenario contains one matched window from both profiles. Supply measured
master true peak in dBTP and post-fader dialogue, music and effects RMS in
dBFS on a common time window and channel basis. For speech, measure the
active line. A null stem means inactive in the window, not an unknown level.
Each essential_cues row is one expected occurrence and lists the delivery
channels actually observed per profile. Duplicate occurrences are meaningful.

The dialogue proxy compares speech with the sum of the two background
powers assuming uncorrelated stems. It does not measure a mixed waveform,
frequency masking, listening conditions, acoustic exposure or intelligibility.
"""

import math


_PROFILES = ('standard', 'quiet')
_STEMS = ('dialogue_rms_dbfs', 'music_rms_dbfs', 'effects_rms_dbfs')
_CHANNELS = ('audio', 'caption', 'visual', 'haptic')
_RANK = {'pass': 0, 'warn': 1, 'fail': 2}


def _fields(row, keys, name):
    if type(row) is not dict or row.keys() != set(keys):
        raise ValueError(f'{name} requires exactly {", ".join(keys)}.')


def _number(value, low, high, name):
    # Compare bounds before any float conversion, including for oversized Python ints.
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f'{name} must be a finite number from {low} to {high}.')


def _list(value, low, high, name):
    if type(value) is not list or not low <= len(value) <= high:
        raise ValueError(f'{name} requires a list of {low}–{high} entries.')


def _validate(data):
    _fields(data, ('targets', 'scenarios'), 'Audio measurements')
    targets = data['targets']
    _fields(targets, ('peak_ceiling_dbtp', 'min_dialogue_margin_db', 'quiet_peak_reduction_db'), 'Targets')
    _number(targets['peak_ceiling_dbtp'], -24, 0, 'peak_ceiling_dbtp')
    _number(targets['min_dialogue_margin_db'], 0, 24, 'min_dialogue_margin_db')
    _number(targets['quiet_peak_reduction_db'], 1, 24, 'quiet_peak_reduction_db')
    _list(data['scenarios'], 1, 32, 'scenarios')
    for scenario in data['scenarios']:
        _fields(scenario, (*_PROFILES, 'essential_cues'), 'Scenario')
        for profile in _PROFILES:
            mix = scenario[profile]
            _fields(mix, ('peak_dbtp', *_STEMS), 'Profile measurement')
            _number(mix['peak_dbtp'], -120, 12, 'peak_dbtp')
            for stem in _STEMS:
                if mix[stem] is not None:
                    _number(mix[stem], -120, 0, stem)
        _list(scenario['essential_cues'], 0, 32, 'essential_cues')
        for cue in scenario['essential_cues']:
            _fields(cue, ('kind', *_PROFILES), 'Essential cue')
            if type(cue['kind']) is not str or cue['kind'] not in ('speech', 'signal'):
                raise ValueError('Cue kind must be speech or signal.')
            for profile in _PROFILES:
                channels = cue[profile]
                _list(channels, 0, len(_CHANNELS), 'Cue delivery channels')
                if any(type(c) is not str or c not in _CHANNELS for c in channels):
                    raise ValueError('Unknown cue delivery channel.')
                if len(set(channels)) != len(channels):
                    raise ValueError('List each delivery channel once per occurrence and profile.')


def _margin(mix):
    """Return the speech-minus-background margin, or None when no comparison exists."""
    speech = mix['dialogue_rms_dbfs']
    beds = [mix[field] for field in ('music_rms_dbfs', 'effects_rms_dbfs') if mix[field] is not None]
    if speech is None or not beds:
        return None
    if len(beds) == 1:
        return speech - beds[0]
    combined_dbfs = 10 * math.log10(sum(10 ** (level / 10) for level in beds))
    return speech - combined_dbfs


def _check(key, label, status, detail):
    return {'id': key, 'label': label, 'status': status, 'detail': detail}


def analyze(data: dict) -> dict:
    """Diagnose coverage and engineering targets in the supplied measurements only."""
    _validate(data)
    targets, scenes = data['targets'], data['scenarios']
    # Ordinals locate a problematic row without attaching any free-form identifiers.
    peak, peak_scene, peak_profile = max(
        ((scene[p]['peak_dbtp'], i, p) for i, scene in enumerate(scenes, 1) for p in _PROFILES),
        key=lambda entry: entry[0])
    ceiling = targets['peak_ceiling_dbtp']
    peak_status = 'fail' if peak > 0 else 'warn' if peak > ceiling else 'pass'
    checks = [_check('peak-headroom', 'Master peak headroom', peak_status,
                     f'Highest supplied peak was {peak:g} dBTP in scenario {peak_scene} ({peak_profile}). '
                     f'Target ceiling {ceiling:g} dBTP. Headroom to full scale {-peak:g} dB.')]

    speech_windows = dict.fromkeys(_PROFILES, 0)
    overlap_windows = dict.fromkeys(_PROFILES, 0)
    worst_margin = dict.fromkeys(_PROFILES)
    minimum = None
    margin_location = ''
    cues = 0
    delivered = dict.fromkeys(_PROFILES, 0)
    alternatives = dropped_speech = 0
    first_missing_delivery = first_missing_alternative = ''
    reductions = []
    for i, scene in enumerate(scenes, 1):
        for p in _PROFILES:
            mix = scene[p]
            speech_windows[p] += mix['dialogue_rms_dbfs'] is not None
            margin = _margin(mix)
            if margin is not None:
                overlap_windows[p] += 1
                if worst_margin[p] is None or margin < worst_margin[p]:
                    worst_margin[p] = margin
                if minimum is None or margin < minimum:
                    minimum, margin_location = margin, f'scenario {i} ({p})'
        dropped_speech += scene['standard']['dialogue_rms_dbfs'] is not None and scene['quiet']['dialogue_rms_dbfs'] is None
        reductions.append(scene['standard']['peak_dbtp'] - scene['quiet']['peak_dbtp'])
        for cue_number, cue in enumerate(scene['essential_cues'], 1):
            cues += 1
            speech = cue['kind'] == 'speech'
            for p in _PROFILES:
                modes = cue[p]
                has_delivery = bool(modes)
                if speech:
                    has_delivery = 'caption' in modes or ('audio' in modes and scene[p]['dialogue_rms_dbfs'] is not None)
                delivered[p] += has_delivery
                if not has_delivery and not first_missing_delivery:
                    first_missing_delivery = f' First missing delivery: scenario {i}, cue {cue_number} ({p}).'
            has_alternative = ('caption' in cue['quiet'] if speech else
                               any(mode != 'audio' for mode in cue['quiet']))
            alternatives += has_alternative
            if not has_alternative and not first_missing_alternative:
                first_missing_alternative = f' First missing alternative: scenario {i}, cue {cue_number}.'

    required = targets['min_dialogue_margin_db']
    balance_status = 'pass'
    if minimum is not None and minimum < 0:
        balance_status = 'fail'
    elif (minimum is not None and minimum < required) or not all(speech_windows.values()):
        balance_status = 'warn'
    margin_detail = (f'Lowest dialogue-minus-background power margin {minimum:.2f} dB in {margin_location}.'
                     if minimum is not None else 'No window contains both speech and a measured active background stem.')
    checks.append(_check('dialogue-margin', 'Dialogue and background balance', balance_status,
                         f'{margin_detail} Target {required:g} dB. Speech windows '
                         f'{speech_windows["standard"]} standard, {speech_windows["quiet"]} quiet.'))

    cue_status = 'warn' if not cues else 'pass' if min(delivered.values()) == cues else 'fail'
    checks.append(_check('essential-cues', 'Essential cue delivery', cue_status,
                         f'Of {cues} expected occurrences, {delivered["standard"]} had a delivery channel in standard '
                         f'and {delivered["quiet"]} in quiet. Speech needs an active dialogue stem with '
                         f'observed audio delivery, or caption.{first_missing_delivery}'))

    reduction = min(reductions)
    quiet_target = targets['quiet_peak_reduction_db']
    if alternatives < cues or reduction < 0:
        quiet_status = 'fail'
    elif not cues or dropped_speech or reduction < quiet_target:
        quiet_status = 'warn'
    else:
        quiet_status = 'pass'
    checks.append(_check('quiet-profile', 'Quiet profile and alternative cues', quiet_status,
                         f'Smallest peak reduction {reduction:g} dB in scenario {reductions.index(reduction) + 1} '
                         f'(target {quiet_target:g} dB). {alternatives}/{cues} required occurrences have '
                         f'a quiet alternative. {dropped_speech} paired windows lose their dialogue '
                         f'stem.{first_missing_alternative}'))
    metrics = {
        'scenario_count': len(scenes), 'maximum_peak_dbtp': peak, 'minimum_headroom_db': -peak,
        'speech_windows': speech_windows, 'overlap_windows': overlap_windows,
        'minimum_dialogue_margin_db': {p: round(m, 3) if m is not None else None for p, m in worst_margin.items()},
        'essential_cue_occurrences': cues, 'delivered_cues': delivered, 'quiet_alternative_cues': alternatives,
        'minimum_quiet_peak_reduction_db': round(reduction, 3), 'dropped_quiet_speech_windows': dropped_speech,
    }
    return {'schema_version': 1, 'kind': 'audio', 'status': max((c['status'] for c in checks), key=_RANK.get),
            'checks': checks, 'metrics': metrics,
            'advisory': ('Results describe submitted digital measurements and cue observations. The background '
                         'power estimate assumes uncorrelated stems. Review actual dialogue clarity, cue meaning, '
                         'mix artistry and device playback separately. Digital levels cannot establish hearing safety.')}


def example() -> dict:
    """Return a fresh synthetic pair of gameplay excerpts, with no media or identifiers."""
    return {
        'targets': {'peak_ceiling_dbtp': -1, 'min_dialogue_margin_db': 6, 'quiet_peak_reduction_db': 4},
        'scenarios': [
            {'standard': {'peak_dbtp': -2.5, 'dialogue_rms_dbfs': -18, 'music_rms_dbfs': -30, 'effects_rms_dbfs': -32},
             'quiet': {'peak_dbtp': -7, 'dialogue_rms_dbfs': -21, 'music_rms_dbfs': -36, 'effects_rms_dbfs': -39},
             'essential_cues': [{'kind': 'speech', 'standard': ['audio'], 'quiet': ['audio', 'caption']},
                                {'kind': 'signal', 'standard': ['audio', 'visual'], 'quiet': ['visual']}]},
            {'standard': {'peak_dbtp': -1.8, 'dialogue_rms_dbfs': None, 'music_rms_dbfs': -24, 'effects_rms_dbfs': -22},
             'quiet': {'peak_dbtp': -8, 'dialogue_rms_dbfs': None, 'music_rms_dbfs': -33, 'effects_rms_dbfs': -29},
             'essential_cues': [{'kind': 'signal', 'standard': ['audio'], 'quiet': ['haptic']}]},
        ],
    }
