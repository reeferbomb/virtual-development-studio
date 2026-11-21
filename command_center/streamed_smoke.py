"""Exercise fixture and custom builds through the local HTTP API."""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.request import Request, urlopen

from .server import ROOT, VERSION, StudioService, create_server


SCENARIOS = {
    'unified': ('Unified Expedition', 'Unified', 'unified_expedition'),
    'living': ('Living World', 'Living World', 'living_world'),
    'city': ('Metropolis', 'City', 'metropolis'),
    'vertical': ('Vertical City', 'Vertical City', 'vertical_city'),
    'advanced': ('Advanced City', 'Advanced City', 'advanced_city'),
    'frontline': ('Frontline City', 'Frontline City', 'frontline_city'),
}


def smoke(workspace, kind):
    title, gate_title, package_id = SCENARIOS[kind]
    qa_flag = f'--{kind}-qa'
    qa_key = f'{kind}_qa'
    service = StudioService(ROOT, workspace)
    server = create_server(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def call(route, method='GET', data=None):
        request = Request(base + route, method=method,
                          headers={'Content-Type': 'application/json', 'X-Studio-Request': '1'},
                          data=json.dumps(data).encode() if data is not None else None)
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def build(route):
        job = call(route + '/build', 'POST', {})
        job_route = '/api/jobs/' + job['id']
        deadline = time.monotonic() + 180
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.25)
            job = call(job_route)
        if job['status'] != 'passed' or job['verified'] is not True:
            raise RuntimeError(str(job) + '\n' + call(job_route + '/log')['log'])
        return job

    def gate(team, status):
        expected = {'name': f'{gate_title} scenario QA', 'status': status}
        assert expected in team['gates'], team['gates']

    try:
        version = call('/api/status')['version']
        assert version == VERSION, version
        packages = call('/api/catalog')['packages']
        listed = [row for row in packages if row['id'] == package_id]
        assert len(listed) == 1 and listed[0]['kind'] == kind and listed[0]['verified'] is True, listed

        project = call('/api/projects', 'POST', {'name': f'{title} Acceptance', 'kind': kind})
        route = '/api/projects/' + project['id']
        team_route = '/api/team/' + project['id']
        release_route = '/api/release/' + project['id']
        initial_team = call(team_route)
        gate(initial_team, 'pending')
        dispatch = initial_team['dispatch_plan']
        assert dispatch['execution_mode'] == 'export_only'
        profile = dispatch['profile']
        assert profile['mode'] == 'fast' and profile['service_tier'] == 'priority'
        assert profile['max_parallel'] == 6
        settings = [(row['model'], row['reasoning_effort']) for row in dispatch['spawn_args']]
        assert settings.count(('gpt-6.2-astra', 'ultra')) == 5
        assert settings.count(('gpt-6.2-sol', 'max')) == 1

        job = build(route)
        assert qa_flag in job['commands'][0]['argv']
        assert dispatch['project']['spec_sha256'] == job['spec_sha256']
        qa = job[qa_key]
        assert qa['pass'] is True and qa['checks'], qa
        team = call(team_route)
        gate(team, 'passed')
        for name in ('Human render review', 'Device review'):
            assert {'name': name, 'status': 'pending'} in team['gates']
        assert len(call(release_route)['release_candidates']) == 1

        call(route + '/spec', 'PUT', {'spec': dict(project['spec'], seed=238)})
        edited = call(team_route)
        gate(edited, 'stale')
        edited_digest = edited['dispatch_plan']['project']['spec_sha256']
        assert dispatch['project']['spec_sha256'] != edited_digest
        assert not call(release_route)['release_candidates']
        custom_job = build(route)
        assert custom_job['spec_sha256'] == edited_digest
        assert qa_flag not in custom_job['commands'][0]['argv']
        assert qa_key not in custom_job
        gate(call(team_route), 'pending')

        return {
            'version': version, 'verified': True, 'dispatch_profile': profile,
            'execution_mode': dispatch['execution_mode'], qa_key: qa,
            'gates': team['gates'], 'edited_gate': 'stale', 'edited_build_gate': 'pending',
            'commands': [{key: value for key, value in row.items() if key != 'argv'} for row in job['commands']],
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        service.pipeline.worker.shutdown(wait=True)


def main(kind, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix=f'studio-{kind}-') as temporary:
        result = json.dumps(smoke(Path(temporary), kind), indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result, encoding='utf-8')
        print(result, end='')
