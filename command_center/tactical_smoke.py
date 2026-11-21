"""Exercise the v10 tactical build workflow through the real local HTTP API."""
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
    server = create_server(service,0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'

    def call(route, method='GET', data=None):
        req = Request(base+route,method=method,headers={'Content-Type':'application/json','X-Studio-Request':'1'},data=json.dumps(data).encode() if data is not None else None)
        with urlopen(req,timeout=15) as response:
            return json.load(response)

    try:
        spec=json.loads((ROOT/'gameplay/tactical_spec.json').read_text())
        project=call('/api/projects','POST',{'name':'Tactical Acceptance Yard','kind':'gameplay'})
        route='/api/projects/'+project['id']
        call(route+'/spec','PUT',{'spec':spec})
        job=call(route+'/build','POST',{})
        deadline=time.monotonic()+150
        while job['status'] in ('queued','running') and time.monotonic()<deadline:
            time.sleep(.25)
            job=call('/api/jobs/'+job['id'])
        if job['status']!='passed' or not job.get('verified'):
            raise RuntimeError(str(job)+'\n'+call('/api/jobs/'+job['id']+'/log')['log'])
        qa=job.get('tactical_qa',{})
        assert qa.get('pass') is True, qa
        team=call('/api/team/'+project['id'])
        assert any(g=={'name':'Tactical scenario QA','status':'passed'} for g in team['gates'])
        # Altering the saved design must invalidate the old tactical evidence.
        changed={**spec,'seed':spec['seed']+1}
        call(route+'/spec','PUT',{'spec':changed})
        updated=call('/api/team/'+project['id'])
        assert any(g=={'name':'Tactical scenario QA','status':'stale'} for g in updated['gates'])
        return {'version':call('/api/status')['version'],'verified':True,'tactical_qa':qa,'gates':team['gates'],'edited_gate':'stale','commands':[{k:v for k,v in x.items() if k!='argv'} for x in job['commands']]}
    finally:
        server.shutdown();server.server_close();thread.join();service.pipeline.worker.shutdown(wait=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='studio-tactical-') as temp:
        result=json.dumps(smoke(Path(temp)),indent=2)+'\n'
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(result)
        print(result)
