import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import request, error

ROOT=Path(__file__).resolve().parents[1]

class CommandHTTPTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((ROOT/'command_center/server.py').exists(),'Command center server missing')
        self.temp=tempfile.TemporaryDirectory()
        self.start_server()

    def start_server(self):
        from command_center.server import StudioService, create_server
        self.service=StudioService(ROOT,Path(self.temp.name))
        self.server=create_server(self.service,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.service.pipeline.worker.shutdown()
        del self.server

    def tearDown(self):
        if hasattr(self,'server'): self.stop_server()
        if hasattr(self,'temp'): self.temp.cleanup()

    def call(self,path,method='GET',data=None,headers=None,expected_status=None):
        h={'Content-Type':'application/json','X-Studio-Request':'1'}
        if headers is not None: h=headers
        req=request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers=h)
        with request.urlopen(req,timeout=5) as r:
            if expected_status is not None: self.assertEqual(r.status,expected_status)
            return json.load(r)

    def test_project_lifecycle(self):
        self.assertEqual(self.call('/api/projects'),[])
        p=self.call('/api/projects','POST',{'name':'Test Scene','kind':'cinematic'})
        self.assertEqual(p['kind'],'cinematic')
        self.assertEqual(self.call('/api/projects/'+p['id'])['spec'],p['spec'])
        p['spec']['shots'][0]['duration']=5
        saved=self.call('/api/projects/'+p['id']+'/spec','PUT',{'spec':p['spec']})
        self.assertEqual(saved['spec']['shots'][0]['duration'],5)
        self.assertEqual(len(self.call('/api/team/'+p['id'])['roles']),6)

    def test_mutations_reject_cross_origin_and_missing_header(self):
        for headers in [{'Content-Type':'application/json'},{'Content-Type':'application/json','X-Studio-Request':'1','Origin':'http://evil.invalid'}]:
            with self.assertRaises(error.HTTPError) as e:
                self.call('/api/projects','POST',{'name':'Bad','kind':'world'},headers)
            self.assertEqual(e.exception.code,403)

    def test_file_allowlist_and_invalid_project(self):
        for route in ['/api/file?path=README.md','/api/file?path=../../etc/passwd','/api/projects/%2e%2e']:
            with self.assertRaises(error.HTTPError): self.call(route)
        with self.assertRaises(error.HTTPError): self.call('/api/projects','POST',{'name':'Invalid','kind':'arbitrary-shell'})
        self.assertEqual(self.call('/api/projects'),[])

    def test_catalog_and_status(self):
        status=self.call('/api/status')
        self.assertEqual(status['version'],'34.0')
        executable=next((path for candidate in ('blender52','blender') if (path:=shutil.which(candidate))),None)
        expected=subprocess.check_output([executable,'--version'], text=True).splitlines()[0] if executable else 'Not installed'
        self.assertEqual(status['tools']['blender'],expected)
        catalog=self.call('/api/catalog')
        self.assertEqual(len(catalog['packages']),16)
        self.assertTrue(all(p['verified'] for p in catalog['packages']))

    def test_generate_world_draft(self):
        project=self.call('/api/projects','POST',{'name':'Generated Yard','kind':'world'})
        route='/api/projects/'+project['id']
        result=self.call(route+'/generate','POST',{'seed':237,'count':24})
        self.assertEqual(len(result['spec']['blocks']),24)
        self.assertGreater(result['route_m'],36)
        self.assertEqual(self.call(route)['spec'],project['spec'])

    def create_checkpoint_project(self):
        project = self.call('/api/projects', 'POST', {'name': 'Checkpoint scene', 'kind': 'cinematic'})
        path = '/api/projects/' + project['id'] + '/checkpoint'
        empty = self.call(path)
        self.assertEqual(empty['project_id'], project['id'])
        self.assertEqual(empty['state'], 'empty')
        self.assertEqual(empty['revision'], 0)
        self.assertEqual(empty['target_seconds'], 18000)
        self.assertIsNone(empty['checkpoint'])
        data = {
            'expected_revision': empty['revision'],
            'spec_sha256': empty['spec_sha256'],
            'elapsed_seconds': 300,
            'status': 'paused',
            'completed_work': ['Updated the opening shot'],
            'verification_evidence': ['Reviewed the shot timeline'],
            'remaining_work': ['Review the closing shot'],
            'next_action': 'Open the closing shot in the editor',
        }
        return project, path, data

    def assert_http_error(self, status, *args):
        with self.assertRaises(error.HTTPError) as raised:
            self.call(*args)
        with raised.exception as response:
            self.assertEqual(response.code, status)
            self.assertTrue(json.load(response)['error'])

    def create_task_board(self, name='Work queue', kind='cinematic'):
        project = self.call('/api/projects', 'POST', {'name': name, 'kind': kind})
        path = '/api/projects/' + project['id'] + '/tasks'
        board = self.call(path)
        self.assertEqual(board['project_id'], project['id'])
        self.assertEqual(board['revision'], 0)
        self.assertEqual(board['tasks'], [])
        return project, path, board

    @staticmethod
    def add_task(task_id, role, depends_on=(), priority=3, gate='manual'):
        return {'op': 'add', 'task': {'id': task_id, 'title': task_id.title(), 'role': role,
                                      'priority': priority, 'depends_on': list(depends_on), 'gate': gate}}

    @staticmethod
    def task_request(board, action):
        return {'expected_revision': board['revision'], 'spec_sha256': board['spec_sha256'],
                'action': action}

    def apply_task(self, path, board, action):
        updated = self.call(path, 'PUT', self.task_request(board, action))
        self.assertEqual(updated['revision'], board['revision'] + 1)
        return updated

    def test_portfolio_recommends_work_across_projects_without_claiming_it(self):
        first, first_path, board = self.create_task_board('First project')
        first_board = self.apply_task(first_path, board, self.add_task('props', 'content'))
        second, second_path, board = self.create_task_board('Second project')
        second_board = self.apply_task(second_path, board, self.add_task('scene', 'content', priority=5))
        portfolio = self.call('/api/portfolio')
        self.assertEqual({row['project_id'] for row in portfolio['projects']}, {first['id'], second['id']})
        self.assertEqual([(row['project_id'], row['task_id']) for row in portfolio['assignments']],
                         [(second['id'], 'scene')])
        self.assertEqual(self.call(first_path), first_board)
        self.assertEqual(self.call(second_path), second_board)
        self.apply_task(second_path, second_board, {'op': 'start', 'task_id': 'scene'})
        self.assertEqual(self.call('/api/portfolio')['assignments'], [])
        self.assert_http_error(404, '/api/portfolio', 'POST', {})

    def test_supervisor_and_performance_routes_are_local_and_read_only(self):
        project, _, board = self.create_task_board()
        base = '/api/projects/' + project['id']
        directory = self.service.projects.directory(project['id'])
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        for resource in ('supervisor', 'performance', 'defects'):
            with self.subTest(resource=resource):
                path = base + '/' + resource
                record = self.call(path, expected_status=200)
                self.assertEqual(record['project_id'], project['id'])
                self.assertEqual(record['spec_sha256'], board['spec_sha256'])
                self.assertEqual(self.call(path), record)
                self.assert_http_error(403, path, 'GET', None, {'Host': 'external.invalid'})
                self.assert_http_error(403, path, 'GET', None, {'Origin': 'http://other.invalid'})
                self.assert_http_error(404, '/api/projects/missing/' + resource)
                self.assert_http_error(404, path, 'POST', {})
                if resource != 'defects':
                    self.assert_http_error(404, path, 'PUT', {})
        self.assertEqual(self.call(base + '/performance')['counts']['total'], 0)
        self.assertEqual(self.call(base + '/performance')['samples'], [])
        self.assertEqual({path.name: path.read_bytes() for path in directory.iterdir()}, before)

    def test_defect_lifecycle_conflicts_and_historical_evidence(self):
        project, _, _ = self.create_task_board()
        base = '/api/projects/' + project['id']
        path = base + '/defects'
        empty = self.call(path)
        self.assertEqual(empty['revision'], 0)
        self.assertEqual(empty['items'], [])
        create = self.task_request(empty, {
            'op': 'add', 'title': 'Missing opening frame', 'severity': 'high',
            'description': 'The opening frame is black.', 'evidence': ['Shot review at frame 1'],
        })
        self.assert_http_error(403, path, 'PUT', create, {'Content-Type': 'application/json'})
        self.assert_http_error(403, path, 'PUT', create, {
            'Content-Type': 'application/json', 'X-Studio-Request': '1', 'Origin': 'http://other.invalid',
        })
        for invalid in ({}, {**create, 'expected_revision': True},
                        {**create, 'action': {**create['action'], 'severity': 'unknown'}}):
            self.assert_http_error(400, path, 'PUT', invalid)
        self.assert_http_error(404, '/api/projects/missing/defects', 'PUT', create)
        self.assertEqual(self.call(path), empty)
        opened = self.call(path, 'PUT', create)
        self.assertEqual(opened['revision'], 1)
        self.assertEqual(opened['summary']['current_open'], 1)
        self.assert_http_error(409, path, 'PUT', create)
        item = opened['items'][0]
        resolve = {'op': 'resolve', 'defect_id': item['id'], 'evidence': ['Reviewed corrected frame']}
        resolved = self.call(path, 'PUT', self.task_request(opened, resolve))
        self.assertEqual(resolved['items'][0]['status'], 'resolved')
        reopen = {'op': 'reopen', 'defect_id': item['id'], 'evidence': ['Observed again on replay']}
        reopened = self.call(path, 'PUT', self.task_request(resolved, reopen))
        self.assertEqual(reopened['items'][0]['status'], 'open')
        self.stop_server()
        self.start_server()
        self.assertEqual(self.call(path), reopened)
        project['spec']['shots'][0]['duration'] = 5
        self.call(base + '/spec', 'PUT', {'spec': project['spec']})
        historical = self.call(path)
        self.assertNotEqual(historical['spec_sha256'], empty['spec_sha256'])
        self.assertEqual(historical['summary']['current_open'], 0)
        self.assertEqual(historical['summary']['historical_open'], 1)
        self.assertEqual(historical['items'], reopened['items'])
        self.assert_http_error(409, path, 'PUT', self.task_request(reopened, resolve))
        self.assert_http_error(409, path, 'PUT', self.task_request(historical, resolve))
        self.assertEqual(self.call(path), historical)

    def test_supervisor_isolates_corrupt_sources(self):
        project, _, _ = self.create_task_board()
        base = '/api/projects/' + project['id']
        directory = self.service.projects.directory(project['id'])
        def checks():
            return {row['id']: row['status'] for row in self.call(base + '/supervisor')['checks']}

        healthy = checks()
        job = self.service.pipeline.jobs / ('a' * 32)
        job.mkdir()
        for record, affected in (
                (directory / 'task-board.json', {'task_board', 'manual_review'}),
                (directory / 'releases.json', {'release'}),
                (directory / 'defects.json', {'defects'}),
                (job / 'job.json', {'build', 'performance'})):
            with self.subTest(record=record.name):
                record.write_bytes(b'invalid JSON')
                try:
                    current = checks()
                    for check in affected:
                        self.assertEqual(current[check], 'fail')
                    self.assertEqual({k: v for k, v in current.items() if k not in affected},
                                     {k: v for k, v in healthy.items() if k not in affected})
                    self.assertEqual(record.read_bytes(), b'invalid JSON')
                finally:
                    record.unlink()
        with patch('command_center.server.profile_jobs', side_effect=ValueError('Invalid timing')):
            self.assertEqual(checks(), {**healthy, 'performance': 'fail'})
        self.assertEqual(checks(), healthy)

    def test_queue_status_cancel_and_retry(self):
        project = self.call('/api/projects', 'POST', {'name': 'Priority test', 'kind': 'cinematic'})
        build_path = '/api/projects/' + project['id'] + '/build'
        started, finish = threading.Event(), threading.Event()

        def hold_builder(kind, directory):
            started.set()
            if not finish.wait(10):
                raise RuntimeError('Test builder timed out')
            return []

        with patch.object(self.service.pipeline, '_commands', side_effect=hold_builder):
            try:
                first = self.call(build_path, 'POST', {}, expected_status=202)
                self.assertTrue(started.wait(5))
                self.assertEqual(first['priority'], 3)
                releases_path = '/api/projects/' + project['id'] + '/releases'
                self.assert_http_error(400, releases_path, 'PUT', {
                    'expected_revision': 0, 'spec_sha256': first['spec_sha256'],
                    'action': {'op': 'promote', 'job_id': first['id']},
                })
                second = self.call(build_path, 'POST', {'priority': 5}, expected_status=202)
                second_path = '/api/jobs/' + second['id']
                queued = self.call('/api/queue')
                self.assertEqual(queued['running']['id'], first['id'])
                self.assertEqual([job['id'] for job in queued['queued']], [second['id']])
                self.assertEqual(queued['counts']['queued'], 1)
                profile = self.call('/api/projects/' + project['id'] + '/performance')
                self.assertEqual(profile['counts']['running'], 1)
                self.assertEqual(profile['counts']['queued'], 1)
                self.assertEqual(profile['counts']['total'], 2)
                self.assert_http_error(409, second_path + '/retry', 'POST', {})
                canceled = self.call(second_path + '/cancel', 'POST', {}, expected_status=200)
                self.assertEqual(canceled['status'], 'canceled')
                retried = self.call(second_path + '/retry', 'POST', {}, expected_status=202)
                self.assertEqual(retried['retry_of'], second['id'])
                self.assertEqual(retried['priority'], 5)
                self.assertNotEqual(retried['id'], second['id'])
                self.assertEqual(self.call(second_path), canceled)
                self.assertEqual([job['id'] for job in self.call('/api/queue')['queued']], [retried['id']])
                self.call('/api/jobs/' + retried['id'] + '/cancel', 'POST', {})
            finally:
                finish.set()

    def test_queue_and_release_requests_reject_unauthorized_or_invalid_mutations(self):
        project = self.call('/api/projects', 'POST', {'name': 'Guard test', 'kind': 'cinematic'})
        project_path = '/api/projects/' + project['id']
        job_path = '/api/jobs/' + '1' * 32
        releases_path = project_path + '/releases'
        registry = self.call(releases_path)
        self.assertEqual(registry['project_id'], project['id'])
        self.assertEqual(registry['revision'], 0)
        self.assertEqual(registry['releases'], [])
        self.assertIsNone(registry['active_release_id'])
        self.assertEqual(registry['active_state'], 'empty')
        promote = {'expected_revision': 0, 'spec_sha256': registry['spec_sha256'],
                   'action': {'op': 'promote', 'job_id': '1' * 32}}
        headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}
        for method, path, body in [('POST', project_path + '/build', {'priority': 2}),
                                   ('POST', job_path + '/cancel', {}), ('POST', job_path + '/retry', {}),
                                   ('PUT', releases_path, promote)]:
            with self.subTest(path=path):
                self.assert_http_error(403, path, method, body, {'Content-Type': 'application/json'})
                self.assert_http_error(403, path, method, body, {**headers, 'Origin': 'http://other.invalid'})
        for path in ('/api/queue', '/api/portfolio', releases_path):
            self.assert_http_error(403, path, 'GET', None, {'Host': 'external.invalid'})
        for body in ({'priority': True}, {'priority': 0}, {'extra': 1}, []):
            self.assert_http_error(400, project_path + '/build', 'POST', body)
        for action in ('cancel', 'retry'):
            self.assert_http_error(400, job_path + '/' + action, 'POST', {'job_id': 3})
            self.assert_http_error(404, job_path + '/' + action, 'POST', {})
            self.assert_http_error(404, job_path + '/' + action, 'PUT', {})
        self.assert_http_error(400, releases_path, 'PUT', {})
        self.assert_http_error(409, releases_path, 'PUT', {**promote, 'expected_revision': 1})
        self.assert_http_error(404, '/api/projects/missing/releases')
        self.assert_http_error(404, releases_path, 'POST', promote)
        self.assertEqual(self.call(releases_path), registry)
        self.assertEqual(self.call('/api/jobs'), [])

    def test_task_scheduling_respects_dependencies_and_role_capacity(self):
        project, path, board = self.create_task_board()
        for action in (self.add_task('scene', 'content', priority=5),
                       self.add_task('props', 'content'),
                       self.add_task('review', 'verification', depends_on=['scene'])):
            board = self.apply_task(path, board, action)
        self.assertEqual(board['ready_task_ids'], ['scene', 'props'])
        team_path = '/api/team/' + project['id']
        team = self.call(team_path)
        self.assertEqual(len(team['dispatch_plan']['assignments']), 6)
        export = team['scheduled_dispatch_plan']
        self.assertEqual(export['board_revision'], board['revision'])
        self.assertEqual([task['task_id'] for task in export['assignments']], ['scene'])
        self.assertEqual([spawn['task_name'] for spawn in export['spawn_args']], ['grimbrush'])
        board = self.apply_task(path, board, {'op': 'start', 'task_id': 'scene'})
        self.assertEqual(board['ready_task_ids'], ['props'])
        self.assertEqual(self.call(team_path)['scheduled_dispatch_plan']['spawn_args'], [])
        for action in ({'op': 'start', 'task_id': 'review'}, {'op': 'start', 'task_id': 'props'},
                       {'op': 'complete', 'task_id': 'scene', 'evidence': []}):
            self.assert_http_error(400, path, 'PUT', self.task_request(board, action))
        self.assertEqual(self.call(path), board)
        board = self.apply_task(path, board, {'op': 'block', 'task_id': 'scene', 'reason': 'Needs scene review'})
        self.assertEqual(board['ready_task_ids'], ['props'])
        board = self.apply_task(path, board, {'op': 'reassign', 'task_id': 'scene', 'role': 'ui'})
        board = self.apply_task(path, board, {'op': 'requeue', 'task_id': 'scene'})
        board = self.apply_task(path, board, {'op': 'start', 'task_id': 'scene'})
        board = self.apply_task(path, board, {'op': 'start', 'task_id': 'props'})
        board = self.apply_task(path, board, {'op': 'complete', 'task_id': 'scene',
                                              'evidence': ['Reviewed opening scene']})
        self.assertEqual(board['ready_task_ids'], ['review'])
        tasks = {task['id']: task for task in board['tasks']}
        self.assertEqual(tasks['scene']['role'], 'ui')
        self.assertEqual(tasks['scene']['status'], 'completed')
        self.assertEqual(tasks['scene']['evidence'], ['Reviewed opening scene'])
        self.assertEqual(tasks['props']['status'], 'running')
        self.assertEqual(self.call(path), board)

    def test_task_revision_and_spec_conflicts_survive_restart(self):
        project, path, empty = self.create_task_board()
        add = self.add_task('lighting', 'content')
        saved = self.apply_task(path, empty, add)
        self.stop_server()
        self.start_server()
        self.assertEqual(self.call(path), saved)
        self.assert_http_error(409, path, 'PUT', self.task_request(empty, add))
        project['spec']['shots'][0]['duration'] = 5
        self.call('/api/projects/' + project['id'] + '/spec', 'PUT', {'spec': project['spec']})
        stale = self.call(path)
        self.assertEqual(stale['state'], 'stale')
        self.assertEqual(stale['revision'], saved['revision'])
        self.assertEqual(stale['board_spec_sha256'], saved['spec_sha256'])
        self.assertNotEqual(stale['spec_sha256'], saved['spec_sha256'])
        team = self.call('/api/team/' + project['id'])
        self.assertEqual(team['scheduled_dispatch_plan']['board_state'], 'stale')
        self.assertEqual(team['scheduled_dispatch_plan']['spawn_args'], [])
        start = {'op': 'start', 'task_id': 'lighting'}
        self.assert_http_error(409, path, 'PUT', self.task_request(saved, start))
        self.assert_http_error(409, path, 'PUT', self.task_request(stale, start))
        self.assertEqual(self.call(path), stale)
        reset = self.apply_task(path, stale, {'op': 'reset'})
        self.assertEqual(reset['state'], 'current')
        self.assertEqual(reset['board_spec_sha256'], stale['spec_sha256'])
        self.assertEqual(reset['tasks'], [])
        self.assert_http_error(409, path, 'PUT', self.task_request(stale, {'op': 'reset'}))
        self.stop_server()
        self.start_server()
        self.assertEqual(self.call(path), reset)

    def test_task_api_rejects_invalid_requests_without_mutation(self):
        _, path, board = self.create_task_board()
        data = self.task_request(board, self.add_task('lighting', 'content'))
        headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}
        self.assert_http_error(403, path, 'PUT', data, {'Content-Type': 'application/json'})
        self.assert_http_error(403, path, 'PUT', data, {**headers, 'Origin': 'http://other.invalid'})
        self.assert_http_error(404, path, 'POST', data)
        self.assert_http_error(404, '/api/projects/missing-project/tasks')
        self.assert_http_error(404, '/api/projects/missing-project/tasks', 'PUT', data)
        for malformed in ({}, [], {**data, 'expected_revision': True},
                          {**data, 'action': {'op': 'unknown'}}, {**data, 'verified': True}):
            self.assert_http_error(400, path, 'PUT', malformed)
        self.assertEqual(self.call(path), board)

    def test_unreadable_board_keeps_team_templates_and_checkpoint_available(self):
        project, path, board = self.create_task_board()
        self.apply_task(path, board, self.add_task('lighting', 'content'))
        record = Path(self.temp.name) / 'projects' / project['id'] / 'task-board.json'
        record.write_text('invalid JSON', encoding='utf-8')
        self.assert_http_error(400, path)
        team = self.call('/api/team/' + project['id'])
        self.assertEqual(len(team['dispatch_plan']['assignments']), 6)
        self.assertNotIn('scheduled_dispatch_plan', team)
        self.assertTrue(team['scheduling_error'])
        checkpoint = self.call('/api/projects/' + project['id'] + '/checkpoint')
        self.assertEqual(checkpoint['state'], 'empty')
        self.assertEqual(record.read_text(encoding='utf-8'), 'invalid JSON')

    @unittest.skipUnless(shutil.which('godot'), 'Godot is required to run the world builder')
    def test_build_gated_task_uses_the_matching_verified_pipeline_job(self):
        project, path, _ = self.create_task_board(kind='world')
        project_path = '/api/projects/' + project['id']
        draft = self.call(project_path + '/generate', 'POST', {'seed': 237, 'count': 24})['spec']
        self.call(project_path + '/spec', 'PUT', {'spec': draft})
        other, other_path, _ = self.create_task_board('Other queue', kind='world')
        self.call('/api/projects/' + other['id'] + '/spec', 'PUT', {'spec': draft})
        add = self.add_task('package', 'build_operations', gate='build')
        start = {'op': 'start', 'task_id': 'package'}
        complete = {'op': 'complete', 'task_id': 'package', 'evidence': ['Verified world package']}
        board = self.apply_task(path, self.call(path), add)
        board = self.apply_task(path, board, start)
        self.assert_http_error(400, path, 'PUT', self.task_request(board, complete))
        job = self.call(project_path + '/build', 'POST', {})
        job_path = '/api/jobs/' + job['id']
        deadline = time.monotonic() + 180
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(0.25)
            job = self.call(job_path)
        self.assertEqual(job['status'], 'passed', self.call(job_path + '/log')['log'])
        self.assertTrue(job['verified'])
        self.assertEqual(job['spec_sha256'], board['spec_sha256'])
        releases_path = project_path + '/releases'
        registry = self.call(releases_path)
        promote = {'expected_revision': registry['revision'], 'spec_sha256': registry['spec_sha256'],
                   'action': {'op': 'promote', 'job_id': job['id']}}
        promoted = self.call(releases_path, 'PUT', promote, expected_status=200)
        self.assertEqual(promoted['active_state'], 'current')
        self.assertEqual(promoted['revision'], registry['revision'] + 1)
        self.assertEqual(promoted['releases'][0]['job_id'], job['id'])
        self.assertTrue(promoted['active_release_id'])
        self.assertEqual(self.call(releases_path), promoted)
        performance = self.call(project_path + '/performance')
        self.assertEqual(performance['counts']['passed'], 1)
        self.assertEqual([sample['job_id'] for sample in performance['samples']], [job['id']])
        self.assertGreater(performance['samples'][0]['total_seconds'], 0)
        self.assertEqual(self.call('/api/projects/' + other['id'] + '/performance')['counts']['total'], 0)
        audit = self.call(project_path + '/supervisor')
        checks = {row['id']: row['status'] for row in audit['checks']}
        self.assertEqual(checks['build'], 'pass')
        self.assertEqual(checks['release'], 'pass')
        self.assertEqual(self.call('/api/release/' + project['id'])['release_candidates'][0]['job_id'], job['id'])
        self.assert_http_error(409, releases_path, 'PUT', promote)
        activate = {'expected_revision': promoted['revision'], 'spec_sha256': promoted['spec_sha256'],
                    'action': {'op': 'activate', 'release_id': promoted['active_release_id']}}
        self.assertEqual(self.call(releases_path, 'PUT', activate, expected_status=200), promoted)
        complete['job_id'] = job['id']
        other_board = self.apply_task(other_path, self.call(other_path), add)
        other_board = self.apply_task(other_path, other_board, start)
        self.assertEqual(other_board['spec_sha256'], board['spec_sha256'])
        self.assert_http_error(400, other_path, 'PUT', self.task_request(other_board, complete))
        self.assertEqual(self.call(other_path), other_board)
        finished = self.apply_task(path, board, complete)
        self.assertEqual(finished['tasks'][0]['status'], 'completed')
        self.assertEqual(finished['tasks'][0]['job_id'], job['id'])
        draft['terrain']['amplitude'] += 0.25
        self.call(project_path + '/spec', 'PUT', {'spec': draft})
        stale_release = self.call(releases_path)
        self.assertEqual(self.call(project_path + '/performance')['counts']['total'], 0)
        self.assertEqual(stale_release['active_state'], 'stale')
        self.assertEqual(stale_release['active_release_id'], promoted['active_release_id'])
        self.assertEqual(stale_release['releases'], promoted['releases'])
        self.assert_http_error(400, releases_path, 'PUT', {**activate, 'spec_sha256': stale_release['spec_sha256']})
        updated = self.apply_task(path, self.call(path), {'op': 'reset'})
        updated = self.apply_task(path, updated, add)
        updated = self.apply_task(path, updated, start)
        self.assertNotEqual(updated['spec_sha256'], job['spec_sha256'])
        self.assert_http_error(400, path, 'PUT', self.task_request(updated, complete))
        self.assertEqual(self.call(path), updated)

    def test_checkpoint_survives_server_restart_and_detects_old_revision(self):
        _, path, data = self.create_checkpoint_project()
        saved = self.call(path, 'PUT', data)
        self.assertEqual(saved['state'], 'current')
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(saved['remaining_seconds'], 17700)
        for field in ('elapsed_seconds', 'status', 'completed_work', 'verification_evidence',
                      'remaining_work', 'next_action'):
            self.assertEqual(saved['checkpoint'][field], data[field])
        self.stop_server()
        self.start_server()
        self.assertEqual(self.call(path), saved)
        self.assert_http_error(409, path, 'PUT', {**data, 'elapsed_seconds': 450})
        self.assertEqual(self.call(path), saved)
        updated = self.call(path, 'PUT', {**data, 'expected_revision': 1, 'elapsed_seconds': 450})
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['remaining_seconds'], 17550)

    def test_checkpoint_stale_after_spec_edit_requires_explicit_reset(self):
        project, path, data = self.create_checkpoint_project()
        original = self.call(path, 'PUT', data)
        project['spec']['shots'][0]['duration'] = 5
        self.call('/api/projects/' + project['id'] + '/spec', 'PUT', {'spec': project['spec']})
        stale = self.call(path)
        self.assertEqual(stale['state'], 'stale')
        self.assertEqual(stale['checkpoint'], original['checkpoint'])
        self.assertIsNone(stale['remaining_seconds'])
        self.assertNotEqual(stale['spec_sha256'], data['spec_sha256'])
        self.assert_http_error(409, path, 'PUT', {**data, 'expected_revision': stale['revision']})
        new_spec = {**data, 'expected_revision': stale['revision'], 'spec_sha256': stale['spec_sha256'],
                    'elapsed_seconds': 0}
        self.assert_http_error(409, path, 'PUT', new_spec)
        self.assertEqual(self.call(path), stale)
        current = self.call(path, 'PUT', {**new_spec, 'reset_for_spec_change': True})
        self.assertEqual(current['state'], 'current')
        self.assertEqual(current['revision'], stale['revision'] + 1)
        self.assertEqual(current['remaining_seconds'], 18000)

    def test_checkpoint_starts_new_run_on_completed_spec(self):
        _, path, data = self.create_checkpoint_project()
        finished = self.call(path, 'PUT', {**data, 'status': 'completed', 'remaining_work': [],
                                           'next_action': ''})
        new_run = {**data, 'expected_revision': finished['revision'], 'status': 'in_progress',
                   'elapsed_seconds': 0, 'start_new_run': True, 'completed_work': [],
                   'verification_evidence': [], 'next_action': 'Review the second scene'}
        current = self.call(path, 'PUT', new_run)
        self.assertEqual(current['state'], 'current')
        self.assertEqual(current['spec_sha256'], finished['spec_sha256'])
        self.assertEqual(current['revision'], finished['revision'] + 1)
        self.assertEqual(current['remaining_seconds'], 18000)
        self.assertEqual(current['checkpoint']['elapsed_seconds'], 0)
        self.assertEqual(current['checkpoint']['status'], 'in_progress')
        self.assert_http_error(409, path, 'PUT', new_run)
        self.assertEqual(self.call(path), current)

    def test_checkpoint_invalid_requests_preserve_empty_state(self):
        from command_center.server import LIMIT
        _, path, data = self.create_checkpoint_project()
        empty = self.call(path)
        self.assert_http_error(400, path, 'PUT', [])
        self.assert_http_error(400, path, 'PUT', {})
        self.assert_http_error(400, path, 'PUT', {**data, 'elapsed_seconds': -1})
        self.assert_http_error(400, path, 'PUT', {**data, 'status': 'invalid'})
        self.assert_http_error(400, path, 'PUT', {**data, 'verification_evidence': 'one unchecked string'})
        self.assert_http_error(404, '/api/projects/missing-project/checkpoint')
        self.assert_http_error(404, '/api/projects/missing-project/checkpoint', 'PUT', data)
        self.assert_http_error(404, path, 'POST', data)
        headers = {'Content-Type': 'application/json', 'X-Studio-Request': '1'}
        self.assert_http_error(403, path, 'PUT', data, {'Content-Type': 'application/json'})
        self.assert_http_error(403, path, 'PUT', data, {**headers, 'Origin': 'http://other.invalid'})
        self.assert_http_error(400, path, 'PUT', data, {**headers, 'Content-Length': str(LIMIT + 1)})
        self.assertEqual(self.call(path), empty)
