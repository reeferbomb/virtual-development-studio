"""Verify the real HTTP open-world creation, dispatch profile, build and stale gates."""
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
        req = Request(base+route, method=method, headers={'Content-Type':'application/json','X-Studio-Request':'1'},
                      data=json.dumps(data).encode() if data is not None else None)
        with urlopen(req, timeout=15) as response:
            return json.load(response)

    try:
        project = call('/api/projects','POST',{'name':'Frontier Acceptance','kind':'openworld'})
        route = '/api/projects/'+project['id']
        team_route = '/api/team/'+project['id']
        dispatch = call(team_route)['dispatch_plan']
        assert dispatch['execution_mode'] == 'export_only'
        assert dispatch['profile']['mode'] == 'fast' and dispatch['profile']['service_tier'] == 'priority'
        assert dispatch['profile']['max_parallel'] == 6
        settings = [(x['model'],x['reasoning_effort']) for x in dispatch['spawn_args']]
        assert settings.count(('gpt-6.2-astra','ultra')) == 5 and settings.count(('gpt-6.2-sol','max')) == 1
        job = call(route+'/build','POST',{})
        deadline = time.monotonic()+180
        while job['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.25)
            job = call('/api/jobs/'+job['id'])
        if job['status']!='passed' or not job['verified']:
            raise RuntimeError(str(job)+'\n'+call('/api/jobs/'+job['id']+'/log')['log'])
        qa = job['openworld_qa']
        assert qa['pass'] is True
        team = call(team_route)
        assert {'name':'Open-world scenario QA','status':'passed'} in team['gates'], team['gates']
        call(route+'/spec','PUT',{'spec':{**project['spec'],'seed':238}})
        changed = call(team_route)
        assert {'name':'Open-world scenario QA','status':'stale'} in changed['gates'], changed['gates']
        assert dispatch['project']['spec_sha256'] != changed['dispatch_plan']['project']['spec_sha256']
        return {'version':call('/api/status')['version'],'verified':True,'dispatch_profile':dispatch['profile'],
                'execution_mode':dispatch['execution_mode'],'openworld_qa':qa,'gates':team['gates'],'edited_gate':'stale',
                'commands':[{k:v for k,v in row.items() if k!='argv'} for row in job['commands']]}
    finally:
        server.shutdown(); server.server_close(); thread.join(); service.pipeline.worker.shutdown(wait=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-frontier-') as temp:
        result=json.dumps(smoke(Path(temp)),indent=2)+'\n'
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(result)
        print(result)
