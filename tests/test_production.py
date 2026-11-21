import json
import math
import unittest
from pathlib import Path

from world import build


class ProductionTests(unittest.TestCase):
    def test_tactical_batch_options_target_real_generated_cover(self):
        from production import configure_encounter
        from world.procedural import generate
        level=build.validate(generate(237,12))
        config=configure_encounter(level,237,4,True,3)
        self.assertTrue(config['tactical'])
        self.assertEqual(config['destructible_blocks'],['central_barrier','cover_01','cover_02'])
        self.assertEqual(len(config['enemies']),4)
        with self.assertRaises(ValueError): configure_encounter(level,237,4,True,13)
    def test_seed_deterministic_and_varied(self):
        from world.procedural import generate
        a = generate(237, 22)
        self.assertEqual(a, generate(237, 22))
        self.assertNotEqual(a, generate(238, 22))
        self.assertEqual(len(a['blocks']), 22)
        build.validate(a)

    def test_route_detours_and_reaches_goal(self):
        from world.procedural import generate, plan_route, clear_segment
        for seed in (1, 237, 238, 2026):
            spec = generate(seed, 24)
            route = plan_route(spec)
            self.assertEqual(route[0], spec['spawn'])
            self.assertEqual(route[-1], spec['goal'])
            self.assertGreater(sum(math.dist(a, b) for a,b in zip(route,route[1:])), 34)
            self.assertTrue(all(clear_segment(spec, a,b) for a,b in zip(route,route[1:])))

    def test_sealed_corridor_rejected(self):
        from world.procedural import plan_route
        spec = json.loads((Path(__file__).resolve().parents[1]/'world/demo_spec.json').read_text())
        spec['blocks']=[{'id':'wall','position':[0,1,0],'size':[1,2,21]}]
        with self.assertRaisesRegex(ValueError,'route'):
            plan_route(spec)

    def test_bad_seed_and_density_rejected(self):
        from world.procedural import generate
        for seed,count in [(-1,12),(True,12),(1,1000),(1,0)]:
            with self.assertRaises(ValueError): generate(seed,count)

    def test_fractional_endpoints(self):
        from world.procedural import plan_route
        spec = json.loads((Path(__file__).resolve().parents[1]/'world/demo_spec.json').read_text())
        spec['spawn']=[-7.2,0,.3]
        spec['goal']=[7.1,0,.2]
        route=plan_route(spec)
        self.assertEqual(route[0],spec['spawn'])
        self.assertEqual(route[-1],spec['goal'])
