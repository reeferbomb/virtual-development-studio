import array
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import wave

SCRIPT = Path(__file__).resolve().parents[1] / "cinematic" / "audio.py"


class CinematicAudioTests(unittest.TestCase):
    def test_sounds_and_repeatability(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for target in (first, second):
                subprocess.run([sys.executable, str(SCRIPT), target], check=True)
            manifest = json.loads((Path(first) / "metadata.json").read_text())
            self.assertIn("procedural", manifest["provenance"])
            for name, bounds in {"ambience": (4, 6), "footstep": (.1, .7), "thunder": (1, 5)}.items():
                path = Path(first) / (name + ".wav")
                self.assertEqual(path.read_bytes(), (Path(second) / path.name).read_bytes())
                with wave.open(str(path)) as wav:
                    self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 22050))
                    samples = array.array("h")
                    samples.frombytes(wav.readframes(wav.getnframes()))
                    if sys.byteorder != "little":
                        samples.byteswap()
                peak = max(map(abs, samples)) / 32768
                rms = math.sqrt(sum(x*x for x in samples) / len(samples)) / 32768
                self.assertLess(peak, .98)
                self.assertGreater(rms, .01)
                self.assertAlmostEqual(rms, manifest["sounds"][name]["rms"], places=6)
                self.assertAlmostEqual(peak, manifest["sounds"][name]["peak"], places=6)
                self.assertTrue(bounds[0] <= len(samples)/22050 <= bounds[1])
                if name == "ambience":
                    self.assertLess(abs(samples[-1] - samples[0]), 600)
