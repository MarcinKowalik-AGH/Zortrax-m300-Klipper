#!/usr/bin/env python3
"""Independent byte-level verification against the user's stock M300 image.

Usage: python3 tests/verify_factory_moon.py /path/M300_stock_1.3.1_application.bin
Decoder follows 0x0800cdf8 and the big-endian 7-bit varint at 0x08011b1c.
The factory image is not redistributed in this host update.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import zlib

BASE = 0x08008000
SOURCE = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'


def decode(data):
    marker, pos, output = data[0], 1, bytearray()
    def varint():
        nonlocal pos
        value = 0
        for _ in range(5):
            value_byte = data[pos]
            pos += 1
            value = (value << 7) | (value_byte & 127)
            if not value_byte & 128:
                return value
        raise ValueError('Invalid factory varint')
    while pos < len(data):
        value = data[pos]
        pos += 1
        if value != marker:
            output.append(value)
        elif data[pos] == 0:
            output.append(marker)
            pos += 1
        else:
            count, distance = varint(), varint()
            if not 0 < distance <= len(output) or len(output) + count > 1250:
                raise ValueError('Invalid factory back-reference')
            for _ in range(count):
                output.append(output[-distance])
    return bytes(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('factory_image', type=Path)
    args = parser.parse_args()
    image = args.factory_image.read_bytes()
    assert hashlib.sha256(image).hexdigest() == SOURCE, 'Unexpected factory image'
    assert image[0x080266F0-BASE:0x080266F0-BASE+19] == b'Entering sleep mode'
    width, height, frames, period, table, mirror = struct.unpack_from(
        '<BBHIII', image, 0x0801D908-BASE)
    assert (width, height, frames, period, mirror) == (50, 50, 1, 0, 0)
    address, = struct.unpack_from('<I', image, table-BASE)
    size, = struct.unpack_from('<I', image, address-BASE)
    decoded = decode(image[address-BASE+4:address-BASE+4+size])
    asset = json.loads((Path(__file__).resolve().parents[1]
                       / 'payload/m300_display_moon.json').read_text())
    expected = zlib.decompress(base64.b64decode(asset['frames'][0]['zlib_b64']))
    assert len(decoded) == 1250 and decoded == expected, 'Factory moon mismatch'
    print(json.dumps({'status': 'PASS_DIRECT_FACTORY_MOON_DECODE',
                      'source_sha256': SOURCE, 'compressed_bytes': size,
                      'decoded_bytes': len(decoded),
                      'frame_address': hex(address),
                      'decoded_sha256': hashlib.sha256(decoded).hexdigest(),
                      'byte_for_byte_equal': True, 'physical_hardware': False}))


if __name__ == '__main__':
    main()
