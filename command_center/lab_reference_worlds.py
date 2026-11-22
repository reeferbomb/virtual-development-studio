"""Simulate scheduled ferry staff, a public response and a repeating shift."""

from .lab_design import _array, _check, _identifier, _object
from .lab_gameplay import _choice, _integer


_ID = 'reference-worlds'
_ACTIONS = ('wait', 'ring', 'listen', 'stamp')
_RESULTS = ('quiet', 'noticed', 'unheard', 'lesson', 'missed', 'issued', 'denied')

TRACK = {
    'id': _ID, 'title': 'Reference worlds, public reactions and recurring schedules',
    'roles': ['content', 'gameplay', 'architecture', 'verification'],
    'workflow': [
        'Read the cited primary sources in reference_studies/WORLDS.md. Record the edition and the '
        'observable action, world response and feedback. Label a proposed implementation as your own inference.',
        'Study ordinary activities and visible wanted levels in Grand Theft Auto V. Design an original '
        'public response with a reason to visit, an escalation condition and an observable recovery.',
        'Study Shenmue’s independent resident schedules. Give each resident a purpose at each stop. '
        'Mark opening and closing boundaries and test an appointment both just before and just after a move.',
        'Study repeated appointments and selective persistence in Majora’s Mask. List what each reset '
        'clears and preserves. Give players a way to discover a missed appointment on the next cycle.',
    ],
    'deliverables': [
        'A sourced observation and original design inference for each studied game. Include a schedule '
        'for the original cast, a world-response table, and a list of transient and persistent state.',
        'A two-cycle trace of arrivals, encounters, visible responses and service availability, '
        'with the final state before reset and the first state afterward.',
    ],
    'verification': [
        'Recompute the roster on location and time boundaries. Test a witnessed call, an unanswered call, '
        'escalation and natural recovery. Compare every field across the reset.',
        'In a playable build, test travel time, interruptions, missed appointments and feedback with a '
        'first-time player. Record what they expect to change or persist on a second visit.',
    ],
    'exercise': 'Run two shifts at a tidal ferry office and predict its staff, public response and repeatable service.',
}


def _row(site, action, present, attention, known, permit, result):
    return dict(site=site, action=action, present=present, attention=attention, known=known,
                permit=permit, result=result)


EXERCISES = [{
    'id': _ID, 'title': 'Run two shifts at the tidal ferry office',
    'brief': (
        'Choose a 6–16 tick shift, 3–8 named sites, a self-service permit office and a guide among 2–4 residents. '
        'Give each resident 2–8 ordered [start,end,site] stops covering [0,period) exactly once and visiting '
        'at least two distinct sites. End ticks belong to the next stop. Submit exactly two shifts of rows. '
        'Each row chooses the traveler’s site and action at that tick and predicts the residents present '
        '(in any order), attention, known tide table, permit and result. Travel takes no modeled time. '
        'Start with zero attention, no knowledge and no permit. Before local tick zero of the second shift, '
        'reset attention and permit, keep knowledge and repeat the staff rounds. First look up the roster. '
        'Ringing with anyone present returns noticed and raises attention by one, capped at two. All other '
        'actions lower attention by one, floored at zero, including an unheard ring. Wait returns quiet. '
        'Then resolve listen: if the guide is present and updated attention is zero, return lesson and set '
        'known true; otherwise return missed. Stamp returns issued and sets permit true only at the office '
        'with knowledge and zero updated attention; otherwise return denied. Knowledge and permit stay set '
        'until their stated reset. Predict all rows. Include a successful and a missed lesson, both kinds of '
        'ring, a witnessed ring at the cap of two, and natural recovery to zero. Obtain knowledge in shift one, demonstrate '
        'a denied stamp and secure a permit in both shifts. Finish shift one at attention two holding a '
        'permit; choose wait on the first tick of shift two to expose the reset.'
    ),
    'criteria': [
        {'id': 'schedule', 'label': 'Cover every tick for every resident with an unambiguous repeating itinerary.'},
        {'id': 'encounters', 'label': 'Predict the complete local roster and both successful and missed lessons.'},
        {'id': 'public-response', 'label': 'Predict witnessed and unheard calls, capped escalation and natural recovery.'},
        {'id': 'knowledge', 'label': 'Learn the timetable in the first shift and preserve it throughout the next.'},
        {'id': 'service', 'label': 'Predict permit ownership, show a denied stamp, and obtain a permit in both shifts.'},
        {'id': 'rollover', 'label': 'Reset attention and permit before the first action of the next shift while retaining knowledge.'},
    ],
    'example': {
        'period': 8, 'sites': ['tower', 'press', 'landing'], 'office': 'press', 'guide': 'reader',
        'schedules': {
            'reader': [[0, 3, 'tower'], [3, 6, 'press'], [6, 8, 'landing']],
            'clerk': [[0, 2, 'press'], [2, 5, 'landing'], [5, 8, 'tower']],
        },
        'trace': [
            _row('press', 'stamp', ['clerk'], 0, False, False, 'denied'),
            _row('tower', 'listen', ['reader'], 0, True, False, 'lesson'),
            _row('press', 'stamp', [], 0, True, True, 'issued'),
            _row('tower', 'ring', [], 0, True, True, 'unheard'),
            _row('landing', 'wait', ['clerk'], 0, True, True, 'quiet'),
            _row('tower', 'ring', ['clerk'], 1, True, True, 'noticed'),
            _row('landing', 'ring', ['reader'], 2, True, True, 'noticed'),
            _row('tower', 'ring', ['clerk'], 2, True, True, 'noticed'),
            _row('press', 'wait', ['clerk'], 0, True, False, 'quiet'),
            _row('landing', 'listen', [], 0, True, False, 'missed'),
            _row('landing', 'ring', ['clerk'], 1, True, False, 'noticed'),
            _row('press', 'ring', ['reader'], 2, True, False, 'noticed'),
            _row('tower', 'wait', [], 1, True, False, 'quiet'),
            _row('press', 'wait', ['reader'], 0, True, False, 'quiet'),
            _row('press', 'stamp', [], 0, True, True, 'issued'),
            _row('landing', 'wait', ['reader'], 0, True, True, 'quiet'),
        ],
    },
}]


def _read(data):
    _object(data, ('period', 'sites', 'office', 'guide', 'schedules', 'trace'), 'World')
    _integer(data['period'], 6, 16, 'Shift period')
    sites = data['sites']
    _array(sites, 3, 8, 'sites')
    for site in sites:
        _identifier(site, 'Site')
    if len(set(sites)) != len(sites):
        raise ValueError('Each site needs a unique identifier.')
    _identifier(data['office'], 'Office')
    _identifier(data['guide'], 'Guide')
    schedules = data['schedules']
    if type(schedules) is not dict or not 2 <= len(schedules) <= 4:
        raise ValueError('Provide schedules for two to four residents.')
    if data['guide'] not in schedules or data['office'] not in sites:
        raise ValueError('Guide and office must resolve to a resident and site.')
    for resident, stops in schedules.items():
        _identifier(resident, 'Resident')
        _array(stops, 2, 8, 'Stops')
        for stop in stops:
            _array(stop, 3, 3, 'Stop')
            start, end, site = stop
            _integer(start, 0, 16, 'Start')
            _integer(end, 0, 16, 'End')
            _choice(site, sites, 'Stop site')
    _array(data['trace'], data['period'] * 2, data['period'] * 2, 'Trace')
    for row in data['trace']:
        _object(row, ('site', 'action', 'present', 'attention', 'known', 'permit', 'result'), 'Tick')
        _choice(row['site'], sites, 'Traveler site')
        _choice(row['action'], _ACTIONS, 'Action')
        _choice(row['result'], _RESULTS, 'Action result')
        _integer(row['attention'], 0, 2, 'Attention')
        if type(row['known']) is not bool or type(row['permit']) is not bool:
            raise ValueError('Knowledge and permit must be booleans.')
        _array(row['present'], 0, 4, 'Roster')
        for resident in row['present']:
            _identifier(resident, 'Predicted resident')


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown reference worlds exercise.')
    _read(submission)
    period, schedules, trace = (submission[key] for key in ('period', 'schedules', 'trace'))
    rosters = [{} for _ in range(period)]
    invalid = []
    for resident, stops in schedules.items():
        cursor = 0
        covered = True
        for start, end, site in stops:
            if start != cursor or not start < end <= period:
                covered = False
                break
            for phase in range(start, end):
                rosters[phase].setdefault(site, set()).add(resident)
            cursor = end
        if not covered or cursor != period or len({s[2] for s in stops}) < 2:
            invalid.append(resident)
    checks = [_check('schedule', not invalid,
                     'Incomplete, unordered or stationary itineraries: ' + ', '.join(sorted(invalid)) + '.'
                     if invalid else f'{len(schedules)} residents have complete {period}-tick itineraries.')]
    if invalid:
        return checks + [_check(c['id'], False, 'Simulation requires complete itineraries.')
                         for c in EXERCISES[0]['criteria'][1:]]

    attention = 0
    known = permit = recovered = capped = learned_first = rollover = boundary_ready = False
    observed = set()
    issued_shifts = set()
    wrong = {lane: [] for lane in ('encounters', 'public-response', 'knowledge', 'service')}
    for tick, row in enumerate(trace):
        phase = tick % period
        if tick == period:
            boundary_ready = known and permit and attention == 2
            attention, permit = 0, False
        site, action = row['site'], row['action']
        present = rosters[phase].get(site, set())
        if sorted(row['present']) != sorted(present):
            wrong['encounters'].append(tick)
        before = attention
        if action == 'ring' and present:
            capped |= attention == 2
            attention = min(2, attention + 1)
            result = 'noticed'
        else:
            attention = max(0, attention - 1)
            if action == 'listen':
                if submission['guide'] in present and attention == 0:
                    known, result = True, 'lesson'
                    learned_first |= tick < period
                else:
                    result = 'missed'
            elif action == 'stamp':
                if site == submission['office'] and known and attention == 0:
                    permit, result = True, 'issued'
                    issued_shifts.add(tick // period)
                else:
                    result = 'denied'
            else:
                result = 'unheard' if action == 'ring' else 'quiet'
        observed.add(result)
        recovered |= before > 0 and attention == 0
        if action == 'listen' and row['result'] != result and tick not in wrong['encounters']:
            wrong['encounters'].append(tick)
        if row['attention'] != attention or (action in ('ring', 'wait') and row['result'] != result):
            wrong['public-response'].append(tick)
        if row['known'] != known:
            wrong['knowledge'].append(tick)
        if row['permit'] != permit or (action == 'stamp' and row['result'] != result):
            wrong['service'].append(tick)
        if tick == period:
            prior = trace[tick - 1]
            rollover = (boundary_ready and prior['attention'] == 2 and prior['permit'] and prior['known']
                        and action == 'wait' and row['result'] == 'quiet' and row['attention'] == 0
                        and row['known'] and not row['permit'])

    def report(lane, coverage, detail):
        return _check(lane, coverage and not wrong[lane], f'{detail} Wrong predictions at ticks {wrong[lane]}.')

    both_ring_outcomes = {'noticed', 'unheard'} <= observed
    checks.extend([
        report('encounters', {'lesson', 'missed'} <= observed, 'Observe both a lesson and a missed meeting.'),
        report('public-response', both_ring_outcomes and recovered and capped,
               f'Both ring outcomes observed={both_ring_outcomes}, heard at cap={capped}, natural recovery={recovered}.'),
        report('knowledge', learned_first, f'Guide taught the pattern in shift one={learned_first}.'),
        report('service', 'denied' in observed and issued_shifts == {0, 1},
               f'Denied stamp observed={"denied" in observed}, shifts with a successful stamp={sorted(issued_shifts)}.'),
        _check('rollover', rollover,
               f'Ended first shift with attention two, permit and knowledge={boundary_ready}. '
               f'End and restart predictions match the required boundary={rollover}.'),
    ])
    return checks
