"""Trace the discovery of environmental story cues through a bounded route graph."""

from collections import defaultdict
from unicodedata import category

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'diegetic-narrative', 'title': 'Environmental clues and diegetic narrative',
    'roles': ['content', 'ui', 'gameplay', 'verification'],
    'workflow': [
        'Choose one event and one response the player can infer before making a decision. Write down what '
        'changed in the place, who had reason to change it, and which physical traces would remain.',
        'Stage traces along the actual approach. A damaged object can establish the problem, a sign can '
        'show where people went, and a sound beyond a doorway can confirm the route. Give signs an author '
        'and a practical purpose in the world. Let the player connect clues instead of explaining the conclusion.',
        'Walk every offered route. Let an optional room add a personal detail while keeping the needed '
        'evidence available to players who take the shortest path. Leave time to draw an inference before acting.',
        'Frame clues at the player camera, including on re-entry and at gameplay speed. Write positional '
        'captions for meaningful sounds and audio descriptions for visual clues. Preserve the evidence '
        'and its ambiguity in each presentation.',
    ],
    'deliverables': [
        'A route map marking first discoveries, optional details, the decision and the information needed there.',
        'A cue sheet with the observed object, sound or inscription, intended inference, placement, '
        'caption or description, and captures from the playable approach.',
    ],
    'verification': [
        'Walk direct and exploratory paths in the build, with sound muted and with visual clues unavailable. '
        'Check framing, lighting, mix, caption timing and navigation to the cue under each supported setting.',
        'In an authorized playtest, ask what happened and which traces suggested it before explaining the '
        'intended story. Record missed or conflicting interpretations separately from route calculations.',
    ],
    'exercise': 'Give two routes through a flooded seed library enough evidence to explain where its trays went.',
}

_BEATS = ('disruption', 'response', 'aside')
_PROFILES = ('standard', 'muted', 'audio-only')
# Each source uses one specific sample, in the units named by its field.
_SAMPLES = {
    'prop': ('visible_height_px', 0, 8192, 24),
    'sign': ('visible_glyph_px', 0, 1024, 14),
    'sound': ('above_ambience_db', -96, 96, 6),
}


def _cue(key, room, second, beat, kind, line, sample, alternative):
    return {'id': key, 'room': room, 'second': second, 'beat': beat, 'kind': kind,
            'evidence': line, 'sample': {_SAMPLES[kind][0]: sample},
            'alternative': {'channel': 'caption' if kind == 'sound' else 'audio-description',
                            'beat': beat, 'evidence': alternative}}


EXERCISES = [{
    'id': TRACK['id'], 'title': 'Follow the missing seed trays',
    'brief': 'Write three inferences named disruption, response and aside. List 3–12 rooms in travel order. '
             'The first is the entry and the last is the decision. A room may link to up to three later '
             'rooms. A visit lasts dwell_s (1–60 seconds, zero at the final decision). List up to 48 cues '
             'with unique IDs. A cue fires at its integer second in the room, starting at zero and strictly '
             'before departure. One cue conveys one beat. Describe observable evidence in up to 140 characters. '
             'For this fixture a prop needs 24 visible pixels of height, a sign needs 14 visible pixels of glyph '
             'height, and a sound needs 6 dB above local ambience. Enter zero visible pixels for a hidden clue. '
             'Standard uses passing primary sources. Muted drops sounds and can receive captions. Audio-only '
             'drops props/signs and can receive audio descriptions. An optional alternative (or null) fires '
             'at the same time, independently of the primary sample, and must identify the same beat. Each '
             'route must support each essential beat with two different primary source kinds. Use all three kinds '
             'across the routes. Make the aside available on some routes and absent from others. In each profile, '
             'place the first response 4–30 seconds after the first disruption and at least 2 seconds before '
             'the decision. The Lab checks declared routes, samples and cue assignments. Playable footage, '
             'listening and reader interpretation require separate review.',
    'criteria': [
        {'id': 'routes', 'label': 'Offer two complete routes, use every room and avoid premature dead ends.'},
        {'id': 'primary-samples', 'label': 'Meet the declared camera or local audibility target for each primary clue.'},
        {'id': 'clue-layers', 'label': 'Support each essential inference with two source kinds per route and use prop, sound and sign across them.'},
        {'id': 'optional-discovery', 'label': 'Let the aside be discovered or missed while retaining both essential beats on every route.'},
        {'id': 'sensory-alternatives', 'label': 'Keep both essential inferences available on each muted and audio-only route with matched alternatives.'},
        {'id': 'discovery-pacing', 'label': 'Space first discoveries and leave time to act in all three presentations.'},
    ],
    'example': {
        'beats': {'disruption': 'Water flooded the seed drawers.',
                  'response': 'The crew moved the trays to the drying loft.',
                  'aside': 'Schoolchildren kept the earliest seed calendars.'},
        'rooms': [
            {'id': 'vestibule', 'dwell_s': 8, 'next': ['cart_bay', 'reading_nook']},
            {'id': 'cart_bay', 'dwell_s': 10, 'next': ['hoist']},
            {'id': 'reading_nook', 'dwell_s': 12, 'next': ['hoist']},
            {'id': 'hoist', 'dwell_s': 6, 'next': ['loft_choice']},
            {'id': 'loft_choice', 'dwell_s': 0, 'next': []},
        ],
        'cues': [
            _cue('waterline', 'vestibule', 1, 'disruption', 'prop', 'Curled drawer labels end at a chalky waterline.', 42,
                 'A chalky waterline crosses the paper labels on the seed drawers.'),
            _cue('drips', 'vestibule', 3, 'disruption', 'sound', 'Drops ring against the empty metal seed drawers.', 9,
                 'Water drips into the seed drawers on the left.'),
            _cue('cart_tag', 'cart_bay', 4, 'response', 'sign', 'A tag on the empty cart reads “Seed trays — drying loft”.', 19,
                 'The cart tag reads “Seed trays — drying loft”.'),
            _cue('lift_basket', 'reading_nook', 5, 'response', 'prop', 'A basket of seed trays hangs halfway to the loft.', 37,
                 'The rope overhead carries a basket of seed trays up toward the loft.'),
            _cue('calendar', 'reading_nook', 8, 'aside', 'sign', 'The oldest sowing chart is signed “Hill School, Year Four”.', 18,
                 'A sowing chart bears a handwritten signature from Hill School, Year Four.'),
            _cue('tray_call', 'hoist', 1, 'response', 'sound', 'Above the hoist a voice calls, “One more tray for the drying loft!”', 11,
                 'Above the hoist, a worker calls for one more tray for the drying loft.'),
        ],
    },
}]


def _words(value, name):
    _text(value, 140, name)
    if not any(category(char)[0] in 'LN' for char in value):
        raise ValueError(f'{name} needs visible words or numbers.')


def _validate(data):
    _object(data, ('beats', 'rooms', 'cues'), 'Submission')
    _object(data['beats'], _BEATS, 'beats')
    for beat in _BEATS:
        _words(data['beats'][beat], beat)
    if len({' '.join(line.casefold().split()) for line in data['beats'].values()}) != len(_BEATS):
        raise ValueError('Give each beat a distinct inference.')

    rooms = data['rooms']
    _array(rooms, 3, 12, 'rooms')
    by_room = {}
    for index, room in enumerate(rooms):
        _object(room, ('id', 'dwell_s', 'next'), 'room')
        key = room['id']
        _identifier(key, 'room ID')
        if key in by_room:
            raise ValueError('Room IDs must be unique.')
        by_room[key] = room
        final = index == len(rooms) - 1
        _integer(room['dwell_s'], 0 if final else 1, 0 if final else 60, 'dwell_s')
        _array(room['next'], 0, 0 if final else 3, 'next')
        for destination in room['next']:
            _identifier(destination, 'destination')
        if len(set(room['next'])) != len(room['next']):
            raise ValueError('Room exits must be distinct.')
    indices = {key: index for index, key in enumerate(by_room)}
    for key, room in by_room.items():
        if any(indices.get(dest, -1) <= indices[key] for dest in room['next']):
            raise ValueError('Each exit must name a later room in the list.')

    _array(data['cues'], 0, 48, 'cues')
    cue_ids = set()
    for cue in data['cues']:
        _object(cue, ('id', 'room', 'second', 'beat', 'kind', 'evidence', 'sample', 'alternative'), 'cue')
        _identifier(cue['id'], 'cue ID')
        _identifier(cue['room'], 'cue room')
        if cue['id'] in cue_ids or cue['room'] not in by_room:
            raise ValueError('Cue IDs must be unique and each cue must name a listed room.')
        cue_ids.add(cue['id'])
        _integer(cue['second'], 0, by_room[cue['room']]['dwell_s'] - 1, 'cue second')
        _choice(cue['beat'], _BEATS, 'cue beat')
        _choice(cue['kind'], _SAMPLES, 'cue kind')
        _words(cue['evidence'], 'cue evidence')
        field, low, high, _ = _SAMPLES[cue['kind']]
        _object(cue['sample'], (field,), 'source sample')
        _integer(cue['sample'][field], low, high, field)
        alt = cue['alternative']
        if alt is not None:
            _object(alt, ('channel', 'beat', 'evidence'), 'alternative')
            _choice(alt['channel'], ('caption', 'audio-description'), 'alternative channel')
            _choice(alt['beat'], _BEATS, 'alternative beat')
            _words(alt['evidence'], 'alternative evidence')
    return by_room


def _walk(rooms, key, prefix=()):
    path = (*prefix, key)
    if not rooms[key]['next']:
        yield path
    for destination in rooms[key]['next']:
        yield from _walk(rooms, destination, path)


def _presentations(cues):
    events = defaultdict(list)
    faint, mismatched = [], []
    for cue in cues:
        kind = cue['kind']
        field, _, _, minimum = _SAMPLES[kind]
        profiles = set()
        if cue['sample'][field] >= minimum:
            profiles.update(('standard', 'audio-only' if kind == 'sound' else 'muted'))
        else:
            faint.append(cue['id'])
        alt = cue['alternative']
        if alt is not None:
            expected = 'caption' if kind == 'sound' else 'audio-description'
            if alt['channel'] == expected and alt['beat'] == cue['beat']:
                profiles.add('muted' if kind == 'sound' else 'audio-only')
            else:
                mismatched.append(cue['id'])
        events[cue['room']].append((cue['second'], cue['beat'], kind, profiles))
    return events, faint, mismatched


def _route_discoveries(path, rooms, events):
    elapsed = 0
    layers = defaultdict(set)
    first = {profile: {} for profile in _PROFILES}
    for key in path:
        for second, beat, kind, profiles in events[key]:
            if 'standard' in profiles:
                layers[beat].add(kind)
            time = elapsed + second
            for profile in profiles:
                first[profile][beat] = min(first[profile].get(beat, time), time)
        elapsed += rooms[key]['dwell_s']
    return elapsed, layers, first


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']:
        raise ValueError('Unknown diegetic narrative exercise.')
    rooms = _validate(submission)
    events, faint, mismatched = _presentations(submission['cues'])
    entry, decision = next(iter(rooms)), next(reversed(rooms))
    walks = list(_walk(rooms, entry))
    complete = [path for path in walks if path[-1] == decision]
    reachable = {key for path in walks for key in path}
    route_count = len(complete)
    layered = essential = optional = accessible = paced = 0
    kinds = set()
    timing_failure = ''
    for path in complete:
        deadline, layers, first = _route_discoveries(path, rooms, events)
        kinds.update(kind for group in layers.values() for kind in group)
        layered += all(len(layers[beat]) >= 2 for beat in _BEATS[:2])
        essential += all(beat in first['standard'] for beat in _BEATS[:2])
        optional += 'aside' in first['standard']
        for profile, moments in first.items():
            both = 'disruption' in moments and 'response' in moments
            if profile != 'standard':
                accessible += both
            if both and 4 <= moments['response'] - moments['disruption'] <= 30 and deadline - moments['response'] >= 2:
                paced += 1
            elif not timing_failure:
                timing_failure = (f' First mismatch on {"/".join(path)} ({profile}): disruption at '
                                  f'{moments.get("disruption", "missing")}, response at {moments.get("response", "missing")}, '
                                  f'decision at {deadline}s.')
    return [
        _check('routes', route_count >= 2 and route_count == len(walks) and len(reachable) == len(rooms),
               f'{route_count} complete routes, {len(walks) - route_count} premature endings, {len(rooms) - len(reachable)} unreachable rooms.'),
        _check('primary-samples', bool(submission['cues']) and not faint,
               f'{len(submission["cues"])} primary cues sampled. Below target: {", ".join(faint[:4]) or "none"}.'),
        _check('clue-layers', route_count > 0 and layered == route_count and kinds == _SAMPLES.keys(),
               f'{layered}/{route_count} complete routes layer both essential beats. Source kinds encountered: {", ".join(sorted(kinds)) or "none"}.'),
        _check('optional-discovery', essential == route_count and 0 < optional < route_count,
               f'Both essential beats found on {essential}/{route_count} standard routes. Aside found on {optional}/{route_count}.'),
        _check('sensory-alternatives', route_count > 0 and accessible == 2 * route_count and not mismatched,
               f'Both beats available on {accessible}/{2 * route_count} muted or audio-only routes. '
               f'Mismatched alternative channels or beats: {", ".join(mismatched[:4]) or "none"}.'),
        _check('discovery-pacing', route_count > 0 and paced == len(_PROFILES) * route_count,
               f'{paced}/{len(_PROFILES) * route_count} route presentations meet both timing windows.' + timing_failure),
    ]
