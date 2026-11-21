"""Build a standalone gameplay project over a verified world package."""
import argparse
import importlib.util
import json
import math
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.util.spec_from_file_location('world_factory', HERE.parent / 'world/build.py')
world = importlib.util.module_from_spec(loader)
loader.loader.exec_module(world)
factory = world.factory

def validate(data, level):
    if not isinstance(data, dict) or not isinstance(data.get('enemies'), list) or not 1 <= len(data['enemies']) <= 16:
        raise ValueError('Specify 1–16 enemies')
    seed = factory.integer(data.get('seed'), 0, 2147483647, 'seed')
    limit = min(level['terrain']['flat_radius'], level['terrain']['width']/2, level['terrain']['depth']/2) - .5
    obstacles = [(b['position'],b['size']) for b in level['blocks']]
    for p in level['placements']:
        if 'collider_size' in p:
            w,h,d = p['collider_size']
            r = math.radians(p['yaw_deg'])
            obstacles.append((p['position'], [abs(math.cos(r))*w+abs(math.sin(r))*d,h,abs(math.sin(r))*w+abs(math.cos(r))*d]))
    def point(value):
        v = world.vector(value, -128, 128, 'patrol point')
        if v[1] != 0 or max(abs(v[0]),abs(v[2])) > limit:
            raise ValueError('Enemies need flat-core points')
        if any(abs(v[0]-p[0]) <= s[0]/2+.5 and abs(v[2]-p[2]) <= s[2]/2+.5 for p,s in obstacles):
            raise ValueError('Enemy point crosses collider clearance')
        return v
    ids, enemies = set(), []
    for row in data['enemies']:
        if not isinstance(row,dict):
            raise ValueError('Enemy must be an object')
        ident = world.identifier(row.get('id'))
        if ident in ids or not isinstance(row.get('patrol'),list) or not 1 <= len(row['patrol']) <= 16:
            raise ValueError('Duplicate ID or invalid patrol')
        ids.add(ident)
        pos = point(row.get('position'))
        if math.dist(pos,level['spawn']) < 1.5 or any(math.dist(pos,e['position']) < 1 for e in enemies):
            raise ValueError('Enemy spawn overlaps another actor')
        enemies.append({'id':ident,'position':pos,'patrol':[point(v) for v in row['patrol']]})
    config = {'seed': seed, 'enemies': enemies}
    if 'tactical' in data:
        if not isinstance(data['tactical'], bool):
            raise ValueError('tactical must be a boolean')
        config['tactical'] = data['tactical']
    if 'destructible_blocks' in data:
        selected = data['destructible_blocks']
        if not isinstance(selected, list) or len(selected) > 128:
            raise ValueError('destructible_blocks must be a list of up to 128 block IDs')
        selected = [world.identifier(value) for value in selected]
        unique_ids = set(selected)
        if len(unique_ids) != len(selected):
            raise ValueError('destructible_blocks must contain unique block IDs')
        unknown = unique_ids - {block['id'] for block in level['blocks']}
        if unknown:
            raise ValueError(f'destructible_blocks contains IDs missing from world blocks: {sorted(unknown)}')
        config['destructible_blocks'] = selected
    return config

def generate(level, seed, count):
    seed = factory.integer(seed,0,2147483647,'seed')
    count = factory.integer(count,1,16,'enemy count')
    rng = random.Random(seed)
    boundary = int(min(level['terrain']['flat_radius'],level['terrain']['width']/2,level['terrain']['depth']/2)-1)
    candidates = [(x,z) for x in range(-boundary,boundary+1) for z in range(-boundary,boundary+1)]
    rng.shuffle(candidates)
    rows = []
    for x,z in candidates:
        if math.dist([x,0,z],level['goal']) < 2 or math.dist([x,0,z],level['spawn']) < 3:
            continue
        if any(math.dist([x,0,z],r['position']) < 3 for r in rows):
            continue
        offsets = [(2,0),(-2,0),(0,2),(0,-2)]
        rng.shuffle(offsets)
        for dx,dz in offsets:
            row = {'id':f'guard_{len(rows)+1:02d}','position':[x,0,z], 'patrol':[[x,0,z],[x+dx/2,0,z+dz/2],[x+dx,0,z+dz]]}
            try:
                validate({'seed':seed,'enemies':rows+[row]},level)
            except ValueError:
                continue
            rows.append(row)
            break
        if len(rows) == count:
            return validate({'seed':seed,'enemies':rows},level)
    raise ValueError('Not enough spaced, clear spawn and patrol points for requested encounter')

def build(spec_path, source, dest, godot, demo_qa, generated_seed=None, count=3, *, tactical_qa=False):
    if generated_seed is not None and tactical_qa:
        raise ValueError('--tactical-qa requires a gameplay spec')
    if factory.verify_package(source):
        raise ValueError('World source integrity check failed')
    level = json.loads((source/'level.json').read_text())
    config = generate(level,generated_seed,count) if generated_seed is not None else validate(json.loads(spec_path.read_text()),level)
    stage = factory.new_staging(dest)
    print(f'Gameplay staging: {stage}',flush=True)
    try:
        shutil.copytree(source,stage,dirs_exist_ok=True)
        shutil.copy2(source/'manifest.json',stage/'reports/world-source-manifest.json')
        for file in (HERE/'template').glob('*'):
            if file.is_file() and file.suffix in {'.gd','.tscn'}:
                shutil.copy2(file,stage/file.name)
        (stage/'tests').mkdir()
        for file in (HERE/'tests').glob('*.gd'):
            shutil.copy2(file,stage/'tests'/file.name)
        factory.write_json(stage/'gameplay.json',config)
        project = stage/'project.godot'
        project.write_text(project.read_text().replace('res://main.tscn','res://gameplay.tscn').replace('Studio Generated Training World','Studio Gameplay Lab'))
        cmd = [godot,'--headless','--path',str(stage)]
        world.run_stage(cmd+['--editor','--import'],stage/'reports/gameplay-import.log')
        world.run_stage(cmd+['--quit-after','10'],stage/'reports/gameplay-launch.log','STUDIO_GAMEPLAY_READY')
        for file in sorted((stage/'tests').glob('*.gd')):
            world.run_stage(cmd+['--script',f'res://tests/{file.name}'],stage/'reports'/f'{file.stem}.log')
        qa = None
        if demo_qa:
            output = world.run_stage(cmd+['--script','res://gameplay_qa.gd'],stage/'reports/gameplay-qa.log','STUDIO_GAMEPLAY_QA_JSON ')
            qa = json.loads(next(line.split(' ',1)[1] for line in output.splitlines() if line.startswith('STUDIO_GAMEPLAY_QA_JSON ')))
            if qa.get('pass') is not True:
                raise ValueError('Gameplay QA failed')
            factory.write_json(stage/'reports/gameplay-qa.json',qa)
        manifest = {
            'schema': 1,
            'status': 'passed',
            'world_sha256': factory.hash_file(source/'manifest.json'),
            'gameplay_qa': qa,
        }
        if tactical_qa:
            marker = 'STUDIO_TACTICAL_QA_JSON '
            log = stage/'reports/tactical-qa.log'
            output = world.run_stage(
                cmd + ['--fixed-fps', '60', '--script', 'res://tactical_qa.gd'], log, marker,
            )
            reports = [line.removeprefix(marker) for line in output.splitlines() if line.startswith(marker)]
            if len(reports) != 1:
                raise ValueError(f'Tactical QA must emit one report. See {log}')
            report = json.loads(reports[0])
            if not isinstance(report, dict) or report.get('pass') is not True:
                raise ValueError(f'Tactical QA failed. See {log}')
            factory.write_json(stage/'reports/tactical-qa.json', report)
            manifest['tactical_qa'] = report
        cache = stage/'.godot'
        if cache.is_dir() and not cache.is_symlink():
            shutil.rmtree(cache)
        manifest['files'] = factory.inventory(stage)
        factory.write_json(stage/'manifest.json', manifest)
        if factory.verify_package(stage) or dest.exists() or dest.is_symlink():
            raise ValueError('Destination integrity or overwrite check failed')
        stage.rename(dest)
        print(f'GAMEPLAY_FACTORY_PASS {dest}')
    except Exception:
        print(f'Gameplay build failed; retained {stage}',file=sys.stderr)
        raise

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec',nargs='?',type=Path)
    parser.add_argument('--world',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--godot',default='godot')
    parser.add_argument('--demo-qa',action='store_true')
    parser.add_argument('--tactical-qa', action='store_true',
                        help='Run headless QA on the tactical training fixture')
    parser.add_argument('--generate',type=int,metavar='SEED',help='Generate a deterministic guard encounter')
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--verify',type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            errors = factory.verify_package(args.verify)
            print('; '.join(errors) if errors else 'GAMEPLAY_INTEGRITY_PASS')
            sys.exit(bool(errors))
        if not args.world or not args.output or (args.spec is None) == (args.generate is None):
            parser.error('Specify either spec or --generate SEED, and --world and --output')
        if args.generate is not None and args.demo_qa:
            parser.error('--demo-qa is for the fixed training fixture only')
        if args.generate is not None and args.tactical_qa:
            parser.error('--tactical-qa requires a gameplay spec')
        build(args.spec.resolve() if args.spec else None, args.world.resolve(), args.output.absolute(),
              args.godot, args.demo_qa, args.generate, args.count, tactical_qa=args.tactical_qa)
    except (ValueError,OSError,RuntimeError) as e:
        print(e,file=sys.stderr)
        sys.exit(1)
