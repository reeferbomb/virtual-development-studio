"""Practice interpreting a bounded synthetic playtest. No participant data is collected."""

from .lab_design import _array, _check, _object
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'player-research', 'title': 'Player research and playtest interpretation',
    'roles': ['gameplay', 'ui', 'verification', 'architecture'],
    'workflow': [
        'Frame a decision around a particular encounter. For example, do players understand why the bridge '
        'resets, and do they want to try another route? Define the task, stopping point and questions before '
        'recruiting. Invite both first-time and experienced players and offer accessible ways to participate.',
        'Explain the purpose, observer roles, data fields, access and deletion date. Obtain informed opt-in '
        'before observing. Ask separately about recording. Allow people to pause, decline questions or leave '
        'with the agreed compensation. Explain how to withdraw data and until when that is possible. '
        'Keep participant contact details separate from coded notes. Remove withdrawn observations according to '
        'the stated withdrawal procedure. A player can stop the game while consenting to use that observation.',
        'Give the same neutral task, build and time window. Log what happened at a specific moment, such as '
        'three retries or a voluntary exit. Ask “What were you trying to do there?” Let players describe '
        'curiosity, mastery, boredom, frustration or a mix in their own words. A retry can follow delight '
        'in a challenge, an unclear cue or pressure to finish. Record the explanation separately.',
        'Find a moment the player would repeat and a moment they would shorten. Someone who tries an optional '
        'route may enjoy discovery or may be lost. Someone who stops may have had a satisfying ending. If a '
        'player reports boredom, ask which choice felt repetitive or which wait felt long. For frustration, '
        'ask what outcome they expected and what feedback they received. Look for counterexamples in the same build.',
        'Compare behaviors and optional self-report in each experience cohort. Report counts with their '
        'denominators and record missing answers. Offer a genuinely optional replay with equal pay and no '
        'lost progress for declining. Separate rewarded or required repeats from voluntary ones.',
        'Write down two explanations that fit the observation. To distinguish repetition from unclear goals, '
        'vary one feature and hold the others steady. Counterbalance build order when the same people try '
        'both. Ask the same neutral follow-up and check whether the predicted pattern changes. Identify '
        'selection, order, access barriers and small samples as limits on any broader conclusion.',
    ],
    'deliverables': [
        'A study plan with the design decision, cohort definitions, accessible task, consent and deletion procedure.',
        'A coded observation sheet separating witnessed actions, voluntary choices, missing answers and reported feelings.',
        'A short readout with cohort denominators, competing explanations, a discriminating retest and remaining uncertainty.',
    ],
    'verification': [
        'Recalculate counts from individual sessions. Check that a skipped survey remains missing, that multiple '
        'feelings can coexist and that a pressured repeat contributes no evidence of voluntary return.',
        'Trace each observation to a specific session. Review evidence that would contradict the interpretation. '
        'Actual reactions require separately consented human playtests. This exercise measures synthetic arithmetic and reasoning.',
    ],
    'exercise': 'Explain an ambiguous early exit using synthetic evidence and design a follow-up that can distinguish two causes.',
}

_GROUPS = ('all', 'new', 'familiar')
_FEELINGS = ('enjoyed', 'bored', 'frustrated')
_REPLAY = ('returned', 'declined', 'required', 'rewarded', 'not-offered', 'unobserved')
_SAFEGUARDS = ('informed_opt_in', 'may_skip_or_stop', 'pay_independent', 'limited_access', 'deletion_scheduled')
_PROBES = {
    'repetitive-actions': 'vary-action-variety',
    'unclear-goal': 'clarify-goal-cue',
    'challenge-mismatch': 'vary-challenge',
    'external-interruption': 'ask-about-context',
}


def _session(code, cohort, outcome, feelings, replay):
    return {'code': code, 'cohort': cohort, 'outcome': outcome, 'feelings': feelings, 'replay': replay}


EXERCISES = [{
    'id': 'player-research', 'title': 'Investigate an early exit',
    'brief': 'Use only invented sessions from the same task and build. Set source to synthetic and declare '
             'the five protocol safeguards as booleans. Give 2–48 sessions unique integer codes (1–48). '
             'Include both new and familiar cohorts. Outcome is finished or stopped. Feelings are optional '
             'multi-select self-reports (enjoyed, bored, frustrated). An empty list means none selected, '
             'null means no answer. For the same optional replay window, returned and declined are observed '
             'unpressured choices. Exclude required, rewarded, not-offered and unobserved from its denominator. '
             'For all, new and familiar, predict [count, eligible] for stops, each feeling and voluntary returns. '
             'A zero denominator means unmeasured. For boredom_bounds give [reported bored, reported bored plus '
             'missing answers, all sessions in group]. These are missing-data limits within the fixture. '
             'Cite one observed early stop and give two distinct candidate explanations with a matching follow-up '
             'for each. Pairs are repetitive-actions/vary-action-variety, unclear-goal/clarify-goal-cue, '
             'challenge-mismatch/vary-challenge and external-interruption/ask-about-context. Choose a scope '
             'of hypotheses-only, proven-cause or all-players. Include no real-world notes, names or recordings.',
    'criteria': [
        {'id': 'safeguards', 'label': 'Plan informed, voluntary participation and limited data use.'},
        {'id': 'observations', 'label': 'Reconstruct stopping behavior overall and in each experience cohort.'},
        {'id': 'self-report', 'label': 'Count each reported feeling among the sessions that answered.'},
        {'id': 'voluntary-return', 'label': 'Measure returns among observed unpressured choices.'},
        {'id': 'uncertainty', 'label': 'Bound the possible boredom count when answers are missing.'},
        {'id': 'interpretation', 'label': 'Ground two testable hypotheses in an observed session outcome.'},
    ],
    'example': {
        'source': 'synthetic',
        'protocol': dict.fromkeys(_SAFEGUARDS, True),
        'sessions': [
            _session(1, 'new', 'stopped', ['frustrated'], 'declined'),
            _session(2, 'new', 'finished', ['enjoyed', 'frustrated'], 'returned'),
            _session(3, 'new', 'stopped', None, 'required'),
            _session(4, 'new', 'finished', [], 'not-offered'),
            _session(5, 'familiar', 'finished', ['bored'], 'declined'),
            _session(6, 'familiar', 'stopped', ['enjoyed'], 'rewarded'),
            _session(7, 'familiar', 'finished', ['enjoyed', 'bored'], 'returned'),
            _session(8, 'familiar', 'stopped', None, 'unobserved'),
        ],
        'summary': {
            'all': {'stops': [4, 8], 'enjoyed': [3, 6], 'bored': [2, 6], 'frustrated': [2, 6],
                    'returns': [2, 4], 'boredom_bounds': [2, 4, 8]},
            'new': {'stops': [2, 4], 'enjoyed': [1, 3], 'bored': [0, 3], 'frustrated': [2, 3],
                    'returns': [1, 2], 'boredom_bounds': [0, 1, 4]},
            'familiar': {'stops': [2, 4], 'enjoyed': [2, 3], 'bored': [2, 3], 'frustrated': [0, 3],
                         'returns': [1, 2], 'boredom_bounds': [2, 3, 4]},
        },
        'interpretation': {
            'code': 3, 'observed_outcome': 'stopped', 'scope': 'hypotheses-only',
            'hypotheses': [
                {'cause': 'repetitive-actions', 'probe': 'vary-action-variety'},
                {'cause': 'unclear-goal', 'probe': 'clarify-goal-cue'},
            ],
        },
    },
}]


def _observations(rows):
    _array(rows, 2, 48, 'sessions')
    sessions = {}
    for row in rows:
        _object(row, ('code', 'cohort', 'outcome', 'feelings', 'replay'), 'session')
        code = row['code']
        _integer(code, 1, 48, 'synthetic session code')
        if code in sessions:
            raise ValueError('Synthetic session codes must be unique.')
        _choice(row['cohort'], _GROUPS[1:], 'cohort')
        _choice(row['outcome'], ('stopped', 'finished'), 'outcome')
        _choice(row['replay'], _REPLAY, 'replay')
        if row['feelings'] is not None:
            _array(row['feelings'], 0, len(_FEELINGS), 'feelings')
            for feeling in row['feelings']:
                _choice(feeling, _FEELINGS, 'feeling')
            if len(set(row['feelings'])) != len(row['feelings']):
                raise ValueError('Each feeling can be selected once in a session.')
        sessions[code] = row
    return sessions


def _summary(rows):
    answers = [row['feelings'] for row in rows if row['feelings'] is not None]
    result = {feeling: [sum(feeling in answer for answer in answers), len(answers)] for feeling in _FEELINGS}
    result['stops'] = [sum(row['outcome'] == 'stopped' for row in rows), len(rows)]
    choices = [row['replay'] for row in rows if row['replay'] in ('returned', 'declined')]
    result['returns'] = [choices.count('returned'), len(choices)]
    bored = result['bored'][0]
    result['boredom_bounds'] = [bored, bored + len(rows) - len(answers), len(rows)]
    return result


def _interpretation(data, sessions):
    _object(data, ('code', 'observed_outcome', 'scope', 'hypotheses'), 'interpretation')
    _integer(data['code'], 1, 48, 'cited session code')
    _choice(data['observed_outcome'], ('stopped', 'finished'), 'observed_outcome')
    _choice(data['scope'], ('hypotheses-only', 'proven-cause', 'all-players'), 'scope')
    _array(data['hypotheses'], 2, 2, 'hypotheses')
    causes = set()
    matched = 0
    for hypothesis in data['hypotheses']:
        _object(hypothesis, ('cause', 'probe'), 'hypothesis')
        cause, probe = hypothesis['cause'], hypothesis['probe']
        _choice(cause, _PROBES, 'cause')
        _choice(probe, _PROBES.values(), 'probe')
        causes.add(cause)
        matched += probe == _PROBES[cause]
    row = sessions.get(data['code'])
    observed = row is not None and row['outcome'] == data['observed_outcome']
    valid = (observed and data['observed_outcome'] == 'stopped' and len(causes) == 2 and matched == 2
             and data['scope'] == 'hypotheses-only')
    return _check('interpretation', valid, f'The cited early stop {"matches" if observed and data["observed_outcome"] == "stopped" else "does not match"} '
                  f'session {data["code"]}. {len(causes)} distinct explanations '
                  f'and {matched}/2 matching follow-ups. Scope is {data["scope"]}. '
                  'A synthetic session can suggest competing explanations, without establishing a cause.')


def assess(exercise_id, submission):
    if exercise_id != 'player-research':
        raise ValueError('Unknown player research exercise.')
    _object(submission, ('source', 'protocol', 'sessions', 'summary', 'interpretation'), 'Player research submission')
    _choice(submission['source'], ('synthetic',), 'source')
    protocol = submission['protocol']
    _object(protocol, _SAFEGUARDS, 'protocol')
    if any(type(value) is not bool for value in protocol.values()):
        raise ValueError('Protocol safeguards must be booleans.')
    sessions = _observations(submission['sessions'])
    declared = submission['summary']
    _object(declared, _GROUPS, 'summary')
    actual = {}
    for group in _GROUPS:
        subset = [row for row in sessions.values() if group == 'all' or row['cohort'] == group]
        actual[group] = _summary(subset)
        _object(declared[group], actual[group], 'cohort summary')
        for key, expected in actual[group].items():
            numbers = declared[group][key]
            _array(numbers, len(expected), len(expected), key)
            for number in numbers:
                _integer(number, 0, 48, key)

    def matched(*metrics):
        return all(declared[group][key] == actual[group][key] for group in _GROUPS for key in metrics)

    def counts(key):
        return ', '.join(f'{group} ' + '/'.join(map(str, actual[group][key])) for group in _GROUPS)

    missing = [key for key in _SAFEGUARDS if not protocol[key]]
    return [
        _check('safeguards', not missing, 'Missing planned safeguards: ' + (', '.join(missing) or 'none') + '.'),
        _check('observations', matched('stops') and all(actual[g]['stops'][1] for g in _GROUPS[1:]),
               'Stopped / sessions: ' + counts('stops') + '. Both experience cohorts must be represented.'),
        _check('self-report', matched(*_FEELINGS), 'Endorsements / answers. '
               + '. '.join(f'{feeling}: {counts(feeling)}' for feeling in _FEELINGS) + '.'),
        _check('voluntary-return', matched('returns'), 'Returned / observed voluntary choices: ' + counts('returns')
               + '. A zero denominator means this group has no observed voluntary choice.'),
        _check('uncertainty', matched('boredom_bounds'), 'Minimum bored, maximum if all missing endorsed boredom, '
               'and total sessions: ' + counts('boredom_bounds') + '. These bounds cover the synthetic sample only.'),
        _interpretation(submission['interpretation'], sessions),
    ]
