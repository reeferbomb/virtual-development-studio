"""Build a bounded set of original seeded worlds and playable encounters with evidence."""
import argparse
import json
from pathlib import Path
import time

from world import build as world
from world.procedural import generate, plan_route
from gameplay import build as gameplay

ROOT = Path(__file__).resolve().parent


def configure_encounter(level, seed, enemies, tactical=False, destructible_count=0):
    if type(tactical) is not bool or type(destructible_count) is not int or not 0<=destructible_count<=len(level['blocks']):
        raise ValueError('Destructible count must fit the generated cover blocks')
    result=gameplay.generate(level,seed,enemies)
    if tactical: result['tactical']=True
    if destructible_count: result['destructible_blocks']=[b['id'] for b in level['blocks'][:destructible_count]]
    return result


def run(seeds, destination, count=24, enemies=4, godot='godot', tactical=False, destructible_count=0):
    if not 1 <= len(seeds) <= 8 or len(set(seeds)) != len(seeds):
        raise ValueError('Specify 1–8 distinct seeds')
    if type(enemies) is not int or not 1 <= enemies <= 16:
        raise ValueError('Enemy count must be 1–16')
    if type(destructible_count) is not int or not 0<=destructible_count<=count:
        raise ValueError('Destructible count must fit the selected cover density')
    designs = [(seed, world.validate(generate(seed,count))) for seed in seeds]
    destination.mkdir(parents=False, exist_ok=False)
    results = []
    for seed,spec in designs:
        base=destination/f'seed-{seed}';base.mkdir()
        spec_path=base/'spec.json';world.factory.write_json(spec_path,spec)
        start=time.monotonic()
        world.build(spec_path,ROOT/'demo/first-batch',base/'world',godot,False,True)
        world_seconds=round(time.monotonic()-start,3)
        level=json.loads((base/'world/level.json').read_text())
        encounter=configure_encounter(level,seed,enemies,tactical,destructible_count)
        encounter_path=base/'encounter.json';world.factory.write_json(encounter_path,encounter)
        start=time.monotonic()
        gameplay.build(encounter_path,base/'world',base/'gameplay',godot,False)
        game_seconds=round(time.monotonic()-start,3)
        for package in [base/'world',base/'gameplay']:
            errors=world.factory.verify_package(package)
            if errors: raise ValueError(f'Package verification failed: {errors}')
        qa=json.loads((base/'world/reports/route-qa.json').read_text())
        results.append({'seed':seed,'cover':len(spec['blocks']),'props':len(spec['placements']),
                        'enemies':len(encounter['enemies']),'tactical':tactical,'destructible_count':destructible_count,'world_build_seconds':world_seconds,
                        'gameplay_build_seconds':game_seconds,'verified':True,'route_qa':qa,
                        'world':f'seed-{seed}/world','gameplay':f'seed-{seed}/gameplay'})
        world.factory.write_json(destination/'report.json',{'scope':'headless world route QA; gameplay import, launch and module tests; not combat encounter completion or GPU performance','results':results})
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,action='append',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cover',type=int,default=24);p.add_argument('--enemies',type=int,default=4);p.add_argument('--godot',default='godot');p.add_argument('--tactical',action='store_true');p.add_argument('--destructible-count',type=int,default=0);a=p.parse_args()
    print(json.dumps(run(a.seed,a.output.absolute(),a.cover,a.enemies,a.godot,a.tactical,a.destructible_count),indent=2))
