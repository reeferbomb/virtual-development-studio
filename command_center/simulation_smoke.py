"""Exercise the expedition build and evidence invalidation through the real HTTP API."""
import argparse
import json
from pathlib import Path
import tempfile
import threading
import time
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
        project = call('/api/projects', 'POST', {'name': 'Expedition Acceptance', 'kind': 'simulation'})
        route = '/api/projects/' + project['id']
        job = call(route + '/build', 'POST', {})
        deadline = time.monotonic() + 180
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.25)
            job = call('/api/jobs/' + job['id'])
        if job['status'] != 'passed' or not job.get('verified'):
            raise RuntimeError(str(job) + '\n' + call('/api/jobs/' + job['id'] + '/log')['log'])
        qa = job.get('simulation_qa', {})
        assert qa.get('pass') is True, qa
        team = call('/api/team/' + project['id'])
        assert {'name': 'Simulation scenario QA', 'status': 'passed'} in team['gates']
        call(route + '/spec', 'PUT', {'spec': {**project['spec'], 'weather': 'fog'}})
        updated = call('/api/team/' + project['id'])
        assert {'name': 'Simulation scenario QA', 'status': 'stale'} in updated['gates']
        return {'version': call('/api/status')['version'], 'verified': True, 'simulation_qa': qa,
                'gates': team['gates'], 'edited_gate': 'stale',
                'commands': [{k: v for k, v in row.items() if k != 'argv'} for row in job['commands']]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        service.pipeline.worker.shutdown(wait=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-expedition-') as temp:
        result = json.dumps(smoke(Path(temp)), indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result)
        print(result)
