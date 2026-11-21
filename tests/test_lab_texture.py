import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / 'demo/asset-preview.png'
SIGNATURE = b'\x89PNG\r\n\x1a\n'


def chunk(kind, data):
    return (struct.pack('>I', len(data)) + kind + data
            + struct.pack('>I', zlib.crc32(kind + data)))


def header(width, height, color=6, depth=8, interlace=0):
    return chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, interlace))


def png(width, height, scanlines, color=6):
    return SIGNATURE + header(width, height, color) + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b'')


class TextureLabTests(unittest.TestCase):
    def test_reads_generated_rgba_texture_at_cli(self):
        # A small two-tone tile with varying alpha; unfiltered input samples are the pixel oracle.
        rows = [bytes(v for x in range(8) for v in (24 + 32 * ((x + y) % 2), 64, 128, 32 * x))
                for y in range(4)]
        data = png(8, 4, b''.join(b'\0' + row for row in rows))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tile.png'
            path.write_bytes(data)
            result = subprocess.run([sys.executable, '-m', 'command_center.lab_texture', str(path),
                                     '--role', 'base_color'], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['status'], 'pass')
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            measured = report['measurements']
            self.assertEqual((measured['width'], measured['height'], measured['channels'], measured['has_alpha']),
                             (8, 4, 4, True))
            self.assertEqual((measured['file_bytes'], measured['decoded_bytes'], measured['mip_chain_bytes']),
                             (len(data), 128, 172))
            self.assertEqual(measured['declared_role'], 'base_color')
            self.assertEqual(measured['pixel_sha256'], hashlib.sha256(b''.join(rows)).hexdigest())
            self.assertEqual(path.read_bytes(), data)

    def inspect_data(self, data, **kwargs):
        from command_center.lab_texture import inspect_texture
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'normal.png'
            path.write_bytes(data)
            report = inspect_texture(path, **kwargs)
            self.assertEqual(report['sha256'], hashlib.sha256(data).hexdigest())
            return report

    def test_reconstructs_all_filters_and_mip_sizes_for_odd_rectangles(self):
        # Hand-encoded gray samples with filters None, Sub, Up, Average, Paeth.
        lines = bytes([0, 10, 20, 30, 1, 15, 2, 14, 2, 246, 4, 9,
                       3, 18, 5, 18, 4, 10, 246, 40])
        pixels = bytes([10, 20, 30, 15, 17, 31, 5, 21, 40, 20, 25, 50, 30, 20, 90])
        report = self.inspect_data(png(3, 5, lines, color=0))
        self.assertEqual(report['status'], 'fail')
        self.assertEqual([c['id'] for c in report['checks'] if c['status'] == 'fail'], ['power_of_two'])
        measured = report['measurements']
        self.assertEqual(measured['pixel_sha256'], hashlib.sha256(pixels).hexdigest())
        self.assertEqual((measured['channels'], measured['has_alpha'], measured['mip_chain_bytes']), (1, False, 18))
        self.assertNotIn('declared_role', measured)

    def test_two_channels_and_only_explicit_roles(self):
        data = png(1, 1, b'\0\x80\xff', color=4)
        report = self.inspect_data(data, role='roughness')
        self.assertEqual((report['status'], report['measurements']['channels'],
                          report['measurements']['has_alpha'], report['measurements']['declared_role']),
                         ('pass', 2, True, 'roughness'))
        self.assertEqual(self.inspect_data(data, role='unrecognized')['status'], 'unavailable')

    def test_real_tracked_preview_matches_independent_raster_digest(self):
        from command_center.lab_texture import inspect_texture
        report = inspect_texture(PREVIEW)
        self.assertEqual(report['sha256'], '4b9f56aee1499a827a1db25e4bb624c8d5c082f627106dc20a12b56fbeda4fed')
        self.assertEqual(report['status'], 'fail')
        measured = report['measurements']
        self.assertEqual((measured['width'], measured['height'], measured['channels'], measured['file_bytes'],
                          measured['decoded_bytes'], measured['mip_chain_bytes']),
                         (960, 540, 4, 488274, 2073600, 2764220))
        # Verified independently with Pillow's full load of the checked-in fixture.
        self.assertEqual(measured['pixel_sha256'], 'a6f406939c97b8aef742e9c24ca255c387eafc5ccd8da8a55e5815448ee62887')
        self.assertEqual([c['id'] for c in report['checks'] if c['status'] == 'fail'], ['power_of_two'])

    def test_limits_return_measurements_only_for_decodable_inputs(self):
        data = png(2048, 1, bytes(2048 * 3 + 1), color=2)
        report = self.inspect_data(data)
        self.assertEqual([(c['id'], c['measured'], c['limit']) for c in report['checks'] if c['status'] == 'fail'],
                         [('max_dimension', 2048, 1024)])
        report = self.inspect_data(png(1024, 1024, bytes(1024 * (1 + 4096))))
        self.assertEqual([(c['id'], c['measured'], c['limit']) for c in report['checks'] if c['status'] == 'fail'],
                         [('mip_chain_bytes', 5592404, 4194304)])
        for width, height in ((0, 1), (1, 4097), (4096, 4096)):
            report = self.inspect_data(png(width, height, b''))
            self.assertEqual((report['status'], report['measurements'], report['checks']), ('unavailable', {}, []))

    def test_invalid_or_unsupported_container_and_scanline_fail_closed(self):
        hdr = header(1, 1)
        compressed = zlib.compress(b'\0\x10\x20\x30\xff')
        idat = chunk(b'IDAT', compressed)
        iend = chunk(b'IEND', b'')
        text = chunk(b'tEXt', b'Source\0https://example.invalid/unused')
        complete = SIGNATURE + hdr + idat + iend
        good = SIGNATURE + hdr + text + chunk(b'IDAT', compressed[:4]) + chunk(b'IDAT', compressed[4:]) + iend
        self.assertEqual(self.inspect_data(good)['status'], 'pass')
        for data in [b'', b'\xff\xd8\xff', complete[:-1], complete + b'x', complete[:-1] + b'\0',
                     SIGNATURE + hdr + hdr + idat + iend, SIGNATURE + hdr + iend,
                     SIGNATURE + hdr + idat + text + idat + iend,
                     SIGNATURE + hdr + chunk(b'ABCD', b'') + idat + iend,
                     SIGNATURE + hdr + chunk(b'acTL', bytes(8)) + idat + iend,
                     SIGNATURE + header(1, 1, color=3) + idat + iend,
                     SIGNATURE + header(1, 1, interlace=1) + idat + iend,
                     SIGNATURE + header(1, 1, depth=16) + idat + iend,
                     SIGNATURE + header(1, 1, color=2) + chunk(b'tRNS', bytes(6)) + idat + iend,
                     png(1, 1, b'\x05' + bytes(4)), png(1, 1, bytes(4)), png(1, 1, bytes(1_000_000)),
                     SIGNATURE + hdr + chunk(b'IDAT', compressed[:-1]) + iend,
                     SIGNATURE + hdr + chunk(b'IDAT', compressed + zlib.compress(b'extra')) + iend]:
            with self.subTest(length=len(data), excerpt=data[:24]):
                report = self.inspect_data(data)
                self.assertEqual((report['status'], report['measurements'], report['checks']),
                                 ('unavailable', {}, []))

    def test_local_regular_file_selection_and_cli_status(self):
        from command_center.lab_texture import inspect_texture
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'symlink').symlink_to(PREVIEW)
            os.mkfifo(root / 'fifo')
            with (root / 'huge').open('wb') as handle:
                handle.truncate(17 * 1024 * 1024)
            for path in (root, root / 'missing', root / 'symlink', root / 'fifo', root / 'huge',
                         'https://example.invalid/remote', 'file:///tmp/pixel.png'):
                report = inspect_texture(path)
                self.assertEqual((report['status'], report['sha256']), ('unavailable', None))
            for path, code, status in [(PREVIEW, 1, 'fail'), (root / 'missing', 2, 'unavailable')]:
                result = subprocess.run([sys.executable, '-m', 'command_center.lab_texture', str(path)],
                                        cwd=ROOT, capture_output=True, text=True)
                self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (code, status))


if __name__ == '__main__':
    unittest.main()
