import tempfile
import unittest
from pathlib import Path

from living.matrix import run_matrix


class MatrixValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / 'matrix'
        self.spec = dict(seed=237, chunk_size=32, radius=1, capacity=40)

    def test_reject_worker_and_size_limits_before_mutation(self):
        for workers in [0, 5, True]:
            with self.assertRaises(ValueError):
                run_matrix(self.output, [self.spec], workers)
        for specs in [[], [self.spec] * 17]:
            with self.assertRaises(ValueError):
                run_matrix(self.output, specs)
        self.assertFalse(self.output.exists())

    def test_reject_duplicates_and_invalid_specs(self):
        for specs in [[self.spec, self.spec], [dict(self.spec, seed=-1)]]:
            with self.assertRaises(ValueError):
                run_matrix(self.output, specs)
        self.assertFalse(self.output.exists())

    def test_preserve_existing_output(self):
        self.output.mkdir()
        sentinel = self.output / 'existing.txt'
        sentinel.write_text('preserve')
        with self.assertRaises(FileExistsError):
            run_matrix(self.output, [self.spec])
        self.assertEqual(sentinel.read_text(), 'preserve')
