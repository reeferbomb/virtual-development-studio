import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'cinematic/sequence.json').read_text())

class SequenceTests(unittest.TestCase):
    def setUp(self):
        path=ROOT/'cinematic/build.py'
        self.assertTrue(path.exists(),'Cinematic builder missing')
        spec=importlib.util.spec_from_file_location('cinematic_builder',path)
        self.builder=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.builder)

    def test_valid_timeline(self):
        self.assertEqual(sum(s['duration'] for s in self.builder.validate(SPEC)['shots']),10)

    def test_reject_bad_clip(self):
        bad=json.loads(json.dumps(SPEC)); bad['shots'][1]['clip']='missing'
        with self.assertRaises(ValueError): self.builder.validate(bad)

    def test_reject_invalid_duration(self):
        bad=json.loads(json.dumps(SPEC)); bad['shots'][0]['duration']=0
        with self.assertRaises(ValueError): self.builder.validate(bad)

    def test_reject_camera_degenerate(self):
        bad=json.loads(json.dumps(SPEC)); bad['shots'][0]['look_from']=bad['shots'][0]['camera_from']
        with self.assertRaises(ValueError): self.builder.validate(bad)

    def test_reject_actor_teleport(self):
        bad=json.loads(json.dumps(SPEC)); bad['shots'][1]['actor_from']=[1,0,0]
        with self.assertRaises(ValueError): self.builder.validate(bad)
