# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only OEM moon. The existing M300 renderer retains its wire format."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

SOURCE_SHA256 = '11e2ea439d33436418bbeb51579cc7c12ef0a329019829bcf7e5eccbfc863b75'
MOON_SHA256 = '56bd4351a045e02e673b0c0d53953f47eae010529b8d3c58e65a83a02e1b7bd1'
ENTERING_TEXT = 'Entering sleep mode'


def load_moon(path=None):
    path = Path(path) if path else Path(__file__).with_name('m300_display_moon.json')
    spec = json.loads(path.read_text())
    if (spec['source_sha256'] != SOURCE_SHA256
            or spec['descriptor'] != '0x0801d908'
            or (spec['width'], spec['height']) != (50, 50)
            or len(spec['frames']) != 1
            or spec['frames'][0]['sha256'] != MOON_SHA256):
        raise ValueError('Unverified M300 OEM moon descriptor')
    raw = zlib.decompress(base64.b64decode(
        spec['frames'][0]['zlib_b64'], validate=True))
    if len(raw) != 1250 or hashlib.sha256(raw).hexdigest() != MOON_SHA256:
        raise ValueError('Unverified M300 OEM moon pixels')
    return 50, 50, raw


def sleep_wire(frame_class, sprite):
    frame = frame_class()
    # Original entry centers the text in the left area and displays the
    # audited moon on the right. No header, invented artwork or actions.
    frame.text((192 - (6 * len(ENTERING_TEXT) - 1)) // 2, 24, ENTERING_TEXT)
    frame.original_sprite(sprite)
    return frame.wire_bytes()
