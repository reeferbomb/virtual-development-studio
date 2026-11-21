"""Generate original deterministic sound effects with the Python standard library."""

from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import wave

RATE = 22050
SEED = 74119


def ambience(rng):
    """Periodic interpolated noise layers create wind above a distant motor hum."""
    duration = 5
    layers = [(weight, [rng.uniform(-1, 1) for _ in range(count)])
              for weight, count in ((.43, 350), (.20, 1700), (.06, 7800))]
    frames = RATE * duration
    for i in range(frames):
        phase = i / frames
        wind = 0
        for weight, knots in layers:
            index, frac = divmod(phase * len(knots), 1)
            index = int(index)
            blend = frac * frac * (3 - 2 * frac)
            wind += weight * (knots[index] * (1 - blend) + knots[(index + 1) % len(knots)] * blend)
        yield wind * (.55 + .18 * math.cos(math.tau * phase)) + .025 * math.sin(math.tau * 290 * phase)


def footstep(rng):
    grit = 0
    for i in range(round(.42 * RATE)):
        t = i / RATE
        grit = .65 * grit + .35 * rng.uniform(-1, 1)
        heel = math.exp(-22*t) * math.sin(math.tau*(83*t + .7*(1-math.exp(-28*t))))
        toe = max(0, t-.075)
        yield min(1, t/.004) * (.53*heel + (.72*math.exp(-28*t) + 16*toe*math.exp(-38*toe))*grit)


def thunder(rng):
    rumble = crack = 0
    for i in range(3 * RATE):
        t = i / RATE
        rumble = .984 * rumble + .016 * rng.uniform(-1, 1)
        crack = .72 * crack + .28 * rng.uniform(-1, 1)
        tail = math.exp(-1.45*t) * min(1, (3-t)/.18)
        roll = .22 * math.sin(math.tau*(37*t + 1.2*math.sin(3*t))) + 2.8*rumble
        yield min(1, t/.008) * (roll*tail + .83*crack*math.exp(-9*t))


def generate(output):
    """Write the WAVs and metadata.json and return the metadata dictionary."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    metadata = {"seed": SEED, "sample_rate": RATE, "channels": 1, "format": "PCM_S16LE",
                "provenance": "Original procedural synthesis. No external samples.", "sounds": {}}
    for offset, synth in enumerate((ambience, footstep, thunder)):
        name = synth.__name__
        samples = array("h", (round(x * 32767) for x in synth(random.Random(SEED + offset))))
        peak = max(map(abs, samples)) / 32768
        rms = math.sqrt(sum(x*x for x in samples) / len(samples)) / 32768
        if not (.01 < rms <= peak < .98):
            raise ValueError(f"Invalid levels for {name}: peak={peak}, rms={rms}")
        if sys.byteorder != "little":
            samples.byteswap()
        path = output / f"{name}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, RATE, len(samples), "NONE", "not compressed"))
            wav.writeframes(samples.tobytes())
        metadata["sounds"][name] = {"file": path.name, "duration": len(samples)/RATE,
                                    "peak": peak, "rms": rms, "loop": name == "ambience",
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    generate(parser.parse_args().output_dir)
