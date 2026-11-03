# SPDX-License-Identifier: MIT
# CRC and classic record layout adapted from Marcin Kowalik's Inventure
# converter v1.4.16, GitHub export v1.4.17 at bed93df495aeb189f784f1dbd81a7e972b151f52.
# Copyright (c) 2026 Marcin Kowalik. See licenses/CONVERTER_MIT.txt.
"""Read-only classic Z-code framing/metadata for future M300 file-provider use.

This module never executes records and never converts Inventure mechanics to
M300 mechanics. A framing/CRC PASS is not a motion-semantic compatibility PASS.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import io
from pathlib import Path
import struct

class ZCodeError(ValueError):
    pass

def crc8_d5(data):
    value = 0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0xD5) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return value

def parse_header(header, family='m300'):
    if len(header) != 128 or header[:5] != b'ZCode':
        raise ZCodeError('Expected a 128-byte classic ZCode header')
    if crc8_d5(header[:127]) != header[127]:
        raise ZCodeError('Header CRC mismatch')
    model = header[61]
    if family == 'm300' and not 20 <= model <= 29:
        raise ZCodeError('Wrong model family for classic M300: %d' % model)
    if family == 'inventure' and not 10 <= model <= 19:
        raise ZCodeError('Wrong model family for classic Inventure: %d' % model)
    if family not in ('m300', 'inventure', 'any'):
        raise ZCodeError('Unknown family policy')
    return {'printer_id': model, 'declared_records': struct.unpack_from('<I', header, 50)[0],
            'print_time_seconds': struct.unpack_from('<I', header, 54)[0],
            'firmware_triplet': list(header[58:61]), 'material_code': header[62],
            'layer_hundredths_mm': header[63], 'software_version': list(header[68:72]),
            'model_filament_mm': struct.unpack_from('<I', header, 73)[0],
            'support_filament_mm': struct.unpack_from('<I', header, 77)[0],
            'support_material_code': header[85],
            'declared_steps_per_mm': dict(zip(('X','Y','Z','E','A','B','Z2'),
                                             struct.unpack_from('<7I', header, 18)))}

def inspect_stream(stream, family='m300', max_bytes=256 * 1024 * 1024, max_records=10000000):
    header = stream.read(128)
    result = parse_header(header, family)
    if result['declared_records'] > max_records:
        raise ZCodeError('Declared record count exceeds inspection limit')
    digest = hashlib.sha256(header)
    ops = Counter()
    offset = 128
    count = 0
    while True:
        first = stream.read(1)
        if not first: break
        length = first[0]
        if length < 2:
            raise ZCodeError('Invalid record length at byte %d' % offset)
        if offset + 1 + length > max_bytes:
            raise ZCodeError('File exceeds inspection byte limit')
        tail = stream.read(length)
        if len(tail) != length:
            raise ZCodeError('Truncated record at byte %d' % offset)
        record = first + tail
        if crc8_d5(record[:-1]) != record[-1]:
            raise ZCodeError('Record CRC mismatch at byte %d' % offset)
        count += 1
        if count > max_records: raise ZCodeError('Record count exceeds inspection limit')
        ops[record[1]] += 1
        digest.update(record)
        offset += len(record)
    if count != result['declared_records']:
        raise ZCodeError('Record count mismatch: header=%d actual=%d' % (result['declared_records'], count))
    result.update({'bytes': offset, 'sha256': digest.hexdigest(), 'records': count,
                   'opcode_counts': {'0x%02X' % op: number for op, number in sorted(ops.items())},
                   'framing_and_crc_valid': True, 'family_policy': family,
                   'motion_semantics_validated': False, 'executed': False})
    return result

def inspect_bytes(data, family='m300', **limits):
    return inspect_stream(io.BytesIO(data), family, **limits)

def inspect_file(path, family='m300', **limits):
    with Path(path).open('rb') as stream:
        return inspect_stream(stream, family, **limits)
