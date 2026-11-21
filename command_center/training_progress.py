"""Privacy-minimized review coverage derived from the validated practice ledger."""

from .dispatch import default_profile
from .training_lab import lab_catalog


def summarize_progress(snapshot):
    """Project recorded practice, never certify a role or rank a model's ability.

    Call only with a snapshot returned by TrainingRecordStore.read/apply.
    Repeated accepted copies of an identical submission count once per role
    and exercise; a historical assessment cannot count in the current rubric.
    """
    catalog = lab_catalog()
    digest = catalog['lab_sha256']
    if snapshot['lab_sha256'] != digest:
        raise ValueError('Practice progress requires the current catalog')
    role_ids = [role['id'] for role in default_profile()['roles']]
    rows = {(role, exercise['id']): {'exercise_id': exercise['id'], 'recorded': 0,
            'pending': 0, 'accepted': 0, 'rejected': 0, 'qualifying_distinct': 0}
            for role in role_ids for exercise in catalog['exercises'] if role in exercise['roles']}
    distinct = set()
    summary = dict.fromkeys(('records', 'current', 'historical', 'reference',
                             'pending', 'accepted', 'rejected', 'qualifying_distinct'), 0)
    for record in snapshot['records']:
        summary['records'] += 1
        if not record['current'] or record['report']['lab_sha256'] != digest:
            summary['historical'] += 1
            continue
        summary['current'] += 1
        row_key = record['role'], record['exercise_id']
        row = rows[row_key]
        row['recorded'] += 1
        summary['reference'] += int(record['reference'])
        decision = record['review']['decision'] if record['review'] else 'pending'
        summary[decision] += 1
        row[decision] += 1
        if decision == 'accepted' and not record['reference'] and record['report']['status'] == 'pass':
            identity = (*row_key, record['report']['submission_sha256'])
            if identity not in distinct:
                distinct.add(identity)
                row['qualifying_distinct'] += 1
                summary['qualifying_distinct'] += 1
    roles = []
    for role in role_ids:
        exercises = [row for (owner, _), row in rows.items() if owner == role]
        roles.append({'role': role, 'assigned_exercises': len(exercises),
                      'reviewed_exercises': sum(e['qualifying_distinct'] > 0 for e in exercises),
                      'qualifying_distinct': sum(e['qualifying_distinct'] for e in exercises),
                      'exercises': exercises})
    return {'revision': snapshot['revision'], 'lab_sha256': digest, 'summary': summary,
            'roles': roles, 'note': 'Current review coverage only; exact reference examples, failed, '
            'pending, rejected and historical submissions do not qualify. Deduplicated per role and exercise. '
            'Role labels are operator-declared, not authenticated identity. This is not a competency rating, '
            'model training, independent authorship proof, or release approval.'}
