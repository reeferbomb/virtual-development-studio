import json
import tempfile
import unittest
from pathlib import Path

from command_center import admin_cli, admin_registry, work_modes
from command_center.dispatch import default_profile


SOURCE = dict(commit='a'*40, release_ref='fixture/v1', library_ref=None, sha256='b'*64, dirty=False)
ROLES = [r['id'] for r in default_profile()['roles']]


def registry():
    return admin_registry.apply(admin_registry.empty(), dict(type='project', project_id='yard', name='Yard',
                                source=SOURCE, environment={'engine':'fixture'}))


def change(state, op, session_id='creative1', **fields):
    return admin_registry.apply(state, dict(type='work-mode', project_id='yard',
                               event=dict(op=op, session_id=session_id, **fields)))


def start(state, mode='creative', session_id='creative1', from_session=None):
    return change(state, 'start', session_id, mode=mode, brief='Design a courier game.',
                  constraints=['Controller support', 'No paid assets'], from_session=from_session)


def reports(state, sid='creative1', unavailable=None):
    for role in ROLES:
        state = change(state, 'report', sid, role=role, status='unavailable' if role == unavailable else 'reported',
                       summary='Independent fixture for ' + role)
    return state


OPTIONS = [dict(id='a', title='Route choice', pitch='Two paths', tradeoff='More world rules'),
           dict(id='b', title='Timed route', pitch='Beat the clock', tradeoff='Time pressure')]
TASKS = [dict(id='prototype', title='Prototype', owner='gameplay', depends_on=[], acceptance=['Controls respond'], high_risk=False),
         dict(id='check', title='Verify', owner='verification', depends_on=['prototype'], acceptance=['Check retries'], high_risk=True)]


def synth(state, sid='creative1', output=None):
    return change(state, 'synthesize', sid, actor='lead', output=output or dict(alternatives=OPTIONS, recommendation='a', risks=['Scope creep']))


def approved(state):
    s = synth(reports(start(state)))
    packet = work_modes.handoff(s['projects']['yard'], 'creative1')
    return change(s, 'decide', actor='user', decision='approve', choice='a', digest=packet['synthesis_sha256'], rationale='Player agency')


class WorkModeTests(unittest.TestCase):
    def test_creative_dispatch_preserves_profiles_and_independence(self):
        s = start(registry())
        initial = work_modes.dispatch(s['projects']['yard'], 'creative1')
        self.assertEqual(initial['profile'], default_profile())
        self.assertEqual([a['role'] for a in initial['assignments']], ROLES)
        self.assertEqual(initial['status'], 'dispatch-plan-only')
        s = change(s, 'report', role='content', status='reported', summary='Private design option')
        self.assertNotIn('Private design option', json.dumps(work_modes.dispatch(s['projects']['yard'], 'creative1')))
        self.assertEqual(initial['assignments'][0]['instruction'], work_modes.dispatch(s['projects']['yard'], 'creative1')['assignments'][0]['instruction'])

    def test_approval_and_creative_to_planning_flow(self):
        s = approved(registry())
        s = start(s, 'planning', 'plan1', 'creative1')
        p = work_modes.handoff(s['projects']['yard'], 'plan1')
        self.assertEqual(p['parent_concept']['id'], 'a')
        s = synth(reports(s,'plan1'), 'plan1', dict(tasks=TASKS, risks=['Test costs']))
        p = work_modes.handoff(s['projects']['yard'], 'plan1')
        s = change(s, 'decide','plan1', actor='user', decision='approve', choice=None, digest=p['synthesis_sha256'], rationale='Ready to plan work')
        p = work_modes.handoff(s['projects']['yard'], 'plan1')
        self.assertEqual(p['decision']['decision'], 'approve')
        self.assertFalse(p['authorizes_execution'])
        self.assertFalse(p['authorizes_release'])

    def test_roles_unavailable_are_explicit_and_verifier_blocks_approval(self):
        s = synth(reports(start(registry()), unavailable='verification'))
        p = work_modes.handoff(s['projects']['yard'], 'creative1')
        self.assertEqual(p['reports']['verification']['status'], 'unavailable')
        with self.assertRaises(ValueError):
            change(s,'decide',actor='user',decision='approve',choice='a',digest=p['synthesis_sha256'],rationale='Not enough review')
        s = change(s,'decide',actor='user',decision='defer',choice=None,digest=None,rationale='Wait for verifier')
        self.assertEqual(work_modes.handoff(s['projects']['yard'],'creative1')['decision']['decision'],'defer')

    def test_duplicate_bad_actor_and_incomplete_synthesis_rejected(self):
        s = start(registry())
        with self.assertRaises(ValueError): synth(s)
        with self.assertRaises(ValueError): start(s, 'planning', 'plan1')
        s = change(s,'report',role='content',status='reported',summary='Draft')
        with self.assertRaises(ValueError): change(s,'report',role='content',status='reported',summary='Duplicate')
        for role in set(ROLES)-{'content'}:
            s = change(s,'report',role=role,status='reported',summary='Fixture')
        s = synth(s)
        p = work_modes.handoff(s['projects']['yard'],'creative1')
        for actor, digest, choice in [('lead',p['synthesis_sha256'],'a'),('user','9'*64,'a'),('user',p['synthesis_sha256'],'missing')]:
            with self.assertRaises(ValueError): change(s,'decide',actor=actor,decision='approve',choice=choice,digest=digest,rationale='Invalid')

    def test_stale_identity_and_parent_rejected(self):
        s = synth(reports(start(registry())))
        p = work_modes.handoff(s['projects']['yard'],'creative1')
        s = admin_registry.apply(s,dict(type='identity',project_id='yard',source=dict(SOURCE, dirty=True),environment={'engine':'fixture'}))
        self.assertFalse(work_modes.handoff(s['projects']['yard'],'creative1')['fresh'])
        with self.assertRaises(ValueError): change(s,'decide',actor='user',decision='approve',choice='a',digest=p['synthesis_sha256'],rationale='Stale')
        s = change(s,'decide',actor='user',decision='defer',choice=None,digest=None,rationale='New source')
        with self.assertRaises(ValueError): start(s,'planning','next','creative1')

    def test_plan_rejects_cycle_unknown_dependency_and_invalid_owner(self):
        s = reports(start(registry(),'planning','plan1'),'plan1')
        for tasks in [[dict(TASKS[0], depends_on=['check']),TASKS[1]], [dict(TASKS[0], depends_on=['absent'])], [dict(TASKS[0], owner='unknown')]]:
            with self.assertRaises(ValueError): synth(s,'plan1',dict(tasks=tasks,risks=[]))
        s = synth(s,'plan1',dict(tasks=TASKS,risks=[]))
        self.assertEqual(work_modes.handoff(s['projects']['yard'],'plan1')['synthesis']['tasks'], TASKS)

    def test_private_journal_mode_cli_and_scoped_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.json'
            def call(*args): return admin_cli.run(admin_cli.parser().parse_args(['--journal',str(path),*args]))
            def append(event, rev):
                file=Path(tmp)/'event.json'; file.write_text(json.dumps(event))
                return call('append','registry',str(file),'--revision',str(rev))
            append(dict(type='project',project_id='yard',name='Yard',source=SOURCE,environment={'engine':'fixture'}),0)
            call('mode-start','yard','creative1','creative','--brief','Explore','--revision','1')
            dispatch = call('mode-dispatch','yard','creative1')
            self.assertEqual(dispatch['status'],'dispatch-plan-only')
            self.assertEqual(dispatch['project_id'],'yard')
            self.assertEqual(call('mode-handoff','yard','creative1')['mode'],'creative')
            s=append(dict(type='checkpoint',project_id='yard',checkpoint_id='cp1',summary='Planning',log_ids=[],criteria=[dict(id='c',description='Test',high_risk=False)],tests=[],pending=[],gaps=[]),2)
            packet=call('handoff','yard','cp1')
            self.assertIn('creative1',packet['work_modes']['captured'])
            self.assertEqual(s['revision'],3)
            call('mode-report','yard','creative1','content','reported','--summary','Original content draft','--revision','3')
            self.assertTrue(call('handoff','yard','cp1')['work_modes']['changed_since_checkpoint'])
            self.assertEqual(call('handoff','yard','cp1')['work_modes']['captured']['creative1']['reports'],{})
            with self.assertRaises(ValueError): call('mode-report','yard','creative1','content','reported','--summary','Duplicate','--revision','4')

    def test_mode_changes_invalidate_pending_continuation_without_affecting_foreign_project(self):
        s = start(registry())
        s = admin_registry.apply(s,dict(type='project', project_id='other',name='Other',source=SOURCE,environment={'engine':'fixture'}))
        for pid in ('yard','other'):
            s = admin_registry.apply(s,dict(type='checkpoint',project_id=pid,checkpoint_id='cp1',summary='Planning',log_ids=[],criteria=[dict(id='c',description='Test',high_risk=False)],tests=[],pending=[],gaps=[]))
        original = admin_registry.handoff(s,'yard','cp1')
        s = admin_registry.apply(s,dict(type='request',project_id='yard',checkpoint_id='cp1',reason='user-request',detail='Test'))
        s = change(s,'report',role='content',status='reported',summary='Private report')
        self.assertNotIn('work_modes',admin_registry.handoff(s,'other','cp1'))
        with self.assertRaises(ValueError):
            admin_registry.apply(s,dict(type='receipt',project_id='yard',checkpoint_id='cp1',packet_sha256=original['packet_sha256'],actual_project_id='yard',mode='regular',chat_id='fixture-chat',ref='fixture'))


if __name__ == '__main__': unittest.main()
