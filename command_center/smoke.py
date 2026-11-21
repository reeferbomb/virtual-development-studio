"""Prove the real HTTP project-edit-build-verify workflow in an isolated workspace."""
import argparse
import json
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from .server import ROOT, StudioService, create_server


def smoke(workspace):
    service = StudioService(ROOT, workspace)
    server = create_server(service, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def call(route, method='GET', data=None):
        req = Request(base + route, method=method,
                      headers={'Content-Type': 'application/json', 'X-Studio-Request': '1'},
                      data=json.dumps(data).encode() if data is not None else None)
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    try:
        project = call('/api/projects', 'POST', {'name': 'Studio Acceptance Yard', 'kind': 'world'})
        route = '/api/projects/' + project['id']
        generated = call(route + '/generate', 'POST', {'seed': 237, 'count': 24})
        project['spec'] = generated['spec']
        project['spec']['terrain']['amplitude'] = 0.5
        saved = call(route + '/spec', 'PUT', {'spec': project['spec']})
        assert saved['spec']['terrain']['amplitude'] == 0.5
        job = call(route + '/build', 'POST', {})
        deadline = time.monotonic() + 180
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(0.25)
            job = call('/api/jobs/' + job['id'])
        assert job['status'] == 'passed' and job['verified'], job
        assert (workspace / job['output'] / 'project.godot').is_file()
        snap = json.loads((workspace / 'jobs' / job['id'] / 'spec.json').read_text())
        assert snap == saved['spec']
        team = call('/api/team/' + project['id'])
        release = call('/api/release/' + project['id'])
        assert len(team['roles']) == 6 and len(release['release_candidates']) == 1
        route_qa = json.loads((workspace / job['output'] / 'reports' / 'route-qa.json').read_text())
        assert route_qa['pass'] is True
        saved['spec']['terrain']['amplitude'] = 0.75
        call(route+'/spec','PUT',{'spec':saved['spec']})
        stale = call('/api/release/'+project['id'])
        assert stale['verification_gate']['status'] == 'stale' and not stale['release_candidates']
        saved['spec']['terrain']['amplitude'] = 0.5
        return {'project': project['name'], 'kind': 'world', 'seed':237, 'cover':24, 'planned_route_m':generated['route_m'], 'route_qa':route_qa, 'edited_terrain_amplitude': 0.5,
                'builder_output': 'project.godot', 'status': job['status'], 'verified': job['verified'],
                'commands': [{k: v for k, v in c.items() if k != 'argv'} for c in job['commands']],
                'gates': team['gates'], 'role_count': len(team['roles']), 'snapshot_matches': snap == saved['spec'], 'edited_build_gate': stale['verification_gate']['status'],
                'tools': call('/api/status')['tools'], 'log': call('/api/jobs/' + job['id'] + '/log')['log'].replace(str(workspace), '<workspace>').replace(str(ROOT), '<studio>')}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        service.pipeline.worker.shutdown(wait=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-acceptance-') as temp:
        report = json.dumps(smoke(Path(temp)), indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report)
        print(report)
