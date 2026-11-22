"""Select takes from synthetic session notes and reconcile the resulting caption sheet."""

import re
from unicodedata import category

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _choice, _integer


TRACK = {
    'id': 'voice-direction', 'title': 'Voice casting, performance and dialogue pickups',
    'roles': ['content', 'ui', 'gameplay', 'verification'],
    'workflow': [
        'Write an original voice brief with an audience, relationship, pace, vocal placement and emotional range. '
        'An NPC trying to calm a neighbor can start close and quick, then slow down when the neighbor responds. '
        'A narrator can give the listener space to picture a reveal. A radio DJ can welcome a whole town, '
        'leave a beat after a station ID and finish before the music vocal begins.',
        'Cast with short original sides from contrasting moments. Explain character, scope of use, credit, '
        'compensation and any recording, editing or reuse plans. Get the performer’s agreement for the specific '
        'use. Obtain separate explicit permission for digital voice replication. An audition from another '
        'project grants no such permission. Direct an original performance through playable traits and avoid '
        'requests to imitate an identifiable person without authorization.',
        'Give each line a stable ID, the preceding cue, what the character knows, their addressee and what they '
        'want to change. Mark intentional stress, breaths and the pronunciation of invented names. To change '
        'a read, give the actor an action such as persuading someone to stay, then try another intention.',
        'Record clean, consistently placed takes with room tone and handles. Keep raw files separate from edits. '
        'Log line, actor code, take, script version, permitted uses and pickup reason. For a radio voice, audition '
        'the dry original and the processed broadcast version. Leave space for key words under the music bed.',
        'Choose takes in scene order. Listen through transitions for shifts in energy, emphasis, mic distance '
        'and noise. For a pickup, play the neighboring accepted lines and match the recording setup. Reconcile '
        'actual spoken words, attribution and caption timing after each edit. Keep uncleared lines on hold.',
    ],
    'deliverables': [
        'Original casting sides and character briefs for dialogue, narration and broadcast work, with a scope-of-use record.',
        'Contextual script, pronunciation guide, take sheet and pickup list tied to line IDs and edit revisions.',
        'Selected dialogue and caption sheet plus listening notes from the dry session and the final game mix.',
    ],
    'verification': [
        'Trace approved lines to their performer, permitted use, selected take and exact spoken boundaries. '
        'Compare the take transcript and pronunciations with the script before declaring a pickup complete.',
        'Have listeners unfamiliar with the script transcribe key words in the actual mix on target outputs. '
        'Review pronunciation, emotional intent, radio intelligibility, caption readability and accessibility '
        'with the performer, director and listeners. Metadata checks alone cannot judge a spoken performance.',
    ],
    'exercise': 'Select and hold takes for an original three-voice scene, diagnose pickups and prepare the caption sheet.',
}

_ROLES = ('npc', 'narrator', 'radio-dj')
_DELIVERIES = ('reassure', 'warn', 'confide', 'welcome', 'explain', 'reflect')
_FAULTS = ('clearance', 'casting', 'delivery', 'script', 'pronunciation', 'clipping', 'timing')
_CONSENT = ('approved-for-role', 'audition-only', 'unconfirmed', 'withdrawn')
_STYLES = ('original', 'unauthorized-imitation')


def _take(key, performer, delivery, text, reading, duration, onset, offset, faults, **changes):
    return dict({'id': key, 'performer': performer, 'consent': 'approved-for-role', 'style': 'original',
                 'delivery': delivery, 'transcript': text, 'reading': reading, 'clip_ms': duration,
                 'in_ms': onset, 'out_ms': offset, 'clipped_samples': 0, 'faults': faults}, **changes)


EXERCISES = [{
    'id': 'voice-direction', 'title': 'Direct the reopening of a night ferry',
    'brief': 'Use synthetic records only. Cast 3–8 fictional speakers and cover npc, narrator and radio-dj '
             'in 3–12 lines. Give each speaker a brief and performer code. Give each line context, a delivery '
             '(reassure, warn, confide, welcome, explain or reflect), text, a case-sensitive pronunciation term '
             'as a complete word or phrase from that text and its target reading. The start_ms (0–120000) and slot_ms (1–30000) define '
             'the line’s edit window. Clip playback starts at start_ms. Mark each of 1–6 takes with every '
             'applicable fault. Clearance requires approved-for-role consent and original style. Casting matches '
             'the performer code, delivery matches the requested intention, script matches the exact transcript '
             'and pronunciation matches the reading. Clipping means clipped_samples > 0. Timing requires '
             '0 <= in_ms < out_ms <= clip_ms and out_ms <= slot_ms. Trailing silence may extend beyond the slot. '
             'Select one fault-free take or use null when every take needs attention. Demonstrate at least one '
             'usable take and one diagnosed fault. A selected take gets one caption with its speaker, verbatim '
             'spoken text and absolute speech start/end. A held line has a null caption. These are synthetic '
             'editorial records. The Lab neither auditions audio nor verifies real consent.',
    'criteria': [
        {'id': 'casting-briefs', 'label': 'Bind all three spoken roles to original briefs and scripted lines.'},
        {'id': 'take-diagnostics', 'label': 'Identify the actual faults in each supplied take record.'},
        {'id': 'use-permission', 'label': 'Select only original takes with declared permission for the role.'},
        {'id': 'edit-selection', 'label': 'Select a usable read where available and hold lines that need pickups.'},
        {'id': 'caption-conform', 'label': 'Reconcile captions with the selected speaker, transcript and audible interval.'},
    ],
    'example': {
        'source': 'synthetic',
        'cast': [
            {'id': 'ren', 'role': 'npc', 'performer': 'actor-a',
             'brief': 'The deckhand talks quietly to the last passenger and slows on the name of the pier.'},
            {'id': 'chronicle', 'role': 'narrator', 'performer': 'actor-b',
             'brief': 'The storyteller leaves a beat between the drifting boat and the first light on shore.'},
            {'id': 'wren-air', 'role': 'radio-dj', 'performer': 'actor-c',
             'brief': 'The evening host speaks to late-shift workers with a gentle lift on each place name.'},
        ],
        'lines': [
            {'id': 'deck-promise', 'speaker': 'ren', 'context': 'The passenger hesitates at the open gangway.',
             'delivery': 'reassure', 'text': 'Yarrow Pier is still lit.', 'term': 'Yarrow', 'reading': 'YAH-roh',
             'start_ms': 1000, 'slot_ms': 2400, 'takes': [
                 _take('deck-a', 'actor-a', 'warn', 'Yarrow Pier is still lit.', 'YA-row', 2300, 80, 2040,
                       ['delivery', 'pronunciation']),
                 _take('deck-b', 'actor-a', 'reassure', 'Yarrow Pier is still lit.', 'YAH-roh', 2700, 110, 2130, []),
             ], 'selected': 'deck-b', 'caption': {
                 'speaker': 'ren', 'text': 'Yarrow Pier is still lit.', 'start_ms': 1110, 'end_ms': 3130}},
            {'id': 'fog-lift', 'speaker': 'chronicle', 'context': 'From the shore, the ferry lamp becomes visible.',
             'delivery': 'reflect', 'text': 'Across Vey, the lamp returned.', 'term': 'Vey', 'reading': 'vay',
             'start_ms': 4000, 'slot_ms': 3200, 'takes': [
                 _take('fog-a', 'actor-b', 'reflect', 'Across Vey, the lamp returned.', 'vay', 3100, 160, 2820,
                       ['clipping'], clipped_samples=4),
             ], 'selected': None, 'caption': None},
            {'id': 'last-crossing', 'speaker': 'wren-air', 'context': 'The music fades for a station service bulletin.',
             'delivery': 'welcome', 'text': 'Brindle riders, your ferry is here.', 'term': 'Brindle', 'reading': 'BRIN-dul',
             'start_ms': 8000, 'slot_ms': 3000, 'takes': [
                 _take('air-a', 'actor-c', 'welcome', 'Brindle riders, your ferry is here.', 'BRIN-dul', 2600, 90,
                       2150, ['clearance'], consent='audition-only'),
                 _take('air-b', 'actor-c', 'welcome', 'Brindle riders, your ferry is here.', 'BRIN-dul', 2840, 40, 2220, []),
             ], 'selected': 'air-b', 'caption': {
                 'speaker': 'wren-air', 'text': 'Brindle riders, your ferry is here.', 'start_ms': 8040, 'end_ms': 10220}},
        ],
    },
}]


def _visible(value, limit, field):
    _text(value, limit, field)
    if not any(category(character)[0] in 'LNPS' for character in value):
        raise ValueError(f'{field} must contain visible text.')


def _index(rows, low, high, field):
    _array(rows, low, high, field)
    result = {}
    for row in rows:
        if type(row) is not dict or 'id' not in row:
            raise ValueError(f'Each {field} entry needs an ID.')
        key = row['id']
        _identifier(key, f'{field} ID')
        if key in result:
            raise ValueError(f'{field} contains a duplicate ID.')
        result[key] = row
    return result


def _cast(rows):
    cast = _index(rows, 3, 8, 'cast')
    for speaker in cast.values():
        _object(speaker, ('id', 'role', 'performer', 'brief'), 'cast member')
        _identifier(speaker['performer'], 'performer code')
        _choice(speaker['role'], _ROLES, 'role')
        _visible(speaker['brief'], 240, 'brief')
    return cast


def _line_fields(line):
    _object(line, ('id', 'speaker', 'context', 'delivery', 'text', 'term', 'reading', 'start_ms', 'slot_ms',
                   'takes', 'selected', 'caption'), 'scripted line')
    _identifier(line['speaker'], 'speaker')
    _choice(line['delivery'], _DELIVERIES, 'line delivery')
    for field, limit in (('context', 240), ('text', 240), ('term', 48), ('reading', 96)):
        _visible(line[field], limit, field)
    _integer(line['start_ms'], 0, 120000, 'start_ms')
    _integer(line['slot_ms'], 1, 30000, 'slot_ms')
    if line['selected'] is not None:
        _identifier(line['selected'], 'selected take')
    if line['caption'] is not None:
        caption = line['caption']
        _object(caption, ('speaker', 'text', 'start_ms', 'end_ms'), 'caption')
        _identifier(caption['speaker'], 'caption speaker')
        _visible(caption['text'], 240, 'caption text')
        for field in ('start_ms', 'end_ms'):
            _integer(caption[field], 0, 150000, field)


def _take_faults(take, line, speaker):
    _object(take, ('id', 'performer', 'consent', 'style', 'delivery', 'transcript', 'reading', 'clip_ms',
                   'in_ms', 'out_ms', 'clipped_samples', 'faults'), 'take')
    _identifier(take['performer'], 'performer code')
    _choice(take['consent'], _CONSENT, 'consent')
    _choice(take['style'], _STYLES, 'style')
    _choice(take['delivery'], _DELIVERIES, 'take delivery')
    _visible(take['transcript'], 240, 'transcript')
    _visible(take['reading'], 96, 'take reading')
    _integer(take['clip_ms'], 1, 60000, 'clip_ms')
    for field in ('in_ms', 'out_ms'):
        _integer(take[field], 0, 60000, field)
    _integer(take['clipped_samples'], 0, 100000, 'clipped_samples')
    _array(take['faults'], 0, len(_FAULTS), 'faults')
    for fault in take['faults']:
        _choice(fault, _FAULTS, 'take fault')
    if len(set(take['faults'])) != len(take['faults']):
        raise ValueError('List each take fault once.')
    defects = {
        'clearance': take['consent'] != 'approved-for-role' or take['style'] != 'original',
        'casting': speaker is None or take['performer'] != speaker['performer'],
        'delivery': take['delivery'] != line['delivery'],
        'script': take['transcript'] != line['text'],
        'pronunciation': take['reading'] != line['reading'],
        'clipping': take['clipped_samples'] > 0,
        'timing': not 0 <= take['in_ms'] < take['out_ms'] <= min(take['clip_ms'], line['slot_ms']),
    }
    return {name for name, active in defects.items() if active}


def assess(exercise_id, submission):
    if exercise_id != 'voice-direction':
        raise ValueError('Unknown voice direction exercise.')
    _object(submission, ('source', 'cast', 'lines'), 'Voice direction submission')
    _choice(submission['source'], ('synthetic',), 'source')
    cast = _cast(submission['cast'])
    lines = _index(submission['lines'], 3, 12, 'lines')
    speakers = set()
    terms_in_script = True
    diagnostic_errors, selection_errors, clearance_errors, caption_errors = [], [], [], []
    diagnosed_takes = used_takes = 0
    for line_id, line in lines.items():
        _line_fields(line)
        speakers.add(line['speaker'])
        term_pattern = r'(?<!\w)' + re.escape(line['term']) + r'(?!\w)'
        terms_in_script &= re.search(term_pattern, line['text']) is not None
        takes = _index(line['takes'], 1, 6, 'takes')
        faults = {}
        for take_id, take in takes.items():
            defects = _take_faults(take, line, cast.get(line['speaker']))
            faults[take_id] = defects
            diagnosed_takes += bool(defects)
            if set(take['faults']) != defects:
                diagnostic_errors.append(f'{line_id}/{take_id}')
        selected = line['selected']
        expected_caption = None
        if selected is None:
            if any(not issues for issues in faults.values()):
                selection_errors.append(line_id)
        elif selected not in takes:
            selection_errors.append(line_id)
            clearance_errors.append(line_id)
        else:
            if faults[selected]:
                selection_errors.append(line_id)
            else:
                used_takes += 1
            if 'clearance' in faults[selected]:
                clearance_errors.append(line_id)
            take = takes[selected]
            expected_caption = {'speaker': line['speaker'], 'text': take['transcript'],
                                'start_ms': line['start_ms'] + take['in_ms'], 'end_ms': line['start_ms'] + take['out_ms']}
        if (selected is not None and selected not in takes) or line['caption'] != expected_caption:
            caption_errors.append(line_id)
    roles = {cast[key]['role'] for key in speakers if key in cast}
    cast_ok = speakers == set(cast) and roles == set(_ROLES) and terms_in_script
    return [
        _check('casting-briefs', cast_ok, f'{len(roles)} of 3 delivery roles appear. Each cast speaker must have a '
               'line and each pronunciation term must occur in its script.'),
        _check('take-diagnostics', diagnosed_takes > 0 and not diagnostic_errors,
               f'{diagnosed_takes} takes contain at least one documented defect. Incorrect fault lists '
               f'({len(diagnostic_errors)}): {", ".join(diagnostic_errors[:6]) or "none"}.'),
        _check('use-permission', not clearance_errors, f'{len(clearance_errors)} selected takes have unverified clearance.'),
        _check('edit-selection', used_takes > 0 and not selection_errors, f'{used_takes} usable takes selected. '
               f'Lines needing a different selection: {", ".join(selection_errors) or "none"}.'),
        _check('caption-conform', not caption_errors, f'{len(caption_errors)} captions differ from the selected '
               'speaker, spoken text or absolute speech boundaries.'),
    ]
