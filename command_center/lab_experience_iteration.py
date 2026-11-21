"""Compare declared synthetic frame pacing and input response across a game iteration."""

import re
from unicodedata import category

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'experience-iteration', 'title': 'Game feel, visual performance, and playtest iteration',
    'roles': ['architecture', 'gameplay', 'content', 'ui', 'verification', 'build_operations'],
    'workflow': [
        'Pick a repeatable action inside a representative level. Describe the intended player decision and '
        'visible feedback, then show the target visual hierarchy with a reference shot and an in-engine capture.',
        'Choose settings for minimum and recommended hardware. Declare display mode, resolution or scale, '
        'graphics preset, refresh and frame targets, input device and power mode. Set frame pacing and '
        'input response budgets per tier before running the test.',
        'Capture the same dense route and scripted inputs from the same starting state in both builds. '
        'Record build, device, scene, workload, settings and capture identities. Hold warm-up, '
        'capture window and measurement method steady inside each comparison.',
        'Inspect p95 frame interval, long frames and the worst observed hitch beside an average. '
        'Measure from input activation through first visible acknowledgement and count missed attempts.',
        'Watch players attempt the action. Record the situation and observable behavior, then propose one '
        'change to address it. Re-run the same measurements and observe the same task with fresh players.',
        'Inspect both presets in motion for readability, visual consistency and lost cues. Review controllability '
        'and player feedback alongside the measurements before accepting the change.',
    ],
    'deliverables': [
        'Representative device and preset matrix, exact test build and scene identities, and a scripted capture route.',
        'Baseline and iteration captures with frame-time, hitch and input-response summaries against declared budgets.',
        'Playtest observation, targeted change, measured delta, and a separate human retest with matched visual captures.',
    ],
    'verification': [
        'Repeat clean runs on representative hardware with matched settings and measurement methods. '
        'Inspect CPU and GPU timings to investigate slow frames and check input to presentation on the actual display.',
        'Review legibility, visual quality and the intended player experience with the current build. '
        'Log tester observations, outstanding aesthetic choices and device coverage separately from budget checks.',
    ],
    'exercise': 'Compare a baseline and an iteration for one scene and player action on two device and preset pairs.',
}


_TIERS = ('minimum', 'recommended')
_PHASES = ('baseline', 'iteration')
_REGRESSION_CAPS = {'frame_p95_us': 5_000, 'worst_frame_us': 10_000, 'late_frames_bps': 1_000, 'input_p95_us': 10_000}
_BUDGET_LIMITS = {'worst_frame_us': (1, 250_000), 'late_frames_bps': (0, 500), 'input_p95_us': (1, 150_000)}
_SAMPLE_LIMITS = {'frame_intervals_us': (60, 1024), 'input_feedback_us': (20, 120)}
_MAX_INTERVAL_US = 2_000_000
_COMPARISONS = ('frame-pacing', 'input-response', 'regression-budgets', 'playtest-iteration')


def _example_capture(build, device, settings, capture, frames, inputs):
    return {'build_sha256': build * 64, 'device_sha256': device * 64, 'settings_sha256': settings * 64,
            'scene_sha256': '1' * 64, 'workload_sha256': '2' * 64, 'capture_sha256': capture * 64,
            'frame_intervals_us': frames, 'input_feedback_us': inputs}


EXERCISES = [{
    'id': 'experience-iteration', 'title': 'Improve feedback in a crowded courtyard',
    'brief': 'Submit synthetic evidence for one fixed scenario, scene, scripted workload and input action. '
             'Use distinct minimum and recommended device fingerprints and presets, with 20–240 target fps '
             'at or below the display refresh. Provide baseline and iteration captures for each tier. '
             'Declare each build, device, scene, workload, settings and capture SHA-256 using 64 lowercase '
             'hex digits. Use distinct builds and captures. In each pair use the same number of frame intervals '
             '(60–1024) and scripted input attempts (20–120). Use whole microseconds from 1 to 2000000. '
             'Enter null for a missed input. The nearest-rank p95 of the candidate frame intervals must fit '
             'the target frame period, rounded up to whole microseconds. The late-frame share counts strictly '
             'longer intervals and rounds up to whole basis points, where 100 basis points equal one percent. '
             'Give each tier limits for worst frame (1–250000 microseconds), late frames (0–500 basis points) '
             'and p95 input response (1–150000 microseconds) with zero missed inputs in the iteration. '
             'Declare permitted increases for frame p95, worst frame, late share and input p95, capped at '
             '5000 microseconds, 10000 microseconds, 1000 basis points and 10000 microseconds respectively. '
             'Link one synthetic playtest observation and action to its exact capture pair, require a positive '
             'improvement on one metric, and give a separate human retest prompt. The practice checks these '
             'synthetic observations. Review appearance and player experience in the measured build.',
    'criteria': [
        {'id': 'tier-coverage', 'label': 'Cover distinct target devices and presets with frame targets the displays support.'},
        {'id': 'evidence-match', 'label': 'Compare distinct builds using matched scene, workload, device, settings and sample counts.'},
        {'id': 'frame-pacing', 'label': 'Keep iteration frame p95, late frames and worst hitch within each tier’s limits.'},
        {'id': 'input-response', 'label': 'Meet the input-to-visible-feedback p95 budget with no missed iteration attempts.'},
        {'id': 'regression-budgets', 'label': 'Keep all frame pacing and input latency increases within the declared limits.'},
        {'id': 'playtest-iteration', 'label': 'Link a playtest-driven change and human retest to an improving exact capture pair.'},
    ],
    'example': {
        'evidence': 'synthetic',
        'scenario': {'id': 'courtyard-dodge', 'scene_sha256': '1' * 64, 'workload_sha256': '2' * 64,
                     'input_action': 'dodge'},
        'builds': {'baseline': '3' * 64, 'iteration': '4' * 64},
        'tiers': {
            'minimum': {
                'device_label': 'Reference handheld', 'device_sha256': '5' * 64, 'preset': 'performance',
                'settings_sha256': '6' * 64, 'display_hz': 60, 'target_fps': 30,
                'budgets': {'worst_frame_us': 48_000, 'late_frames_bps': 350, 'input_p95_us': 65_000},
                'regressions': {'frame_p95_us': 1_000, 'worst_frame_us': 2_000, 'late_frames_bps': 50, 'input_p95_us': 3_000},
                'baseline': _example_capture('3', '5', '6', '9', [31_000] * 56 + [36_000] * 3 + [48_000], [64_000] * 20),
                'iteration': _example_capture('4', '5', '6', 'a', [30_000] * 59 + [38_000], [48_000] * 20),
            },
            'recommended': {
                'device_label': 'Reference desktop', 'device_sha256': '7' * 64, 'preset': 'quality',
                'settings_sha256': '8' * 64, 'display_hz': 120, 'target_fps': 60,
                'budgets': {'worst_frame_us': 30_000, 'late_frames_bps': 350, 'input_p95_us': 50_000},
                'regressions': {'frame_p95_us': 1_000, 'worst_frame_us': 2_000, 'late_frames_bps': 50, 'input_p95_us': 3_000},
                'baseline': _example_capture('3', '7', '8', 'b', [15_100] * 59 + [20_500], [30_000] * 20),
                'iteration': _example_capture('4', '7', '8', 'c', [14_900] * 59 + [21_000], [32_000] * 20),
            },
        },
        'playtest': {
            'tier': 'minimum', 'baseline_capture_sha256': '9' * 64, 'iteration_capture_sha256': 'a' * 64,
            'observation': 'Two players pressed dodge again while waiting for its first visible cue in the courtyard.',
            'change': 'Show the dodge cue on the first rendered frame after gameplay accepts the input.',
            'metric': 'input_p95_us', 'minimum_improvement': 8_000,
            'human_retest': 'Ask fresh players to dodge the first courtyard hazard and record repeated presses and cue recognition.',
        },
    },
}]


def _digest(value, field):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        raise ValueError(f'{field} must be a lowercase SHA-256 digest.')


def _visible_text(value, limit, field):
    _text(value, limit, field)
    if not any(category(char)[0] in 'LNPS' for char in value):
        raise ValueError(f'{field} needs visible text.')


def _validate_capture(capture):
    hashes = ('build_sha256', 'device_sha256', 'settings_sha256', 'scene_sha256', 'workload_sha256', 'capture_sha256')
    _object(capture, (*hashes, *_SAMPLE_LIMITS), 'Capture')
    for field in hashes:
        _digest(capture[field], field)
    for field, (minimum, maximum) in _SAMPLE_LIMITS.items():
        samples = capture[field]
        _array(samples, minimum, maximum, field)
        for value in samples:
            if value is not None or field == 'frame_intervals_us':
                _integer(value, 1, _MAX_INTERVAL_US, field)


def _validate_tier(tier):
    _object(tier, ('device_label', 'device_sha256', 'preset', 'settings_sha256', 'display_hz', 'target_fps',
                   'budgets', 'regressions', *_PHASES), 'Tier')
    _visible_text(tier['device_label'], 100, 'device_label')
    _identifier(tier['preset'], 'preset')
    for field in ('device_sha256', 'settings_sha256'):
        _digest(tier[field], field)
    _integer(tier['display_hz'], 20, 480, 'display_hz')
    _integer(tier['target_fps'], 20, 240, 'target_fps')
    _object(tier['budgets'], tuple(_BUDGET_LIMITS), 'Budget limits')
    _object(tier['regressions'], tuple(_REGRESSION_CAPS), 'Regression limits')
    for field, (minimum, maximum) in _BUDGET_LIMITS.items():
        _integer(tier['budgets'][field], minimum, maximum, field)
    for field, maximum in _REGRESSION_CAPS.items():
        _integer(tier['regressions'][field], 0, maximum, field)
    for phase in _PHASES:
        _validate_capture(tier[phase])


def _validate_submission(data):
    _object(data, ('evidence', 'scenario', 'builds', 'tiers', 'playtest'), 'Experience iteration submission')
    _choice(data['evidence'], ('synthetic',), 'evidence')
    scenario = data['scenario']
    _object(scenario, ('id', 'scene_sha256', 'workload_sha256', 'input_action'), 'Scenario')
    _identifier(scenario['id'], 'Scenario ID')
    _identifier(scenario['input_action'], 'Input action')
    for field in ('scene_sha256', 'workload_sha256'):
        _digest(scenario[field], field)
    _object(data['builds'], _PHASES, 'Builds')
    for phase in _PHASES:
        _digest(data['builds'][phase], phase)
    _object(data['tiers'], _TIERS, 'Tiers')
    for tier in data['tiers'].values():
        _validate_tier(tier)

    playtest = data['playtest']
    _object(playtest, ('tier', 'baseline_capture_sha256', 'iteration_capture_sha256', 'observation',
                       'change', 'metric', 'minimum_improvement', 'human_retest'), 'Playtest')
    _choice(playtest['tier'], _TIERS, 'Playtest tier')
    for field in ('baseline_capture_sha256', 'iteration_capture_sha256'):
        _digest(playtest[field], field)
    for field in ('observation', 'change', 'human_retest'):
        _visible_text(playtest[field], 480, field)
    metric = playtest['metric']
    _choice(metric, tuple(_REGRESSION_CAPS), 'Playtest metric')
    _integer(playtest['minimum_improvement'], 1, 10_000 if metric == 'late_frames_bps' else _MAX_INTERVAL_US,
             'minimum_improvement')


def _tier_check(tiers):
    duplicates = [field for field in ('device_sha256', 'preset', 'settings_sha256')
                  if len({tier[field] for tier in tiers.values()}) != len(tiers)]
    over_refresh = [name for name in _TIERS if tiers[name]['target_fps'] > tiers[name]['display_hz']]
    issues = [f'Shared {field} across tiers.' for field in duplicates]
    issues.extend(f'{name} targets more frames per second than its display refresh.' for name in over_refresh)
    targets = ', '.join(f"{name} {tiers[name]['target_fps']} fps at {tiers[name]['display_hz']} Hz" for name in _TIERS)
    return _check('tier-coverage', not issues, ' '.join(issues) or f'Distinct device and preset targets are {targets}.')


def _evidence_issues(data):
    builds, scenario = data['builds'], data['scenario']
    issues = []
    seen_captures = set()
    if builds['baseline'] == builds['iteration']:
        issues.append('Baseline and iteration identify the same build.')
    for name in _TIERS:
        tier = data['tiers'][name]
        for phase in _PHASES:
            capture = tier[phase]
            expected = {'build_sha256': builds[phase], 'device_sha256': tier['device_sha256'],
                        'settings_sha256': tier['settings_sha256'], 'scene_sha256': scenario['scene_sha256'],
                        'workload_sha256': scenario['workload_sha256']}
            mismatches = [field for field, value in expected.items() if capture[field] != value]
            if mismatches:
                issues.append(f'{name} {phase} mismatches {", ".join(mismatches)}.')
            if capture['capture_sha256'] in seen_captures:
                issues.append(f'{name} {phase} reuses a capture digest.')
            seen_captures.add(capture['capture_sha256'])
        for field in _SAMPLE_LIMITS:
            if len(tier['baseline'][field]) != len(tier['iteration'][field]):
                issues.append(f'{name} has different baseline and iteration counts for {field}.')
    return issues


def _p95(samples):
    return sorted(samples)[(95 * len(samples) + 99) // 100 - 1]


def _measure(capture, frame_budget):
    frames = capture['frame_intervals_us']
    input_trials = capture['input_feedback_us']
    inputs = [sample for sample in input_trials if sample is not None]
    late = sum(sample > frame_budget for sample in frames)
    return {'frame_p95_us': _p95(frames), 'worst_frame_us': max(frames),
            'late_frames_bps': (10_000 * late + len(frames) - 1) // len(frames),
            'input_p95_us': _p95(inputs) if inputs else None, 'missed_inputs': len(input_trials) - len(inputs)}


def _playtest_check(tiers, observations, playtest):
    name, field = playtest['tier'], playtest['metric']
    tier = tiers[name]
    if any(playtest[f'{phase}_capture_sha256'] != tier[phase]['capture_sha256'] for phase in _PHASES):
        return _check('playtest-iteration', False, 'Link the playtest change to both exact captures in its selected tier.')
    before, after = (observations[name][phase][field] for phase in _PHASES)
    if before is None or after is None:
        return _check('playtest-iteration', False, f'{name} needs an observed {field} in both captures.')
    improvement, minimum = before - after, playtest['minimum_improvement']
    return _check('playtest-iteration', improvement >= minimum,
                  f'{name} changed {field} from {before} to {after}, an improvement of {improvement} against '
                  f'the required {minimum}. The submission includes a human retest prompt.')


def _comparison_checks(tiers, playtest):
    observations = {}
    frame_details, input_details, regressions = [], [], []
    frame_pass, input_pass = True, True
    for name in _TIERS:
        tier = tiers[name]
        fps, limits = tier['target_fps'], tier['budgets']
        frame_budget = (1_000_000 + fps - 1) // fps
        baseline, current = (_measure(tier[phase], frame_budget) for phase in _PHASES)
        observations[name] = {'baseline': baseline, 'iteration': current}

        p95, worst, late = (current[field] for field in ('frame_p95_us', 'worst_frame_us', 'late_frames_bps'))
        frame_pass &= p95 <= frame_budget and worst <= limits['worst_frame_us'] and late <= limits['late_frames_bps']
        frame_details.append(f"{name} p95 {p95}/{frame_budget} us, worst {worst}/{limits['worst_frame_us']} us, "
                             f"late {late}/{limits['late_frames_bps']} bps.")

        input_p95, missed = current['input_p95_us'], current['missed_inputs']
        input_pass &= input_p95 is not None and input_p95 <= limits['input_p95_us'] and missed == 0
        latency = 'unavailable' if input_p95 is None else f'{input_p95} us'
        input_details.append(f"{name} p95 {latency} against {limits['input_p95_us']} us, {missed} missed inputs.")

        for field in _REGRESSION_CAPS:
            allowance = tier['regressions'][field]
            before, after = baseline[field], current[field]
            if before is None or after is None:
                regressions.append(f'{name} needs an observed {field} in both captures.')
            elif after - before > allowance:
                regressions.append(f'{name} {field} increased by {after - before}, above the budget of {allowance}.')

    return [
        _check('frame-pacing', frame_pass, ' '.join(frame_details)),
        _check('input-response', input_pass, ' '.join(input_details)),
        _check('regression-budgets', not regressions, ' '.join(regressions) or 'Both tiers stayed within all four regression limits.'),
        _playtest_check(tiers, observations, playtest),
    ]


def assess(exercise_id, submission):
    if exercise_id != 'experience-iteration':
        raise ValueError('Unknown experience iteration exercise.')
    _validate_submission(submission)
    tiers = submission['tiers']
    issues = _evidence_issues(submission)
    checks = [_tier_check(tiers), _check('evidence-match', not issues, ' '.join(issues)
                                        or 'Four distinct synthetic captures match the declared builds and scenario context.')]
    if issues:
        return checks + [_check(key, False, 'Provide matched baseline and iteration captures for both tiers.')
                         for key in _COMPARISONS]
    return checks + _comparison_checks(tiers, submission['playtest'])
