"""Inspect one local static 8-bit PNG texture against a single-map practice budget.

Supports non-interlaced grayscale, grayscale-alpha, RGB and RGBA with all five
PNG filters. Alpha must be an explicit channel. Ancillary metadata is skipped.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import struct
import zlib

from .lab_artifact import require
from .lab_content import _mip_bytes


PROFILE = 'static-texture-png-v1'
SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_EDGE = 4096
MAX_PIXELS = 4 * 1024 * 1024
MAX_CHUNKS = 8192
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
ROLES = ('base_color', 'normal', 'roughness', 'metallic', 'occlusion', 'orm', 'emissive', 'height', 'opacity')
BUDGET = {'file_bytes': 4 * 1024 * 1024, 'max_dimension': 1024, 'mip_chain_bytes': 4 * 1024 * 1024}


def read_file(path):
    name = os.fsdecode(path)
    require(not re.match(r'^[A-Za-z][A-Za-z0-9+.\-]*:', name) and not name.startswith(('//', '\\\\')),
            'Select a local regular file')
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'Select a local regular file')
        require(info.st_size <= MAX_FILE_BYTES, 'PNG exceeds the file inspection limit')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        require(len(raw) <= MAX_FILE_BYTES, 'PNG exceeds the file inspection limit')
        return raw
    finally:
        os.close(fd)


def chunks(raw):
    require(raw.startswith(SIGNATURE), 'Expected a PNG signature')
    data = memoryview(raw)
    offset = len(SIGNATURE)
    for _ in range(MAX_CHUNKS):
        require(offset + 12 <= len(data), 'Incomplete PNG chunk or missing IEND')
        length, kind = struct.unpack_from('>I4s', data, offset)
        stop = offset + 8 + length
        require(stop + 4 <= len(data), 'PNG chunk exceeds file length')
        require(kind.isalpha() and kind[2:3].isupper(), 'Invalid PNG chunk type')
        checksum, = struct.unpack_from('>I', data, stop)
        require(zlib.crc32(data[offset + 4:stop]) == checksum, 'Invalid PNG chunk CRC')
        if kind == b'IEND':
            require(length == 0 and stop + 4 == len(data), 'Invalid or trailing IEND data')
        yield kind, data[offset + 8:stop]
        if kind == b'IEND':
            return
        offset = stop + 4
    raise ValueError('PNG exceeds the chunk count limit')


def read_png(raw):
    parts = chunks(raw)
    kind, data = next(parts)
    require(kind == b'IHDR' and len(data) == 13, 'Expected a 13-byte PNG IHDR')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
    require(1 <= width <= MAX_EDGE and 1 <= height <= MAX_EDGE and width * height <= MAX_PIXELS,
            'PNG dimensions exceed inspection bounds')
    require(depth == 8 and color in CHANNELS and (compression, filtering, interlace) == (0, 0, 0),
            'Expected a non-interlaced 8-bit grayscale, grayscale-alpha, RGB or RGBA PNG')

    image_data = []
    ended_data = False
    palette = False
    for kind, data in parts:
        if kind == b'IDAT':
            require(not ended_data, 'Image data chunks must be consecutive')
            image_data.append(data)
        else:
            ended_data = bool(image_data)
            if kind == b'PLTE':
                require(not palette and not ended_data and color in (2, 6)
                        and 0 < len(data) <= 768 and len(data) % 3 == 0, 'Invalid PNG palette')
                palette = True
            elif kind != b'IEND':
                require(kind[0:1].islower(), 'Unsupported or repeated critical PNG chunk')
                require(kind not in (b'tRNS', b'acTL', b'fcTL', b'fdAT'),
                        'Only static PNGs with implicit opaque pixels or explicit alpha channels are supported')
    require(image_data, 'PNG contains no image data')
    channels = CHANNELS[color]
    expected = height * (1 + width * channels)
    decoder = zlib.decompressobj()
    scanlines = decoder.decompress(b''.join(image_data), expected + 1)
    require(len(scanlines) == expected and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
            'PNG must contain one complete zlib stream with exactly the declared scanlines')
    return width, height, channels, scanlines


def paeth(left, up, corner):
    prediction = left + up - corner
    a, b, c = abs(prediction - left), abs(prediction - up), abs(prediction - corner)
    if a <= b and a <= c:
        return left
    return up if b <= c else corner


def pixel_digest(width, channels, scanlines):
    """Reverse each scanline filter before hashing tightly packed native-channel samples."""
    stride = width * channels
    previous = bytes(stride)
    digest = hashlib.sha256()
    for offset in range(0, len(scanlines), stride + 1):
        mode = scanlines[offset]
        require(mode <= 4, 'Invalid PNG scanline filter')
        row = bytearray(scanlines[offset + 1:offset + stride + 1])
        if mode == 1:
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 255
        elif mode == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, previous))
        elif mode in (3, 4):
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = previous[i]
                if mode == 3:
                    predictor = (left + up) // 2
                else:
                    corner = previous[i - channels] if i >= channels else 0
                    predictor = paeth(left, up, corner)
                row[i] = (row[i] + predictor) & 255
        digest.update(row)
        previous = row
    return digest.hexdigest()


def inspect_texture(path, role=None):
    """Decode the selected local file and return an evidence report without writing files."""
    report = {'profile': PROFILE, 'status': 'unavailable', 'sha256': None, 'measurements': {}, 'checks': []}
    try:
        raw = read_file(path)
        report['sha256'] = hashlib.sha256(raw).hexdigest()
        require(role is None or role in ROLES, 'Unknown declared texture role')
        width, height, channels, scanlines = read_png(raw)
        measured = {
            'width': width, 'height': height, 'channels': channels, 'has_alpha': channels in (2, 4),
            'bit_depth': 8, 'file_bytes': len(raw), 'max_dimension': max(width, height),
            'decoded_bytes': width * height * channels, 'mip_chain_bytes': _mip_bytes(width, height, channels),
            'power_of_two': (width & (width - 1)) == 0 and (height & (height - 1)) == 0,
            'pixel_sha256': pixel_digest(width, channels, scanlines),
        }
    except (OSError, TypeError, ValueError, zlib.error) as exc:
        report['note'] = str(exc)
        return report
    if role is not None:
        measured['declared_role'] = role
    checks = [{'id': name, 'measured': measured[name], 'limit': limit,
               'status': 'pass' if measured[name] <= limit else 'fail'} for name, limit in BUDGET.items()]
    checks.append({'id': 'power_of_two', 'measured': measured['power_of_two'], 'limit': True,
                   'status': 'pass' if measured['power_of_two'] else 'fail'})
    report.update(status='pass' if all(c['status'] == 'pass' for c in checks) else 'fail',
                  measurements=measured, checks=checks,
                  note='Pixel digest covers decoded 8-bit samples in row order. Memory estimates assume '
                       'tightly packed channels; the mip chain includes the base through 1×1. Role is '
                       'caller-declared. Color space, appearance and GPU allocation require separate review.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', metavar='PATH', help='local static 8-bit PNG')
    parser.add_argument('--role', choices=ROLES, help='caller-declared material map role')
    args = parser.parse_args(argv)
    report = inspect_texture(args.path, role=args.role)
    print(json.dumps(report, indent=2, allow_nan=False))
    return {'pass': 0, 'fail': 1, 'unavailable': 2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
