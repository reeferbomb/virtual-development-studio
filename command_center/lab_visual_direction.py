"""Check a simulated visual review packet against its own art-direction targets."""

from collections import Counter
import re
from unicodedata import category

from .lab_design import _array, _check, _identifier, _object, _text
from .lab_gameplay import _integer


_ID = 'visual-direction'
# Physical / representation limits for the fixture data. Each project sets its own target band.
_LIMITS = {'luma_delta': 255, 'landmark_height_pct': 100, 'door_height_cm': 1000,
           'roughness_gap_pct': 100, 'foot_drift_mm': 1000, 'open_seams': 1000}
_VIEWS = {'establishing': ('luma_delta', 'landmark_height_pct'),
          'gameplay': ('landmark_height_pct', 'door_height_cm'),
          'detail': ('roughness_gap_pct', 'open_seams'),
          'motion': ('foot_drift_mm', 'open_seams')}
_REQUIRED = {(view, metric) for view, metrics in _VIEWS.items() for metric in metrics}


TRACK = {
    'id': _ID, 'title': 'Visual direction and production expectations',
    'roles': ['content', 'gameplay', 'ui', 'verification', 'build_operations'],
    'workflow': [
        'Write a visual brief naming the genre, style, target platform, display size, camera distance and '
        'what the player must recognize in motion. A stylized handheld adventure can prioritize a readable '
        'landmark and bold shapes. A first-person restoration game may need close surface and tool detail.',
        'Assemble credited references for place, lighting, materials and movement. Annotate what to carry '
        'over and why. Pick one approved target frame and compare the candidate at the same distance, '
        'exposure and delivery size. Let the brief determine the degree of realism.',
        'Build a world whose scale and construction make sense. Check a doorway against the character, '
        'a curb against a foot, and wear against use. Separate key surfaces by material response. Test '
        'the light direction, shadow values and silhouettes at the player camera before adding detail.',
        'Compose the approach around the player’s decision. Group values around a focal point, preserve '
        'navigation cues with the HUD on, and test the route under representative lighting conditions.',
        'Watch the character traverse that route at gameplay speed. Check weight transfer, foot contact, '
        'animation transitions and camera motion. Inspect seams, clipping, aliasing and level-of-detail '
        'changes on the target device. Assign visible defects a location, owner and retake.',
    ],
    'deliverables': [
        'A genre, platform and style brief with credited references, an annotated target frame and '
        'a small set of measurable targets tied to player tasks.',
        'A review matrix pairing establishing, gameplay, material-detail and motion captures from a '
        'named candidate with reference targets, capture settings, observations and retake assignments.',
    ],
    'verification': [
        'Match build, framing, output dimensions and motion rate before comparing captures. Record '
        'measurements with units and inspect the actual images and footage at delivery size.',
        'Review art direction, scale, lighting, material consistency, readability and movement with a '
        'human reviewer. Replay retakes on the target platform and record the reviewed revision.',
    ],
    'exercise': 'Review four views of a street approach against a project-specific visual brief and assign its retakes.',
}


def _example_capture(view, digest, observations):
    moving = view == 'motion'
    return {'view': view, 'build_sha256': 'b' * 64, 'artifact_sha256': digest * 64,
            'width': 1280, 'height': 720, 'frames': 60 if moving else 1, 'fps': 30 if moving else 0,
            'observations': observations}


EXERCISES = [{
    'id': _ID, 'title': 'Review a street approach at delivery size',
    'brief': (
        'State the genre, platform, style, player task, output width, height and fps. Supply at least two '
        'distinct credited references with a takeaway each. For each metric set one inclusive integer target '
        'band and cite a reference ID. Choose the bands to suit the brief. luma_delta is the absolute '
        'difference in sampled subject and background grayscale values (0–255). landmark_height_pct '
        'is the landmark height as a percentage of the frame. door_height_cm is the world opening height. '
        'roughness_gap_pct is the difference in percentage points between two authored surface roughnesses. '
        'foot_drift_mm is horizontal travel of the planted foot during contact. open_seams counts visible '
        'unintended geometry gaps. Supply one distinct artifact SHA-256 per view from the candidate build '
        'at delivery size, separate from reference artifacts. For stills use one frame and zero fps. Motion '
        'needs at least two frames and one second at delivery fps. Measure light and landmark in establishing, landmark and '
        'door in gameplay, roughness and seams in detail, drift and seams in motion. Extra known metrics '
        'are allowed. Assign one retake with an owner and action for each observation outside its band. '
        'All example identities and measurements are simulated. This assessment checks the declared packet.'
    ),
    'criteria': [
        {'id': 'reference-links', 'label': 'Ground all six project targets in at least two distinct credited references.'},
        {'id': 'shot-matrix', 'label': 'Supply establishing, gameplay, detail and motion views exactly once.'},
        {'id': 'capture-identity', 'label': 'Bind distinct capture artifacts to this candidate and keep them apart from the reference sources.'},
        {'id': 'delivery-settings', 'label': 'Match delivery dimensions and use the prescribed still or motion sampling.'},
        {'id': 'observations', 'label': 'Record all eight required view and metric combinations.'},
        {'id': 'retakes', 'label': 'Assign every out-of-band observation exactly one retake and avoid unsupported retakes.'},
    ],
    'example': {
        'brief': {'genre': 'Exploration adventure', 'platform': 'Handheld',
                  'style': 'Painted plaster, broad shadow shapes and a brass wayfinding bell',
                  'player_task': 'Recognize the bell from the street and find the doorway beneath it.',
                  'width': 1280, 'height': 720, 'fps': 30},
        'candidate_sha256': 'b' * 64,
        'references': [
            {'id': 'street_study', 'source': 'Studio art team, Bell Street value and surface study',
             'takeaway': 'Separate the brass bell from the plaster and hold its silhouette against the sky.',
             'sha256': 'a' * 64},
            {'id': 'walk_study', 'source': 'Studio animation team, measured doorway walk-through',
             'takeaway': 'Use the character as a scale reference and keep the forefoot planted on the paving.',
             'sha256': 'c' * 64},
        ],
        'targets': {
            'luma_delta': {'reference': 'street_study', 'min': 32, 'max': 70},
            'landmark_height_pct': {'reference': 'street_study', 'min': 8, 'max': 18},
            'roughness_gap_pct': {'reference': 'street_study', 'min': 20, 'max': 45},
            'door_height_cm': {'reference': 'walk_study', 'min': 202, 'max': 215},
            'foot_drift_mm': {'reference': 'walk_study', 'min': 0, 'max': 15},
            'open_seams': {'reference': 'street_study', 'min': 0, 'max': 0},
        },
        'captures': [
            _example_capture('establishing', '1', {'luma_delta': 44, 'landmark_height_pct': 9}),
            _example_capture('gameplay', '2', {'landmark_height_pct': 16, 'door_height_cm': 210}),
            _example_capture('detail', '3', {'roughness_gap_pct': 31, 'open_seams': 1}),
            _example_capture('motion', '4', {'foot_drift_mm': 12, 'open_seams': 0}),
        ],
        'retakes': [{'view': 'detail', 'metric': 'open_seams', 'owner': 'environment_artist',
                     'action': 'Close the daylight gap above the left jamb and recapture the doorway detail.'}],
    },
}]


def _visible(value, name):
    _text(value, 240, name)
    if not any(category(char)[0] in 'LN' for char in value):
        raise ValueError(f'{name} needs visible words or numbers.')


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Artifact identities must be lowercase SHA-256 hex digests.')


def _settings(row, is_capture):
    for field in ('width', 'height'):
        _integer(row[field], 1, 16384, field)
    _integer(row['fps'], 0 if is_capture else 1, 240, 'fps')


def _validate(submission):
    _object(submission, ('brief', 'candidate_sha256', 'references', 'targets', 'captures', 'retakes'), 'Submission')
    brief = submission['brief']
    prose = ('genre', 'platform', 'style', 'player_task')
    _object(brief, (*prose, 'width', 'height', 'fps'), 'Brief')
    for field in prose:
        _visible(brief[field], field)
    _settings(brief, False)
    _sha(submission['candidate_sha256'])

    _array(submission['references'], 0, 8, 'references')
    for ref in submission['references']:
        _object(ref, ('id', 'source', 'takeaway', 'sha256'), 'Reference')
        _identifier(ref['id'], 'Reference ID')
        _visible(ref['source'], 'Reference source')
        _visible(ref['takeaway'], 'Reference takeaway')
        _sha(ref['sha256'])

    _object(submission['targets'], _LIMITS, 'Targets')
    for metric, target in submission['targets'].items():
        _object(target, ('reference', 'min', 'max'), 'Target')
        _identifier(target['reference'], 'Target reference')
        _integer(target['min'], 0, _LIMITS[metric], metric)
        _integer(target['max'], target['min'], _LIMITS[metric], metric)

    _array(submission['captures'], 0, 8, 'captures')
    for shot in submission['captures']:
        _object(shot, ('view', 'build_sha256', 'artifact_sha256', 'width', 'height', 'frames', 'fps',
                       'observations'), 'Capture')
        _identifier(shot['view'], 'Capture view')
        if shot['view'] not in _VIEWS:
            raise ValueError('Unknown capture view.')
        _settings(shot, True)
        _integer(shot['frames'], 1, 72000, 'frames')
        _sha(shot['artifact_sha256'])
        _sha(shot['build_sha256'])
        values = shot['observations']
        if type(values) is not dict or not values.keys() <= _LIMITS.keys():
            raise ValueError('Observations must be an object of known metrics.')
        for metric, value in values.items():
            _integer(value, 0, _LIMITS[metric], metric)

    _array(submission['retakes'], 0, 24, 'retakes')
    for row in submission['retakes']:
        _object(row, ('view', 'metric', 'owner', 'action'), 'Retake')
        _identifier(row['view'], 'Retake view')
        _identifier(row['metric'], 'Retake metric')
        if row['view'] not in _VIEWS or row['metric'] not in _LIMITS:
            raise ValueError('Unknown retake view or metric.')
        _identifier(row['owner'], 'Retake owner')
        _visible(row['action'], 'Retake action')


def _cell_names(cells):
    return ', '.join(f'{view}/{metric}' for view, metric in sorted(cells))


def assess(exercise_id, submission):
    if exercise_id != _ID:
        raise ValueError('Unknown visual direction exercise.')
    _validate(submission)
    brief, targets, shots = submission['brief'], submission['targets'], submission['captures']
    references = submission['references']
    ref_ids = {row['id'] for row in references}
    ref_hashes = {row['sha256'] for row in references}
    linked = {target['reference'] for target in targets.values()}
    traceable = (len(ref_ids) == len(ref_hashes) == len(references) and len(linked) >= 2 and linked <= ref_ids)

    views = Counter(shot['view'] for shot in shots)
    candidate = submission['candidate_sha256']
    artifacts = [shot['artifact_sha256'] for shot in shots]
    reused = len(artifacts) - len(set(artifacts))
    unrelated = sum(shot['build_sha256'] != candidate for shot in shots)
    reserved = len(set(artifacts) & (ref_hashes | {candidate}))
    mismatched, observed, outliers = [], set(), []
    for shot in shots:
        view = shot['view']
        if view == 'motion':
            sampling_ok = shot['fps'] == brief['fps'] and shot['frames'] >= max(2, brief['fps'])
        else:
            sampling_ok = shot['frames'] == 1 and shot['fps'] == 0
        if not sampling_ok or (shot['width'], shot['height']) != (brief['width'], brief['height']):
            mismatched.append(view)
        for metric, value in shot['observations'].items():
            observed.add((view, metric))
            target = targets[metric]
            if not target['min'] <= value <= target['max']:
                outliers.append((view, metric, value))

    missing = _REQUIRED - observed
    outside = {(view, metric) for view, metric, value in outliers}
    assigned = Counter((row['view'], row['metric']) for row in submission['retakes'])
    retake_errors = (outside ^ assigned.keys()) | {cell for cell, count in assigned.items() if count > 1}
    if retake_errors:
        disposition = 'Missing, unsupported or repeated retake at ' + _cell_names(retake_errors) + '.'
    elif outliers:
        samples = [f"{view}/{metric} measured {value}, target {targets[metric]['min']}–{targets[metric]['max']}"
                   for view, metric, value in sorted(outliers)[:4]]
        disposition = f'{len(outside)} assigned retakes. ' + '. '.join(samples) + '.'
    else:
        disposition = 'All declared observations fall within their target bands.'
    return [
        _check('reference-links', traceable,
               f'{len(linked & ref_ids)} linked reference IDs, {len(ref_ids)} distinct IDs and '
               f'{len(ref_hashes)} distinct digests across {len(references)} reference records.'),
        _check('shot-matrix', all(views[v] == 1 for v in _VIEWS),
               'Capture counts by view: ' + ', '.join(f'{v} {views[v]}' for v in _VIEWS) + '.'),
        _check('capture-identity', bool(shots) and not (reused or unrelated or reserved),
               f'{unrelated} captures name a different build, {reused} repeat an artifact and '
               f'{reserved} artifact digests duplicate a reference or candidate package.'),
        _check('delivery-settings', bool(shots) and not mismatched,
               'Delivery mismatch at ' + ', '.join(mismatched) + '.' if mismatched
               else f'{len(shots)} captures match the declared sampling and output size.'),
        _check('observations', not missing,
               'Missing measurements at ' + _cell_names(missing) + '.' if missing
               else 'All eight required view and metric combinations have declared measurements.'),
        _check('retakes', not retake_errors, disposition),
    ]
