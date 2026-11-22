"""Practice dependency-aware autonomous pre-production, never authorize builds."""

from .lab_design import _array, _check, _object, _text
from .lab_gameplay import _integer
from .work_modes import _synthesis

TRACK = dict(id='autonomous-planning', title='Autonomous planning and adaptive production',
             roles=['architecture','gameplay','verification','ui','content','build_operations'],
             workflow=['Translate selected concept into outcomes, non-goals, constraints and ordered deliverables. Split the smallest meaningful vertical slice.',
                       'Assign one responsible role per task, identify dependencies, estimate bounded effort and compare critical paths. Do not invent external availability.',
                       'Record risks, assumptions, measurable acceptance, independent positive and negative tests, and rollback. Plan cheap discovery tasks for unknowns.',
                       'Proceed autonomously within delegated drafting authority; checkpoint progress, revisit stale assumptions, stop for blockers and final user approval.'],
             deliverables=['Dependency-checked work breakdown with role owners and effort estimates.',
                           'Verification and risk register, critical path, fallback and explicit approval boundary.'],
             verification=['Reject cycles, unavailable prerequisites, budget overruns and missing risk tests.',
                           'Reconcile projected effort with actual evidence in later development; no plan is proof of a completed feature.'],
             exercise='Plan a bounded courier vertical slice, predict dependency duration and include risk recovery.')

EXERCISES = [dict(id=TRACK['id'],title='Plan a vertical slice with explicit verification',
    brief='Provide 1–12 tasks with id/title/owner/depends_on/acceptance/high_risk plus duration (1–12 ticks), negative_test and rollback (nonblank text or null). Predict critical-path ticks with unlimited role concurrency; budget is 12 ticks. Every high-risk task needs a negative test and rollback, and an independent verification task must depend directly on each high-risk task. This is an estimate, not actual production time.',
    criteria=[dict(id='dependency',label='Tasks have valid acyclic dependencies and known owners.'),dict(id='schedule',label='Predicted critical path matches the graph and fits 12 ticks.'),dict(id='risk',label='High-risk tasks include negative verification and rollback.'),dict(id='independent',label='A verification-role task follows every high-risk implementation task.')],
    example=dict(tasks=[dict(id='architecture',title='Specify route contracts',owner='architecture',depends_on=[],acceptance=['Both route states defined'],high_risk=False,duration=2,negative_test=None,rollback=None),
                        dict(id='prototype',title='Implement route rules',owner='gameplay',depends_on=['architecture'],acceptance=['Route uses required inputs'],high_risk=True,duration=4,negative_test='Reject unknown route',rollback='Restore prior rule set'),
                        dict(id='verify',title='Verify route rules',owner='verification',depends_on=['prototype'],acceptance=['Both routes and rejection pass'],high_risk=False,duration=2,negative_test=None,rollback=None)],predicted_ticks=8))]


def assess(exercise_id, submission):
    if exercise_id != TRACK['id']: raise ValueError('Unknown planning practice')
    _object(submission, ('tasks','predicted_ticks'),'submission')
    rows = submission['tasks']; _array(rows,1,12,'tasks')
    _integer(submission['predicted_ticks'],1,144,'predicted ticks'); predicted = submission['predicted_ticks']
    keys = ('id','title','owner','depends_on','acceptance','high_risk')
    base=[]; durations={}
    for row in rows:
        _object(row, (*keys,'duration','negative_test','rollback'),'task')
        base.append({k:row[k] for k in keys})
        _integer(row['duration'],1,12,'duration'); durations[row['id']] = row['duration']
        for field in ('negative_test','rollback'):
            if row[field] is not None: _text(row[field],240,field)
    try:
        _synthesis('planning',dict(tasks=base,risks=[]))
    except ValueError:
        return [_check(c['id'],False,'Invalid dependency graph or task schema.') for c in EXERCISES[0]['criteria']]
    finish={}; remaining={r['id']:r for r in rows}
    while remaining:
        ready=[r for r in remaining.values() if all(d in finish for d in r['depends_on'])]
        for row in ready:
            finish[row['id']]=durations[row['id']]+max((finish[d] for d in row['depends_on']),default=0)
            del remaining[row['id']]
    critical=max(finish.values())
    risky=[r for r in rows if r['high_risk']]
    return [_check('dependency',True,'Acyclic graph and valid role owners.'),
            _check('schedule',critical==predicted and critical<=12,f'Critical path is {critical} ticks.'),
            _check('risk',bool(risky) and all(r['negative_test'] and r['rollback'] for r in risky),'High-risk work needs a negative test and rollback.'),
            _check('independent',bool(risky) and all(r['owner']!='verification' and any(v['owner']=='verification' and r['id'] in v['depends_on'] for v in rows) for r in risky),'Require a separate verification task after each risky implementation.')]
