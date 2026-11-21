"""Create the multiplayer training arena from the verified v4 fixture."""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location('world_factory', HERE.parent / 'world/build.py')
world = importlib.util.module_from_spec(loader)
loader.loader.exec_module(world)
factory = world.factory

def build(source, dest, godot):
    if factory.verify_package(source):
        raise ValueError('World source integrity check failed')
    level = json.loads((source/'level.json').read_text())
    baseline = world.validate(json.loads((HERE.parent/'world/demo_spec.json').read_text()))
    if level != baseline:
        raise ValueError('The current network spawn fixture requires the original training-yard layout')
    stage = factory.new_staging(dest)
    print(f'Multiplayer staging: {stage}',flush=True)
    try:
        shutil.copytree(source,stage,dirs_exist_ok=True)
        shutil.copy2(source/'manifest.json',stage/'reports/world-source-manifest.json')
        for file in (HERE/'template').glob('*'):
            if file.is_file() and file.suffix in {'.gd','.tscn'}:
                shutil.copy2(file,stage/file.name)
        for name in ('combat.gd','navigation.gd'):
            shutil.copy2(HERE.parent/'gameplay/template'/name,stage/name)
        (stage/'tests').mkdir()
        for file in (HERE/'tests').glob('*.gd'):
            shutil.copy2(file,stage/'tests'/file.name)
        project = stage/'project.godot'
        project.write_text(project.read_text().replace('res://main.tscn','res://network.tscn').replace('Studio Generated Training World','Studio Multiplayer Arena'))
        cmd = [godot,'--headless','--path',str(stage)]
        world.run_stage(cmd+['--editor','--import'],stage/'reports/network-import.log')
        for file in sorted((stage/'tests').glob('*.gd')):
            world.run_stage(cmd+['--script',f'res://tests/{file.name}'],stage/'reports'/f'{file.stem}.log')
        # Run the real multi-process harness before finalizing the package.
        for n in (2,4,8):
            factory.invoke([sys.executable,str(HERE/'stress.py'),'--project',str(stage),'--output',str(stage/'reports'/f'loopback-{n}'),'--clients',str(n),'--godot',godot],stage/'reports'/f'stress-{n}.log',timeout=60)
        cache = stage/'.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        factory.write_json(stage/'manifest.json',{'schema':1,'status':'passed','world_sha256':factory.hash_file(source/'manifest.json'),'validation':'Godot module tests and real loopback sessions with 2, 4 and 8 remote clients','files':factory.inventory(stage)})
        if factory.verify_package(stage) or dest.exists() or dest.is_symlink():
            raise ValueError('Destination integrity or overwrite check failed')
        stage.rename(dest)
        print(f'MULTIPLAYER_FACTORY_PASS {dest}')
    except Exception:
        print(f'Multiplayer build failed; retained {stage}',file=sys.stderr)
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--godot',default='godot')
    parser.add_argument('--verify',type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            errors = factory.verify_package(args.verify)
            print('; '.join(errors) if errors else 'MULTIPLAYER_INTEGRITY_PASS')
            sys.exit(bool(errors))
        if not args.world or not args.output:
            parser.error('Specify --world and --output, or --verify')
        build(args.world.resolve(),args.output.absolute(),args.godot)
    except (OSError,ValueError,RuntimeError) as e:
        print(e,file=sys.stderr)
        sys.exit(1)
