"""Replay an original game's startup, menu, loading and checkpoint flow in memory."""

from dataclasses import dataclass
import re

from .lab_design import _identifier
from .lab_gameplay import _array, _choice, _integer, _object, _result
from .provenance import spec_digest


TRACK = {
    'id': 'startup-sequences', 'title': 'Game startup, title flow and safe return to play',
    'roles': ['architecture', 'gameplay', 'ui', 'content', 'verification', 'build_operations'],
    'workflow': [
        'Inventory platform or contract notices, accessibility setup and optional studio logos. Confirm the exact '
        'approved text, placement and timing with the responsible owner and give optional media an obvious skip.',
        'Render a small navigable shell first. Offer input, narration, captions, volume and motion preferences '
        'before optional media. Apply saved preferences on return and leave settings reachable from the menu.',
        'Separate title from menu attention and show Continue only after verifying save compatibility and '
        'integrity. Select the last verified checkpoint, explain fallback or failure, and preserve save files.',
        'Load the selected scene in the background with feedback and a clear way to retry or return. Give each '
        'attempt an identity and bind results to it. Enter the scene only after a successful matching load.',
        'Distinguish foreground resume, checkpoint retry and confirmed restart. Measure startup and loading '
        'on representative clean and returning profiles, including error and suspend paths.',
    ],
    'deliverables': [
        'Startup state and timing diagram with skip, notice, accessibility, title, menu and recovery behavior.',
        'Save availability, checkpoint, suspend and restart matrix with input ownership at each transition.',
        'Exact build timing trace and device acceptance notes for first paint, input readiness and loading feedback.',
    ],
    'verification': [
        'Exercise first launch, saved preferences, corrupt and incompatible saves, failed load, retry and late results.',
        'Verify real menu navigation, reduced motion, notice legibility, device suspend and save persistence in the target build.',
    ],
    'exercise': 'Predict startup and play recovery across a first launch, a return and an invalid save pair.',
}


_CASES = ('first-run', 'returning', 'damaged')
_PRESETS = ('standard', 'comfort')
_SLOTS = ('primary', 'backup')
_CHECKPOINTS = ('station', 'gallery', 'controls')
_SCREENS = ('boot', 'setup', 'notice', 'logos', 'title', 'menu', 'loading', 'load-error', 'playing',
            'paused', 'suspended', 'confirm-restart')
_FIELDS = ('accepted', 'screen', 'preferences', 'save_source', 'position', 'checkpoint', 'ticket', 'progress')
_TRANSITIONS = {('logos', 'skip'): 'title', ('logos', 'logos-done'): 'title', ('playing', 'pause'): 'paused',
                ('playing', 'suspend'): 'suspended', ('suspended', 'restore'): 'paused',
                ('paused', 'resume'): 'playing', ('paused', 'restart'): 'confirm-restart',
                ('confirm-restart', 'back'): 'paused'}
_LOAD_COMMANDS = {('menu', 'continue'), ('menu', 'new-game'), ('paused', 'checkpoint'),
                  ('confirm-restart', 'confirm'), ('load-error', 'retry')}
_OP_ARGUMENTS = {'configure': ('preset',), 'progress': ('ticket', 'percent'),
                 'failed': ('ticket',), 'loaded': ('ticket',)}
_OPS = frozenset(('ready', 'advance', 'open', 'walk', *_OP_ARGUMENTS,
                  *(op for _, op in _TRANSITIONS), *(op for _, op in _LOAD_COMMANDS)))
_LIMITS = (1500, 400, 3500)
_MAX_STEPS = 48


def _save(checkpoint, version=2):
    payload = {'version': version, 'checkpoint': checkpoint}
    return dict(payload, sha256=spec_digest(payload))


def _scenario(rows, preferences, primary, backup):
    # Each row is a hand-authored observation. Optional fields carry forward when omitted.
    expected = dict.fromkeys(_FIELDS)
    expected['preferences'] = preferences
    steps = []
    for clock, op, screen, options in rows:
        args = {key: options[key] for key in _OP_ARGUMENTS.get(op, ())}
        changes = {key: value for key, value in options.items() if key not in args}
        expected = dict(expected, screen=screen, accepted=True)
        if screen != 'loading':
            expected.update(ticket=None, progress=None)
        expected.update(changes)
        steps.append(dict(at_ms=clock, op=op, expected=expected, **args))
    return {'preferences': preferences, 'primary': primary, 'backup': backup, 'steps': steps}


EXERCISES = [{
    'id': 'startup-sequences', 'title': 'Bring the relay station back online',
    'brief': 'Trace three fixtures (first-run, returning, damaged) with 1–48 strictly increasing event times '
             'from 0 to 120000 ms. Start at boot. Ready enters setup if no preferences were saved, otherwise '
             'notice. Configure standard or comfort in setup. Comfort represents saved narration, captions, '
             'larger text and reduced motion. Advance from notice only once its 250–5000 ms minimum expires. '
             'Skip works only on the optional logos, where logos-done also leads to title. Open enters menu. '
             'Continue takes the first usable slot (primary before backup). A usable slot is version 2 with a '
             'known checkpoint (station, gallery or controls) and the lowercase SHA-256 of the compact sorted '
             'JSON object containing checkpoint and version. Null means a missing slot. New-game starts at station. '
             'Each scene load or retry enters loading with a new integer ticket starting at 1 and progress zero. '
             'Progress must increase (1–99). Progress, failed and loaded must name the current ticket. Failure '
             'leaves live position and checkpoint unchanged. Retry starts the same destination with a fresh ticket. '
             'Back from a load or load error returns to menu or pause. Successful loading commits position and '
             'checkpoint to the destination. Walk moves playing to corridor without changing its checkpoint. '
             'Suspend and restore return playing to pause with position held. Resume returns to play. Paused '
             'checkpoint reloads the committed location. Restart opens confirmation and confirm loads station. '
             'Back from confirmation returns to pause. Trace each step including refusals. On first-run show '
             'comfort setup, early notice refusal, optional skip, backup Continue, failed load and retry with stale '
             'success refused, suspend/resume, checkpoint reload and confirmed restart. On returning use primary. '
             'On damaged refuse Continue and choose New Game. Simulated limits are 1500 ms to Ready, 400 ms to '
             'first load feedback, and 3500 ms to each load end. The modeled minimum is an exercise rule.',
    'criteria': [
        {'id': 'startup-path', 'label': 'Apply first-run or saved settings and reach the interactive title and menu.'},
        {'id': 'legal-and-skip', 'label': 'Observe the required notice minimum and skip only optional logos.'},
        {'id': 'save-selection', 'label': 'Choose valid primary or backup saves and keep Continue unavailable when both fail.'},
        {'id': 'load-recovery', 'label': 'Report monotonic progress, recover from failure and disregard stale completion.'},
        {'id': 'playback-return', 'label': 'Resume live position, restore a checkpoint and confirm restart before replacing live state.'},
        {'id': 'timing', 'label': 'Meet synthetic boot, load feedback and load end budgets.'},
    ],
    'example': {'notice_min_ms': 500, 'cases': {
        'first-run': _scenario([
            (100, 'ready', 'setup', {}),
            (200, 'configure', 'notice', {'preset': 'comfort', 'preferences': 'comfort'}),
            (300, 'skip', 'notice', {'accepted': False}),
            (699, 'advance', 'notice', {'accepted': False}),
            (700, 'advance', 'logos', {}),
            (710, 'skip', 'title', {}),
            (720, 'open', 'menu', {'save_source': 'backup'}),
            (730, 'continue', 'loading', {'progress': 0, 'ticket': 1}),
            (850, 'progress', 'loading', {'percent': 25, 'ticket': 1, 'progress': 25}),
            (900, 'progress', 'loading', {'percent': 20, 'ticket': 1, 'accepted': False}),
            (980, 'failed', 'load-error', {'ticket': 1}),
            (990, 'retry', 'loading', {'ticket': 2, 'progress': 0}),
            (1000, 'loaded', 'loading', {'ticket': 1, 'accepted': False}),
            (1090, 'progress', 'loading', {'ticket': 2, 'percent': 55, 'progress': 55}),
            (1300, 'loaded', 'playing', {'ticket': 2, 'position': 'gallery', 'checkpoint': 'gallery'}),
            (1400, 'walk', 'playing', {'position': 'corridor'}),
            (1500, 'suspend', 'suspended', {}), (2000, 'restore', 'paused', {}), (2100, 'resume', 'playing', {}),
            (2200, 'pause', 'paused', {}), (2300, 'checkpoint', 'loading', {'ticket': 3, 'progress': 0}),
            (2400, 'loaded', 'playing', {'ticket': 3, 'position': 'gallery'}),
            (2500, 'pause', 'paused', {}), (2600, 'restart', 'confirm-restart', {}), (2650, 'back', 'paused', {}),
            (2700, 'restart', 'confirm-restart', {}), (2800, 'confirm', 'loading', {'ticket': 4, 'progress': 0}),
            (2900, 'loaded', 'playing', {'ticket': 4, 'position': 'station', 'checkpoint': 'station'}),
        ], None, dict(_save('controls'), sha256='0' * 64), _save('gallery')),
        'returning': _scenario([
            (120, 'ready', 'notice', {}), (620, 'advance', 'logos', {}), (670, 'logos-done', 'title', {}),
            (700, 'open', 'menu', {'save_source': 'primary'}), (720, 'continue', 'loading', {'ticket': 1, 'progress': 0}),
            (800, 'progress', 'loading', {'ticket': 1, 'percent': 30, 'progress': 30}),
            (1000, 'loaded', 'playing', {'ticket': 1, 'position': 'controls', 'checkpoint': 'controls'}),
        ], 'comfort', _save('controls'), _save('gallery')),
        'damaged': _scenario([
            (130, 'ready', 'notice', {}), (650, 'advance', 'logos', {}), (660, 'skip', 'title', {}),
            (680, 'open', 'menu', {}), (690, 'continue', 'menu', {'accepted': False}),
            (700, 'new-game', 'loading', {'ticket': 1, 'progress': 0}),
            (800, 'loaded', 'playing', {'ticket': 1, 'position': 'station', 'checkpoint': 'station'}),
        ], 'standard', _save('controls', 3), dict(_save('gallery'), sha256='0' * 64)),
    }},
}]


def _optional(value, options, label):
    if value is not None:
        _choice(value, options, label)


def _validate_slot(slot):
    if slot is None:
        return
    _object(slot, ('version', 'checkpoint', 'sha256'), 'Save fixture')
    _integer(slot['version'], 1, 10, 'Save version')
    _identifier(slot['checkpoint'], 'Saved checkpoint')
    if type(slot['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', slot['sha256']):
        raise ValueError('Save SHA-256 must use 64 lowercase hex digits.')


def _validate(submission):
    _object(submission, ('notice_min_ms', 'cases'), 'Startup submission')
    _integer(submission['notice_min_ms'], 250, 5000, 'Notice minimum')
    _object(submission['cases'], _CASES, 'Startup cases')
    for case in submission['cases'].values():
        _object(case, ('preferences', *_SLOTS, 'steps'), 'Startup case')
        _optional(case['preferences'], _PRESETS, 'Saved preferences')
        for key in _SLOTS:
            _validate_slot(case[key])
        _array(case['steps'], _MAX_STEPS, 'Startup steps', minimum=1)
        clock = -1
        for step in case['steps']:
            if type(step) is not dict:
                raise ValueError('Each startup step must be an object.')
            op = step.get('op')
            _choice(op, tuple(sorted(_OPS)), 'Startup operation')
            args = _OP_ARGUMENTS.get(op, ())
            _object(step, ('at_ms', 'op', 'expected', *args), 'Startup step')
            _integer(step['at_ms'], clock + 1, 120_000, 'Startup event time')
            clock = step['at_ms']
            if 'preset' in args:
                _choice(step['preset'], _PRESETS, 'Configured preferences')
            if 'ticket' in args:
                _integer(step['ticket'], 1, _MAX_STEPS, 'Load callback ticket')
            if 'percent' in args:
                _integer(step['percent'], 1, 99, 'Load progress')
            row = step['expected']
            _object(row, _FIELDS, 'Expected startup state')
            if type(row['accepted']) is not bool:
                raise ValueError('Expected acceptance must be boolean.')
            _choice(row['screen'], _SCREENS, 'Expected screen')
            for key, options in [('preferences', _PRESETS), ('save_source', _SLOTS),
                                 ('position', (*_CHECKPOINTS, 'corridor')), ('checkpoint', _CHECKPOINTS)]:
                _optional(row[key], options, key)
            for key, minimum, maximum in [('ticket', 1, _MAX_STEPS), ('progress', 0, 99)]:
                if row[key] is not None:
                    _integer(row[key], minimum, maximum, key)


def _select_save(case):
    for key in _SLOTS:
        slot = case[key]
        if slot and slot['version'] == 2 and slot['checkpoint'] in _CHECKPOINTS and slot == _save(slot['checkpoint']):
            return key, slot['checkpoint']
    return None, None


@dataclass
class _Session:
    preferences: str | None
    notice_min_ms: int
    screen: str = 'boot'
    notice_at: int = 0
    save_source: str | None = None
    saved_checkpoint: str | None = None
    position: str | None = None
    checkpoint: str | None = None
    active_target: str | None = None
    attempt: int = 0
    progress: int = 0

    def enter_notice(self, clock):
        self.screen, self.notice_at = 'notice', clock

    def start_load(self, op):
        target = {'continue': self.saved_checkpoint, 'new-game': 'station', 'checkpoint': self.checkpoint,
                  'confirm': 'station', 'retry': self.active_target}[op]
        if target is None:
            return False
        self.screen, self.active_target, self.progress = 'loading', target, 0
        self.attempt += 1
        return True

    def callback(self, op, step):
        if self.screen != 'loading' or step['ticket'] != self.attempt:
            return False
        if op == 'progress':
            if step['percent'] <= self.progress:
                return False
            self.progress = step['percent']
        elif op == 'failed':
            self.screen = 'load-error'
        else:
            self.screen = 'playing'
            self.position = self.checkpoint = self.active_target
            self.active_target = None
        return True

    def dispatch(self, case, step):
        op, clock = step['op'], step['at_ms']
        action = (self.screen, op)
        if action in _TRANSITIONS:
            self.screen = _TRANSITIONS[action]
        elif action in _LOAD_COMMANDS:
            return self.start_load(op)
        elif op in ('progress', 'loaded', 'failed'):
            return self.callback(op, step)
        elif action == ('boot', 'ready'):
            if self.preferences is None:
                self.screen = 'setup'
            else:
                self.enter_notice(clock)
        elif action == ('setup', 'configure'):
            self.preferences = step['preset']
            self.enter_notice(clock)
        elif action == ('notice', 'advance') and clock - self.notice_at >= self.notice_min_ms:
            self.screen = 'logos'
        elif action == ('title', 'open'):
            self.screen = 'menu'
            self.save_source, self.saved_checkpoint = _select_save(case)
        elif action == ('playing', 'walk'):
            self.position = 'corridor'
        elif op == 'back' and self.screen in ('loading', 'load-error'):
            self.screen = 'paused' if self.position is not None else 'menu'
            self.active_target = None
        else:
            return False
        return True

    def observe(self, accepted):
        loading = self.screen == 'loading'
        return {'accepted': accepted, 'screen': self.screen, 'preferences': self.preferences,
                'save_source': self.save_source, 'position': self.position, 'checkpoint': self.checkpoint,
                'ticket': self.attempt if loading else None, 'progress': self.progress if loading else None}


def _replay(case, notice_min_ms):
    session = _Session(case['preferences'], notice_min_ms)
    return [(step, session.observe(session.dispatch(case, step))) for step in case['steps']]


def _matches(trace, fields, ops=None):
    return all(all(step['expected'][field] == state[field] for field in fields)
               for step, state in trace if ops is None or step['op'] in ops)


def _timings(trace):
    first_frame = None
    starts, feedback, ends = {}, {}, {}
    current = None
    for step, row in trace:
        clock, ticket = step['at_ms'], row['ticket']
        if step['op'] == 'ready' and row['accepted']:
            first_frame = clock
        if current is not None and row['accepted']:
            elapsed = clock - starts[current]
            if step['op'] in ('progress', 'loaded', 'failed'):
                feedback.setdefault(current, elapsed)
            if ticket is None:
                ends[current] = elapsed
        if ticket is not None and ticket != current:
            starts[ticket] = clock
        current = ticket
    return (first_frame, max(feedback.values(), default=None), max(ends.values(), default=None),
            bool(starts) and starts.keys() == feedback.keys() == ends.keys())


def assess(exercise_id, submission):
    if exercise_id != 'startup-sequences':
        raise ValueError('Unknown startup sequences exercise.')
    _validate(submission)
    cases = submission['cases']
    traces = {name: _replay(cases[name], submission['notice_min_ms']) for name in _CASES}
    first = traces['first-run']
    events = {(step['op'], row['accepted'], row['screen']) for step, row in first}
    menu_ops = {'ready', 'configure', 'open'}
    startup = (cases['first-run']['preferences'] is None and ('ready', True, 'setup') in events
               and any(step['op'] == 'configure' and row['accepted'] and row['preferences'] == 'comfort' for step, row in first)
               and all(cases[name]['preferences'] is not None for name in _CASES[1:])
               and all(any(step['op'] == 'open' and row['accepted'] for step, row in trace)
                       and _matches(trace, ('accepted', 'screen', 'preferences'), menu_ops) for trace in traces.values()))
    notice_events = {('skip', False, 'notice'), ('advance', False, 'notice'), ('advance', True, 'logos'), ('skip', True, 'title')}
    notice = notice_events <= events and all(_matches(trace, ('screen', 'accepted'), {'advance', 'skip', 'logos-done'})
                                             for trace in traces.values())

    sources = tuple(_select_save(cases[name])[0] for name in _CASES)
    saves = (sources == ('backup', 'primary', None)
             and all(any(step['op'] == 'continue' and row['accepted'] == (source is not None) for step, row in traces[name])
                     and _matches(traces[name], ('save_source',))
                     and _matches(traces[name], ('screen', 'accepted'), {'continue', 'new-game'})
                     for name, source in zip(_CASES, sources, strict=True))
             and any(step['op'] == 'new-game' and row['accepted'] for step, row in traces['damaged']))

    retried = {row['ticket'] for step, row in first if step['op'] == 'retry' and row['accepted']}
    stale = any(step['op'] == 'loaded' and row['ticket'] in retried and step['ticket'] != row['ticket']
                and not row['accepted'] for step, row in first)
    recovered = (('failed', True, 'load-error') in events and stale
                 and ('loaded', True, 'playing') in events
                 and all(_matches(trace, ('ticket', 'progress'))
                         and _matches(trace, ('screen', 'accepted'), {'progress', 'failed', 'retry', 'loaded'})
                         for trace in traces.values()))

    returns = {('suspend', True, 'suspended'), ('restore', True, 'paused'), ('resume', True, 'playing'),
               ('checkpoint', True, 'loading'), ('restart', True, 'confirm-restart'), ('confirm', True, 'loading')}
    playback = (returns <= events and all(_matches(trace, ('position', 'checkpoint')) for trace in traces.values())
                and _matches(first, ('screen', 'accepted'), {op for op, _, _ in returns} | {'back'}))

    timing_pass, timing_details = True, []
    for name, trace in traces.items():
        *times, complete = _timings(trace)
        timing_pass &= complete and all(actual is not None and actual <= limit for actual, limit in zip(times, _LIMITS, strict=True))
        timing_details.append(f'{name} Ready/feedback/end {times[0]}/{times[1]}/{times[2]} ms. Every load reported {complete}.')
    return [
        _result('startup-path', startup, 'Configured first-run preferences before optional media and routed returning profiles to menu.'),
        _result('legal-and-skip', notice, f'Checked early refusal, the {submission["notice_min_ms"]} ms minimum and optional logo skip.'),
        _result('save-selection', saves, f'Selected save sources across first-run, returning and damaged are {sources}.'),
        _result('load-recovery', recovered, f'Fresh retry tickets {sorted(retried)}. Stale completion was refused {stale}.'),
        _result('playback-return', playback, 'Compared foreground resume, checkpoint load and confirmed restart with live position and checkpoint.'),
        _result('timing', timing_pass, ' '.join(timing_details)),
    ]
