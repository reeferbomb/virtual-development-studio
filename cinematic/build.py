"""Generate a Blender-to-Godot cinematic package with validated source assets."""
import argparse
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('world_factory',HERE.parent/'world/build.py')
world=importlib.util.module_from_spec(loader);loader.loader.exec_module(world)
factory=world.factory
CLIPS={'Idle','Walk','Run','Aim','Crouch','Reload'}

def original_asset_provenance(assets):
    """Record the known original outputs of the city, actor and audio generators."""
    names = {"city.glb", "city.json", "animated_actor.glb", "ambience.wav",
             "footstep.wav", "thunder.wav", "metadata.json"}
    files = sorted(assets.iterdir())
    if {p.name for p in files} != names or any(p.is_symlink() or not p.is_file() for p in files):
        raise ValueError("Cinematic asset directory differs from the original generator outputs")
    return [{
        "path": p.name,
        "source": "Studio original procedural generation",
        "license": "MIT",
        "attribution": "Copyright (c) 2026 Virtual Development Studio contributors. "
                       "Retain the copyright and permission notices in LICENSE.",
        "sha256": factory.hash_file(p),
    } for p in files]

def validate(data):
    if not isinstance(data,dict) or not isinstance(data.get('shots'),list) or not 1<=len(data['shots'])<=12:
        raise ValueError('Specify 1–12 shots')
    seed=factory.integer(data.get('seed'),0,2147483647,'city seed')
    names=set();shots=[];previous=None
    for row in data['shots']:
        if not isinstance(row,dict): raise ValueError('Shot must be an object')
        ident=world.identifier(row.get('id'))
        if ident in names or row.get('clip') not in CLIPS: raise ValueError('Duplicate ID or unknown animation clip')
        names.add(ident)
        shot={'id':ident,'duration':factory.number(row.get('duration'),.25,30,'duration'),'clip':row['clip'],
              'fov':factory.number(row.get('fov'),20,100,'fov'),'rain':factory.number(row.get('rain'),0,1,'rain'),
              'light':factory.number(row.get('light'),0,4,'light')}
        for key in ('camera_from','camera_to','look_from','look_to','actor_from','actor_to'):
            shot[key]=world.vector(row.get(key),-30,30,key)
        # Scene has a 6m-wide clear street. Restrict moving cameras/actors to it.
        for key in ('camera_from','camera_to','actor_from','actor_to'):
            x,y,z=shot[key]
            if abs(x)>2.7 or abs(z)>14 or y<0 or y>8: raise ValueError('Actor/camera outside clear street')
            if key.startswith('actor') and y!=0: raise ValueError('Actor needs ground level')
        for suffix in ('from','to'):
            a,b=shot['camera_'+suffix],shot['look_'+suffix]
            if math.hypot(a[0]-b[0],a[2]-b[2])<.1: raise ValueError('Camera target is degenerate')
        if previous is not None and shot['actor_from']!=previous: raise ValueError('Actor motion discontinuity')
        previous=shot['actor_to'];shots.append(shot)
    if sum(s['duration'] for s in shots)>120: raise ValueError('Timeline exceeds 120s')
    return {'id':world.identifier(data.get('id')),'seed':seed,'shots':shots}

def build(spec_path,dest,blender,godot,demo_qa):
    spec=validate(json.loads(spec_path.read_text()))
    stage=factory.new_staging(dest)
    print(f'Cinematic staging: {stage}',flush=True)
    try:
        assets=stage/'assets';assets.mkdir();reports=stage/'reports';reports.mkdir()
        for file in (HERE/'template').iterdir():
            if file.is_file(): shutil.copy2(file,stage/file.name)
        factory.write_json(stage/'sequence.json',spec)
        b=[blender,'-b','--python-exit-code','1','--python']
        factory.invoke(b+[str(HERE/'art/city.py'),'--',str(assets),str(spec['seed'])],reports/'city-build.log',timeout=120)
        factory.invoke(b+[str(HERE/'art/test_city.py'),'--',str(assets)],reports/'city-test.log',timeout=120)
        factory.invoke(b+[str(HERE/'art/animate.py'),'--',str(assets)],reports/'animation-build.log',timeout=120)
        factory.invoke([sys.executable,str(HERE/'art/test_animation.py'),str(assets)],reports/'animation-test.log',timeout=60)
        factory.invoke([sys.executable,str(HERE/'audio.py'),str(assets)],reports/'audio-build.log')
        source=stage/'source';source.mkdir();(source/'.gdignore').touch()
        for path in assets.glob('*.blend'): path.rename(source/path.name)
        factory.write_json(assets/'provenance.json', original_asset_provenance(assets))
        cmd=[godot,'--headless','--path',str(stage)]
        imported=world.run_stage(cmd+['--editor','--import'],reports/'import.log')
        launched=world.run_stage(cmd+['--quit-after','10'],reports/'launch.log','STUDIO_CINEMATIC_READY')
        if 'ERROR:' in imported or 'ERROR:' in launched: raise ValueError('Godot emitted an engine error')
        qa=None
        if demo_qa:
            output=world.run_stage(cmd+['--script','res://cinematic_qa.gd'],reports/'qa.log','STUDIO_CINEMATIC_QA_JSON ')
            qa=json.loads(next(l.split(' ',1)[1] for l in output.splitlines() if l.startswith('STUDIO_CINEMATIC_QA_JSON ')))
            if qa.get('pass') is not True or 'ERROR:' in output: raise ValueError('Cinematic timeline QA failed')
            factory.write_json(reports/'qa.json',qa)
        factory.invoke(b+[str(HERE/'art/render_preview.py'),'--',str(assets),str(stage/'preview.png')],reports/'preview-render.log',timeout=180)
        from PIL import Image, ImageStat
        with Image.open(stage/'preview.png') as image:
            stat=ImageStat.Stat(image.convert('L'))
            if image.size!=(960,540) or stat.stddev[0]<8: raise ValueError('Preview is blank or wrong dimensions')
            factory.write_json(reports/'preview.json',{'dimensions':list(image.size),'luminance_mean':stat.mean[0],'luminance_stddev':stat.stddev[0],'renderer':'Blender Cycles CPU','scope':'Raster sanity, not live Godot appearance'})
        cache=stage/'.godot'
        if cache.is_dir() and not cache.is_symlink(): shutil.rmtree(cache)
        factory.write_json(stage/'manifest.json',{'schema':1,'status':'passed','sequence':spec['id'],'qa':qa,'files':factory.inventory(stage)})
        if factory.verify_package(stage) or dest.exists() or dest.is_symlink(): raise ValueError('Package integrity or destination collision')
        stage.rename(dest)
        print(f'CINEMATIC_FACTORY_PASS {dest}')
    except Exception:
        print(f'Cinematic build failed; retained {stage}',file=sys.stderr)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',nargs='?',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--blender',default='blender52')
    parser.add_argument('--godot',default='godot')
    parser.add_argument('--demo-qa',action='store_true')
    parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    try:
        if args.verify:
            errors=factory.verify_package(args.verify);print('; '.join(errors) if errors else 'CINEMATIC_INTEGRITY_PASS');sys.exit(bool(errors))
        if not args.spec or not args.output: parser.error('Specify sequence and --output, or --verify')
        build(args.spec.resolve(),args.output.absolute(),args.blender,args.godot,args.demo_qa)
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as e:
        print(e,file=sys.stderr);sys.exit(1)
