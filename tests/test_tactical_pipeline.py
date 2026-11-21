import json
from pathlib import Path
import tempfile
import unittest

from command_center.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]


class TacticalPipelineTests(unittest.TestCase):
    def test_exact_tactical_fixture_runs_integration_qa(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            pipeline = Pipeline(ROOT, directory/'workspace')
            self.addCleanup(pipeline.worker.shutdown)
            fixture = ROOT/'gameplay/tactical_spec.json'
            self.assertTrue(fixture.exists(), 'Tactical fixture must be supplied')
            data = json.loads(fixture.read_text())
            (directory/'spec.json').write_text(json.dumps(data))
            args = pipeline._commands('gameplay',directory)[0][1]
            self.assertIn('--tactical-qa',args)
            data['seed'] += 1
            (directory/'spec.json').write_text(json.dumps(data))
            args = pipeline._commands('gameplay',directory)[0][1]
            self.assertNotIn('--tactical-qa',args)
